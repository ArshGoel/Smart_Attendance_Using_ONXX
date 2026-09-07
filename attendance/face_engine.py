import os
import json
import base64
import numpy as np
import cv2
from pathlib import Path
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Lazy loaded ONNX Runtime Session
_ONNX_SESSION = None
_FACE_DETECTOR = None

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = BASE_DIR / 'attendance' / 'models_onnx' / 'w600k_mbf.onnx'

def get_onnx_session():
    global _ONNX_SESSION
    if _ONNX_SESSION is None and MODEL_PATH.exists():
        try:
            import onnxruntime as ort
            _ONNX_SESSION = ort.InferenceSession(str(MODEL_PATH), providers=['CPUExecutionProvider'])
            logger.info("ONNX ArcFace session initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to load ONNX model: {e}")
    return _ONNX_SESSION

def get_face_detector():
    global _FACE_DETECTOR
    if _FACE_DETECTOR is None:
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            _FACE_DETECTOR = cv2.CascadeClassifier(cascade_path)
        except Exception as e:
            logger.error(f"Failed to load Haar Cascade face detector: {e}")
    return _FACE_DETECTOR

def preprocess_face_crop(img_bgr, bbox):
    x, y, w, h = bbox
    h_img, w_img = img_bgr.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(w_img, x + w)
    y2 = min(h_img, y + h)

    if x2 <= x1 or y2 <= y1:
        return None

    face_crop = img_bgr[y1:y2, x1:x2]
    if face_crop.size == 0:
        return None

    face_resized = cv2.resize(face_crop, (112, 112))
    face_rgb = cv2.cvtColor(face_resized, cv2.COLOR_BGR2RGB)
    face_norm = (face_rgb.astype(np.float32) - 127.5) / 127.5
    face_tensor = np.transpose(face_norm, (2, 0, 1))
    face_tensor = np.expand_dims(face_tensor, axis=0)
    return face_tensor

def compute_onnx_embedding(img_bgr, bbox):
    session = get_onnx_session()
    if session is None:
        return None

    tensor = preprocess_face_crop(img_bgr, bbox)
    if tensor is None:
        return None

    try:
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        raw_emb = session.run([output_name], {input_name: tensor})[0][0]
        
        norm = np.linalg.norm(raw_emb)
        if norm > 0:
            raw_emb = raw_emb / norm
        return raw_emb.tolist()
    except Exception as e:
        logger.error(f"ONNX embedding computation error: {e}")
        return None

def compute_centroid_embedding(embeddings_list):
    """
    Given multiple 512D ArcFace embeddings for a single student (extracted from multiple images),
    computes the normalized mean centroid vector.
    """
    if not embeddings_list:
        return None
    matrix = np.array(embeddings_list, dtype=np.float32)
    mean_vector = np.mean(matrix, axis=0)
    norm = np.linalg.norm(mean_vector)
    if norm > 0:
        mean_vector = mean_vector / norm
    return mean_vector.tolist()

def cosine_similarity(v1, v2):
    v1 = np.array(v1, dtype=np.float32)
    v2 = np.array(v2, dtype=np.float32)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))

def decode_base64_image(base64_str):
    try:
        if ',' in base64_str:
            base64_str = base64_str.split(',')[1]
        img_bytes = base64.b64decode(base64_str)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        logger.error(f"Error decoding base64 image: {e}")
        return None

_INSIGHTFACE_APP = None

def get_insightface_app():
    global _INSIGHTFACE_APP
    if _INSIGHTFACE_APP is None:
        try:
            import insightface
            from insightface.app import FaceAnalysis
            _INSIGHTFACE_APP = FaceAnalysis(name='buffalo_s', providers=['CPUExecutionProvider'])
            _INSIGHTFACE_APP.prepare(ctx_id=0, det_size=(640, 640))
        except Exception:
            _INSIGHTFACE_APP = False
    return _INSIGHTFACE_APP if _INSIGHTFACE_APP is not False else None

def extract_faces_from_image(img_bgr):
    if img_bgr is None:
        return []

    # First attempt cached InsightFace if installed locally
    app = get_insightface_app()
    if app:
        try:
            faces = app.get(img_bgr)
            results = []
            for face in faces:
                bbox = face.bbox.astype(int).tolist()
                results.append({
                    'bbox': bbox,
                    'embedding': face.embedding.astype(float).tolist()
                })
            if results:
                return results
        except Exception:
            pass

    # High-Performance ONNX + OpenCV Fallback (Works on Vercel under 100MB!)
    detector = get_face_detector()
    if detector is None:
        return []

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    faces_rects = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))

    results = []
    for (x, y, w, h) in faces_rects:
        bbox_xywh = [x, y, w, h]
        emb = compute_onnx_embedding(img_bgr, bbox_xywh)
        if emb:
            results.append({
                'bbox': [int(x), int(y), int(x + w), int(y + h)],
                'embedding': emb
            })

    return results

def sync_dataset_to_db(dataset_path, StudentEmbedding_model):
    dataset_dir = Path(dataset_path)
    if not dataset_dir.exists():
        return {'status': 'error', 'message': f'Dataset directory {dataset_path} does not exist'}

    indexed_count = 0
    updated_count = 0

    for student_dir in dataset_dir.iterdir():
        if student_dir.is_dir():
            roll_number = student_dir.name
            img_files = list(student_dir.glob("*.jpg")) + list(student_dir.glob("*.png")) + list(student_dir.glob("*.jpeg"))
            if not img_files:
                continue

            extracted_embeddings = []
            primary_cloudinary_url = None

            for idx, img_path_obj in enumerate(img_files, start=1):
                img_path = str(img_path_obj)
                img_bgr = cv2.imread(img_path)
                if img_bgr is None:
                    continue

                # Upload all images to Cloudinary under scms_student_dataset/<roll_number>/
                if getattr(settings, 'CLOUDINARY_CLOUD_NAME', None):
                    try:
                        import cloudinary.uploader
                        res = cloudinary.uploader.upload(
                            img_path,
                            public_id=f"{roll_number}_photo_{idx}",
                            folder=f"scms_student_dataset/{roll_number}",
                            overwrite=True
                        )
                        cloud_url = res.get('secure_url')
                        if cloud_url and primary_cloudinary_url is None:
                            primary_cloudinary_url = cloud_url
                    except Exception as e:
                        logger.error(f"Cloudinary dataset upload failed for {roll_number} (#{idx}): {e}")

                faces = extract_faces_from_image(img_bgr)
                if faces:
                    extracted_embeddings.append(faces[0]['embedding'])

            # Compute centroid embedding across multiple photos for maximum accuracy
            final_embedding = compute_centroid_embedding(extracted_embeddings)

            if final_embedding:
                record, created = StudentEmbedding_model.objects.get_or_create(
                    roll_number=roll_number,
                    defaults={
                        'student_name': f"Student {roll_number}",
                        'image_path': str(img_files[0]),
                        'image_url': primary_cloudinary_url or ''
                    }
                )
                record.set_embedding(final_embedding)
                record.image_path = str(img_files[0])
                if primary_cloudinary_url:
                    record.image_url = primary_cloudinary_url
                record.save()

                if created:
                    indexed_count += 1
                else:
                    updated_count += 1

    return {
        'status': 'success',
        'indexed': indexed_count,
        'updated': updated_count,
        'total': indexed_count + updated_count
    }

def match_faces_in_frame(frame_bgr, registered_embeddings, threshold=0.38):
    detected_faces = extract_faces_from_image(frame_bgr)
    results = []

    for face in detected_faces:
        face_emb = face['embedding']
        bbox = face['bbox']
        
        best_match = None
        best_score = 0.0

        for target in registered_embeddings:
            score = cosine_similarity(face_emb, target['embedding'])
            if score > best_score:
                best_score = score
                best_match = target

        if best_match and best_score >= threshold:
            results.append({
                'roll_number': best_match['roll_number'],
                'student_name': best_match.get('name', f"Student {best_match['roll_number']}"),
                'confidence': round(best_score * 100, 1),
                'status': 'PRESENT',
                'bbox': bbox
            })
        else:
            results.append({
                'roll_number': 'UNKNOWN',
                'student_name': 'Unknown Person',
                'confidence': round(best_score * 100, 1) if best_match else 0.0,
                'status': 'UNKNOWN',
                'bbox': bbox
            })

    return results
