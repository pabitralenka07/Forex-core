"""Vercel Serverless Function entrypoint for Forex-Core FastAPI backend."""

import os
import sys

# Add backend directory to Python system path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app

__all__ = ["app"]
