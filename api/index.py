import os
import sys

# Ensure root directory is at position 0 in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.main import app

# Export FastAPI instance for Vercel
app = app
