import os
import secrets
from typing import Optional

def get_env_var(name: str, default: Optional[str] = None, required: bool = False) -> str:
    """Get environment variable with optional default and required check"""
    value = os.getenv(name, default)
    
    if required and not value:
        raise ValueError(f"Required environment variable {name} is not set!")
    
    return value

# Generate a secure secret key if not provided
def generate_secret_key() -> str:
    """Generate a cryptographically secure secret key"""
    return secrets.token_urlsafe(64)

# JWT Configuration
SECRET_KEY = get_env_var("SECRET_KEY") or generate_secret_key()
ALGORITHM = get_env_var("ALGORITHM", "HS256")