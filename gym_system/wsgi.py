# WSGI file for PythonAnywhere
import sys
import os

# Add project directory to path
project_home = '/home/gymsystem/sytem-gym/gym_system'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables
os.environ['FLASK_ENV'] = 'production'
os.environ['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
os.environ['DATABASE_URL'] = 'sqlite:///gym.db'

# Import and create app
from app import create_app

application = create_app('production')
