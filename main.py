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
            <a href="/files" style="display: inline-block; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 4px; margin-right: 10px;">📁 Files</a>
            <a href="/terminal" style="display: inline-block; padding: 10px 20px; background: #6f42c1; color: white; text-decoration: none; border-radius: 4px; margin-right: 10px;">💻 Terminal</a>
            <br><br>
            <span style="color: #666;">Manage your workspace with scheduling, file editing, and Python terminal</span>
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
                    <label>Scheduled Time (Your Local Time)</label>
                    <input type="datetime-local" name="schedule_time" required>
                    <small style="color: #999; font-size: 12px;">
                        Enter time in your local timezone. Current local time: <span id="localTime">Loading...</span>
                    </small>
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
            
            // Convert local time to UTC for server
            if (data.schedule_time) {
                const localDateTime = new Date(data.schedule_time);
                // Convert to UTC ISO string, then remove the 'Z' to match server format
                data.schedule_time = localDateTime.toISOString().slice(0, 19);
                console.log('Local time selected:', data.schedule_time);
                console.log('Converted to UTC:', localDateTime.toISOString());
            }
            
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
        
        // Update local time display in modal
        function updateLocalTimeDisplay() {
            const now = new Date();
            const localTimeEl = document.getElementById('localTime');
            if (localTimeEl) {
                localTimeEl.textContent = now.toLocaleString();
            }
        }
        
        // Update local time every second when modal is open
        setInterval(updateLocalTimeDisplay, 1000);
        updateLocalTimeDisplay();
    </script>
</body>
</html>
"""

# File Manager HTML template
FILES_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Manager - Lightning AI Studio</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: white; }
        .container { max-width: 1200px; margin: 0 auto; }
        .nav { margin: 20px 0; }
        .nav a { color: #007bff; text-decoration: none; margin-right: 20px; }
        .nav a:hover { text-decoration: underline; }
        .card { background: #333; border-radius: 8px; padding: 20px; margin: 20px 0; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .form-group { margin: 15px 0; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px; border: 1px solid #555; border-radius: 4px; background: #222; color: white; }
        button { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; margin: 2px; }
        .btn-primary { background: #007bff; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-warning { background: #ffc107; color: black; }
        .btn-small { padding: 4px 8px; font-size: 12px; }
        .file-list { max-height: 400px; overflow-y: auto; }
        .file-item { display: flex; justify-content: between; align-items: center; padding: 10px; margin: 5px 0; background: #444; border-radius: 4px; }
        .file-info { flex-grow: 1; }
        .file-actions { display: flex; gap: 5px; }
        .editor { background: #222; border: 1px solid #555; border-radius: 4px; }
        .output { background: #000; color: #0f0; padding: 15px; border-radius: 4px; font-family: monospace; max-height: 200px; overflow-y: auto; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #555; }
        th { background: #444; }
        .status-success { color: #28a745; }
        .status-failed { color: #dc3545; }
        .hidden { display: none; }
        .modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; }
        .modal-content { background: #333; margin: 5% auto; padding: 20px; width: 80%; max-width: 500px; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">← Back to Dashboard</a>
            <a href="/scheduler">⏰ Scheduler</a>
            <a href="/terminal">💻 Terminal</a>
        </div>
        
        <h1>📁 File Manager</h1>
        
        <div class="grid">
            <!-- File Browser -->
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h2>Workspace Files</h2>
                    <div>
                        <button class="btn-success btn-small" onclick="showNewFileModal()">+ New</button>
                        <button class="btn-warning btn-small" onclick="showUploadModal()">📤 Upload</button>
                        <button class="btn-primary btn-small" onclick="refreshFiles()">🔄 Refresh</button>
                    </div>
                </div>
                
                <div id="filesList" class="file-list">
                    {% if files %}
                        {% for file in files %}
                        <div class="file-item">
                            <div class="file-info" onclick="{% if file.type == 'file' %}loadFile('{{ file.path }}'){% endif %}">
                                <div style="font-weight: bold;">
                                    {% if file.type == 'directory' %}📁{% else %}📄{% endif %}
                                    {{ file.name }}
                                </div>
                                {% if file.type == 'file' %}
                                    <div style="font-size: 12px; color: #999;">
                                        {{ "%.1f"|format(file.size / 1024) }} KB • {{ file.modified.split('T')[0] }}
                                    </div>
                                {% endif %}
                            </div>
                            {% if file.type == 'file' %}
                                <div class="file-actions">
                                    <button class="btn-success btn-small" onclick="executeFileQuick('{{ file.path }}')">▶️</button>
                                    <button class="btn-primary btn-small" onclick="downloadFile('{{ file.path }}')">📥</button>
                                    <button class="btn-danger btn-small" onclick="deleteFile('{{ file.path }}')">🗑️</button>
                                </div>
                            {% endif %}
                        </div>
                        {% endfor %}
                    {% else %}
                        <div style="text-align: center; color: #666; padding: 40px;">
                            No files found. Create your first file!
                        </div>
                    {% endif %}
                </div>
            </div>
            
            <!-- File Editor -->
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h2>File Editor</h2>
                    <div>
                        <button id="saveBtn" class="btn-primary btn-small" onclick="saveFile()" disabled>💾 Save</button>
                        <button id="executeBtn" class="btn-success btn-small" onclick="showExecuteModal()" disabled>▶️ Execute</button>
                    </div>
                </div>
                
                <div id="editorContainer">
                    <div id="noFileSelected" style="text-align: center; color: #666; padding: 40px;">
                        Select a file to edit
                    </div>
                    
                    <div id="fileEditor" class="hidden">
                        <div class="form-group">
                            <input type="text" id="currentFileName" placeholder="filename.py" class="editor">
                        </div>
                        <div class="form-group">
                            <textarea id="fileContent" rows="15" class="editor" placeholder="Enter your code here..."></textarea>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Execution Output -->
        <div class="card">
            <h2>Execution Output</h2>
            <div id="executionOutput" class="output">
                No executions yet. Execute a file to see output here.
            </div>
        </div>

        <!-- Startup Scripts -->
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h2>🚀 Startup Scripts</h2>
                <button class="btn-success btn-small" onclick="showStartupScriptModal()">+ Add Startup Script</button>
            </div>
            
            <div id="startupScripts">
                <div style="text-align: center; color: #666; padding: 20px;">
                    No startup scripts configured. Add scripts to run automatically when the studio starts.
                </div>
            </div>
        </div>

        <!-- Execution History -->
        <div class="card">
            <h2>Recent Executions</h2>
            {% if execution_history %}
                <table>
                    <thead>
                        <tr>
                            <th>File</th>
                            <th>Command</th>
                            <th>Time</th>
                            <th>Duration</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for exec in execution_history %}
                        <tr onclick="viewExecution('{{ exec.id }}')" style="cursor: pointer;">
                            <td>{{ exec.file_path }}</td>
                            <td style="font-family: monospace; font-size: 12px;">{{ exec.command[:40] }}{% if exec.command|length > 40 %}...{% endif %}</td>
                            <td>{{ exec.timestamp.split('T')[1].split('.')[0] }}</td>
                            <td>{{ "%.2f"|format(exec.execution_time) }}s</td>
                            <td class="{% if exec.success %}status-success{% else %}status-failed{% endif %}">
                                {% if exec.success %}✅ Success{% else %}❌ Failed{% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <div style="text-align: center; color: #666; padding: 20px;">
                    No executions yet
                </div>
            {% endif %}
        </div>
    </div>

    <!-- New File Modal -->
    <div id="newFileModal" class="modal hidden">
        <div class="modal-content">
            <h3>Create New File</h3>
            <form id="newFileForm">
                <div class="form-group">
                    <label>File Name</label>
                    <input type="text" name="filename" placeholder="script.py" required>
                </div>
                <div style="text-align: right; margin-top: 20px;">
                    <button type="button" onclick="hideNewFileModal()" class="btn-warning">Cancel</button>
                    <button type="submit" class="btn-success">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Execute Modal -->
    <div id="executeModal" class="modal hidden">
        <div class="modal-content">
            <h3>Execute File</h3>
            <form id="executeForm">
                <div class="form-group">
                    <label>Interpreter</label>
                    <select name="interpreter">
                        <option value="python">Python</option>
                        <option value="bash">Bash</option>
                        <option value="node">Node.js</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Arguments (optional)</label>
                    <input type="text" name="args" placeholder="--arg1 value1">
                </div>
                <div class="form-group">
                    <label>Timeout (seconds)</label>
                    <input type="number" name="timeout" value="300" min="1" max="3600">
                </div>
                <div style="text-align: right; margin-top: 20px;">
                    <button type="button" onclick="hideExecuteModal()" class="btn-warning">Cancel</button>
                    <button type="submit" class="btn-success">Execute</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Upload Modal -->
    <div id="uploadModal" class="modal hidden">
        <div class="modal-content">
            <h3>Upload File</h3>
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="form-group">
                    <label>Select File</label>
                    <input type="file" name="file" required style="background: #444; color: white;">
                </div>
                <div style="text-align: right; margin-top: 20px;">
                    <button type="button" onclick="hideUploadModal()" class="btn-warning">Cancel</button>
                    <button type="submit" class="btn-success">Upload</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Startup Script Modal -->
    <div id="startupScriptModal" class="modal hidden">
        <div class="modal-content">
            <h3>Add Startup Script</h3>
            <form id="startupScriptForm">
                <div class="form-group">
                    <label>Script Name</label>
                    <input type="text" name="name" placeholder="My Startup Script" required>
                </div>
                <div class="form-group">
                    <label>Script Type</label>
                    <select name="type" onchange="toggleScriptFields(this.value)">
                        <option value="workspace">Workspace File</option>
                        <option value="remote">Remote Machine File</option>
                        <option value="command">Direct Command</option>
                    </select>
                </div>
                <div class="form-group" id="workspaceFileField">
                    <label>Workspace File Path</label>
                    <input type="text" name="workspace_file" placeholder="script.py">
                </div>
                <div class="form-group hidden" id="remoteFileField">
                    <label>Remote File Path</label>
                    <input type="text" name="remote_file" placeholder="/home/user/script.py">
                </div>
                <div class="form-group hidden" id="commandField">
                    <label>Command</label>
                    <input type="text" name="command" placeholder="pip install -r requirements.txt">
                </div>
                <div class="form-group">
                    <label>Interpreter</label>
                    <select name="interpreter">
                        <option value="python">Python</option>
                        <option value="bash">Bash</option>
                        <option value="node">Node.js</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Arguments (optional)</label>
                    <input type="text" name="args" placeholder="--verbose">
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" name="enabled" checked> Enabled
                    </label>
                </div>
                <div style="text-align: right; margin-top: 20px;">
                    <button type="button" onclick="hideStartupScriptModal()" class="btn-warning">Cancel</button>
                    <button type="submit" class="btn-success">Add Script</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Execution Result Modal -->
    <div id="executionResultModal" class="modal hidden">
        <div class="modal-content" style="max-width: 800px;">
            <h3>Execution Result</h3>
            <div id="executionResultContent">
                <!-- Content will be loaded here -->
            </div>
            <div style="text-align: right; margin-top: 20px;">
                <button onclick="hideExecutionResultModal()" class="btn-primary">Close</button>
            </div>
        </div>
    </div>

    <script>
        let currentFilePath = null;
        let isModified = false;

        // File operations
        async function loadFile(filePath) {
            try {
                const response = await fetch('/api/files/read/' + encodeURIComponent(filePath));
                const data = await response.json();
                
                if (data.success) {
                    currentFilePath = filePath;
                    document.getElementById('currentFileName').value = filePath;
                    document.getElementById('fileContent').value = data.content;
                    
                    document.getElementById('noFileSelected').style.display = 'none';
                    document.getElementById('fileEditor').classList.remove('hidden');
                    
                    document.getElementById('saveBtn').disabled = false;
                    document.getElementById('executeBtn').disabled = false;
                    
                    isModified = false;
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Failed to load file');
            }
        }

        async function saveFile() {
            if (!currentFilePath) return;
            
            const content = document.getElementById('fileContent').value;
            const fileName = document.getElementById('currentFileName').value;
            
            try {
                const response = await fetch('/api/files/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: fileName, content: content })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    alert('File saved successfully');
                    currentFilePath = fileName;
                    isModified = false;
                    refreshFiles();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Failed to save file');
            }
        }

        async function executeFile(interpreter, args, timeout) {
            if (!currentFilePath) return;
            
            // Save first if modified
            if (isModified) {
                await saveFile();
            }
            
            try {
                const response = await fetch('/api/files/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        file_path: currentFilePath, 
                        interpreter: interpreter,
                        args: args,
                        timeout: timeout
                    })
                });
                
                const data = await response.json();
                
                const outputDiv = document.getElementById('executionOutput');
                outputDiv.innerHTML = `
                    <div style="margin-bottom: 10px;">
                        <strong>Executed:</strong> ${currentFilePath}
                        <span style="margin-left: 20px; color: ${data.success ? '#0f0' : '#f00'};">
                            ${data.success ? '✅ SUCCESS' : '❌ FAILED'} (${data.execution_time?.toFixed(2)}s)
                        </span>
                    </div>
                    ${data.stdout ? `<div><strong>Output:</strong><pre style="color: #0f0;">${data.stdout}</pre></div>` : ''}
                    ${data.stderr ? `<div><strong>Error:</strong><pre style="color: #f00;">${data.stderr}</pre></div>` : ''}
                `;
                
                hideExecuteModal();
                
                if (data.success) {
                    alert('File executed successfully');
                } else {
                    alert('File execution failed');
                }
                
                // Refresh execution history
                setTimeout(() => location.reload(), 1000);
                
            } catch (error) {
                alert('Failed to execute file');
            }
        }

        async function executeFileQuick(filePath) {
            try {
                const response = await fetch('/api/files/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: filePath })
                });
                
                const data = await response.json();
                
                const outputDiv = document.getElementById('executionOutput');
                outputDiv.innerHTML = `
                    <div style="margin-bottom: 10px;">
                        <strong>Quick Execute:</strong> ${filePath}
                        <span style="margin-left: 20px; color: ${data.success ? '#0f0' : '#f00'};">
                            ${data.success ? '✅ SUCCESS' : '❌ FAILED'} (${data.execution_time?.toFixed(2)}s)
                        </span>
                    </div>
                    ${data.stdout ? `<div><strong>Output:</strong><pre style="color: #0f0;">${data.stdout}</pre></div>` : ''}
                    ${data.stderr ? `<div><strong>Error:</strong><pre style="color: #f00;">${data.stderr}</pre></div>` : ''}
                `;
                
                if (data.success) {
                    alert('File executed successfully');
                } else {
                    alert('File execution failed');
                }
                
                // Refresh execution history
                setTimeout(() => location.reload(), 1000);
                
            } catch (error) {
                alert('Failed to execute file');
            }
        }

        async function deleteFile(filePath) {
            if (!confirm('Are you sure you want to delete ' + filePath + '?')) return;
            
            try {
                const response = await fetch('/api/files/delete/' + encodeURIComponent(filePath), {
                    method: 'DELETE'
                });
                
                const data = await response.json();
                
                if (data.success) {
                    alert('File deleted successfully');
                    refreshFiles();
                    
                    if (currentFilePath === filePath) {
                        document.getElementById('noFileSelected').style.display = 'block';
                        document.getElementById('fileEditor').classList.add('hidden');
                        currentFilePath = null;
                    }
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Failed to delete file');
            }
        }

        async function downloadFile(filePath) {
            try {
                const response = await fetch('/api/files/download/' + encodeURIComponent(filePath));
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filePath.split('/').pop();
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                } else {
                    alert('Failed to download file');
                }
            } catch (error) {
                alert('Failed to download file');
            }
        }

        async function uploadFile() {
            const formData = new FormData(document.getElementById('uploadForm'));
            
            try {
                const response = await fetch('/api/files/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (data.success) {
                    alert('File uploaded successfully');
                    hideUploadModal();
                    refreshFiles();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Failed to upload file');
            }
        }

        async function viewExecution(executionId) {
            try {
                const response = await fetch('/api/files/execution/' + executionId);
                const data = await response.json();
                
                if (data.success) {
                    const exec = data.execution;
                    const content = document.getElementById('executionResultContent');
                    content.innerHTML = `
                        <div class="form-group">
                            <label>File:</label>
                            <div style="background: #222; padding: 8px; border-radius: 4px;">${exec.file_path}</div>
                        </div>
                        <div class="form-group">
                            <label>Command:</label>
                            <div style="background: #222; padding: 8px; border-radius: 4px; font-family: monospace;">${exec.command}</div>
                        </div>
                        <div class="form-group">
                            <label>Execution Time:</label>
                            <div style="background: #222; padding: 8px; border-radius: 4px;">${exec.execution_time.toFixed(2)} seconds</div>
                        </div>
                        <div class="form-group">
                            <label>Status:</label>
                            <div style="background: #222; padding: 8px; border-radius: 4px; color: ${exec.success ? '#0f0' : '#f00'};">
                                ${exec.success ? '✅ Success' : '❌ Failed'} (Return Code: ${exec.return_code})
                            </div>
                        </div>
                        ${exec.stdout ? `
                            <div class="form-group">
                                <label>Output:</label>
                                <div class="output" style="max-height: 200px;">${exec.stdout}</div>
                            </div>
                        ` : ''}
                        ${exec.stderr ? `
                            <div class="form-group">
                                <label>Error:</label>
                                <div class="output" style="max-height: 200px; color: #f00;">${exec.stderr}</div>
                            </div>
                        ` : ''}
                    `;
                    document.getElementById('executionResultModal').classList.remove('hidden');
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Failed to load execution result');
            }
        }

        function refreshFiles() {
            location.reload();
        }

        // Modal functions
        function showNewFileModal() {
            document.getElementById('newFileModal').classList.remove('hidden');
        }

        function hideNewFileModal() {
            document.getElementById('newFileModal').classList.add('hidden');
            document.getElementById('newFileForm').reset();
        }

        function showExecuteModal() {
            document.getElementById('executeModal').classList.remove('hidden');
        }

        function hideExecuteModal() {
            document.getElementById('executeModal').classList.add('hidden');
        }

        function showUploadModal() {
            document.getElementById('uploadModal').classList.remove('hidden');
        }

        function hideUploadModal() {
            document.getElementById('uploadModal').classList.add('hidden');
            document.getElementById('uploadForm').reset();
        }

        function showStartupScriptModal() {
            document.getElementById('startupScriptModal').classList.remove('hidden');
        }

        function hideStartupScriptModal() {
            document.getElementById('startupScriptModal').classList.add('hidden');
            document.getElementById('startupScriptForm').reset();
        }

        function hideExecutionResultModal() {
            document.getElementById('executionResultModal').classList.add('hidden');
        }

        function toggleScriptFields(type) {
            document.getElementById('workspaceFileField').classList.toggle('hidden', type !== 'workspace');
            document.getElementById('remoteFileField').classList.toggle('hidden', type !== 'remote');
            document.getElementById('commandField').classList.toggle('hidden', type !== 'command');
        }

        // Form submissions
        document.getElementById('newFileForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const filename = e.target.filename.value;
            
            currentFilePath = filename;
            document.getElementById('currentFileName').value = filename;
            document.getElementById('fileContent').value = '';
            
            document.getElementById('noFileSelected').style.display = 'none';
            document.getElementById('fileEditor').classList.remove('hidden');
            
            document.getElementById('saveBtn').disabled = false;
            document.getElementById('executeBtn').disabled = false;
            
            hideNewFileModal();
        });

        document.getElementById('executeForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            
            executeFile(data.interpreter, data.args, parseInt(data.timeout));
        });

        document.getElementById('uploadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            uploadFile();
        });

        document.getElementById('startupScriptForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            data.enabled = formData.get('enabled') === 'on';
            
            // Add startup script logic here
            alert('Startup script functionality will be implemented in the backend');
            hideStartupScriptModal();
        });

        // Track modifications
        document.getElementById('fileContent').addEventListener('input', function() {
            isModified = true;
        });
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
            debug_print(f"SCHEDULER: About to execute {action} for schedule '{schedule_name}'")
            
            if action == "start":
                if studio:
                    debug_print(f"SCHEDULER: Studio object exists, calling studio.start(Machine.CPU)")
                    try:
                        studio.start(Machine.CPU)
                        debug_print(f"SCHEDULER: studio.start() call completed successfully")
                        success = True
                        message = "Studio start initiated by scheduler"
                        log_event("schedule_start_success", f"Scheduled start completed for '{schedule_name}'", "event")
                    except Exception as start_error:
                        debug_print(f"SCHEDULER: Error during studio.start(): {start_error}")
                        log_event("schedule_start_error", f"Scheduled start failed for '{schedule_name}': {start_error}", "error")
                        success = False
                        message = f"Studio start failed: {start_error}"
                else:
                    debug_print(f"SCHEDULER: Studio object is None!")
                    success = False
                    message = "Studio not initialized"
            
            elif action == "stop":
                if studio:
                    debug_print(f"SCHEDULER: Studio object exists, calling studio.stop()")
                    try:
                        studio.stop()
                        debug_print(f"SCHEDULER: studio.stop() call completed successfully")
                        success = True
                        message = "Studio stop initiated by scheduler"
                        log_event("schedule_stop_success", f"Scheduled stop completed for '{schedule_name}'", "event")
                    except Exception as stop_error:
                        debug_print(f"SCHEDULER: Error during studio.stop(): {stop_error}")
                        log_event("schedule_stop_error", f"Scheduled stop failed for '{schedule_name}': {stop_error}", "error")
                        success = False
                        message = f"Studio stop failed: {stop_error}"
                else:
                    debug_print(f"SCHEDULER: Studio object is None!")
                    success = False
                    message = "Studio not initialized"
            
            elif action == "restart":
                if studio:
                    debug_print(f"SCHEDULER: Studio object exists, calling studio.stop() then studio.start()")
                    try:
                        studio.stop()
                        debug_print(f"SCHEDULER: studio.stop() completed, waiting 5 seconds...")
                        time.sleep(5)
                        studio.start(Machine.CPU)
                        debug_print(f"SCHEDULER: studio.start() completed successfully")
                        success = True
                        message = "Studio restart initiated by scheduler"
                        log_event("schedule_restart_success", f"Scheduled restart completed for '{schedule_name}'", "event")
                    except Exception as restart_error:
                        debug_print(f"SCHEDULER: Error during studio restart: {restart_error}")
                        log_event("schedule_restart_error", f"Scheduled restart failed for '{schedule_name}': {restart_error}", "error")
                        success = False
                        message = f"Studio restart failed: {restart_error}"
                else:
                    debug_print(f"SCHEDULER: Studio object is None!")
                    success = False
                    message = "Studio not initialized"
            
            else:
                debug_print(f"SCHEDULER: Unknown action: {action}")
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
        debug_print(f"SCHEDULER: Checking schedules at {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        debug_print(f"SCHEDULER: Found {len(self.schedules)} total schedules")
        
        enabled_schedules = [s for s in self.schedules if s.get('enabled', True)]
        debug_print(f"SCHEDULER: Found {len(enabled_schedules)} enabled schedules")
        
        for schedule in self.schedules:
            if not schedule.get('enabled', True):
                debug_print(f"SCHEDULER: Skipping disabled schedule '{schedule['name']}'")
                continue
                
            try:
                # Parse schedule time
                schedule_dt = datetime.fromisoformat(schedule['schedule_time'].replace('Z', '+00:00'))
                if schedule_dt.tzinfo is None:
                    # Treat as local time if no timezone info
                    schedule_dt = schedule_dt.replace(tzinfo=None)
                
                # Check if it's time to execute (within 1 minute window)
                time_diff = (current_time - schedule_dt).total_seconds()
                
                debug_print(f"SCHEDULER: Schedule '{schedule['name']}' - Current: {current_time.strftime('%H:%M:%S')}, Scheduled: {schedule_dt.strftime('%H:%M:%S')}, Diff: {time_diff:.1f}s")
                
                if 0 <= time_diff <= 60:  # Execute if within 1 minute past scheduled time
                    debug_print(f"SCHEDULER: *** EXECUTING scheduled task: {schedule['name']} ***")
                    success, message = self.execute_schedule(schedule)
                    debug_print(f"SCHEDULER: Execution result - Success: {success}, Message: {message}")
                elif time_diff > 60:
                    debug_print(f"SCHEDULER: Schedule '{schedule['name']}' is overdue by {time_diff:.1f} seconds")
                else:
                    debug_print(f"SCHEDULER: Schedule '{schedule['name']}' is {abs(time_diff):.1f} seconds in the future")
                    
            except Exception as e:
                debug_print(f"SCHEDULER: Error checking schedule {schedule['id']}: {e}")
                log_event("scheduler_check_error", f"Error checking schedule {schedule['id']}: {e}", "error")
                continue

# Initialize scheduler
scheduler = SimpleScheduler()

# === File Manager Service ===
class SimpleFileManager:
    def __init__(self):
        self.executions = []
        self.executions_file = "executions.json"
        self._load_executions()
    
    def _load_executions(self):
        try:
            if os.path.exists(self.executions_file):
                with open(self.executions_file, 'r') as f:
                    self.executions = json.load(f)
                    debug_print(f"Loaded {len(self.executions)} execution records")
        except Exception as e:
            debug_print(f"Error loading executions: {e}")
            self.executions = []
    
    def _save_executions(self):
        try:
            # Keep only last 100 executions
            self.executions = self.executions[-100:]
            with open(self.executions_file, 'w') as f:
                json.dump(self.executions, f, indent=2)
        except Exception as e:
            debug_print(f"Error saving executions: {e}")
    
    def get_workspace_files(self, path="."):
        files = []
        try:
            if not os.path.exists(path):
                return files
            
            for item in os.listdir(path):
                if item.startswith('.'):
                    continue
                    
                item_path = os.path.join(path, item)
                
                if os.path.isfile(item_path):
                    stat = os.stat(item_path)
                    files.append({
                        "name": item,
                        "path": item_path,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type": "file"
                    })
                elif os.path.isdir(item_path):
                    files.append({
                        "name": item,
                        "path": item_path,
                        "type": "directory"
                    })
        
        except Exception as e:
            debug_print(f"Error listing files: {e}")
        
        return sorted(files, key=lambda x: (x["type"] == "file", x["name"]))
    
    def read_file(self, file_path):
        try:
            if not os.path.exists(file_path):
                return None, "File not found"
            
            if os.path.getsize(file_path) > 1024 * 1024:  # 1MB limit
                return None, "File too large to display"
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            return content, None
            
        except Exception as e:
            return None, str(e)
    
    def save_file(self, file_path, content):
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else '.', exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            log_event("file_saved", f"File saved: {file_path}", "event")
            return True, "File saved successfully"
            
        except Exception as e:
            log_event("file_save_error", f"Error saving file {file_path}: {e}", "error")
            return False, str(e)
    
    def delete_file(self, file_path):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                log_event("file_deleted", f"File deleted: {file_path}", "event")
                return True, "File deleted successfully"
            else:
                return False, "File not found"
                
        except Exception as e:
            log_event("file_delete_error", f"Error deleting file {file_path}: {e}", "error")
            return False, str(e)
    
    def execute_file(self, file_path, interpreter="python", args="", timeout=300):
        execution_id = f"exec_{int(time.time())}"
        
        try:
            if not os.path.exists(file_path):
                return {"success": False, "error": "File not found", "execution_id": execution_id}
            
            # Build command
            if interpreter == "python":
                command = f"python {file_path} {args}".strip()
            elif interpreter == "bash":
                command = f"bash {file_path} {args}".strip()
            elif interpreter == "node":
                command = f"node {file_path} {args}".strip()
            else:
                command = f"{interpreter} {file_path} {args}".strip()
            
            log_event("file_execute_start", f"Executing: {command}", "event")
            debug_print(f"FILE EXEC: Starting execution of {command}")
            
            start_time = time.time()
            
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.path.dirname(file_path) if os.path.dirname(file_path) else "."
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Record execution
            execution_record = {
                "id": execution_id,
                "file_path": file_path,
                "command": command,
                "timestamp": datetime.now().isoformat(),
                "execution_time": execution_time,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0
            }
            
            self.executions.append(execution_record)
            self._save_executions()
            
            if result.returncode == 0:
                log_event("file_execute_success", f"File executed successfully: {file_path}", "event", {
                    "execution_time": execution_time,
                    "command": command
                })
                debug_print(f"FILE EXEC: Success - {execution_time:.2f}s")
            else:
                log_event("file_execute_error", f"File execution failed: {file_path}", "error", {
                    "return_code": result.returncode,
                    "command": command,
                    "error": result.stderr[:500]
                })
                debug_print(f"FILE EXEC: Failed with code {result.returncode}")
            
            return {
                "success": result.returncode == 0,
                "execution_id": execution_id,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "execution_time": execution_time
            }
            
        except subprocess.TimeoutExpired:
            error_msg = f"Execution timed out after {timeout} seconds"
            log_event("file_execute_timeout", f"File execution timeout: {file_path}", "error")
            debug_print(f"FILE EXEC: Timeout after {timeout}s")
            
            execution_record = {
                "id": execution_id,
                "file_path": file_path,
                "command": command if 'command' in locals() else file_path,
                "timestamp": datetime.now().isoformat(),
                "execution_time": timeout,
                "return_code": -1,
                "stdout": "",
                "stderr": error_msg,
                "success": False
            }
            
            self.executions.append(execution_record)
            self._save_executions()
            
            return {
                "success": False,
                "execution_id": execution_id,
                "error": error_msg,
                "stdout": "",
                "stderr": error_msg,
                "return_code": -1,
                "execution_time": timeout
            }
            
        except Exception as e:
            error_msg = str(e)
            log_event("file_execute_exception", f"File execution exception: {file_path} - {error_msg}", "error")
            debug_print(f"FILE EXEC: Exception - {error_msg}")
            
            execution_record = {
                "id": execution_id,
                "file_path": file_path,
                "command": command if 'command' in locals() else file_path,
                "timestamp": datetime.now().isoformat(),
                "execution_time": 0,
                "return_code": -1,
                "stdout": "",
                "stderr": error_msg,
                "success": False
            }
            
            self.executions.append(execution_record)
            self._save_executions()
            
            return {
                "success": False,
                "execution_id": execution_id,
                "error": error_msg,
                "stdout": "",
                "stderr": error_msg,
                "return_code": -1,
                "execution_time": 0
            }
    
    def get_execution_history(self, limit=20):
        return self.executions[-limit:] if self.executions else []

# Initialize file manager
file_manager = SimpleFileManager()

# === Routes ===
@app.route("/")
def dashboard():
    return render_template_string(SIMPLE_DASHBOARD_HTML)

@app.route("/scheduler")
def scheduler_page():
    schedules = scheduler.get_schedules()
    return render_template_string(SCHEDULER_HTML, schedules=schedules)

@app.route("/files")
def files_page():
    files = file_manager.get_workspace_files()
    execution_history = file_manager.get_execution_history()
    return render_template_string(FILES_HTML, files=files, execution_history=execution_history)

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

# File Manager API Routes
@app.route("/api/files/list")
def list_files():
    try:
        path = request.args.get('path', '.')
        files = file_manager.get_workspace_files(path)
        return jsonify({"success": True, "files": files, "current_path": path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/files/read/<path:file_path>")
def read_file(file_path):
    try:
        content, error = file_manager.read_file(file_path)
        if error:
            return jsonify({"success": False, "error": error}), 400
        return jsonify({"success": True, "content": content, "file_path": file_path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/files/save", methods=['POST'])
def save_file():
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        content = data.get('content', '')
        
        if not file_path:
            return jsonify({"success": False, "error": "File path is required"}), 400
        
        success, message = file_manager.save_file(file_path, content)
        return jsonify({"success": success, "message": message})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/files/delete/<path:file_path>", methods=['DELETE'])
def delete_file(file_path):
    try:
        success, message = file_manager.delete_file(file_path)
        return jsonify({"success": success, "message": message})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/files/execute", methods=['POST'])
def execute_file():
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        interpreter = data.get('interpreter', 'python')
        args = data.get('args', '')
        timeout = data.get('timeout', 300)
        
        if not file_path:
            return jsonify({"success": False, "error": "File path is required"}), 400
        
        result = file_manager.execute_file(file_path, interpreter, args, timeout)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/files/execution-history")
def get_execution_history():
    try:
        limit = request.args.get('limit', 20, type=int)
        history = file_manager.get_execution_history(limit)
        return jsonify({"success": True, "history": history})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/files/execution/<execution_id>")
def get_execution_result(execution_id):
    try:
        for execution in file_manager.executions:
            if execution["id"] == execution_id:
                return jsonify({"success": True, "execution": execution})
        return jsonify({"success": False, "error": "Execution not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/files/upload", methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        # Save file to workspace
        filename = file.filename
        file_path = os.path.join('.', filename)
        file.save(file_path)
        
        log_event("file_uploaded", f"File '{filename}' uploaded successfully", "event")
        return jsonify({
            "success": True,
            "message": f"File '{filename}' uploaded successfully",
            "file_path": file_path
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/files/download/<path:file_path>")
def download_file(file_path):
    try:
        if not os.path.exists(file_path):
            return jsonify({"success": False, "error": "File not found"}), 404
        
        from flask import send_file
        log_event("file_downloaded", f"File downloaded: {file_path}", "event")
        return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))
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

# Start monitor thread immediately when app is created (not just in __main__)
def start_monitor_thread():
    debug_print("Starting monitor thread...")
    monitor_thread = threading.Thread(target=monitor_loop)
    monitor_thread.daemon = True
    monitor_thread.start()
    debug_print("Monitor thread started successfully")

# Start the monitor thread now
start_monitor_thread()

if __name__ == "__main__":
    log_event("startup", "Enhanced Lightning AI Dashboard starting")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)