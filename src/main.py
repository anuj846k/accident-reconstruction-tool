from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.api.routes import (
    login_route, 
    projects_route, 
    processing_route, 
    analysis_route,
    homography_route,
    kestra_route,  # Kestra orchestration endpoints
    # vlm_analysis_route,  # COMMENTED OUT: Oumi VLM - kept for Oumi hackathon track demo only
)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="CCTV Accident Reconstruction API - Orchestrated by Kestra",
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoints
@app.get("/")
async def root():
    return {"status": "healthy", "app": settings.app_name}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# Include API routes with /api/v1 prefix
app.include_router(login_route.router, prefix="/api/v1")
app.include_router(projects_route.router, prefix="/api/v1")
app.include_router(processing_route.router, prefix="/api/v1")
app.include_router(analysis_route.router, prefix="/api/v1")
app.include_router(kestra_route.router, prefix="/api/v1")  # Kestra integration
app.include_router(homography_route.router, prefix="/api/v1")
# COMMENTED OUT: Oumi VLM routes - kept for Oumi hackathon track demo only
# The Oumi VLM code is preserved in vlm_analysis_route.py but not active
# due to memory constraints (18GB+ RAM required for local inference)
# app.include_router(vlm_analysis_route.router, prefix="/api/v1")