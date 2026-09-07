echo "Installing dependencies..."
pip install -r requirements.txt

echo "Applying Migrations..."
python3 manage.py migrate