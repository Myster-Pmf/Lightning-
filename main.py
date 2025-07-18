import os
import threading
import time
import subprocess
import sys
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request
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
            debug_print(f"Current status: {str(status)}")
            now = datetime.now()

            if str(status) == "running":
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

            elif str(status) == "stopped":
                consecutive_errors = 0
                crash_count += 1
                debug_print(f"Studio stopped unexpectedly. Crash #{crash_count}")
                log_event("crash", f"Unexpected stop. Crash #{crash_count}")
                log_event("pre_start", f"Restarting after crash #{crash_count}")
                
                # Use subprocess to avoid SystemExit killing the main process
                import subprocess
                import sys
                
                try:
                    debug_print("Attempting to start machine using subprocess...")
                    # Create a simple Python script to start the studio
                    start_script = f"""
import sys
sys.path.insert(0, '/opt/venv/lib/python3.12/site-packages')
from lightning_sdk import Studio, Machine
import os

studio = Studio(
    "{os.getenv('STUDIO_NAME')}",
    teamspace="{os.getenv('TEAMSPACE')}",
    user="{os.getenv('USERNAME')}",
    create_ok=True
)

try:
    result = studio.start(Machine.CPU)
    print(f"SUCCESS: {{result}}")
    sys.exit(0)
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
"""
                    
                    with open('/tmp/start_studio.py', 'w') as f:
                        f.write(start_script)
                    
                    result = subprocess.run([sys.executable, '/tmp/start_studio.py'], 
                                          capture_output=True, text=True, timeout=60)
                    
                    if result.returncode == 0:
                        debug_print(f"Subprocess start successful: {result.stdout}")
                        log_event("post_start", f"Studio restarted after crash #{crash_count}")
                        running_since = datetime.now()
                    else:
                        debug_print(f"Subprocess start failed: {result.stderr}")
                        log_event("start_error", f"Subprocess start failed: {result.stderr}")
                        
                except subprocess.TimeoutExpired:
                    debug_print("Start operation timed out")
                    log_event("start_timeout", "Start operation timed out")
                except Exception as start_error:
                    debug_print(f"Failed to start machine: {start_error}")
                    log_event("start_error", f"Failed to start: {start_error}")
                    
                time.sleep(30)  # Wait longer before retrying

            elif str(status) == "starting":
                debug_print("Studio is starting...")
                log_event("starting", "Studio is in starting state")
                consecutive_errors = 0
                
            elif str(status) == "stopping":
                debug_print("Studio is stopping...")
                log_event("stopping", "Studio is in stopping state")
                consecutive_errors = 0
                
            else:
                debug_print(f"Unknown studio state: {str(status)}")
                log_event("unknown", f"Unknown studio state: {str(status)}")

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
            status = studio.status
            info["studio_status"] = str(status)  # Convert to string
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
        return jsonify({"status": str(status)})  # Convert to string
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === Web Terminal Route ===
@app.route("/terminal")
def terminal():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lightning AI Terminal</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
        <style>
            .terminal {
                background: #1a1a1a;
                color: #00ff00;
                font-family: 'Courier New', monospace;
                padding: 20px;
                border-radius: 8px;
                height: 500px;
                overflow-y: auto;
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            .command-input {
                background: #2a2a2a;
                color: #00ff00;
                border: 1px solid #444;
                font-family: 'Courier New', monospace;
                padding: 10px;
                width: 100%;
                border-radius: 4px;
            }
            .command-input:focus {
                outline: none;
                border-color: #00ff00;
            }
            .preset-btn {
                background: #333;
                color: #00ff00;
                border: 1px solid #555;
                padding: 5px 10px;
                margin: 2px;
                border-radius: 4px;
                cursor: pointer;
                font-family: 'Courier New', monospace;
                font-size: 12px;
            }
            .preset-btn:hover {
                background: #444;
            }
        </style>
    </head>
    <body class="bg-gray-900 text-white p-4">
        <div class="max-w-6xl mx-auto">
            <h1 class="text-3xl mb-4 font-bold">🖥️ Lightning AI Terminal</h1>
            
            <div class="mb-4">
                <a href="/" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded mr-2">Dashboard</a>
                <a href="/debug" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded mr-2">Debug</a>
                <a href="/logs" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded">Logs</a>
            </div>

            <div class="mb-4">
                <h3 class="text-lg mb-2">Quick Commands:</h3>
                <div class="flex flex-wrap">
                    <button class="preset-btn" onclick="runPreset('lightning --help')">lightning --help</button>
                    <button class="preset-btn" onclick="runPreset('lightning login --help')">lightning login --help</button>
                    <button class="preset-btn" onclick="runPreset('lightning list studios')">lightning list studios</button>
                    <button class="preset-btn" onclick="runPreset('lightning status')">lightning status</button>
                    <button class="preset-btn" onclick="runPreset('whoami')">whoami</button>
                    <button class="preset-btn" onclick="runPreset('env | grep LIGHTNING')">env | grep LIGHTNING</button>
                    <button class="preset-btn" onclick="runPreset('python -c \"from lightning_sdk import Studio; print(Studio.list())\"')">List Studios (Python)</button>
                    <button class="preset-btn" onclick="runPreset('python -c \"from lightning_sdk import Studio, Machine; s = Studio(\'my-studio\', teamspace=\'Vision-model\', user=\'oyonhossainp\'); print(s.status)\"')">Check Studio Status</button>
                    <button class="preset-btn" onclick="runPreset('python -c \"from lightning_sdk import Studio, Machine; s = Studio(\'my-studio\', teamspace=\'Vision-model\', user=\'oyonhossainp\'); print(s.start(Machine.CPU))\"')">Start Studio</button>
                </div>
            </div>

            <div class="terminal" id="terminal">
                Lightning AI Terminal Ready
                Type commands below or use the preset buttons above.
                
                Current Environment:
                - STUDIO_NAME: my-studio
                - TEAMSPACE: Vision-model  
                - USERNAME: oyonhossainp
                
                =====================================================
                
            </div>

            <div class="mt-4 flex">
                <input type="text" id="commandInput" class="command-input flex-1" placeholder="Enter command..." onkeypress="handleKeyPress(event)">
                <button onclick="runCommand()" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded ml-2">Run</button>
                <button onclick="clearTerminal()" class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded ml-2">Clear</button>
            </div>

            <div class="mt-4 text-sm text-gray-400">
                <p><strong>Tips:</strong></p>
                <ul class="list-disc list-inside">
                    <li>Use 'lightning login' if you get authentication errors</li>
                    <li>Try 'lightning list studios' to see available studios</li>
                    <li>Python commands can access the Lightning SDK directly</li>
                    <li>Check environment variables with 'env | grep LIGHTNING'</li>
                </ul>
            </div>
        </div>

        <script>
            function appendToTerminal(text) {
                const terminal = document.getElementById('terminal');
                terminal.textContent += text + '\\n';
                terminal.scrollTop = terminal.scrollHeight;
            }

            function runPreset(command) {
                document.getElementById('commandInput').value = command;
                runCommand();
            }

            function runCommand() {
                const input = document.getElementById('commandInput');
                const command = input.value.trim();
                
                if (!command) return;
                
                appendToTerminal('$ ' + command);
                input.value = '';
                
                // Show loading
                appendToTerminal('Executing...');
                
                fetch('/terminal/exec', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ command: command })
                })
                .then(response => response.json())
                .then(data => {
                    // Remove the "Executing..." line
                    const terminal = document.getElementById('terminal');
                    const lines = terminal.textContent.split('\\n');
                    lines.pop(); // Remove empty line
                    lines.pop(); // Remove "Executing..."
                    terminal.textContent = lines.join('\\n') + '\\n';
                    
                    if (data.success) {
                        if (data.stdout) {
                            appendToTerminal(data.stdout);
                        }
                        if (data.stderr) {
                            appendToTerminal('STDERR: ' + data.stderr);
                        }
                        appendToTerminal('Exit code: ' + data.returncode);
                    } else {
                        appendToTerminal('ERROR: ' + data.error);
                    }
                    appendToTerminal('');
                })
                .catch(error => {
                    appendToTerminal('Network error: ' + error);
                    appendToTerminal('');
                });
            }

            function handleKeyPress(event) {
                if (event.key === 'Enter') {
                    runCommand();
                }
            }

            function clearTerminal() {
                document.getElementById('terminal').textContent = 'Terminal cleared.\\n\\n';
            }

            // Focus on input when page loads
            document.addEventListener('DOMContentLoaded', function() {
                document.getElementById('commandInput').focus();
            });
        </script>
    </body>
    </html>
    """)

# === Terminal Command Execution ===
@app.route("/terminal/exec", methods=["POST"])
def terminal_exec():
    try:
        data = request.get_json()
        command = data.get("command", "").strip()
        
        if not command:
            return jsonify({"success": False, "error": "No command provided"})
        
        # Security check - basic command filtering
        dangerous_commands = ["rm -rf", "sudo", "passwd", "shutdown", "reboot", "halt", "init"]
        if any(dangerous in command.lower() for dangerous in dangerous_commands):
            return jsonify({"success": False, "error": "Command not allowed for security reasons"})
        
        # Set up environment
        env = os.environ.copy()
        env.update({
            "STUDIO_NAME": os.getenv("STUDIO_NAME", "my-studio"),
            "TEAMSPACE": os.getenv("TEAMSPACE", "Vision-model"),
            "USERNAME": os.getenv("USERNAME", "oyonhossainp"),
            "PYTHONPATH": "/opt/venv/lib/python3.12/site-packages",
        })
        
        # Execute command
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                cwd="/app"
            )
            
            return jsonify({
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            })
            
        except subprocess.TimeoutExpired:
            return jsonify({"success": False, "error": "Command timed out (30s limit)"})
            
        except Exception as e:
            return jsonify({"success": False, "error": f"Execution error: {str(e)}"})
            
    except Exception as e:
        return jsonify({"success": False, "error": f"Request error: {str(e)}"})

# === Test Authentication Route ===
@app.route("/test-auth")
def test_auth():
    try:
        from lightning_sdk import Studio
        
        # Just try to list studios
        studios = Studio.list()
        return jsonify({"success": True, "studios": [str(s) for s in studios]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
@app.route("/start")
def manual_start():
    if not studio:
        return jsonify({"error": "Studio not initialized"}), 500
    
    try:
        # Use a separate thread to avoid SystemExit killing the worker
        import threading
        import queue
        
        result_queue = queue.Queue()
        
        def start_studio():
            try:
                result = studio.start(Machine.CPU)
                result_queue.put(("success", result))
            except SystemExit as e:
                result_queue.put(("system_exit", f"SystemExit: {e}"))
            except Exception as e:
                result_queue.put(("error", str(e)))
        
        thread = threading.Thread(target=start_studio)
        thread.start()
        thread.join(timeout=30)  # 30 second timeout
        
        if thread.is_alive():
            return jsonify({"error": "Start operation timed out"}), 408
        
        if result_queue.empty():
            return jsonify({"error": "No result from start operation"}), 500
        
        result_type, result_data = result_queue.get()
        
        if result_type == "success":
            log_event("manual_start", "Manual start triggered successfully")
            return jsonify({"result": "started", "details": str(result_data)})
        elif result_type == "system_exit":
            log_event("manual_start_system_exit", f"Manual start system exit: {result_data}")
            return jsonify({"error": f"Start failed with system exit: {result_data}"}), 500
        else:
            log_event("manual_start_error", f"Manual start failed: {result_data}")
            return jsonify({"error": result_data}), 500
            
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
            <a href="/terminal" class="bg-yellow-600 hover:bg-yellow-700 px-4 py-2 rounded mr-2">Terminal</a>
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
