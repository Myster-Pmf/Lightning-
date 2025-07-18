import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string, jsonify
from lightning_sdk import Studio, Machine
import requests
from dotenv import load_dotenv

load_dotenv()

# === Debug Configuration ===
DEBUG = True

def debug_print(message):
    if DEBUG:
        print(f"[DEBUG {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

# === Supabase Config ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
TABLE_NAME = "studio_logs"

# === Studio Config ===
try:
    studio = Studio(
        os.getenv("STUDIO_NAME"),
        teamspace=os.getenv("TEAMSPACE"),
        user=os.getenv("USERNAME"),
        create_ok=True
    )
    debug_print("Studio object created successfully")
except Exception as e:
    debug_print(f"Failed to create Studio object: {e}")
    studio = None

# === Flask App ===
app = Flask(__name__)

# === Enhanced Logging Function ===
def log_event(event_type, note="", type="event"):
    debug_print(f"Logging event: {event_type} - {note}")
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
            debug_print(f"Log Error: {r.status_code} - {r.text}")
        else:
            debug_print("Event logged successfully")
    except Exception as e:
        debug_print(f"Log Exception: {e}")

# === Configuration Debug ===
def debug_config():
    debug_print("=== Configuration Debug ===")
    debug_print(f"STUDIO_NAME: {os.getenv('STUDIO_NAME')}")
    debug_print(f"TEAMSPACE: {os.getenv('TEAMSPACE')}")
    debug_print(f"USERNAME: {os.getenv('USERNAME')}")
    debug_print(f"SUPABASE_URL: {os.getenv('SUPABASE_URL')}")
    debug_print(f"SUPABASE_API_KEY: {'***SET***' if os.getenv('SUPABASE_API_KEY') else 'NOT SET'}")
    
    if studio:
        try:
            status = studio.status
            debug_print(f"Studio status: {status}")
            debug_print(f"Studio object: {studio}")
        except Exception as e:
            debug_print(f"Studio connection error: {e}")
    else:
        debug_print("Studio object is None")

# === Enhanced Monitor Logic ===
def monitor_loop():
    debug_print("Starting monitor loop")
    running_since = None
    crash_count = 0
    consecutive_errors = 0

    while True:
        try:
            if not studio:
                debug_print("Studio object is None, cannot monitor")
                time.sleep(60)
                continue

            status = studio.status
            debug_print(f"Current status: {status}")
            now = datetime.now()

            if status == "running":
                consecutive_errors = 0
                if not running_since:
                    running_since = now
                    log_event("start", "Studio marked as running")
                    debug_print("Studio started successfully")

                if now.minute % 5 == 0 and now.second < 60:
                    log_event("running", "Heartbeat: studio is alive", type="heartbeat")

                elapsed = (now - running_since).total_seconds()
                if elapsed >= 3 * 60 * 60:
                    debug_print(f"Stopping after {elapsed/60:.1f} minutes")
                    log_event("pre_stop", f"Stopping after {elapsed/60:.1f} minutes")
                    try:
                        studio.stop()
                        log_event("post_stop", "Studio stopped after 3hr session")
                        time.sleep(5)
                        log_event("pre_start", "Restarting studio after scheduled stop")
                        studio.start(Machine.CPU)
                        log_event("post_start", "Studio restarted after 3hr")
                        running_since = datetime.now()
                    except Exception as stop_start_error:
                        debug_print(f"Error during stop/start cycle: {stop_start_error}")
                        log_event("cycle_error", f"Stop/start error: {stop_start_error}")

            elif status == "stopped":
                consecutive_errors = 0
                crash_count += 1
                debug_print(f"Studio stopped unexpectedly. Crash #{crash_count}")
                log_event("crash", f"Unexpected stop. Crash #{crash_count}")
                log_event("pre_start", f"Restarting after crash #{crash_count}")
                
                try:
                    debug_print("Attempting to start machine...")
                    result = studio.start(Machine.CPU)
                    debug_print(f"Start result: {result}")
                    log_event("post_start", f"Studio restarted after crash #{crash_count}")
                    running_since = datetime.now()
                except Exception as start_error:
                    debug_print(f"Failed to start machine: {start_error}")
                    log_event("start_error", f"Failed to start: {start_error}")
                    time.sleep(30)  # Wait longer before retrying

            elif status == "starting":
                debug_print("Studio is starting...")
                log_event("starting", "Studio is in starting state")
                consecutive_errors = 0
                
            elif status == "stopping":
                debug_print("Studio is stopping...")
                log_event("stopping", "Studio is in stopping state")
                consecutive_errors = 0
                
            else:
                debug_print(f"Unknown studio state: {status}")
                log_event("unknown", f"Unknown studio state: {status}")

        except Exception as e:
            consecutive_errors += 1
            debug_print(f"Exception during monitor loop: {e}")
            log_event("error", f"Exception during monitor loop: {e}")
            
            if consecutive_errors >= 5:
                debug_print("Too many consecutive errors, taking longer break")
                time.sleep(300)  # 5 minutes break
                consecutive_errors = 0

        time.sleep(60)

# === Debug Route ===
@app.route("/debug")
def debug_info():
    debug_config()
    
    info = {
        "studio_name": os.getenv("STUDIO_NAME"),
        "teamspace": os.getenv("TEAMSPACE"),
        "username": os.getenv("USERNAME"),
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_API_KEY),
        "studio_object": studio is not None,
        "current_time": datetime.now().isoformat()
    }
    
    if studio:
        try:
            info["studio_status"] = studio.status
        except Exception as e:
            info["studio_status_error"] = str(e)
    
    return jsonify(info)

# === Enhanced Status Check ===
@app.route("/status")
def status_check():
    if not studio:
        return jsonify({"error": "Studio not initialized"}), 500
    
    try:
        status = studio.status
        return jsonify({"status": status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === Manual Start Route ===
@app.route("/start")
def manual_start():
    if not studio:
        return jsonify({"error": "Studio not initialized"}), 500
    
    try:
        result = studio.start(Machine.CPU)
        log_event("manual_start", "Manual start triggered")
        return jsonify({"result": "started", "details": str(result)})
    except Exception as e:
        log_event("manual_start_error", f"Manual start failed: {e}")
        return jsonify({"error": str(e)}), 500

# === Your existing routes ===
@app.route("/logs")
def show_logs():
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}"
    }
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?order=timestamp.desc&limit=100",
            headers=headers
        )
        logs = r.json() if r.status_code == 200 else []
    except Exception as e:
        logs = []

    return render_template_string("""
    <html>
    <head>
        <title>Studio Logs</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-900 text-white p-4">
        <h1 class="text-3xl mb-4 font-bold">🪵 LightningAI Studio Logs</h1>
        <div class="mb-4">
            <a href="/debug" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded mr-2">Debug Info</a>
            <a href="/status" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded mr-2">Status Check</a>
            <a href="/start" class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded">Manual Start</a>
        </div>
        <table class="table-auto w-full text-sm">
            <thead class="bg-gray-700">
                <tr>
                    <th class="px-2 py-1 text-left">Time</th>
                    <th class="px-2 py-1 text-left">Type</th>
                    <th class="px-2 py-1 text-left">Event</th>
                    <th class="px-2 py-1 text-left">Note</th>
                </tr>
            </thead>
            <tbody>
                {% for log in logs %}
                <tr class="border-b border-gray-800">
                    <td class="px-2 py-1">{{ log.timestamp }}</td>
                    <td class="px-2 py-1">{{ log.type }}</td>
                    <td class="px-2 py-1">{{ log.event_type }}</td>
                    <td class="px-2 py-1">{{ log.note }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </body>
    </html>
    """, logs=logs)

@app.route("/")
def dashboard():
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}"
    }
    logs = []
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?order=timestamp.asc&limit=1000", headers=headers)
        if r.status_code == 200:
            logs = r.json()
    except:
        pass

    is_running = logs[-1]["event_type"] in ["start", "running", "post_start"] if logs else False

    return render_template_string("""
    <html>
    <head>
        <title>Studio Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-900 text-white min-h-screen p-6">
        <h1 class="text-4xl font-bold mb-6">⚡ LightningAI Studio Dashboard</h1>
        <p class="mb-4">Status: <span class="font-bold {{ 'text-green-400' if is_running else 'text-red-400' }}">{{ 'Running' if is_running else 'Stopped' }}</span></p>
        
        <div class="mb-4">
            <a href="/debug" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded mr-2">Debug Info</a>
            <a href="/status" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded mr-2">Status Check</a>
            <a href="/start" class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded mr-2">Manual Start</a>
            <a href="/logs" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded">View Logs</a>
        </div>

        <canvas id="uptimeChart" width="400" height="200"></canvas>

        <script>
        const ctx = document.getElementById('uptimeChart').getContext('2d');
        const logs = {{ logs|tojson }};

        const dataPoints = logs.map(log => ({
            x: new Date(log.timestamp),
            y: log.event_type === "running" || log.event_type === "start" || log.event_type === "post_start" ? 1 : 0
        }));

        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [{
                    label: 'Studio Status (1=Up, 0=Down)',
                    data: dataPoints,
                    fill: false,
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1
                }]
            },
            options: {
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'minute'
                        }
                    },
                    y: {
                        min: 0,
                        max: 1,
                        ticks: {
                            stepSize: 1,
                            callback: value => value === 1 ? 'Running' : 'Down'
                        }
                    }
                }
            }
        });
        </script>
    </body>
    </html>
    """, logs=logs, is_running=is_running)

# === Background Thread for Monitor ===
def start_monitor():
    thread = threading.Thread(target=monitor_loop)
    thread.daemon = True
    thread.start()

# === Start Monitor + Flask ===
if __name__ == "__main__":
    debug_config()
    log_event("startup", "Monitor and UI server starting")
    start_monitor()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
