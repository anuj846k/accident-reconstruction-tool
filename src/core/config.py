from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    How it works:
    - Pydantic automatically reads from .env file
    - Variable names are case-insensitive (APP_NAME becomes app_name)
    - Type validation happens automatically (debug must be bool, etc.)
    - If a required variable is missing, app crashes with clear error
    """
    
    # Application Settings
    app_name: str = "AccidentReconstruction"
    debug: bool = False
    secret_key: str  # Required - no default, must be in .env
    
    # Database
    database_url: str  # Required - your Neon connection string
    
    
    # Cloudinary
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    
    
    # File Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 500
    
    # Kestra
    kestra_api_url: str = "http://localhost:8080/api/v1"
    
    # JWT Authentication
    access_token_expire_minutes: int = 30
    algorithm: str = "HS256"  # JWT signing algorithm
    
    # Model Cache Directories (for external SSD storage)
    hf_cache_dir: Optional[str] = None  # HuggingFace cache directory
    hf_home: Optional[str] = None  # Alternative HF_HOME env var
    transformers_cache: Optional[str] = None  # Alternative TRANSFORMERS_CACHE env var
    torch_home: Optional[str] = None  # PyTorch cache directory
    
    class Config:
        # Tell Pydantic where to find the .env file
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Why @lru_cache?
    - Reads .env file only once (on first call)
    - All subsequent calls return the same instance
    - Better performance (no repeated file I/O)
    - Acts like a singleton pattern
    """
    return Settings()

settings = get_settings()