# WSGI file for PythonAnywhere
import sys
import os

# Add project directory to path
project_home = '/home/gymsystem/sytem-gym/gym_system'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Import from main.py
from main import application
