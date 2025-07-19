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
# Used to store async task results, like the manual start progress
app.config['ASYNC_TASKS'] = {}


# === Python Interpreter Session ===
class PythonInterpreter:
    def __init__(self):
        self.reset()

    def execute(self, code):
        """Executes Python code and returns the result."""
        try:
            # Try to evaluate as an expression first
            try:
                result = eval(code, self.globals, self.locals)
                # If the result is a complex object, just show its type
                if hasattr(result, '__dict__'):
                    output = f"<Object of type '{type(result).__name__}'>"
                else:
                    output = repr(result)
                return {"success": True, "result": output, "type": "expression"}
            except SyntaxError:
                # If it's not a valid expression, execute as a statement
                exec(code, self.globals, self.locals)
                return {"success": True, "result": "Statement executed successfully.", "type": "statement"}
        except Exception as e:
            return {"success": False, "error": str(e), "traceback": traceback.format_exc()}

    def reset(self):
        """Resets the interpreter's session."""
        self.globals = {}
        self.locals = {}
        # Initialize with some useful imports and the studio object
        exec("import os, sys, time, json, requests", self.globals)
        exec("from datetime import datetime, timedelta", self.globals)
        exec("from lightning_sdk import Studio, Machine", self.globals)
        # Safely re-initialize the studio object within the interpreter's context
        studio_name = os.getenv('STUDIO_NAME')
        teamspace = os.getenv('TEAMSPACE')
        username = os.getenv('USERNAME')
        if studio_name and teamspace and username:
            exec(f"studio = Studio('{studio_name}', teamspace='{teamspace}', user='{username}', create_ok=True)", self.globals)
        debug_print("Python interpreter session has been reset.")


# Global Python interpreter instance
python_interpreter = PythonInterpreter()

# === Enhanced Logging Function ===
def log_event(event_type, note="", type="event", metadata=None):
    debug_print(f"Logging event: {event_type} - {note}")
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
            debug_print(f"Log Error: {r.status_code} - {r.text}")
        else:
            debug_print("Event logged successfully")
    except Exception as e:
        debug_print(f"Log Exception: {e}")

# === Get Real Studio Status ===
def get_studio_status():
    """Get the actual studio status with error handling"""
    try:
        if not studio:
            return "error", "Studio not initialized"
        
        status = studio.status
        return str(status), None
    except Exception as e:
        return "error", str(e)

# === Configuration Debug ===
def get_debug_info():
    """Gathers all debug information into a dictionary."""
    info = {}
    info["STUDIO_NAME"] = os.getenv('STUDIO_NAME')
    info["TEAMSPACE"] = os.getenv('TEAMSPACE')
    info["USERNAME"] = os.getenv('USERNAME')
    info["SUPABASE_URL"] = os.getenv('SUPABASE_URL')
    info["SUPABASE_API_KEY"] = '***SET***' if os.getenv('SUPABASE_API_KEY') else 'NOT SET'
    
    status, error = get_studio_status()
    info["studio_status"] = status
    if error:
        info["studio_error"] = error
    
    return info

# === Enhanced Monitor Logic ===
def monitor_loop():
    debug_print("Starting monitor loop")
    running_since = None
    crash_count = 0
    consecutive_errors = 0
    last_status_check_log = datetime.now() - timedelta(minutes=5) # Log immediately on first run

    while True:
        try:
            if not studio:
                debug_print("Studio object is None, cannot monitor. Retrying in 60s.")
                time.sleep(60)
                continue

            now = datetime.now()
            status, error = get_studio_status()
            
            # Log status check every 5 minutes
            if (now - last_status_check_log).total_seconds() >= 300:
                log_event("status_check", f"Scheduled status check: {status}", "heartbeat", 
                         {"status": status, "error": error})
                last_status_check_log = now
            
            debug_print(f"Current status: {status}")

            if status == "running":
                consecutive_errors = 0
                if not running_since:
                    running_since = now
                    log_event("start", "Studio marked as running", "event", {"start_time": now.isoformat()})
                    debug_print("Studio started successfully")

                # Auto-restart after 3 hours
                elapsed = (now - running_since).total_seconds()
                if elapsed >= 3 * 60 * 60:
                    debug_print(f"Stopping after {elapsed/3600:.1f} hours for scheduled restart.")
                    log_event("pre_stop", f"Stopping after {elapsed/3600:.1f} hours", "event", {"session_duration": elapsed})
                    try:
                        studio.stop()
                        log_event("post_stop", "Studio stopped for 3hr cycle")
                        time.sleep(30)
                        log_event("pre_start", "Restarting studio after scheduled stop")
                        studio.start(Machine.CPU)
                        log_event("post_start", "Studio restarted after 3hr cycle")
                        running_since = datetime.now()
                    except Exception as cycle_error:
                        debug_print(f"Error during scheduled restart cycle: {cycle_error}")
                        log_event("cycle_error", f"Stop/start error: {cycle_error}")

            elif status == "stopped":
                consecutive_errors = 0
                if running_since: # This means it was running and then stopped unexpectedly
                    downtime = (now - running_since).total_seconds()
                    crash_count += 1
                    log_event("crash", f"Unexpected stop. Crash #{crash_count}", "event", 
                             {"crash_count": crash_count, "last_uptime_seconds": downtime})
                    debug_print(f"Studio stopped unexpectedly. Crash #{crash_count}")
                
                running_since = None # Reset running timer
                
                log_event("pre_start", f"Attempting restart after being stopped. Crash count: {crash_count}")
                try:
                    debug_print("Attempting to start machine...")
                    studio.start(Machine.CPU)
                    log_event("post_start", f"Studio restart attempt successful after crash #{crash_count}")
                    running_since = datetime.now() # Reset timer on successful start command
                except Exception as start_error:
                    debug_print(f"Failed to start machine: {start_error}")
                    log_event("start_error", f"Failed to start: {start_error}")
                
                time.sleep(60) # Wait a bit before the next check after a stop/restart cycle

            elif status in ["starting", "stopping", "restarting"]:
                debug_print(f"Studio is in a transient state: {status}...")
                log_event(status, f"Studio is in {status} state")
                consecutive_errors = 0
                running_since = None # Not considered "running" yet
                
            elif status == "error":
                consecutive_errors += 1
                debug_print(f"Studio status error: {error}. Consecutive errors: {consecutive_errors}")
                log_event("error", f"Studio status error: {error}", metadata={"consecutive_errors": consecutive_errors})
                running_since = None
                
            else: # Unknown status
                consecutive_errors += 1
                debug_print(f"Unknown studio state: {status}. Consecutive errors: {consecutive_errors}")
                log_event("unknown", f"Unknown studio state: {status}", metadata={"consecutive_errors": consecutive_errors})

        except Exception as e:
            consecutive_errors += 1
            debug_print(f"CRITICAL: Exception in monitor loop: {e}\n{traceback.format_exc()}")
            log_event("monitor_error", f"Exception in monitor loop: {e}", metadata={"traceback": traceback.format_exc()})
            
        finally:
            # Implement exponential backoff for consecutive errors
            if consecutive_errors > 0:
                sleep_time = min(60 * (2 ** (consecutive_errors - 1)), 600) # Max 10 min
                debug_print(f"Backing off for {sleep_time} seconds due to errors.")
                time.sleep(sleep_time)
            else:
                time.sleep(60)  # Standard 1-minute check

# === Flask Routes ===

@app.route("/")
def dashboard():
    return render_template_string(open("dashboard.html").read())

@app.route("/api/logs")
def get_logs_data():
    """API endpoint to fetch logs for the dashboard chart."""
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}"
    }
    logs = []
    try:
        # Fetch last 24 hours of logs, max 2000 entries
        since = (datetime.now() - timedelta(hours=24)).isoformat()
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?order=timestamp.asc&limit=2000&timestamp=gte.{since}",
            headers=headers,
            timeout=15
        )
        if r.status_code == 200:
            logs = r.json()
        else:
            debug_print(f"Failed to fetch logs for dashboard: {r.status_code} {r.text}")
    except Exception as e:
        debug_print(f"Exception fetching logs for dashboard: {e}")

    # Also get the current live status
    current_status, error = get_studio_status()
    
    return jsonify({
        "logs": logs,
        "live_status": {
            "status": current_status,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
    })


@app.route("/status")
def status_check():
    if not studio:
        return jsonify({"error": "Studio not initialized"}), 500
    
    status, error = get_studio_status()
    return jsonify({
        "status": status,
        "error": error,
        "timestamp": datetime.now().isoformat()
    })

@app.route("/start", methods=['POST'])
def manual_start():
    if not studio:
        return jsonify({"error": "Studio not initialized"}), 500
    
    current_status, _ = get_studio_status()
    if current_status == "running":
        return jsonify({"result": "already_running", "status": current_status})

    start_id = f"start_{int(time.time())}"
    
    def start_studio_async():
        """The actual start logic to run in a background thread."""
        log_event("manual_start_begin", f"Manual start initiated: {start_id}")
        try:
            result = studio.start(Machine.CPU)
            log_event("manual_start_success", f"Manual start completed: {start_id}", metadata={"result": str(result)})
            app.config['ASYNC_TASKS'][start_id] = {"status": "completed", "success": True, "result": str(result)}
        except Exception as e:
            error_str = str(e)
            log_event("manual_start_error", f"Manual start failed: {start_id} - {error_str}")
            app.config['ASYNC_TASKS'][start_id] = {"status": "completed", "success": False, "error": error_str}

    # Store the initial state of the task
    app.config['ASYNC_TASKS'][start_id] = {"status": "starting", "start_time": datetime.now().isoformat()}
    
    # Start the task in a background thread
    thread = threading.Thread(target=start_studio_async)
    thread.daemon = True
    thread.start()
    
    return jsonify({"result": "start_initiated", "start_id": start_id})

@app.route("/start/progress/<start_id>")
def start_progress(start_id):
    task = app.config['ASYNC_TASKS'].get(start_id)
    if not task:
        return jsonify({"error": "Start ID not found"}), 404
    
    if task['status'] == 'starting':
        start_time = datetime.fromisoformat(task['start_time'])
        elapsed = (datetime.now() - start_time).total_seconds()
        return jsonify({
            "status": "starting",
            "elapsed_seconds": elapsed,
            "message": f"Starting... ({elapsed:.0f}s elapsed)"
        })
    else: # 'completed'
        return jsonify(task)

@app.route("/terminal")
def terminal():
    return render_template_string(open("terminal.html").read())

@app.route('/terminal/python', methods=['POST'])
def execute_python():
    data = request.get_json()
    if not data or 'code' not in data:
        return jsonify({"success": False, "error": "No code provided."}), 400
    
    code = data['code']
    result = python_interpreter.execute(code)
    return jsonify(result)

@app.route('/terminal/reset', methods=['POST'])
def reset_interpreter():
    python_interpreter.reset()
    return jsonify({"success": True, "message": "Python interpreter session has been reset."})

@app.route("/logs")
def view_logs():
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}"
    }
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?order=timestamp.desc&limit=200", headers=headers)
        logs = r.json() if r.status_code == 200 else []
    except Exception as e:
        logs = [{"error": str(e)}]
    return render_template_string(open("logs.html").read(), logs=logs)

@app.route("/debug")
def debug_view():
    debug_info = get_debug_info()
    return render_template_string(open("debug.html").read(), debug_info=debug_info)


# === Background Thread for Monitor ===
def start_monitor():
    thread = threading.Thread(target=monitor_loop)
    thread.daemon = True
    thread.start()

# === Main Execution ===
if __name__ == "__main__":
    # Create necessary HTML files if they don't exist
    if not os.path.exists("dashboard.html"):
        with open("dashboard.html", "w") as f:
            f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lightning AI Studio Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        .status-dot {
            height: 12px;
            width: 12px;
            border-radius: 50%;
            display: inline-block;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 0, 0, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(0, 0, 0, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 0, 0, 0); }
        }
        .bg-green-500 { box-shadow: 0 0 8px #34d399; }
        .bg-red-500 { box-shadow: 0 0 8px #f87171; }
        .bg-yellow-500 { box-shadow: 0 0 8px #fbbf24; }
        .bg-gray-500 { box-shadow: 0 0 8px #9ca3af; }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen p-4 md:p-6">
    <div class="max-w-7xl mx-auto">
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-6">
            <div>
                <h1 class="text-3xl md:text-4xl font-bold">⚡ Lightning AI Studio Dashboard</h1>
                <p id="status-text" class="mt-2 text-lg text-gray-400">Current Status: <span class="font-bold">Loading...</span></p>
            </div>
            <div class="flex space-x-2 mt-4 md:mt-0">
                <a href="/debug" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-semibold">Debug</a>
                <a href="/terminal" class="bg-yellow-500 hover:bg-yellow-600 px-4 py-2 rounded-lg text-sm font-semibold">Terminal</a>
                <a href="/logs" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg text-sm font-semibold">Logs</a>
            </div>
        </div>

        <div class="bg-gray-800 p-4 rounded-lg shadow-lg mb-6">
            <h2 class="text-xl font-semibold mb-3">Controls</h2>
            <button id="manualStartBtn" class="bg-green-600 hover:bg-green-700 px-5 py-2 rounded-lg font-semibold transition-all duration-200 ease-in-out transform hover:scale-105">
                Manual Start
            </button>
        </div>

        <div class="bg-gray-800 p-4 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-3">Studio Uptime Timeline (Last 24 Hours)</h2>
            <div class="h-48">
                <canvas id="uptimeChart"></canvas>
            </div>
        </div>
    </div>

    <!-- Modal for Start Progress -->
    <div id="startModal" class="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center hidden z-50">
        <div class="bg-gray-800 p-8 rounded-lg shadow-2xl text-center max-w-sm w-full">
            <h2 id="modalTitle" class="text-2xl font-bold mb-4">Starting Studio...</h2>
            <p id="modalMessage" class="text-lg mb-6">Please wait while the machine boots up.</p>
            <div id="modalSpinner" class="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-400 mx-auto"></div>
            <div id="modalResult" class="hidden">
                 <p id="modalResultText" class="text-lg mb-6"></p>
                 <button onclick="closeModal()" class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg font-semibold">Close</button>
            </div>
        </div>
    </div>

    <script>
        const statusText = document.getElementById('status-text').querySelector('span');
        const chartCanvas = document.getElementById('uptimeChart');
        let uptimeChart;

        const STATUS_COLORS = {
            running: 'rgba(52, 211, 153, 0.7)',  // green-400
            stopped: 'rgba(248, 113, 113, 0.7)', // red-400
            starting: 'rgba(251, 191, 36, 0.7)', // yellow-400
            stopping: 'rgba(251, 146, 60, 0.7)', // orange-400
            restarting: 'rgba(251, 146, 60, 0.7)',
            error: 'rgba(239, 68, 68, 0.7)',     // red-500
            unknown: 'rgba(156, 163, 175, 0.7)', // gray-400
            crash: 'rgba(190, 24, 93, 0.7)', // fuchsia-800
            default: 'rgba(107, 114, 128, 0.5)' // gray-500
        };

        function getStatusFromEvents(event_type) {
            if (['start', 'post_start', 'running', 'status_check'].includes(event_type)) return 'running';
            if (['crash', 'post_stop', 'pre_stop'].includes(event_type)) return 'stopped';
            if (['starting', 'pre_start', 'manual_start_begin'].includes(event_type)) return 'starting';
            if (['stopping'].includes(event_type)) return 'stopping';
            if (['error', 'start_error', 'cycle_error'].includes(event_type)) return 'error';
            return 'unknown';
        }

        function createChart(logs) {
            const datasets = [];
            if (logs.length > 0) {
                let lastTimestamp = new Date(logs[0].timestamp);
                let lastStatus = getStatusFromEvents(logs[0].event_type);

                for (let i = 1; i < logs.length; i++) {
                    const log = logs[i];
                    const currentTimestamp = new Date(log.timestamp);
                    const currentStatus = getStatusFromEvents(log.event_type);

                    datasets.push({
                        label: lastStatus,
                        data: [{ x: [lastTimestamp, currentTimestamp], y: 'Status' }],
                        backgroundColor: STATUS_COLORS[lastStatus] || STATUS_COLORS.default
                    });
                    
                    lastTimestamp = currentTimestamp;
                    lastStatus = currentStatus;
                }
                // Add a final segment from the last log to now
                datasets.push({
                    label: lastStatus,
                    data: [{ x: [lastTimestamp, new Date()], y: 'Status' }],
                    backgroundColor: STATUS_COLORS[lastStatus] || STATUS_COLORS.default
                });
            }

            const config = {
                type: 'bar',
                data: { datasets },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const start = new Date(context.raw.x[0]).toLocaleString();
                                    const end = new Date(context.raw.x[1]).toLocaleString();
                                    return `${context.dataset.label}: ${start} to ${end}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            type: 'time',
                            time: { unit: 'hour' },
                            min: new Date(new Date().setDate(new Date().getDate() - 1)), // last 24 hours
                            max: new Date(),
                            stacked: true,
                            grid: { color: 'rgba(255, 255, 255, 0.1)' },
                            ticks: { color: 'white' }
                        },
                        y: {
                            stacked: true,
                            grid: { display: false },
                            ticks: { color: 'white' }
                        }
                    }
                }
            };
            if (uptimeChart) uptimeChart.destroy();
            uptimeChart = new Chart(chartCanvas, config);
        }

        function updateStatus(liveStatus) {
            const status = liveStatus.status;
            let dotClass = 'bg-gray-500';
            if (status === 'running') dotClass = 'bg-green-500';
            else if (status === 'stopped') dotClass = 'bg-red-500';
            else if (status === 'starting' || status === 'restarting' || status === 'stopping') dotClass = 'bg-yellow-500';
            
            statusText.innerHTML = `<span class="status-dot ${dotClass}" style="animation-play-state: ${status === 'running' ? 'running' : 'paused'}"></span> ${status}`;
        }

        async function fetchData() {
            try {
                const response = await fetch('/api/logs');
                const data = await response.json();
                createChart(data.logs);
                updateStatus(data.live_status);
            } catch (error) {
                console.error('Failed to fetch data:', error);
                statusText.textContent = 'Error loading status';
            }
        }
        
        // --- Modal Logic ---
        const modal = document.getElementById('startModal');
        const modalTitle = document.getElementById('modalTitle');
        const modalMessage = document.getElementById('modalMessage');
        const modalSpinner = document.getElementById('modalSpinner');
        const modalResult = document.getElementById('modalResult');
        const modalResultText = document.getElementById('modalResultText');
        let progressInterval;

        function showModal() { modal.classList.remove('hidden'); }
        function closeModal() { 
            modal.classList.add('hidden'); 
            clearInterval(progressInterval);
            // Reset modal state
            modalTitle.textContent = "Starting Studio...";
            modalMessage.textContent = "Please wait while the machine boots up.";
            modalSpinner.classList.remove('hidden');
            modalResult.classList.add('hidden');
        }

        async function checkProgress(startId) {
            const response = await fetch(`/start/progress/${startId}`);
            const data = await response.json();

            if (data.status === 'starting') {
                modalMessage.textContent = `Please wait... (${Math.round(data.elapsed_seconds)}s elapsed)`;
            } else if (data.status === 'completed') {
                clearInterval(progressInterval);
                modalSpinner.classList.add('hidden');
                modalResult.classList.remove('hidden');
                if (data.success) {
                    modalTitle.textContent = "✅ Success!";
                    modalResultText.textContent = "Studio started successfully.";
                } else {
                    modalTitle.textContent = "❌ Error!";
                    modalResultText.textContent = `Failed to start: ${data.error}`;
                }
                fetchData(); // Refresh dashboard data
            }
        }

        document.getElementById('manualStartBtn').addEventListener('click', async () => {
            showModal();
            const response = await fetch('/start', { method: 'POST' });
            const data = await response.json();
            
            if (data.start_id) {
                progressInterval = setInterval(() => checkProgress(data.start_id), 2000);
            } else if (data.result === 'already_running') {
                 modalTitle.textContent = "Already Running";
                 modalMessage.textContent = "The studio is already in a running state.";
                 modalSpinner.classList.add('hidden');
                 modalResult.classList.remove('hidden');
                 modalResultText.textContent = "";
            } else {
                modalTitle.textContent = "❌ Error!";
                modalMessage.textContent = data.error || "An unknown error occurred.";
                modalSpinner.classList.add('hidden');
                modalResult.classList.remove('hidden');
                modalResultText.textContent = "";
            }
        });

        fetchData();
        setInterval(fetchData, 60000); // Refresh every 60 seconds
    </script>
</body>
</html>
            """)
    if not os.path.exists("terminal.html"):
        with open("terminal.html", "w") as f:
            f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Lightning AI Python Terminal</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        #terminal { background: #1a1a1a; color: #00ff00; font-family: 'Courier New', monospace; padding: 20px; border-radius: 8px; height: 500px; overflow-y: auto; white-space: pre-wrap; word-wrap: break-word; }
        .command-input { background: #2a2a2a; color: #00ff00; border: 1px solid #444; font-family: 'Courier New', monospace; padding: 10px; width: 100%; border-radius: 4px; }
        .command-input:focus { outline: none; border-color: #00ff00; }
        .preset-btn { background: #333; color: #00ff00; border: 1px solid #555; padding: 5px 10px; margin: 2px; border-radius: 4px; cursor: pointer; font-family: 'Courier New', monospace; font-size: 12px; }
        .preset-btn:hover { background: #444; }
        .result-success { color: #00ff00; }
        .result-error { color: #ff6b6b; }
        .result-expression { color: #ffd93d; }
        .result-statement { color: #80aaff; }
        .prompt { color: #00ff00; }
        .error-trace { color: #ff6b6b; font-size: 0.8em; white-space: pre-wrap; }
    </style>
</head>
<body class="bg-gray-900 text-white p-4">
    <div class="max-w-6xl mx-auto">
        <h1 class="text-3xl mb-4 font-bold">🐍 Lightning AI Python Terminal</h1>
        <div class="mb-4">
            <a href="/" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded mr-2">Dashboard</a>
            <a href="/debug" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded mr-2">Debug</a>
            <a href="/logs" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded mr-2">Logs</a>
            <button onclick="resetInterpreter()" class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded">Reset Session</button>
        </div>
        <div class="mb-4">
            <h3 class="text-lg mb-2">Quick Commands:</h3>
            <div class="flex flex-wrap">
                <button class="preset-btn" onclick="runPreset('studio.status')">studio.status</button>
                <button class="preset-btn" onclick="runPreset('studio.start(Machine.CPU)')">studio.start()</button>
                <button class="preset-btn" onclick="runPreset('studio.stop()')">studio.stop()</button>
                <button class="preset-btn" onclick="runPreset('Studio.list()')">Studio.list()</button>
                <button class="preset-btn" onclick="runPreset('datetime.now()')">Current Time</button>
                <button class="preset-btn" onclick="runPreset('a = 5\\nb = 10\\nc = a + b\\nprint(f\\"a={a}, b={b}, c={c}\\")')">Variable Test</button>
            </div>
        </div>
        <div id="terminal"></div>
        <div class="mt-4 flex">
            <span class="prompt text-2xl mr-2">&gt;&gt;&gt;</span>
            <textarea id="commandInput" class="command-input flex-1" placeholder="Enter Python code..." onkeydown="handleKeyDown(event)"></textarea>
            <button onclick="runCommand()" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded ml-2">Run</button>
        </div>
    </div>
    <script>
        const terminal = document.getElementById('terminal');
        const commandInput = document.getElementById('commandInput');

        function appendToTerminal(htmlContent) {
            terminal.innerHTML += htmlContent;
            terminal.scrollTop = terminal.scrollHeight;
        }

        function initialMessage() {
            appendToTerminal(`
                <span class="result-success">Lightning AI Python Terminal Ready</span><br>
                <span class="result-statement">Python interpreter session started with persistent state.</span><br>
                <span class="result-statement">Available objects: studio, Machine, os, sys, time, datetime, json, requests</span><br>
                <span class="result-statement">Type Python commands below. Variables persist. Use Shift+Enter for new lines.</span><br>
                <span class="result-success">=====================================================</span><br>
            `);
        }

        function runPreset(command) {
            commandInput.value = command.replace(/\\n/g, '\\n');
            runCommand();
        }

        async function runCommand() {
            const command = commandInput.value.trim();
            if (!command) return;
            
            appendToTerminal(`<span class="prompt">&gt;&gt;&gt; </span><span class="result-success">${command.replace(/\\n/g, '<br>... ')}</span><br>`);
            commandInput.value = '';
            commandInput.style.height = 'auto';

            try {
                const response = await fetch('/terminal/python', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: command })
                });
                const data = await response.json();

                if (data.success) {
                    let className = 'result-success';
                    if (data.type === 'expression') className = 'result-expression';
                    if (data.type === 'statement') className = 'result-statement';
                    appendToTerminal(`<span class="${className}">${data.result}</span><br>`);
                } else {
                    appendToTerminal(`<span class="result-error">Error: ${data.error}</span><br>`);
                    if (data.traceback) {
                        appendToTerminal(`<pre class="error-trace">${data.traceback}</pre>`);
                    }
                }
            } catch (err) {
                appendToTerminal(`<span class="result-error">Fetch Error: ${err}</span><br>`);
            }
        }

        async function resetInterpreter() {
            if (!confirm('Are you sure you want to reset the Python session? All variables will be lost.')) return;
            try {
                const response = await fetch('/terminal/reset', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    terminal.innerHTML = '';
                    initialMessage();
                    appendToTerminal(`<span class="result-success">${data.message}</span><br>`);
                }
            } catch (err) {
                 appendToTerminal(`<span class="result-error">Error resetting session: ${err}</span><br>`);
            }
        }

        function handleKeyDown(event) {
            // Auto-resize textarea
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';

            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                runCommand();
            }
        }
        commandInput.addEventListener('keydown', handleKeyDown);

        initialMessage();
    </script>
</body>
</html>
            """)
    if not os.path.exists("logs.html"):
        with open("logs.html", "w") as f:
            f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Studio Logs</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-900 text-white p-6">
    <div class="max-w-7xl mx-auto">
        <h1 class="text-3xl font-bold mb-4">📜 Studio Logs</h1>
        <a href="/" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded mb-6 inline-block">Back to Dashboard</a>
        <div class="bg-gray-800 rounded-lg shadow-lg overflow-hidden">
            <table class="min-w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Timestamp</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Type</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Event</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Note</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-700">
                    {% for log in logs %}
                    <tr class="hover:bg-gray-700">
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">{{ log.timestamp }}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-400">{{ log.type }}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm font-semibold 
                            {% if 'error' in log.event_type or 'crash' in log.event_type %}text-red-400
                            {% elif 'start' in log.event_type %}text-green-400
                            {% elif 'stop' in log.event_type %}text-yellow-400
                            {% else %}text-blue-400{% endif %}">{{ log.event_type }}</td>
                        <td class="px-6 py-4 whitespace-normal text-sm text-gray-300">{{ log.note }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
            """)
    if not os.path.exists("debug.html"):
        with open("debug.html", "w") as f:
            f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Debug Info</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-900 text-white p-6">
    <div class="max-w-4xl mx-auto">
        <h1 class="text-3xl font-bold mb-4">🐞 Debug Information</h1>
        <a href="/" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded mb-6 inline-block">Back to Dashboard</a>
        <div class="bg-gray-800 rounded-lg shadow-lg p-6">
            <h2 class="text-xl font-semibold mb-4 border-b border-gray-700 pb-2">Live Status</h2>
            <p><strong>Studio Status:</strong> <span class="font-mono {{ 'text-green-400' if debug_info.studio_status == 'running' else 'text-red-400' }}">{{ debug_info.studio_status }}</span></p>
            {% if debug_info.studio_error %}
            <p><strong>Error:</strong> <span class="font-mono text-red-400">{{ debug_info.studio_error }}</span></p>
            {% endif %}
            
            <h2 class="text-xl font-semibold mb-4 mt-6 border-b border-gray-700 pb-2">Configuration</h2>
            <ul class="space-y-2">
                {% for key, value in debug_info.items() %}
                    {% if key not in ['studio_status', 'studio_error'] %}
                    <li><strong>{{ key }}:</strong> <span class="font-mono text-gray-300">{{ value }}</span></li>
                    {% endif %}
                {% endfor %}
            </ul>
        </div>
    </div>
</body>
</html>
            """)

    debug_print("=== Initializing Application ===")
    log_event("startup", "Monitor and UI server starting")
    start_monitor()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

