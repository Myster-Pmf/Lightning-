"""
Enhanced logging utilities with local JSON file storage
"""
import os
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Local JSON file configuration
LOGS_FILE = "data/studio_logs.json"
MAX_LOGS = 10000  # Maximum number of logs to keep

# Debug configuration
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

def setup_logging():
    """Setup enhanced logging"""
    logging.basicConfig(
        level=logging.INFO if DEBUG else logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def debug_print(message):
    """Print debug messages"""
    if DEBUG:
        print(f"[DEBUG {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def _ensure_logs_dir():
    """Ensure logs directory exists"""
    os.makedirs("data", exist_ok=True)

def _load_logs():
    """Load logs from JSON file"""
    try:
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        debug_print(f"Error loading logs: {e}")
    return []

def _save_logs(logs):
    """Save logs to JSON file"""
    try:
        _ensure_logs_dir()
        # Keep only the most recent logs
        if len(logs) > MAX_LOGS:
            logs = logs[-MAX_LOGS:]
        
        with open(LOGS_FILE, 'w') as f:
            json.dump(logs, f, indent=2)
        return True
    except Exception as e:
        debug_print(f"Error saving logs: {e}")
        return False

def log_event(event_type, note="", type="event", metadata=None):
    """Enhanced logging function with local JSON storage"""
    debug_print(f"Logging to local file: {event_type} - {note}")
    
    try:
        # Load existing logs
        logs = _load_logs()
        
        # Create new log entry
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "note": note[:255] if note else "",
            "type": type,
            "metadata": metadata if metadata else {}
        }
        
        # Add to logs
        logs.append(log_entry)
        
        # Save logs
        return _save_logs(logs)
        
    except Exception as e:
        debug_print(f"Local Log Exception: {e}")
        return False

def get_logs(hours=24, limit=500):
    """Fetch logs from local JSON file"""
    try:
        logs = _load_logs()
        
        # Filter by time range
        since = datetime.now() - timedelta(hours=hours)
        filtered_logs = []
        
        for log in logs:
            try:
                log_time = datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00'))
                if log_time >= since:
                    filtered_logs.append(log)
            except Exception as e:
                debug_print(f"Error parsing log timestamp: {e}")
                # Include logs with parsing errors anyway
                filtered_logs.append(log)
        
        # Sort by timestamp (newest first) and limit
        filtered_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return filtered_logs[:limit]
        
    except Exception as e:
        debug_print(f"Exception fetching logs: {e}")
        return []