/**
 * Real-Time Face Recognition Scanner & Multi-Photo Cloudinary Analyzer
 */
class AttendanceScanner {
    constructor(videoElemId, canvasElemId, processUrl, saveUrl, uploadUrl) {
        this.video = document.getElementById(videoElemId);
        this.canvas = document.getElementById(canvasElemId);
        this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
        this.processUrl = processUrl;
        this.saveUrl = saveUrl;
        this.uploadUrl = uploadUrl;
        
        this.stream = null;
        this.isScanning = false;
        this.scanInterval = null;
        
        // Map of detected students: roll_number -> { roll_number, student_name, confidence, status, bbox, photo_appearances }
        this.detectedStudents = new Map();
        this.uploadedPhotos = [];
    }

    async startCamera() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
                audio: false
            });
            if (this.video) {
                this.video.style.display = 'block';
                this.video.srcObject = this.stream;
                await this.video.play();
            }
            
            if (this.canvas) {
                this.canvas.width = this.video ? this.video.videoWidth : 640;
                this.canvas.height = this.video ? this.video.videoHeight : 480;
            }
            
            this.isScanning = true;
            this.startScanningLoop();
            console.log("WebRTC Camera started successfully.");
            return true;
        } catch (err) {
            console.error("Camera access failed: ", err);
            alert("Could not access webcam. You can use the Upload Classroom Photo(s) option below!");
            return false;
        }
    }

    stopCamera() {
        this.isScanning = false;
        if (this.scanInterval) clearInterval(this.scanInterval);
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
        }
        if (this.ctx) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }
        console.log("WebRTC Camera stopped.");
    }

    startScanningLoop() {
        if (this.scanInterval) clearInterval(this.scanInterval);
        this.scanInterval = setInterval(() => {
            if (this.isScanning) {
                this.captureAndProcessFrame();
            }
        }, 900);
    }

    captureFrameBase64() {
        if (!this.video || !this.video.videoWidth) return null;
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = this.video.videoWidth;
        tempCanvas.height = this.video.videoHeight;
        const tempCtx = tempCanvas.getContext('2d');
        tempCtx.drawImage(this.video, 0, 0, tempCanvas.width, tempCanvas.height);
        return tempCanvas.toDataURL('image/jpeg', 0.85);
    }

    async captureAndProcessFrame() {
        const frameData = this.captureFrameBase64();
        if (!frameData) return;

        try {
            const csrfToken = this.getCsrfToken();
            const response = await fetch(this.processUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ frame: frameData })
            });

            const result = await response.json();
            if (result.status === 'success') {
                this.renderDetectedFacesOnCanvas(result.faces, this.video.videoWidth || 640, this.video.videoHeight || 480);
            }
        } catch (err) {
            console.error("Frame processing API error:", err);
        }
    }

    async processMultipleUploadedImages(fileInput) {
        if (!fileInput.files || fileInput.files.length === 0) return;
        const files = Array.from(fileInput.files);

        // Stop camera if active
        if (this.isScanning) {
            this.stopCamera();
            const btn = document.getElementById('btn-toggle-cam');
            if (btn) {
                btn.innerHTML = '▶ Live Camera';
                btn.className = 'btn btn-primary';
            }
        }

        const formData = new FormData();
        files.forEach(file => {
            formData.append('classroom_images', file);
        });

        const statusDiv = document.getElementById('upload-status');
        const tabsContainer = document.getElementById('photo-tabs-container');
        if (statusDiv) {
            statusDiv.innerHTML = `<span style="color: var(--primary);">⌛ Processing & uploading ${files.length} classroom photo(s) to Cloudinary...</span>`;
        }

        try {
            const csrfToken = this.getCsrfToken();
            const response = await fetch(this.uploadUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                },
                body: formData
            });

            const result = await response.json();
            if (result.status === 'success') {
                if (this.video) this.video.style.display = 'none';

                this.uploadedPhotos = result.photos || [];

                // Deduplicated presentees map update
                this.detectedStudents.clear();
                (result.unique_students || []).forEach(student => {
                    this.detectedStudents.set(student.roll_number, {
                        roll_number: student.roll_number,
                        student_name: student.student_name,
                        confidence: student.confidence,
                        status: 'PRESENT',
                        photo_appearances: student.photo_appearances || []
                    });
                });

                this.updateDetectedUI();

                // Render Photo Tabs Switcher
                if (tabsContainer) {
                    tabsContainer.innerHTML = '';
                    this.uploadedPhotos.forEach((p, idx) => {
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = idx === 0 ? 'btn btn-primary' : 'btn btn-secondary';
                        btn.style.fontSize = '12px';
                        btn.style.padding = '6px 12px';
                        btn.innerHTML = `Photo #${p.photo_index} (${p.detected_count} Faces)`;
                        btn.onclick = () => this.switchPhotoCanvasView(idx, files[idx]);
                        tabsContainer.appendChild(btn);
                    });
                }

                // Render first photo canvas
                if (this.uploadedPhotos.length > 0 && files[0]) {
                    this.switchPhotoCanvasView(0, files[0]);
                }

                if (statusDiv) {
                    statusDiv.innerHTML = `<span style="color: var(--success);">✓ Processed ${result.total_photos} photos! Found <strong>${result.total_unique_present} Unique Recognized Students</strong> (Deduplicated across all images).</span>`;
                }
            } else {
                if (statusDiv) {
                    statusDiv.innerHTML = `<span style="color: var(--danger);">Error: ${result.message}</span>`;
                }
            }
        } catch (err) {
            console.error("Multiple classroom image upload error:", err);
            if (statusDiv) {
                statusDiv.innerHTML = `<span style="color: var(--danger);">Upload failed: ${err}</span>`;
            }
        }
    }

    switchPhotoCanvasView(photoIndex, fileObj) {
        if (!this.uploadedPhotos[photoIndex]) return;
        const photoData = this.uploadedPhotos[photoIndex];

        // Highlight selected tab button
        const tabBtns = document.querySelectorAll('#photo-tabs-container button');
        tabBtns.forEach((btn, i) => {
            btn.className = i === photoIndex ? 'btn btn-primary' : 'btn btn-secondary';
        });

        const img = new Image();
        img.onload = () => {
            this.canvas.width = img.width;
            this.canvas.height = img.height;
            this.ctx.drawImage(img, 0, 0);

            // Draw bounding boxes for this photo
            this.renderDetectedFacesOnCanvas(photoData.faces, img.width, img.height, false);
        };

        if (fileObj) {
            img.src = URL.createObjectURL(fileObj);
        } else if (photoData.cloudinary_url) {
            img.src = photoData.cloudinary_url;
        }
    }

    renderDetectedFacesOnCanvas(faces, origW, origH, clearCanvas = true) {
        if (!this.ctx) return;
        if (clearCanvas) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }

        const scaleX = this.canvas.width / origW;
        const scaleY = this.canvas.height / origH;

        faces.forEach(face => {
            const bbox = face.bbox; // [x1, y1, x2, y2]
            if (bbox && bbox.length === 4) {
                const x = bbox[0] * scaleX;
                const y = bbox[1] * scaleY;
                const w = (bbox[2] - bbox[0]) * scaleX;
                const h = (bbox[3] - bbox[1]) * scaleY;

                const isRecognized = face.status === 'PRESENT';
                const strokeColor = isRecognized ? '#10B981' : '#EF4444';

                // Draw bounding box
                this.ctx.strokeStyle = strokeColor;
                this.ctx.lineWidth = Math.max(3, Math.round(this.canvas.width / 300));
                this.ctx.strokeRect(x, y, w, h);

                // Label tag header
                const labelText = isRecognized ? `${face.roll_number} (${face.confidence}%)` : 'UNKNOWN';
                const fontPx = Math.max(12, Math.round(this.canvas.width / 45));
                this.ctx.font = `bold ${fontPx}px Outfit, sans-serif`;
                const textMetrics = this.ctx.measureText(labelText);
                const bgWidth = textMetrics.width + 12;
                const bgHeight = fontPx + 10;

                this.ctx.fillStyle = strokeColor;
                this.ctx.fillRect(x, Math.max(0, y - bgHeight), bgWidth, bgHeight);

                this.ctx.fillStyle = '#FFFFFF';
                this.ctx.fillText(labelText, x + 6, Math.max(fontPx, y - 6));

                // Live Camera single frame update
                if (isRecognized && face.roll_number !== 'UNKNOWN' && this.isScanning) {
                    if (!this.detectedStudents.has(face.roll_number)) {
                        this.detectedStudents.set(face.roll_number, {
                            roll_number: face.roll_number,
                            student_name: face.student_name,
                            confidence: face.confidence,
                            status: 'PRESENT'
                        });
                        this.updateDetectedUI();
                    }
                }
            }
        });
    }

    updateDetectedUI() {
        const container = document.getElementById('detected-list-container');
        const countSpan = document.getElementById('detected-count');
        if (!container) return;

        container.innerHTML = '';
        let presentCount = 0;

        this.detectedStudents.forEach((student, roll) => {
            if (student.status === 'PRESENT') presentCount++;
            
            const appearancesText = student.photo_appearances && student.photo_appearances.length > 0 ? 
                ` &bull; Photos: #${student.photo_appearances.join(', #')}` : '';

            const card = document.createElement('div');
            card.className = 'detected-card';
            card.innerHTML = `
                <div>
                    <h4 style="font-size: 14px; margin-bottom: 2px;">${student.student_name}</h4>
                    <span style="font-size: 12px; color: var(--text-muted);">${student.roll_number} &bull; Match: ${student.confidence}%${appearancesText}</span>
                </div>
                <div>
                    <button type="button" class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="window.scannerInstance.toggleStatus('${roll}')">
                        ${student.status === 'PRESENT' ? '<span style="color: var(--success);">✓ Present</span>' : '<span style="color: var(--danger);">✗ Absent</span>'}
                    </button>
                </div>
            `;
            container.appendChild(card);
        });

        if (countSpan) {
            countSpan.innerText = presentCount;
        }
    }

    toggleStatus(roll) {
        if (this.detectedStudents.has(roll)) {
            const current = this.detectedStudents.get(roll);
            current.status = current.status === 'PRESENT' ? 'ABSENT' : 'PRESENT';
            this.updateDetectedUI();
        }
    }

    async saveSession(subjectId, dateStr, timeSlot) {
        const entries = [];
        this.detectedStudents.forEach(item => {
            entries.push(item);
        });

        if (entries.length === 0) {
            alert("No recognized students detected yet! Scan live faces or upload classroom photo(s).");
            return;
        }

        try {
            const csrfToken = this.getCsrfToken();
            const response = await fetch(this.saveUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    subject_id: subjectId,
                    date: dateStr,
                    time_slot: timeSlot,
                    entries: entries
                })
            });

            const res = await response.json();
            if (res.status === 'success') {
                alert("Attendance session saved successfully to online database!");
                window.location.href = '/teacher/dashboard/';
            } else {
                alert("Error saving session: " + res.message);
            }
        } catch (e) {
            alert("Network error while saving session: " + e);
        }
    }

    getCsrfToken() {
        const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }
}
