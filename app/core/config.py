import os
from pathlib import Path

# Base directory: root of ispbilling project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings:
    PROJECT_NAME: str = "CyberNet ISP Billing System"
    VERSION: str = "2.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/cybernet.db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "cybernet-isp-secret-key-9fa789")
    DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "SAR")
    
    # Default MikroTik connection values
    DEFAULT_ROUTER_HOST: str = os.getenv("DEFAULT_ROUTER_HOST", "10.20.30.1")
    DEFAULT_ROUTER_PORT: int = int(os.getenv("DEFAULT_ROUTER_PORT", "8728"))

settings = Settings()
