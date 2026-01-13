# WSGI file for PythonAnywhere
import sys
import os

# Add project directory to path
project_home = '/home/gymsystem/sytem-gym/gym_system'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables for PythonAnywhere
os.environ['FLASK_ENV'] = 'production'
os.environ['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
os.environ['DATABASE_URL'] = f'sqlite:///{project_home}/instance/gym_system.db'

# Ensure instance directory exists
instance_dir = os.path.join(project_home, 'instance')
if not os.path.exists(instance_dir):
    os.makedirs(instance_dir, exist_ok=True)

# Import from main.py
from main import application
