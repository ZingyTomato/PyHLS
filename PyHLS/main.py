import os
import shutil
import uuid
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Header, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from utils import generate_hls, create_access_token, verify_access_token, hash_video_id
from database import VideoDatabase

app = FastAPI()
MEDIA_ROOT = "media"
HLS_ROOT = os.path.join(MEDIA_ROOT, "hls")
db = VideoDatabase()

os.makedirs(HLS_ROOT, exist_ok=True)

@app.post("/upload/", summary="Upload a media file to stream.")
async def upload_media(
    media: UploadFile = File(...),
    expiry_minutes: int = Query(60, ge=1, le=10080), request: Request = None  # max 7 days
, ):
    # Generate unique identifiers for each field
    internal_media_id = uuid.uuid4().hex  # Internal storage ID
    public_media_id = uuid.uuid4().hex    # Public reference ID
    access_key = uuid.uuid4().hex         # Secret key for token generation
    admin_key = uuid.uuid4().hex          # Admin key for destructive operations (shown only once)
    
    # Create directory using internal ID for security
    media_path = os.path.join(HLS_ROOT, f"{internal_media_id}.mp4")
    hls_dir = os.path.join(HLS_ROOT, internal_media_id)
    os.makedirs(hls_dir, exist_ok=True)

    # Save uploaded media
    with open(media_path, "wb") as f:
        f.write(await media.read())

    try:
        # Convert to HLS
        generate_hls(media_path, hls_dir)
    except Exception as e:
        shutil.rmtree(hls_dir)
        raise HTTPException(status_code=500, detail=f"Encoding failed: {str(e)}!")
    finally:
        # Clean up original file to save space
        if os.path.exists(media_path):
            os.remove(media_path)

    # Store media metadata in database
    media_data = {
        "public_id": public_media_id,
        "internal_id": internal_media_id,
        "access_key": access_key,
        "admin_key": admin_key,  # Store admin key for verification
        "upload_time": datetime.utcnow().isoformat(),
        "expiry_minutes": expiry_minutes
    }
    db.store_video(public_media_id, media_data)

    # Generate initial access token
    access_token = create_access_token(public_media_id, access_key, expiry_minutes)
    
    return {
        "media_id": public_media_id,
        "access_token": access_token,
        "admin_key": admin_key,  # IMPORTANT: Save this key! It's only shown once
        "playlist_url": f"{request.base_url}stream/{public_media_id}/playlist.m3u8?token={access_token}",
        "expires_in_minutes": expiry_minutes,
        "message": "Media uploaded and processed successfully. IMPORTANT: Save the admin_key - you'll need it for token refresh, deletion, and other admin operations!"
    }

@app.post("/refresh-token/{media_id}", summary="Refresh expired tokens.")
def refresh_access_token(
    media_id: str, 
    admin_key: str = Query(..., description="Admin key obtained in `upload`."),
    expiry_minutes: int = Query(60, ge=1, le=10080), request: Request = None
):
    """Generate a new access token for an existing video if it needs to be used after expiry - requires admin key"""
    media_data = db.get_video(media_id)
    if not media_data:
        raise HTTPException(status_code=404, detail="Media not found!")
    
    # Verify that the admin key is valid
    if media_data.get("admin_key") != admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key!")
    
    # Check if internal files still exist
    internal_id = media_data["internal_id"]
    hls_dir = os.path.join(HLS_ROOT, internal_id)
    playlist_path = os.path.join(hls_dir, "playlist.m3u8")
    
    if not os.path.exists(playlist_path):
        raise HTTPException(status_code=404, detail="Media files not found!")
    
    # Generate new access token
    access_token = create_access_token(media_id, media_data["access_key"], expiry_minutes)
    
    # Update expiry in database
    media_data["expiry_minutes"] = expiry_minutes
    media_data["last_token_refresh"] = datetime.utcnow().isoformat()
    db.update_video(media_id, media_data)
    
    return {
        "media_id": media_id,
        "access_token": access_token,
        "playlist_url": f"{request.base_url}stream/{media_id}/playlist.m3u8?token={access_token}",
        "expires_in_minutes": expiry_minutes,
        "message": "Access token refreshed successfully!"
    }

@app.get("/stream/{media_id}/playlist.m3u8", summary="Retrieve a specific m3u8 file.")
def get_playlist(media_id: str, access_token: str = Query(...,
                                                        description="The `access_token` obtained in `upload`.",
                                                        alias="token")):
    """Serve the HLS playlist after veryifying a valid token"""
    media_data = db.get_video(media_id)
    
    if not media_data:
        raise HTTPException(status_code=404, detail="Media not found!")
    
    if not verify_access_token(access_token, media_id, media_data["access_key"]):
        raise HTTPException(status_code=403, detail="Invalid or expired access token!")
    
    internal_id = media_data["internal_id"]
    playlist_path = os.path.join(HLS_ROOT, internal_id, "playlist.m3u8")
    
    if not os.path.exists(playlist_path):
        raise HTTPException(status_code=404, detail="Playlist not found!")
    
    # Rewrite playlist to include auth tokens in segment URLs
    updated_playlist = rewrite_playlist_with_auth_urls(playlist_path, media_id, access_token)
    
    from fastapi.responses import Response
    return Response(content=updated_playlist, media_type="application/vnd.apple.mpegurl")

@app.get("/stream/{media_id}/{segment_name}", summary="Retrieve a specific segment in a m3u8 file.")
def get_segment(media_id: str, segment_name: str, access_token: str = Query(..., description="The `access_token` obtained in `upload`.",
                                                                            alias="token")):
    """Serve video segments"""
    media_data = db.get_video(media_id)
    
    if not media_data:
        raise HTTPException(status_code=404, detail="Media not found!")
    
    if not verify_access_token(access_token, media_id, media_data["access_key"]):
        raise HTTPException(status_code=403, detail="Invalid or expired access token!")
    
    # Validate segment name to prevent path traversal
    if not segment_name.endswith('.ts') or '/' in segment_name or '..' in segment_name:
        raise HTTPException(status_code=400, detail="Invalid segment name!")
    
    internal_id = media_data["internal_id"]
    segment_path = os.path.join(HLS_ROOT, internal_id, segment_name)
    # Normalize and ensure segment_path is within the intended directory
    abs_hls_dir = os.path.abspath(os.path.join(HLS_ROOT, internal_id))
    norm_segment_path = os.path.abspath(os.path.normpath(segment_path))
    if not norm_segment_path.startswith(abs_hls_dir + os.sep):
        raise HTTPException(status_code=400, detail="Invalid segment path!")
    if not os.path.exists(norm_segment_path):
        raise HTTPException(status_code=404, detail="Segment not found")
    
    return FileResponse(norm_segment_path, media_type="video/MP2T")

@app.delete("/media/{media_id}", summary="Delete media from the db.")
def delete_media(
    media_id: str, 
    admin_key: str = Query(..., description="Admin key obtained in `/upload/`.")
):
    """Delete a video and its associated files"""
    media_data = db.get_video(media_id)
        
    if not media_data:
        raise HTTPException(status_code=404, detail="Media not found!")
    
    # Verify admin key as its a write operation
    if media_data.get("admin_key") != admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key!")
    
    # Delete the entry from the db
    internal_id = media_data['internal_id']
    contents = db._load_database()
    del contents[media_id]
    db._save_database(contents)
    
    hls_dir = os.path.join(HLS_ROOT, internal_id)
    if os.path.exists(hls_dir):
        shutil.rmtree(hls_dir)
    
    return {"message": "Media successfully deleted!"}

@app.get("/media/{media_id}/info", summary="Retrieve information about a specific media file.")
def get_media_info(
    media_id: str, 
    admin_key: str = Query(..., description="Admin key obtained in `/upload/`.")
):
    """Get detailed video information - requires admin key"""
    media_data = db.get_video(media_id)
    
    if not media_data:
        raise HTTPException(status_code=404, detail="Media not found!")
    
    # Verify admin key for detailed info
    if media_data.get("admin_key") != admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key!")
    
    return {
        "media_id": media_id,
        "upload_time": media_data["upload_time"],
        "expiry_minutes": media_data.get("expiry_minutes", 60),
        "last_token_refresh": media_data.get("last_token_refresh"),
        "created_at": media_data.get("created_at"),
        "updated_at": media_data.get("updated_at")
    }

@app.post("/media/{media_id}/extend-expiry", summary="Extend a media URL's expiry time.")
def extend_media_expiry(
    media_id: str,
    admin_key: str = Query(..., description="Admin key obtained in `/upload/`."),
    additional_minutes: int = Query(..., ge=1, le=10080, description="Additional minutes to extend.")
):
    """Extend media expiry time"""
    media_data = db.get_video(media_id)
    
    if not media_data:
        raise HTTPException(status_code=404, detail="Media not found!")
    
    # Verify admin key
    if media_data.get("admin_key") != admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key!")
    
    # Update expiry
    current_expiry = media_data.get("expiry_minutes", 60)
    new_expiry = current_expiry + additional_minutes
    
    # Cap at maximum allowed (7 days)
    new_expiry = min(new_expiry, 10080)
    
    media_data["expiry_minutes"] = new_expiry
    media_data["expiry_extended_at"] = datetime.utcnow().isoformat()
    db.update_video(media_id, media_data)
    
    return {
        "media_id": media_id,
        "previous_expiry_minutes": current_expiry,
        "new_expiry_minutes": new_expiry,
        "extended_by_minutes": new_expiry - current_expiry,
        "message": "Media expiry successfully extended!"
    }

def rewrite_playlist_with_auth_urls(playlist_path, media_id, auth_token):
    """Update playlist to include auth tokens in segment URLs"""
    with open(playlist_path, "r") as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        line = line.strip()
        if line.endswith(".ts"):
            # Add auth token to segment URL
            segment_name = line.split("/")[-1]  # Get just the filename
            new_line = f"/stream/{media_id}/{segment_name}?token={auth_token}"
            new_lines.append(new_line + "\n")
        else:
            new_lines.append(line + "\n")
    
    return "".join(new_lines)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)