import time
from datetime import datetime
import requests
from lightning_sdk import Studio, Machine
import os
from dotenv import load_dotenv

load_dotenv()

# === Supabase Config ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
TABLE_NAME = "studio_logs"

# === Studio Config ===
studio = Studio(
    os.getenv("STUDIO_NAME"),
    teamspace=os.getenv("TEAMSPACE"),
    user=os.getenv("USERNAME"),
    create_ok=True
)

def log_event(event_type, note="", type="event"):
    payload = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "note": note[:255],
        "type": type
    }

    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}", json=payload, headers=headers)
        if r.status_code not in [200, 201]:
            print("[⚠️] Log failed:", r.status_code, r.text)
    except Exception as e:
        print(f"[‼️] Logging exception: {e}")

def monitor_loop():
    running_since = None
    crash_count = 0

    while True:
        try:
            status = studio.status
            now = datetime.now()

            if status == "running":
                if not running_since:
                    running_since = now
                    log_event("start", "Studio marked as running")

                # Heartbeat every 5 minutes
                if now.minute % 5 == 0 and now.second < 60:
                    log_event("running", "Heartbeat: studio is alive", type="heartbeat")

                # Restart after 3 hours
                elapsed = (now - running_since).total_seconds()
                if elapsed >= 3 * 60 * 60:
                    log_event("pre_stop", f"Stopping after {elapsed/60:.1f} minutes")
                    studio.stop()
                    log_event("post_stop", "Studio stopped after 3hr session")

                    time.sleep(5)

                    log_event("pre_start", "Restarting studio after scheduled stop")
                    studio.start(Machine.CPU)
                    log_event("post_start", "Studio restarted after 3hr")

                    running_since = datetime.now()

            elif status == "stopped":
                # Unexpected crash
                crash_count += 1
                log_event("crash", f"Unexpected stop. Crash #{crash_count}")
                print("[💥] Studio crashed. Restarting...")

                log_event("pre_start", f"Restarting after crash #{crash_count}")
                studio.start(Machine.CPU)
                log_event("post_start", f"Studio restarted after crash #{crash_count}")

                running_since = datetime.now()

            else:
                log_event("unknown", f"Unknown studio state: {status}")
                print("[🤷] Unknown status, sleeping...")

        except Exception as e:
            log_event("error", f"Exception during monitor loop: {e}")
            print("[‼️] Exception:", e)

        time.sleep(60)

# === RUN ===
if __name__ == "__main__":
    log_event("startup", "Monitor started on Render")
    monitor_loop()
