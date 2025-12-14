"""
API Routes.

All routes are imported here for use in main.py
"""

from src.api.routes import login_route
from src.api.routes import projects_route
from src.api.routes import processing_route
from src.api.routes import analysis_route
from src.api.routes import kestra_route

# COMMENTED OUT: Oumi VLM routes - kept for Oumi hackathon track demo
# The code is preserved but not active due to memory constraints
# from src.api.routes import vlm_analysis_route

__all__ = [
    "login_route",
    "projects_route",
    "processing_route",
    "analysis_route",
    "kestra_route",
    # "vlm_analysis_route",  # Commented out - Oumi track demo only
]






