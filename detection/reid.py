import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ReIDEngine:
    def __init__(self):
        # session_cache: {reid_token: {exit_time: datetime, reentry_count: int}}
        self.session_cache: Dict[str, Dict[str, Any]] = {}
        # 24-hour cache TTL
        self.cache_ttl = timedelta(hours=24)

    def generate_reid_token(self, track_id: int, appearance_features: Optional[Dict[str, Any]] = None) -> str:
        """
        Generates a deterministic Re-ID token for a tracked shopper.
        If appearance features are available, they can be blended into the hash.
        """
        feat_str = str(appearance_features) if appearance_features else ""
        payload = f"REID_{track_id}_{feat_str}"
        hasher = hashlib.sha256(payload.encode('utf-8'))
        sha_hex = hasher.hexdigest().upper()
        # Return REID_ followed by the first 12 chars of the hash
        return f"REID_{sha_hex[:12]}"

    def check_reentry(self, reid_token: str, frame_time: datetime) -> bool:
        """
        Checks if the visitor has re-entered the store.
        Re-entry is valid if they exited within the last 5 minutes (300,000 milliseconds).
        """
        self._cleanup_expired_sessions(frame_time)
        
        session = self.session_cache.get(reid_token)
        if not session or not session.get('exit_time'):
            return False

        exit_time = session['exit_time']
        time_since_exit = frame_time - exit_time
        
        # 5-minute threshold (300 seconds)
        if time_since_exit.total_seconds() <= 300.0:
            logger.info("reentry_detected", token=reid_token, delta_sec=time_since_exit.total_seconds())
            return True
            
        return False

    def store_session(self, reid_token: str, exit_time: datetime) -> None:
        """Stores the session exit timestamp and increments the visitor's session counter."""
        if reid_token not in self.session_cache:
            self.session_cache[reid_token] = {
                'reentry_count': 0,
                'exit_time': None
            }
            
        self.session_cache[reid_token]['exit_time'] = exit_time
        self.session_cache[reid_token]['reentry_count'] += 1
        logger.info("session_stored", token=reid_token, reentry_count=self.session_cache[reid_token]['reentry_count'])

    def get_session_number(self, reid_token: str) -> int:
        """Returns the session sequence count for a visitor token."""
        session = self.session_cache.get(reid_token)
        return session['reentry_count'] if session else 0

    def _cleanup_expired_sessions(self, current_time: datetime) -> None:
        """Removes sessions from the cache that are older than the 24-hour TTL."""
        expired_tokens = []
        for token, data in self.session_cache.items():
            exit_time = data.get('exit_time')
            if exit_time and (current_time - exit_time) > self.cache_ttl:
                expired_tokens.append(token)
                
        for token in expired_tokens:
            self.session_cache.pop(token, None)
            logger.info("cache_ttl_expired", token=token)
