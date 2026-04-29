"""
Production entrypoint.

Usage:
    uv run uvicorn scalemyprints.main:app --host 0.0.0.0 --port 8000
"""

from scalemyprints.app import create_app

app = create_app()
