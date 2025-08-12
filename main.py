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
        
        <div style="margin: 20px 0;">
            <a href="/scheduler" style="display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; margin-right: 10px;">⏰ Scheduler</a>
            <span style="color: #666;">Automate studio start/stop operations</span>
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

# Simple Scheduler HTML template
SCHEDULER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scheduler - Lightning AI Studio</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: white; }
        .container { max-width: 1000px; margin: 0 auto; }
        .nav { margin: 20px 0; }
        .nav a { color: #007bff; text-decoration: none; margin-right: 20px; }
        .nav a:hover { text-decoration: underline; }
        .card { background: #333; border-radius: 8px; padding: 20px; margin: 20px 0; }
        .form-group { margin: 15px 0; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input, .form-group select { width: 100%; padding: 8px; border: 1px solid #555; border-radius: 4px; background: #222; color: white; }
        button { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; margin: 5px; }
        .btn-primary { background: #007bff; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-warning { background: #ffc107; color: black; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #555; }
        th { background: #444; }
        .status-enabled { color: #28a745; }
        .status-disabled { color: #dc3545; }
        .hidden { display: none; }
        .modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; }
        .modal-content { background: #333; margin: 5% auto; padding: 20px; width: 80%; max-width: 500px; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">← Back to Dashboard</a>
        </div>
        
        <h1>⏰ Schedule Manager</h1>
        
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h2>Active Schedules</h2>
                <button class="btn-success" onclick="showAddModal()">+ Add Schedule</button>
            </div>
            
            {% if schedules %}
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Action</th>
                            <th>Scheduled Time</th>
                            <th>Countdown</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for schedule in schedules %}
                        <tr>
                            <td>{{ schedule.name }}</td>
                            <td>
                                <span style="padding: 4px 8px; border-radius: 4px; font-size: 12px;
                                    {% if schedule.action == 'start' %}background: #28a745;
                                    {% elif schedule.action == 'stop' %}background: #dc3545;
                                    {% elif schedule.action == 'restart' %}background: #ffc107; color: black;
                                    {% endif %}">
                                    {{ schedule.action.title() }}
                                </span>
                            </td>
                            <td>{{ schedule.schedule_time.split('T')[0] }} {{ schedule.schedule_time.split('T')[1][:5] }}</td>
                            <td class="countdown-cell" data-countdown="{{ schedule.countdown_seconds if schedule.countdown_seconds else 0 }}">
                                <span class="countdown-text">{{ schedule.countdown if schedule.countdown else 'N/A' }}</span>
                            </td>
                            <td class="{% if schedule.enabled %}status-enabled{% else %}status-disabled{% endif %}">
                                {% if schedule.enabled %}Enabled{% else %}Disabled{% endif %}
                            </td>
                            <td>
                                <button class="btn-danger" onclick="deleteSchedule('{{ schedule.id }}')">Delete</button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <p style="text-align: center; color: #666; margin: 40px 0;">
                    No schedules configured. Create your first automated schedule!
                </p>
            {% endif %}
        </div>
    </div>

    <!-- Add Schedule Modal -->
    <div id="addModal" class="modal hidden">
        <div class="modal-content">
            <h3>Add New Schedule</h3>
            <form id="scheduleForm">
                <div class="form-group">
                    <label>Schedule Name</label>
                    <input type="text" name="name" required placeholder="e.g., Morning Startup">
                </div>
                
                <div class="form-group">
                    <label>Action</label>
                    <select name="action" required>
                        <option value="start">Start Studio</option>
                        <option value="stop">Stop Studio</option>
                        <option value="restart">Restart Studio</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label>Scheduled Time</label>
                    <input type="datetime-local" name="schedule_time" required>
                </div>
                
                <div style="text-align: right; margin-top: 20px;">
                    <button type="button" onclick="hideAddModal()" class="btn-warning">Cancel</button>
                    <button type="submit" class="btn-success">Create Schedule</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function showAddModal() {
            document.getElementById('addModal').classList.remove('hidden');
        }
        
        function hideAddModal() {
            document.getElementById('addModal').classList.add('hidden');
            document.getElementById('scheduleForm').reset();
        }
        
        async function deleteSchedule(scheduleId) {
            if (!confirm('Are you sure you want to delete this schedule?')) return;
            
            try {
                const response = await fetch('/api/scheduler/delete/' + scheduleId, { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    location.reload();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Failed to delete schedule');
            }
        }
        
        document.getElementById('scheduleForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            
            try {
                const response = await fetch('/api/scheduler/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                
                if (result.success) {
                    hideAddModal();
                    location.reload();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Failed to create schedule');
            }
        });
        
        // Update countdowns every second
        function updateCountdowns() {
            const countdownCells = document.querySelectorAll('.countdown-cell');
            
            countdownCells.forEach(cell => {
                const countdownSeconds = parseInt(cell.dataset.countdown);
                const countdownText = cell.querySelector('.countdown-text');
                
                if (countdownSeconds > 0) {
                    const newCountdown = countdownSeconds - 1;
                    cell.dataset.countdown = newCountdown;
                    
                    if (newCountdown <= 0) {
                        countdownText.textContent = 'Executing...';
                        countdownText.style.color = '#ffc107';
                        // Reload page after 30 seconds to show updated status
                        setTimeout(() => location.reload(), 30000);
                    } else {
                        const days = Math.floor(newCountdown / 86400);
                        const hours = Math.floor((newCountdown % 86400) / 3600);
                        const minutes = Math.floor((newCountdown % 3600) / 60);
                        const seconds = newCountdown % 60;
                        
                        let countdownStr = '';
                        if (days > 0) {
                            countdownStr = `${days}d ${hours}h ${minutes}m`;
                        } else if (hours > 0) {
                            countdownStr = `${hours}h ${minutes}m ${seconds}s`;
                        } else if (minutes > 0) {
                            countdownStr = `${minutes}m ${seconds}s`;
                        } else {
                            countdownStr = `${seconds}s`;
                        }
                        
                        countdownText.textContent = countdownStr;
                        
                        // Color coding based on time remaining
                        if (newCountdown <= 60) {
                            countdownText.style.color = '#dc3545'; // Red for last minute
                        } else if (newCountdown <= 300) {
                            countdownText.style.color = '#ffc107'; // Yellow for last 5 minutes
                        } else {
                            countdownText.style.color = '#28a745'; // Green for more time
                        }
                    }
                }
            });
        }
        
        // Start countdown updates
        setInterval(updateCountdowns, 1000);
        
        // Show current server time for timezone reference
        function showServerTime() {
            const now = new Date();
            const timeStr = now.toLocaleString();
            console.log('Current local time:', timeStr);
        }
        
        showServerTime();
        setInterval(showServerTime, 60000); // Update every minute
    </script>
</body>
</html>
"""

# === Scheduler Service (Enhanced) ===
class SimpleScheduler:
    def __init__(self):
        self.schedules = []
        self.schedules_file = "schedules.json"
        self._load_schedules()
    
    def _load_schedules(self):
        try:
            if os.path.exists(self.schedules_file):
                with open(self.schedules_file, 'r') as f:
                    self.schedules = json.load(f)
                    debug_print(f"Loaded {len(self.schedules)} schedules")
        except Exception as e:
            debug_print(f"Error loading schedules: {e}")
            self.schedules = []
    
    def _save_schedules(self):
        try:
            with open(self.schedules_file, 'w') as f:
                json.dump(self.schedules, f, indent=2)
        except Exception as e:
            debug_print(f"Error saving schedules: {e}")
    
    def add_schedule(self, name, action, schedule_time):
        schedule_id = f"schedule_{int(time.time())}"
        schedule = {
            "id": schedule_id,
            "name": name,
            "action": action,
            "schedule_time": schedule_time,
            "enabled": True,
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "status": "pending"
        }
        self.schedules.append(schedule)
        self._save_schedules()
        log_event("schedule_added", f"Schedule '{name}' added for {schedule_time}", "event", schedule)
        return schedule_id
    
    def get_schedules(self):
        # Add countdown info to schedules
        current_time = datetime.now()
        schedules_with_countdown = []
        
        for schedule in self.schedules.copy():
            schedule_copy = schedule.copy()
            try:
                # Parse schedule time (handle both with and without timezone)
                schedule_dt = datetime.fromisoformat(schedule['schedule_time'].replace('Z', '+00:00'))
                if schedule_dt.tzinfo is None:
                    # Treat as local time if no timezone info
                    schedule_dt = schedule_dt.replace(tzinfo=None)
                    current_time_for_calc = current_time
                else:
                    # Convert to UTC for comparison
                    current_time_for_calc = current_time
                
                time_diff = schedule_dt - current_time_for_calc
                
                if time_diff.total_seconds() > 0:
                    # Future schedule
                    days = time_diff.days
                    hours, remainder = divmod(time_diff.seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    if days > 0:
                        schedule_copy['countdown'] = f"{days}d {hours}h {minutes}m"
                    elif hours > 0:
                        schedule_copy['countdown'] = f"{hours}h {minutes}m {seconds}s"
                    elif minutes > 0:
                        schedule_copy['countdown'] = f"{minutes}m {seconds}s"
                    else:
                        schedule_copy['countdown'] = f"{seconds}s"
                    
                    schedule_copy['countdown_seconds'] = int(time_diff.total_seconds())
                else:
                    # Past schedule
                    schedule_copy['countdown'] = "Overdue"
                    schedule_copy['countdown_seconds'] = 0
                    
            except Exception as e:
                debug_print(f"Error calculating countdown for schedule {schedule['id']}: {e}")
                schedule_copy['countdown'] = "Error"
                schedule_copy['countdown_seconds'] = 0
            
            schedules_with_countdown.append(schedule_copy)
        
        return schedules_with_countdown
    
    def delete_schedule(self, schedule_id):
        self.schedules = [s for s in self.schedules if s["id"] != schedule_id]
        self._save_schedules()
        log_event("schedule_deleted", f"Schedule {schedule_id} deleted", "event")
    
    def execute_schedule(self, schedule):
        """Execute a scheduled action"""
        try:
            action = schedule['action']
            schedule_id = schedule['id']
            schedule_name = schedule['name']
            
            log_event("schedule_execute", f"Executing schedule '{schedule_name}' - {action}", "event", schedule)
            
            if action == "start":
                if studio:
                    studio.start(Machine.CPU)
                    success = True
                    message = "Studio start initiated"
                else:
                    success = False
                    message = "Studio not initialized"
            
            elif action == "stop":
                if studio:
                    studio.stop()
                    success = True
                    message = "Studio stop initiated"
                else:
                    success = False
                    message = "Studio not initialized"
            
            elif action == "restart":
                if studio:
                    studio.stop()
                    time.sleep(5)
                    studio.start(Machine.CPU)
                    success = True
                    message = "Studio restart initiated"
                else:
                    success = False
                    message = "Studio not initialized"
            
            else:
                success = False
                message = f"Unknown action: {action}"
            
            # Update schedule status
            for i, s in enumerate(self.schedules):
                if s['id'] == schedule_id:
                    self.schedules[i]['last_run'] = datetime.now().isoformat()
                    self.schedules[i]['status'] = 'completed' if success else 'failed'
                    # Disable one-time schedules after execution
                    self.schedules[i]['enabled'] = False
                    break
            
            self._save_schedules()
            
            log_event(
                "schedule_completed",
                f"Schedule '{schedule_name}' completed - {message}",
                "event" if success else "error",
                {"schedule_id": schedule_id, "success": success, "message": message}
            )
            
            return success, message
            
        except Exception as e:
            error_msg = f"Error executing schedule {schedule.get('id', 'unknown')}: {e}"
            debug_print(error_msg)
            log_event("schedule_error", error_msg, "error")
            return False, error_msg
    
    def check_and_execute_schedules(self):
        """Check for schedules that need to be executed"""
        current_time = datetime.now()
        
        for schedule in self.schedules:
            if not schedule.get('enabled', True):
                continue
                
            try:
                # Parse schedule time
                schedule_dt = datetime.fromisoformat(schedule['schedule_time'].replace('Z', '+00:00'))
                if schedule_dt.tzinfo is None:
                    # Treat as local time if no timezone info
                    schedule_dt = schedule_dt.replace(tzinfo=None)
                
                # Check if it's time to execute (within 1 minute window)
                time_diff = (current_time - schedule_dt).total_seconds()
                
                if 0 <= time_diff <= 60:  # Execute if within 1 minute past scheduled time
                    debug_print(f"Executing scheduled task: {schedule['name']}")
                    self.execute_schedule(schedule)
                    
            except Exception as e:
                debug_print(f"Error checking schedule {schedule['id']}: {e}")
                continue

# Initialize scheduler
scheduler = SimpleScheduler()

# === Routes ===
@app.route("/")
def dashboard():
    return render_template_string(SIMPLE_DASHBOARD_HTML)

@app.route("/scheduler")
def scheduler_page():
    schedules = scheduler.get_schedules()
    return render_template_string(SCHEDULER_HTML, schedules=schedules)

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

@app.route("/api/scheduler/add", methods=['POST'])
def add_schedule():
    try:
        data = request.get_json()
        name = data.get('name')
        action = data.get('action')
        schedule_time = data.get('schedule_time')
        
        if not all([name, action, schedule_time]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        schedule_id = scheduler.add_schedule(name, action, schedule_time)
        return jsonify({"success": True, "schedule_id": schedule_id, "message": "Schedule created successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/scheduler/delete/<schedule_id>", methods=['POST'])
def delete_schedule(schedule_id):
    try:
        scheduler.delete_schedule(schedule_id)
        return jsonify({"success": True, "message": "Schedule deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/scheduler/list")
def list_schedules():
    try:
        schedules = scheduler.get_schedules()
        return jsonify({"success": True, "schedules": schedules})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# === Monitor Logic ===
def monitor_loop():
    debug_print("Starting enhanced monitor loop with scheduler")
    last_known_status = None
    last_schedule_check = 0

    while True:
        try:
            current_time = time.time()
            
            # Check studio status (every 60 seconds)
            if not studio:
                debug_print("Studio object is None, cannot monitor.")
                time.sleep(60)
                continue

            status, error = get_studio_status()
            log_event("status_check", f"Current status: {status}", "heartbeat", {"status": status, "error": error})

            if status != last_known_status:
                log_event("state_change", f"Status changed from '{last_known_status}' to '{status}'", "event", {"from": last_known_status, "to": status})
                last_known_status = status
            
            # Check schedules (every 30 seconds for better precision)
            if current_time - last_schedule_check >= 30:
                try:
                    debug_print("Checking for scheduled tasks...")
                    scheduler.check_and_execute_schedules()
                    last_schedule_check = current_time
                except Exception as e:
                    debug_print(f"Error checking schedules: {e}")
                    log_event("scheduler_error", f"Error checking schedules: {e}", "error")
            
        except Exception as e:
            debug_print(f"CRITICAL: Exception in monitor loop: {e}\n{traceback.format_exc()}")
            log_event("monitor_error", f"Exception in monitor loop: {e}", "error")
        
        time.sleep(30)  # Check more frequently for better schedule precision

if __name__ == "__main__":
    log_event("startup", "Enhanced Lightning AI Dashboard starting")
    monitor_thread = threading.Thread(target=monitor_loop)
    monitor_thread.daemon = True
    monitor_thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)