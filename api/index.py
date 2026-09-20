import os
import sys

# Ensure project root is in Python module path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app

# Export ASGI app for Vercel Serverless Functions
app = app
