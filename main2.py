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


# === Python Interpreter Session ===
class PythonInterpreter:
    def __init__(self):
        self.reset()

    def execute(self, code):
        try:
            try:
                result = eval(code, self.globals, self.locals)
                output = repr(result)
                return {"success": True, "result": output, "type": "expression"}
            except SyntaxError:
                exec(code, self.globals, self.locals)
                return {"success": True, "result": "Statement executed successfully.", "type": "statement"}
        except Exception as e:
            return {"success": False, "error": str(e), "traceback": traceback.format_exc()}

    def reset(self):
        self.globals = {}
        self.locals = {}
        exec("import os, sys, time, json, requests", self.globals)
        exec("from datetime import datetime, timedelta", self.globals)
        exec("from lightning_sdk import Studio, Machine", self.globals)
        studio_name = os.getenv('STUDIO_NAME')
        teamspace = os.getenv('TEAMSPACE')
        username = os.getenv('USERNAME')
        if studio_name and teamspace and username:
            exec(f"studio = Studio('{studio_name}', teamspace='{teamspace}', user='{username}', create_ok=True)", self.globals)
        debug_print("Python interpreter session has been reset.")

python_interpreter = PythonInterpreter()

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

# === Supabase Health Check (with Write Test) ===
def check_supabase_health():
    start_time = time.time()
    # FIX: Ask Supabase to return the created row so we can parse it as JSON
    headers = {
        "apikey": SUPABASE_API_KEY, 
        "Authorization": f"Bearer {SUPABASE_API_KEY}", 
        "Content-Type": "application/json",
        "Prefer": "return=representation" 
    }
    test_payload = {"event_type": "health_check", "note": "testing write access", "type": "health_check"}
    
    try:
        # 1. Test Write
        r_write = requests.post(f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}", json=test_payload, headers=headers, timeout=10)
        
        if r_write.status_code != 201:
             return {"status": "error", "message": f"Write test failed. Status: {r_write.status_code} - {r_write.text}. Check RLS policies."}

        # FIX: Now that we expect a JSON response, this will work.
        try:
            write_response_json = r_write.json()
            if not write_response_json:
                raise ValueError("Response is empty.")
        except (requests.exceptions.JSONDecodeError, ValueError):
            return {"status": "error", "message": f"Write test returned success status ({r_write.status_code}) but response was not valid JSON. Check URL/proxy settings."}

        # 2. Test Delete (cleanup)
        inserted_id = write_response_json[0]['id']
        delete_headers = {"apikey": SUPABASE_API_KEY, "Authorization": f"Bearer {SUPABASE_API_KEY}"}
        r_delete = requests.delete(f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?id=eq.{inserted_id}", headers=delete_headers, timeout=10)
        if r_delete.status_code != 204:
             return {"status": "warning", "message": f"Write test passed, but failed to delete test record (ID: {inserted_id}). Please delete it manually."}

        latency = (time.time() - start_time) * 1000
        return {"status": "ok", "message": "Supabase connection and write/delete access successful.", "latency_ms": round(latency)}

    except Exception as e:
        return {"status": "error", "message": f"Exception during Supabase health check: {e}"}

# === Configuration & Debug Info ===
def get_debug_info():
    info = {
        "STUDIO_NAME": os.getenv('STUDIO_NAME'),
        "TEAMSPACE": os.getenv('TEAMSPACE'),
        "USERNAME": os.getenv('USERNAME'),
        "SUPABASE_URL": os.getenv('SUPABASE_URL'),
        "SUPABASE_API_KEY": '***SET***' if os.getenv('SUPABASE_API_KEY') else 'NOT SET'
    }
    status, error = get_studio_status()
    info["studio_status"] = status
    if error: info["studio_error"] = error
    info["supabase_health"] = check_supabase_health()
    return info

# === Monitor Logic (MANUAL CONTROL ONLY) ===
def monitor_loop():
    debug_print("Starting monitor loop (Manual Control Mode)")
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

# === HTML Templates (Self-contained) ===
DASHBOARD_HTML = """
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
        .status-dot { height: 12px; width: 12px; border-radius: 50%; display: inline-block; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 0, 0, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(0, 0, 0, 0); } }
        .bg-green-500 { box-shadow: 0 0 8px #34d399; } .bg-red-500 { box-shadow: 0 0 8px #f87171; } .bg-yellow-500 { box-shadow: 0 0 8px #fbbf24; } .bg-gray-500 { box-shadow: 0 0 8px #9ca3af; }
        .time-range-btn.active { background-color: #4f46e5; color: white; }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen p-4 md:p-6">
    <div class="max-w-7xl mx-auto">
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-6">
            <div>
                <h1 class="text-3xl md:text-4xl font-bold">âš¡ Lightning AI Studio Dashboard</h1>
                <p id="status-text" class="mt-2 text-lg text-gray-400">Current Status: <span class="font-bold">Loading...</span></p>
            </div>
            <div class="flex space-x-2 mt-4 md:mt-0">
                <a href="/debug" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-semibold">Debug</a>
                <a href="/terminal" class="bg-yellow-500 hover:bg-yellow-600 px-4 py-2 rounded-lg text-sm font-semibold">Terminal</a>
                <a href="/logs" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg text-sm font-semibold">Logs</a>
            </div>
        </div>

        <div class="bg-gray-800 p-4 rounded-lg shadow-lg mb-6 flex justify-between items-center">
            <div class="flex space-x-4">
                <button id="manualStartBtn" class="bg-green-600 hover:bg-green-700 px-5 py-2 rounded-lg font-semibold transition-transform transform hover:scale-105">Manual Start</button>
                <button id="manualStopBtn" class="bg-red-600 hover:bg-red-700 px-5 py-2 rounded-lg font-semibold transition-transform transform hover:scale-105">Manual Stop</button>
            </div>
            <div class="flex space-x-1 bg-gray-700 p-1 rounded-lg">
                <button id="1h-btn" class="time-range-btn px-3 py-1 rounded-md text-sm font-medium" onclick="setTimeRange('1h')">1 Hour</button>
                <button id="24h-btn" class="time-range-btn px-3 py-1 rounded-md text-sm font-medium" onclick="setTimeRange('24h')">24 Hours</button>
            </div>
        </div>

        <div class="bg-gray-800 p-4 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-3">Studio Activity Timeline</h2>
            <div class="h-64"><canvas id="uptimeChart"></canvas></div>
        </div>
    </div>

    <!-- Modal -->
    <div id="modal" class="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center hidden z-50">
        <div class="bg-gray-800 p-8 rounded-lg shadow-2xl text-center max-w-sm w-full">
            <h2 id="modalTitle" class="text-2xl font-bold mb-4"></h2>
            <p id="modalMessage" class="text-lg mb-6"></p>
            <div id="modalSpinner" class="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-400 mx-auto hidden"></div>
            <div id="modalActions"></div>
        </div>
    </div>

    <script>
        let currentRange = '1h';
        const statusText = document.getElementById('status-text').querySelector('span');
        const chartCanvas = document.getElementById('uptimeChart');
        let uptimeChart;

        const STATUS_MAP = {
            running: { color: 'rgba(52, 211, 153, 0.8)', label: 'Running' },
            stopped: { color: 'rgba(239, 68, 68, 0.8)', label: 'Stopped' },
            starting: { color: 'rgba(251, 191, 36, 0.8)', label: 'Starting' },
            stopping: { color: 'rgba(249, 115, 22, 0.8)', label: 'Stopping' },
            restarting: { color: 'rgba(251, 146, 60, 0.8)', label: 'Restarting' },
            error: { color: 'rgba(190, 24, 93, 0.8)', label: 'Error' },
            unknown: { color: 'rgba(107, 114, 128, 0.8)', label: 'Unknown' }
        };

        function getStatusFromLog(log) {
            const type = log.event_type;
            if (type.includes('running') || type === 'start' || type === 'post_start' || (type === 'status_check' && log.metadata && log.metadata.status === 'running')) return 'running';
            if (type.includes('stopped') || type.includes('stop') || (type === 'status_check' && log.metadata && log.metadata.status === 'stopped')) return 'stopped';
            if (type.includes('starting') || type.includes('start_begin') || (type === 'status_check' && log.metadata && log.metadata.status === 'starting')) return 'starting';
            if (type.includes('stopping') || (type === 'status_check' && log.metadata && log.metadata.status === 'stopping')) return 'stopping';
            if (type.includes('restarting') || (type === 'status_check' && log.metadata && log.metadata.status === 'restarting')) return 'restarting';
            if (type.includes('error') || (type === 'status_check' && log.metadata && log.metadata.status === 'error')) return 'error';
            return 'unknown';
        }
        
        function formatDuration(ms) {
            if (ms < 1000) return `${Math.round(ms)}ms`;
            const s = ms / 1000;
            if (s < 60) return `${s.toFixed(1)}s`;
            const m = s / 60;
            if (m < 60) return `${m.toFixed(1)}m`;
            const h = m / 60;
            return `${h.toFixed(1)}h`;
        }

        function createChart(logs, range) {
            const datasets = [];
            if (logs.length > 0) {
                for (let i = 0; i < logs.length - 1; i++) {
                    const currentLog = logs[i];
                    const nextLog = logs[i+1];
                    const status = getStatusFromLog(currentLog);
                    datasets.push({
                        label: STATUS_MAP[status]?.label || 'Unknown',
                        data: [{ x: [new Date(currentLog.timestamp), new Date(nextLog.timestamp)], y: 'Activity' }],
                        backgroundColor: STATUS_MAP[status]?.color || STATUS_MAP.unknown.color
                    });
                }
                const lastLog = logs[logs.length - 1];
                const lastStatus = getStatusFromLog(lastLog);
                datasets.push({
                    label: STATUS_MAP[lastStatus]?.label || 'Unknown',
                    data: [{ x: [new Date(lastLog.timestamp), new Date()], y: 'Activity' }],
                    backgroundColor: STATUS_MAP[lastStatus]?.color || STATUS_MAP.unknown.color
                });
            }

            const timeConfig = {
                '1h': { unit: 'minute', min: new Date(new Date().getTime() - 60 * 60 * 1000) },
                '24h': { unit: 'hour', min: new Date(new Date().getTime() - 24 * 60 * 60 * 1000) }
            };

            const config = {
                type: 'bar',
                data: { datasets },
                options: {
                    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: {
                            label: (ctx) => `${ctx.dataset.label}: ${formatDuration(ctx.raw.x[1] - ctx.raw.x[0])}`,
                            title: (ctx) => `${new Date(ctx[0].raw.x[0]).toLocaleString()} - ${new Date(ctx[0].raw.x[1]).toLocaleString()}`
                        }}
                    },
                    scales: {
                        x: { type: 'time', time: { unit: timeConfig[range].unit }, min: timeConfig[range].min, max: new Date(), stacked: true, grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: 'white' } },
                        y: { stacked: true, grid: { display: false }, ticks: { color: 'white' } }
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
            else if (['starting', 'stopping', 'restarting'].includes(status)) dotClass = 'bg-yellow-500';
            statusText.innerHTML = `<span class="status-dot ${dotClass}" style="animation-play-state: ${status === 'running' ? 'running' : 'paused'}"></span> ${status}`;
        }

        async function fetchData(range) {
            try {
                const response = await fetch(`/api/logs?range=${range}`);
                const data = await response.json();
                createChart(data.logs, range);
                updateStatus(data.live_status);
            } catch (error) {
                console.error('Failed to fetch data:', error);
                statusText.textContent = 'Error loading status';
            }
        }
        
        function setTimeRange(range) {
            currentRange = range;
            document.getElementById('1h-btn').classList.toggle('active', range === '1h');
            document.getElementById('24h-btn').classList.toggle('active', range === '24h');
            fetchData(range);
        }

        const modal = document.getElementById('modal'), modalTitle = document.getElementById('modalTitle'), modalMessage = document.getElementById('modalMessage'), modalSpinner = document.getElementById('modalSpinner'), modalActions = document.getElementById('modalActions');
        let progressInterval;

        function showModal(title, message, actions = [], showSpinner = false) {
            modalTitle.textContent = title;
            modalMessage.textContent = message;
            modalSpinner.style.display = showSpinner ? 'block' : 'none';
            modalActions.innerHTML = '';
            actions.forEach(action => {
                const button = document.createElement('button');
                button.textContent = action.text;
                button.className = action.class;
                button.onclick = action.onclick;
                modalActions.appendChild(button);
            });
            modal.classList.remove('hidden');
        }
        function closeModal() { modal.classList.add('hidden'); clearInterval(progressInterval); }

        async function checkProgress(startId) {
            const response = await fetch(`/start/progress/${startId}`);
            const data = await response.json();
            if (data.status === 'starting') {
                modalMessage.textContent = `Please wait... (${Math.round(data.elapsed_seconds)}s elapsed)`;
            } else if (data.status === 'completed') {
                clearInterval(progressInterval);
                const actions = [{ text: 'Close', class: 'bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg font-semibold', onclick: closeModal }];
                if (data.success) {
                    showModal("âœ… Success!", "Studio start process completed.", actions);
                } else {
                    showModal("âŒ Error!", `Failed to start: ${data.error}`, actions);
                }
                fetchData(currentRange);
            }
        }

        document.getElementById('manualStartBtn').addEventListener('click', async () => {
            showModal("Starting Studio...", "Sending start command...", [], true);
            const response = await fetch('/start', { method: 'POST' });
            const data = await response.json();
            if (data.start_id) {
                progressInterval = setInterval(() => checkProgress(data.start_id), 3000);
            } else {
                const actions = [{ text: 'Close', class: 'bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg font-semibold', onclick: closeModal }];
                showModal("âŒ Error!", data.error || "An unknown error occurred.", actions);
            }
        });

        document.getElementById('manualStopBtn').addEventListener('click', () => {
            const actions = [
                { text: 'Cancel', class: 'bg-gray-600 hover:bg-gray-700 px-6 py-2 rounded-lg font-semibold mr-4', onclick: closeModal },
                { text: 'Yes, Stop It', class: 'bg-red-600 hover:bg-red-700 px-6 py-2 rounded-lg font-semibold', onclick: async () => {
                    showModal("Stopping Studio...", "Sending stop command...", [], true);
                    const response = await fetch('/stop', { method: 'POST' });
                    const data = await response.json();
                    const closeAction = [{ text: 'Close', class: 'bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded-lg font-semibold', onclick: closeModal }];
                    if(data.success) {
                        showModal("âœ… Command Sent", "Stop command sent successfully. The dashboard will update.", closeAction);
                    } else {
                        showModal("âŒ Error", `Failed to stop: ${data.error}`, closeAction);
                    }
                    fetchData(currentRange);
                }}
            ];
            showModal("Confirm Stop", "Are you sure you want to stop the studio?", actions);
        });

        setTimeRange('1h'); // Default view
        setInterval(() => fetchData(currentRange), 300000);
    </script>
</body>
</html>
"""
TERMINAL_HTML = """
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
        .result-success { color: #00ff00; } .result-error { color: #ff6b6b; } .result-expression { color: #ffd93d; } .result-statement { color: #80aaff; } .prompt { color: #00ff00; } .error-trace { color: #ff6b6b; font-size: 0.8em; white-space: pre-wrap; }
    </style>
</head>
<body class="bg-gray-900 text-white p-4">
    <div class="max-w-6xl mx-auto">
        <h1 class="text-3xl mb-4 font-bold">ðŸ Lightning AI Python Terminal</h1>
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
        const terminal = document.getElementById('terminal'), commandInput = document.getElementById('commandInput');
        function appendToTerminal(htmlContent) { terminal.innerHTML += htmlContent; terminal.scrollTop = terminal.scrollHeight; }
        function initialMessage() { appendToTerminal(`<span class="result-success">Lightning AI Python Terminal Ready</span><br><span class="result-statement">Python interpreter session started with persistent state.</span><br><span class="result-statement">Available objects: studio, Machine, os, sys, time, datetime, json, requests</span><br><span class="result-statement">Type Python commands below. Variables persist. Use Shift+Enter for new lines.</span><br><span class="result-success">=====================================================</span><br>`); }
        function runPreset(command) { commandInput.value = command.replace(/\\\\n/g, '\\n'); runCommand(); }
        async function runCommand() {
            const command = commandInput.value.trim(); if (!command) return;
            appendToTerminal(`<span class="prompt">&gt;&gt;&gt; </span><span class="result-success">${command.replace(/\\n/g, '<br>... ')}</span><br>`);
            commandInput.value = ''; commandInput.style.height = 'auto';
            try {
                const response = await fetch('/terminal/python', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: command }) });
                const data = await response.json();
                if (data.success) {
                    let className = data.type === 'expression' ? 'result-expression' : 'result-statement';
                    appendToTerminal(`<span class="${className}">${data.result}</span><br>`);
                } else {
                    appendToTerminal(`<span class="result-error">Error: ${data.error}</span><br>`);
                    if (data.traceback) appendToTerminal(`<pre class="error-trace">${data.traceback}</pre>`);
                }
            } catch (err) { appendToTerminal(`<span class="result-error">Fetch Error: ${err}</span><br>`); }
        }
        async function resetInterpreter() {
            if (!confirm('Are you sure you want to reset the Python session? All variables will be lost.')) return;
            try {
                const response = await fetch('/terminal/reset', { method: 'POST' });
                const data = await response.json();
                if (data.success) { terminal.innerHTML = ''; initialMessage(); appendToTerminal(`<span class="result-success">${data.message}</span><br>`); }
            } catch (err) { appendToTerminal(`<span class="result-error">Error resetting session: ${err}</span><br>`); }
        }
        function handleKeyDown(event) { this.style.height = 'auto'; this.style.height = (this.scrollHeight) + 'px'; if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); runCommand(); } }
        commandInput.addEventListener('keydown', handleKeyDown);
        initialMessage();
    </script>
</body>
</html>
"""
LOGS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Studio Logs</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-900 text-white p-6">
    <div class="max-w-7xl mx-auto">
        <h1 class="text-3xl font-bold mb-4">ðŸ“œ Studio Logs</h1>
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
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">{{ log.timestamp.replace('T', ' ').split('.')[0] }}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-400">{{ log.type }}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm font-semibold 
                            {% if 'error' in log.event_type or 'crash' in log.event_type %}text-red-400
                            {% elif 'start' in log.event_type %}text-green-400
                            {% elif 'stop' in log.event_type %}text-yellow-400
                            {% elif 'running' in log.event_type %}text-blue-400
                            {% else %}text-gray-400{% endif %}">{{ log.event_type }}</td>
                        <td class="px-6 py-4 whitespace-normal text-sm text-gray-300">{{ log.note }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
DEBUG_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Debug Info</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-900 text-white p-6">
    <div class="max-w-4xl mx-auto">
        <h1 class="text-3xl font-bold mb-4">ðŸž Debug Information</h1>
        <a href="/" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded mb-6 inline-block">Back to Dashboard</a>
        <div class="bg-gray-800 rounded-lg shadow-lg p-6">
            <h2 class="text-xl font-semibold mb-4 border-b border-gray-700 pb-2">Live Status</h2>
            <p><strong>Studio Status:</strong> <span class="font-mono {{ 'text-green-400' if debug_info.studio_status == 'running' else 'text-red-400' }}">{{ debug_info.studio_status }}</span></p>
            {% if debug_info.studio_error %}<p><strong>Error:</strong> <span class="font-mono text-red-400">{{ debug_info.studio_error }}</span></p>{% endif %}
            
            <h2 class="text-xl font-semibold mb-4 mt-6 border-b border-gray-700 pb-2">Supabase Health Check</h2>
            {% set health = debug_info.supabase_health %}
            <p><strong>Status:</strong> <span class="font-mono {{ 'text-green-400' if health.status == 'ok' else 'text-red-400' }}">{{ health.status }}</span></p>
            <p><strong>Message:</strong> <span class="font-mono text-gray-300">{{ health.message }}</span></p>
            {% if health.latency_ms %}<p><strong>Latency:</strong> <span class="font-mono text-gray-300">{{ health.latency_ms }} ms</span></p>{% endif %}

            <h2 class="text-xl font-semibold mb-4 mt-6 border-b border-gray-700 pb-2">Configuration</h2>
            <ul class="space-y-2">
                {% for key, value in debug_info.items() %}
                    {% if key not in ['studio_status', 'studio_error', 'supabase_health'] %}
                    <li><strong>{{ key }}:</strong> <span class="font-mono text-gray-300">{{ value }}</span></li>
                    {% endif %}
                {% endfor %}
            </ul>
        </div>
    </div>
</body>
</html>
"""

# === Flask Routes ===
@app.route("/")
def dashboard(): return render_template_string(DASHBOARD_HTML)

@app.route("/api/logs")
def get_logs_data():
    range_arg = request.args.get('range', '1h') # Default to 1 hour
    hours = 1 if range_arg == '1h' else 24
    
    headers = {"apikey": SUPABASE_API_KEY, "Authorization": f"Bearer {SUPABASE_API_KEY}"}
    logs = []
    try:
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?order=timestamp.asc&limit=2000&timestamp=gte.{since}", headers=headers, timeout=15)
        if r.status_code == 200:
            logs = r.json()
            for log in logs:
                if isinstance(log.get('metadata'), str):
                    try: log['metadata'] = json.loads(log['metadata'])
                    except: log['metadata'] = {}
        else:
            debug_print(f"Failed to fetch logs for dashboard: {r.status_code} {r.text}")
    except Exception as e:
        debug_print(f"Exception fetching logs for dashboard: {e}")
    current_status, error = get_studio_status()
    return jsonify({"logs": logs, "live_status": {"status": current_status, "error": error, "timestamp": datetime.now().isoformat()}})

@app.route("/start", methods=['POST'])
def manual_start():
    start_id = f"start_{int(time.time())}"
    def start_async():
        log_event("manual_start_begin", f"Manual start initiated via UI: {start_id}", "event")
        try:
            studio.start(Machine.CPU)
            app.config['ASYNC_TASKS'][start_id] = {"status": "completed", "success": True}
        except Exception as e:
            error_str = str(e)
            log_event("manual_start_error", f"Manual start failed for {start_id}: {error_str}", "error")
            app.config['ASYNC_TASKS'][start_id] = {"status": "completed", "success": False, "error": error_str}
    
    app.config['ASYNC_TASKS'][start_id] = {"status": "starting", "start_time": datetime.now().isoformat()}
    thread = threading.Thread(target=start_async); thread.daemon = True; thread.start()
    return jsonify({"result": "start_initiated", "start_id": start_id})

@app.route("/start/progress/<start_id>")
def start_progress(start_id):
    task = app.config['ASYNC_TASKS'].get(start_id)
    if not task: return jsonify({"error": "Start ID not found"}), 404
    if task['status'] == 'starting':
        elapsed = (datetime.now() - datetime.fromisoformat(task['start_time'])).total_seconds()
        return jsonify({"status": "starting", "elapsed_seconds": elapsed})
    else: return jsonify(task)

@app.route("/stop", methods=['POST'])
def manual_stop():
    try:
        log_event("manual_stop_begin", "Manual stop initiated", "event")
        studio.stop()
        return jsonify({"success": True, "message": "Stop command sent."})
    except Exception as e:
        log_event("manual_stop_error", f"Manual stop failed: {e}", "error")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/terminal")
def terminal(): return render_template_string(TERMINAL_HTML)

@app.route('/terminal/python', methods=['POST'])
def execute_python():
    data = request.get_json()
    if not data or 'code' not in data: return jsonify({"success": False, "error": "No code provided."}), 400
    return jsonify(python_interpreter.execute(data['code']))

@app.route('/terminal/reset', methods=['POST'])
def reset_interpreter():
    python_interpreter.reset()
    return jsonify({"success": True, "message": "Python interpreter session has been reset."})

@app.route("/logs")
def view_logs():
    headers = {"apikey": SUPABASE_API_KEY, "Authorization": f"Bearer {SUPABASE_API_KEY}"}
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?order=timestamp.desc&limit=500", headers=headers)
        logs = r.json() if r.status_code == 200 else []
    except Exception as e:
        logs = [{"timestamp": datetime.now().isoformat(), "event_type": "error", "note": f"Could not fetch logs: {e}", "type": "error"}]
    return render_template_string(LOGS_HTML, logs=logs)

@app.route("/debug")
def debug_view(): return render_template_string(DEBUG_HTML, debug_info=get_debug_info())

# === Main Execution ===
if __name__ == "__main__":
    log_event("startup", "Monitor and UI server starting")
    monitor_thread = threading.Thread(target=monitor_loop)
    monitor_thread.daemon = True
    monitor_thread.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
