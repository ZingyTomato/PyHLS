# PyHLS

A self-hosted, secure HTTP Live Streaming (HLS) service designed as an open-source alternative to enterprise media delivery platforms. PyHLS provides token-based authentication, automatic video transcoding, and time-limited access control for media content distribution including audio and video files.

## 📑 Table of Contents

-   [🎧 Features](#-features)
-   [❓ How It Works](#-how-it-works)
-   [🔨 Requirements](#-requirements)
-   [👨🏻‍🔧 Installation](#-installation)
-   [🎵 Example Usage](#-example-usage)
-   [📖 API Documentation](#-api-documentation)
-   [📙 Configuration](#-configuration)
-   [👨🏻‍💻 Security Considerations](#-security-considerations)
-   [🚤 Performance Notes](#-performance-notes)
-   [❌ Limitations](#-limitations)
-   [🏥 Contributing](#-contributing)

## 🎧 Features

-   **Secure Token-Based Access**: JWT authentication with configurable expiration times.
-   **Automatic HLS Transcoding**: Converts uploaded audio/videos to HLS format with segmented playback.
-   **Multi-Layer Security**: Separate internal/public IDs, access keys, and admin keys.
-   **Time-Limited Content**: Configurable media expiry (1 minute to 7 days).
-   **Path Traversal Protection**: Secure file serving with input validation.
-   **Thread-Safe Database**: File-based JSON storage.
-   **Admin Operations**: Token refresh, expiry extension, and content management.
-   **Universal Media Support**: Works with both video and audio files.

## ❓ How It Works

1.  **Upload**: When media is uploaded, it's assigned a set of unique IDs:

	-   A private internal ID for storage
	-   A public ID for API access
	-   A secure access key for generating playback tokens
	-   An admin key for refreshing tokens or deleting the video
    
2.  **Automatic HLS Conversion**: The uploaded video is converted to **HLS (HTTP Live Streaming)** format using `ffmpeg`. HLS works by splitting video into short `.ts` segments (around 10 seconds each) and generating an `.m3u8` playlist file that tells the player how to stream them. 
    
3.  **Access Control**: Every request requires a valid, signed JWT token. These tokens are tied to specific medias and expire after a set time, preventing long-term link sharing.
    
4.  **Dynamic Playlist Generation**: When someone requests the playlist, it’s dynamically rewritten to include secure, time-expiring URLs for each segment. Even if someone shares the playlist URL, the embedded links will expire on their own.

All media metadata, including IDs, access keys, expiry times, and status, is stored in a local file-based database (`video_database.json`), stored in `/media/`. This JSON file provides persistent storage with thread-safe read/write operations.

## 🔨 Requirements

-   Python 3.7+
-   FFmpeg
-   Enough disk space to store your required media files.

## 👨🏻‍🔧 Installation

### **🐳** Docker (Recommended)

```bash
---
services:
  pyhls:
    image: zingytomato/pyhls:main
    container_name: pyhls
    ports:
      - 8001:8000 # External port can be changed
    volumes:
      - PyHLS:/PyHLS/media # Change PyHLS to your preferred directory
    restart: unless-stopped

volumes: # Remove this if using your own local directory
  PyHLS:
```

### 💻 Manual Installation

```bash
# Clone repository
git clone https://github.com/zingytomato/pyhls.git
cd pyhls

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg (Ubuntu/Debian)
sudo apt update && sudo apt install ffmpeg

# Install FFmpeg (macOS)
brew install ffmpeg

# Run server
uvicorn main:app --reload --port 8000 --host 127.0.0.1
```

## 🎵 Example Usage

Here's a complete example of uploading and streaming a music file, you can also go to `http://YOUR_HOST:8000/docs`:

### Step 1: Upload an Audio File

```bash
# Upload a music file with 4-hour expiry
curl -X POST "http://localhost:8000/upload/?expiry_minutes=240" \
  -F "media=@song.mp3"

```

**Response:**

```json
{
  "media_id": "m3u8_abc123def456",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtZWRpYV9pZCI6Im0zdTh...",
  "admin_key": "admin_xyz789uvw123",
  "playlist_url": "http://localhost:8000/stream/m3u8_abc123def456/playlist.m3u8?token=eyJ0eXA...",
  "expires_in_minutes": 240,
  "message": "Media uploaded and processed successfully. Audio transcoded to HLS format."
}

```
Keep note of `admin_key` as it's only shown once for each file and will come in handy for any operations that require writing to the database.

### Step 2: Stream the Audio

Use the playlist URL in any HLS-compatible player:

```javascript
// Web player example
const video = document.createElement('video');
video.src = 'http://localhost:8000/stream/m3u8_abc123def456/playlist.m3u8?token=eyJ0eXA...';
video.controls = true;
document.body.appendChild(video);

```

```bash
# Or test with VLC/mpv
vlc "http://localhost:8000/stream/m3u8_abc123def456/playlist.m3u8?token=eyJ0eXA..."
```

### Step 3: Extend Access (Optional)

```bash
# Extend access by 2 more hours
curl -X POST "http://localhost:8000/media/m3u8_abc123def456/extend-expiry?admin_key=admin_xyz789uvw123&additional_minutes=120"
```

## 📖 API Documentation

### Upload Media

Upload and transcode a media file for streaming.

**Endpoint:** `POST /upload/`

**Parameters:**

-   `media` (file): Media file to upload
-   `expiry_minutes` (query, optional): Expiry time in minutes (default: 60, max: 10080)

**Response:**

```json
{
  "media_id": "abc123def456",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "admin_key": "xyz789uvw123",
  "playlist_url": "http://localhost:8000/stream/abc123def456/playlist.m3u8?token=...",
  "expires_in_minutes": 60,
  "message": "Media uploaded and processed successfully..."
}
```

**Example:**

```bash
curl -X POST "http://localhost:8000/upload/?expiry_minutes=120" \
  -F "media=@media.mp4"
```
Keep note of `admin_key` as it's only shown once for each file and will come in handy for any operations that require writing to the database.

### Stream Playlist

Retrieve the HLS playlist file for media playback.

**Endpoint:** `GET /stream/{media_id}/playlist.m3u8`

**Parameters:**

-   `media_id` (path): Public media identifier
-   `token` (query): Access token from upload response

**Response:** HLS playlist file (application/vnd.apple.mpegurl)

**Example:**

```bash
curl "http://localhost:8000/stream/abc123def456/playlist.m3u8?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
```

### Stream Segment

Retrieve individual media segments.

**Endpoint:** `GET /stream/{media_id}/{segment_name}`

**Parameters:**

-   `media_id` (path): Public media identifier
-   `segment_name` (path): Segment filename (e.g., segment0.ts)
-   `token` (query): Access token

**Response:** Media segment (video/MP2T)

**Example:**

```bash
curl "http://localhost:8000/stream/abc123def456/segment0.ts?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
```

### Refresh Access Token

Generate a new access token for expired media.

**Endpoint:** `POST /refresh-token/{media_id}`

**Parameters:**

-   `media_id` (path): Public media identifier
-   `admin_key` (query): Admin key from upload response
-   `expiry_minutes` (query, optional): New expiry time (default: 60)

**Response:**

```json
{
  "media_id": "abc123def456",
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "playlist_url": "http://localhost:8000/stream/abc123def456/playlist.m3u8?token=...",
  "expires_in_minutes": 60,
  "message": "Access token refreshed successfully!"
}
```

**Example:**

```bash
curl -X POST "http://localhost:8000/refresh-token/abc123def456?admin_key=xyz789uvw123&expiry_minutes=180"
```

### Get Media Information

Retrieve metadata about uploaded media.

**Endpoint:** `GET /media/{media_id}/info`

**Parameters:**

-   `media_id` (path): Public media identifier
-   `admin_key` (query): Admin key from upload response

**Response:**

```json
{
  "media_id": "abc123def456",
  "upload_time": "2025-07-20T10:30:00.000000",
  "expiry_minutes": 60,
  "last_token_refresh": "2025-07-20T11:00:00.000000",
  "created_at": "2025-07-20T10:30:00.000000",
  "updated_at": "2025-07-20T11:00:00.000000"
}
```

**Example:**

```bash
curl "http://localhost:8000/media/abc123def456/info?admin_key=xyz789uvw123"
```

### Extend Media Expiry

Extend the expiration time of uploaded media.

**Endpoint:** `POST /media/{media_id}/extend-expiry`

**Parameters:**

-   `media_id` (path): Public media identifier
-   `admin_key` (query): Admin key from upload response
-   `additional_minutes` (query): Minutes to add (max total: 10080)

**Response:**

```json
{
  "media_id": "abc123def456",
  "previous_expiry_minutes": 60,
  "new_expiry_minutes": 180,
  "extended_by_minutes": 120,
  "message": "Media expiry successfully extended!"
}
```

**Example:**

```bash
curl -X POST "http://localhost:8000/media/abc123def456/extend-expiry?admin_key=xyz789uvw123&additional_minutes=120"
```

### Delete Media

Remove media and associated files from the server.

**Endpoint:** `DELETE /media/{media_id}`

**Parameters:**

-   `media_id` (path): Public media identifier
-   `admin_key` (query): Admin key from upload response

**Response:**

```json
{
  "message": "Media successfully deleted!"
}
```

**Example:**

```bash
curl -X DELETE "http://localhost:8000/media/abc123def456?admin_key=xyz789uvw123"
```

## 📙 Configuration

Environment variables can be set to customize behavior:

-   `SECRET_KEY`: JWT signing key (auto-generated if not provided)
-   `ALGORITHM`: JWT algorithm (default: HS256)

## 👨🏻‍💻 Security Considerations

-   **Admin Key Storage**: Admin keys are shown only once during upload. Store them securely.
-   **Token Expiration**: Access tokens expire based on configured time limits.
-   **Path Validation**: All file operations include path traversal protection.
-   **Internal ID Isolation**: File storage uses internal IDs invisible to API consumers.

## 🚤 Performance Notes

-   Media files are transcoded to H.264/AAC for maximum compatibility.
-   Segments are 10 seconds long for optimal streaming performance.
-   Original uploaded files are deleted after transcoding to save space.

## ❌ Limitations

-   File-based database (suitable for moderate loads).
-   Single-node architecture (horizontal scaling requires additional work).
-   No built-in CDN capabilities.
-   FFmpeg dependency required for media processing.

## 🏥 Contributing

Feel free to create an issue if you encounter any bugs or would like to suggest something!