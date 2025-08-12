"""
Enhanced Lightning AI Studio Dashboard
Main entry point for the application
"""
import os
import threading
import time
import subprocess
import sys
import json
import queue
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request
from lightning_sdk import Studio, Machine
import requests
from dotenv import load_dotenv
import traceback

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
app.config['ASYNC_TASKS'] = {}
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this')

# === Enhanced Logging Function ===
def log_event(event_type, note="", type="event", metadata=None):
    debug_print(f"Logging to Supabase: {event_type} - {note}")
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        debug_print("Supabase URL or API Key is not set. Skipping log.")
        return

    payload = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "note": note[:255],
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
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}", json=payload, headers=headers, timeout=10)
        if r.status_code not in [200, 201]:
            debug_print(f"!!! Supabase Log Error: {r.status_code} - {r.text}")
    except Exception as e:
        debug_print(f"!!! Supabase Log Exception: {e}")

# === Get Real Studio Status ===
def get_studio_status():
    try:
        if not studio: return "error", "Studio not initialized"
        return str(studio.status), None
    except Exception as e:
        return "error", str(e)

# Simple HTML template for basic functionality
SIMPLE_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lightning AI Studio Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: white; }
        .container { max-width: 800px; margin: 0 auto; }
        .status { padding: 20px; background: #333; border-radius: 8px; margin: 20px 0; }
        .controls { display: flex; gap: 10px; margin: 20px 0; }
        button { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
        .start { background: #28a745; color: white; }
        .stop { background: #dc3545; color: white; }
        .restart { background: #ffc107; color: black; }
        .status-running { color: #28a745; }
        .status-stopped { color: #dc3545; }
        .status-error { color: #dc3545; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Lightning AI Studio Dashboard</h1>
        
        <div class="status">
            <h2>Current Status: <span id="status" class="status-unknown">Loading...</span></h2>
            <p>Last Updated: <span id="lastUpdated">--</span></p>
        </div>
        
        <div class="controls">
            <button class="start" onclick="startStudio()">Start Studio</button>
            <button class="stop" onclick="stopStudio()">Stop Studio</button>
            <button class="restart" onclick="restartStudio()">Restart Studio</button>
        </div>
        
        <div id="message" style="margin: 20px 0; padding: 10px; border-radius: 4px; display: none;"></div>
    </div>

    <script>
        async function updateStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                const statusEl = document.getElementById('status');
                statusEl.textContent = data.status;
                statusEl.className = 'status-' + data.status;
                
                document.getElementById('lastUpdated').textContent = new Date().toLocaleString();
            } catch (error) {
                console.error('Failed to update status:', error);
            }
        }
        
        function showMessage(text, type = 'info') {
            const msgEl = document.getElementById('message');
            msgEl.textContent = text;
            msgEl.style.display = 'block';
            msgEl.style.background = type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : '#17a2b8';
            setTimeout(() => msgEl.style.display = 'none', 5000);
        }
        
        async function startStudio() {
            showMessage('Starting studio...', 'info');
            try {
                const response = await fetch('/api/start', { method: 'POST' });
                const data = await response.json();
                showMessage(data.success ? 'Studio start initiated' : data.error, data.success ? 'success' : 'error');
                updateStatus();
            } catch (error) {
                showMessage('Failed to start studio', 'error');
            }
        }
        
        async function stopStudio() {
            if (!confirm('Are you sure you want to stop the studio?')) return;
            showMessage('Stopping studio...', 'info');
            try {
                const response = await fetch('/api/stop', { method: 'POST' });
                const data = await response.json();
                showMessage(data.success ? 'Studio stop initiated' : data.error, data.success ? 'success' : 'error');
                updateStatus();
            } catch (error) {
                showMessage('Failed to stop studio', 'error');
            }
        }
        
        async function restartStudio() {
            if (!confirm('Are you sure you want to restart the studio?')) return;
            showMessage('Restarting studio...', 'info');
            try {
                const response = await fetch('/api/restart', { method: 'POST' });
                const data = await response.json();
                showMessage(data.success ? 'Studio restart initiated' : data.error, data.success ? 'success' : 'error');
                updateStatus();
            } catch (error) {
                showMessage('Failed to restart studio', 'error');
            }
        }
        
        // Initialize
        updateStatus();
        setInterval(updateStatus, 30000);
    </script>
</body>
</html>
"""

# === Routes ===
@app.route("/")
def dashboard():
    return render_template_string(SIMPLE_DASHBOARD_HTML)

@app.route("/api/status")
def get_status():
    status, error = get_studio_status()
    return jsonify({
        'status': status,
        'error': error,
        'timestamp': datetime.now().isoformat()
    })

@app.route("/api/start", methods=['POST'])
def start_studio():
    try:
        log_event("manual_start_begin", "Manual start initiated via UI", "event")
        studio.start(Machine.CPU)
        log_event("manual_start_success", "Manual start completed", "event")
        return jsonify({"success": True, "message": "Studio start initiated"})
    except Exception as e:
        error_str = str(e)
        log_event("manual_start_error", f"Manual start failed: {error_str}", "error")
        return jsonify({"success": False, "error": error_str}), 500

@app.route("/api/stop", methods=['POST'])
def stop_studio():
    try:
        log_event("manual_stop_begin", "Manual stop initiated", "event")
        studio.stop()
        log_event("manual_stop_success", "Manual stop completed", "event")
        return jsonify({"success": True, "message": "Studio stop initiated"})
    except Exception as e:
        error_str = str(e)
        log_event("manual_stop_error", f"Manual stop failed: {error_str}", "error")
        return jsonify({"success": False, "error": error_str}), 500

@app.route("/api/restart", methods=['POST'])
def restart_studio():
    try:
        log_event("manual_restart_begin", "Manual restart initiated", "event")
        studio.stop()
        time.sleep(5)
        studio.start(Machine.CPU)
        log_event("manual_restart_success", "Manual restart completed", "event")
        return jsonify({"success": True, "message": "Studio restart initiated"})
    except Exception as e:
        error_str = str(e)
        log_event("manual_restart_error", f"Manual restart failed: {error_str}", "error")
        return jsonify({"success": False, "error": error_str}), 500

# === Monitor Logic ===
def monitor_loop():
    debug_print("Starting monitor loop")
    last_known_status = None

    while True:
        try:
            if not studio:
                debug_print("Studio object is None, cannot monitor.")
                time.sleep(60)
                continue

            status, error = get_studio_status()
            log_event("status_check", f"Current status: {status}", "heartbeat", {"status": status, "error": error})

            if status != last_known_status:
                log_event("state_change", f"Status changed from '{last_known_status}' to '{status}'", "event", {"from": last_known_status, "to": status})
                last_known_status = status
            
        except Exception as e:
            debug_print(f"CRITICAL: Exception in monitor loop: {e}\n{traceback.format_exc()}")
            log_event("monitor_error", f"Exception in monitor loop: {e}", "error")
        
        time.sleep(60)

if __name__ == "__main__":
    log_event("startup", "Enhanced Lightning AI Dashboard starting")
    monitor_thread = threading.Thread(target=monitor_loop)
    monitor_thread.daemon = True
    monitor_thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)