echo "Installing Python dependencies..."
python3 -m pip install -r requirements.txt

echo "Collecting Static Files..."
python3 manage.py collectstatic --noinput

echo "Applying Database Migrations..."
python3 manage.py migrate