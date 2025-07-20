import os
import subprocess
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta
from env import SECRET_KEY, ALGORITHM

def generate_hls(video_path, output_dir):
    """Convert video to HLS format"""
    os.makedirs(output_dir, exist_ok=True)
    playlist_path = os.path.join(output_dir, "playlist.m3u8")
    
    command = [
        "ffmpeg", "-i", video_path,
        "-c:v", "libx264",  # Updated codec syntax
        "-c:a", "aac",
        "-hls_time", "10",
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", os.path.join(output_dir, "segment%d.ts"),
        "-f", "hls",
        playlist_path
    ]
    
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return playlist_path
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg error: {e.stderr}")

def create_access_token(media_id, access_key, expiry_minutes):
    """Create a secure access token for video streaming"""
    now = datetime.utcnow()
    
    # Create a unique token ID for this specific token
    token_id = secrets.token_hex(16)
    
    payload = {
        "media_id": media_id,
        "access_key_hash": hash_string(access_key),  # Don't store raw key in token
        "iat": now,
        "exp": now + timedelta(minutes=expiry_minutes),
        "jti": token_id,  # Unique token identifier
        "token_type": "access"
    }
    
    # Use a combination of secret key and access key for signing
    signing_key = generate_signing_key(SECRET_KEY, access_key)
    return jwt.encode(payload, signing_key, algorithm=ALGORITHM)

def verify_access_token(token, expected_video_id, access_key):
    """Verify access token and check permissions"""
    try:
        signing_key = generate_signing_key(SECRET_KEY, access_key)
        payload = jwt.decode(token, signing_key, algorithms=[ALGORITHM])
        
        # Verify token type
        if payload.get("token_type") != "access":
            return False
            
        # Verify video ID matches
        if payload.get("media_id") != expected_video_id:
            return False
            
        # Verify access key hash
        expected_hash = hash_string(access_key)
        if payload.get("access_key_hash") != expected_hash:
            return False
            
        return True
        
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False
    except Exception:
        return False

def generate_signing_key(secret_key, access_key):
    """Generate a unique signing key for each video"""
    combined = f"{secret_key}:{access_key}"
    return hashlib.sha256(combined.encode()).hexdigest()

def hash_string(value):
    """Create a secure hash of a string"""
    return hashlib.sha256(value.encode()).hexdigest()

def hash_video_id(video_id):
    """Create a secure hash for internal storage mapping"""
    salt = SECRET_KEY[:16]  # Use part of secret as salt
    return hashlib.pbkdf2_hmac('sha256', video_id.encode(), salt.encode(), 100000).hex()

def generate_secure_filename():
    """Generate a cryptographically secure filename"""
    return secrets.token_hex(32)

def validate_token_format(token):
    """Basic validation of token format"""
    if not token or not isinstance(token, str):
        return False
    
    # JWT tokens have 3 parts separated by dots
    parts = token.split('.')
    if len(parts) != 3:
        return False
        
    return True

def create_admin_token(admin_key, expiry_hours=24):
    """Create an admin token for management operations"""
    now = datetime.utcnow()
    
    payload = {
        "admin": True,
        "admin_key_hash": hash_string(admin_key),
        "iat": now,
        "exp": now + timedelta(hours=expiry_hours),
        "jti": secrets.token_hex(16),
        "token_type": "admin"
    }
    
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_admin_token(token, admin_key):
    """Verify admin token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("token_type") != "admin":
            return False
            
        if not payload.get("admin"):
            return False
            
        expected_hash = hash_string(admin_key)
        if payload.get("admin_key_hash") != expected_hash:
            return False
            
        return True
        
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False
    except Exception:
        return False