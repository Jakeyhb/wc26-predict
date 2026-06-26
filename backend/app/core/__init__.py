"""core — pure prediction engine with zero IO dependencies.

Rules for app.core.*:
- No SQLAlchemy imports
- No FastAPI imports
- No Streamlit imports
- No Celery imports
- No requests/httpx imports
- No file writes
- No environment variable reads
- No DB access
- No model loading
"""
