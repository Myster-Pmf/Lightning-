"""
Enhanced logging utilities with Supabase integration
"""
import os
import json
import requests
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
TABLE_NAME = "studio_logs"

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

def log_event(event_type, note="", type="event", metadata=None):
    """Enhanced logging function with better error handling"""
    debug_print(f"Logging to Supabase: {event_type} - {note}")
    
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        debug_print("Supabase URL or API Key is not set. Skipping log.")
        return False

    payload = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "note": note[:255] if note else "",
        "type": type,
        "metadata": json.dumps(metadata) if metadata else None
    }
    
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}", 
            json=payload, 
            headers=headers, 
            timeout=10
        )
        
        if response.status_code not in [200, 201]:
            debug_print(f"Supabase Log Error: {response.status_code} - {response.text}")
            return False
        
        return True
        
    except Exception as e:
        debug_print(f"Supabase Log Exception: {e}")
        return False

def get_logs(hours=24, limit=500):
    """Fetch logs from Supabase"""
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        return []
    
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}"
    }
    
    try:
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"
        params = {
            "order": "timestamp.desc",
            "limit": limit,
            "timestamp": f"gte.{since}"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            logs = response.json()
            # Parse metadata strings back to objects
            for log in logs:
                if isinstance(log.get('metadata'), str):
                    try:
                        log['metadata'] = json.loads(log['metadata'])
                    except:
                        log['metadata'] = {}
            return logs
        else:
            debug_print(f"Failed to fetch logs: {response.status_code} {response.text}")
            return []
            
    except Exception as e:
        debug_print(f"Exception fetching logs: {e}")
        return []