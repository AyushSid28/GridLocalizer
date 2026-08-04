import sys
import os

# Add backend to Python path so app imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.main import app  # noqa: F401 - Vercel uses 'app' as the ASGI entrypoint
