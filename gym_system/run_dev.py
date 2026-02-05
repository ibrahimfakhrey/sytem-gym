#!/usr/bin/env python
"""Development server runner"""
import os
os.environ['FLASK_ENV'] = 'development'

from app import create_app
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=True)
