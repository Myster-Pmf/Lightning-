import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string
from lightning_sdk import Studio, Machine
import requests
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

# === Flask App ===
app = Flask(__name__)

# === Logging Function ===
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
            print("[Log Error]", r.status_code, r.text)
    except Exception as e:
        print("[Log Exception]", e)

# === Monitor Logic ===
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

                if now.minute % 5 == 0 and now.second < 60:
                    log_event("running", "Heartbeat: studio is alive", type="heartbeat")

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
                crash_count += 1
                log_event("crash", f"Unexpected stop. Crash #{crash_count}")
                log_event("pre_start", f"Restarting after crash #{crash_count}")
                studio.start(Machine.CPU)
                log_event("post_start", f"Studio restarted after crash #{crash_count}")
                running_since = datetime.now()

            else:
                log_event("unknown", f"Unknown studio state: {status}")

        except Exception as e:
            log_event("error", f"Exception during monitor loop: {e}")

        time.sleep(60)

# === UI Routes ===
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
    log_event("startup", "Monitor and UI server starting")
    start_monitor()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
