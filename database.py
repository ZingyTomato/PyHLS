import json
import os
import threading
from datetime import datetime
from typing import Dict, Optional

class VideoDatabase:
    """Simple file-based database for video metadata"""
    
    def __init__(self, db_path: str = "video_database.json"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database file if it doesn't exist"""
        if not os.path.exists(self.db_path):
            with open(self.db_path, 'w') as f:
                json.dump({}, f)
    
    def _load_database(self) -> Dict:
        """Load database from file"""
        try:
            with open(self.db_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_database(self, data: Dict):
        """Save database to file"""
        # Create backup
        backup_path = f"{self.db_path}.backup"
        if os.path.exists(self.db_path):
            os.rename(self.db_path, backup_path)
        
        try:
            with open(self.db_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            # Remove backup if successful
            if os.path.exists(backup_path):
                os.remove(backup_path)
                
        except Exception as e:
            # Restore backup if save failed
            if os.path.exists(backup_path):
                os.rename(backup_path, self.db_path)
            raise e
    
    def store_video(self, public_id: str, video_data: Dict):
        """Store video metadata"""
        with self.lock:
            db_data = self._load_database()
            
            # Add timestamp
            video_data['created_at'] = datetime.utcnow().isoformat()
            video_data['updated_at'] = datetime.utcnow().isoformat()
            
            db_data[public_id] = video_data
            self._save_database(db_data)
    
    def get_video(self, public_id: str) -> Optional[Dict]:
        """Retrieve video metadata"""
        with self.lock:
            db_data = self._load_database()
            return db_data.get(public_id)
    
    def update_video(self, public_id: str, video_data: Dict):
        """Update video metadata"""
        with self.lock:
            db_data = self._load_database()
            
            if public_id in db_data:
                video_data['updated_at'] = datetime.utcnow().isoformat()
                db_data[public_id] = video_data
                self._save_database(db_data)
                return True
            return False
    
    def delete_video(self, public_id: str) -> bool:
        """Delete video metadata"""
        with self.lock:
            db_data = self._load_database()
            
            if public_id in db_data:
                del db_data[public_id]
                self._save_database(db_data)
                return True
            return False
    
    def list_videos(self, status: str = None) -> Dict:
        """List all videos, optionally filtered by status"""
        with self.lock:
            db_data = self._load_database()
            
            if status:
                return {k: v for k, v in db_data.items() if v.get('status') == status}
            
            return db_data
    
    def cleanup_expired_videos(self) -> int:
        """Remove expired video entries (for maintenance)"""
        with self.lock:
            db_data = self._load_database()
            current_time = datetime.utcnow()
            expired_count = 0
            
            videos_to_remove = []
            
            for public_id, video_data in db_data.items():
                try:
                    upload_time = datetime.fromisoformat(video_data['upload_time'])
                    expiry_minutes = video_data.get('expiry_minutes', 60)
                    
                    if current_time > upload_time + timedelta(minutes=expiry_minutes):
                        videos_to_remove.append(public_id)
                        expired_count += 1
                        
                except (ValueError, KeyError):
                    # Invalid date format or missing data
                    continue
            
            # Remove expired videos
            for public_id in videos_to_remove:
                del db_data[public_id]
            
            if expired_count > 0:
                self._save_database(db_data)
            
            return expired_count
    
    def get_video_by_internal_id(self, internal_id: str) -> Optional[Dict]:
        """Find video by internal ID (for maintenance tasks)"""
        with self.lock:
            db_data = self._load_database()
            
            for public_id, video_data in db_data.items():
                if video_data.get('internal_id') == internal_id:
                    return video_data
            
            return None
    
    def update_video_status(self, public_id: str, status: str):
        """Update only the status of a video"""
        with self.lock:
            db_data = self._load_database()
            
            if public_id in db_data:
                db_data[public_id]['status'] = status
                db_data[public_id]['updated_at'] = datetime.utcnow().isoformat()
                self._save_database(db_data)
                return True
            return False
    
    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        with self.lock:
            db_data = self._load_database()
            
            total_videos = len(db_data)
            status_counts = {}
            
            for video_data in db_data.values():
                status = video_data.get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                'total_videos': total_videos,
                'status_distribution': status_counts,
                'database_size_bytes': os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            }