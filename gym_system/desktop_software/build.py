"""
Build script for creating executable
"""

import subprocess
import sys
import os

# Change to the desktop_software directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# PyInstaller command
cmd = [
    sys.executable, '-m', 'PyInstaller',
    '--name=GymSystem',
    '--onefile',
    '--windowed',
    '--icon=assets/icon.ico',
    '--add-data=assets;assets',
    '--hidden-import=customtkinter',
    '--hidden-import=pyodbc',
    '--hidden-import=requests',
    '--hidden-import=PIL',
    'main.py'
]

# For macOS, adjust the separator
if sys.platform == 'darwin':
    cmd[5] = '--add-data=assets:assets'

print("Building executable...")
print(f"Command: {' '.join(cmd)}")
print()

try:
    subprocess.run(cmd, check=True)
    print("\nBuild complete! Check the 'dist' folder for the executable.")
except subprocess.CalledProcessError as e:
    print(f"\nBuild failed: {e}")
except FileNotFoundError:
    print("\nPyInstaller not found. Install it with: pip install pyinstaller")
