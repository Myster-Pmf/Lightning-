"""
API routes for the enhanced Lightning AI dashboard
"""
import time
import threading
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app
from lightning_sdk import Machine
from ..utils.logging_utils import get_logs, log_event

api_bp = Blueprint('api', __name__)

@api_bp.route('/status')
def get_status():
    """Get current studio status"""
    lightning_service = current_app.config['LIGHTNING_SERVICE']
    status, error = lightning_service.get_status()
    
    return jsonify({
        'status': status,
        'error': error,
        'timestamp': datetime.now().isoformat()
    })

@api_bp.route('/logs')
def get_logs_api():
    """Get logs for dashboard charts"""
    range_arg = request.args.get('range', '1h')
    hours = 1 if range_arg == '1h' else 24
    
    logs = get_logs(hours=hours, limit=2000)
    
    # Get current status
    lightning_service = current_app.config['LIGHTNING_SERVICE']
    current_status, error = lightning_service.get_status()
    
    return jsonify({
        'logs': logs,
        'live_status': {
            'status': current_status,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
    })

@api_bp.route('/start', methods=['POST'])
def start_studio():
    """Start the studio"""
    data = request.get_json() or {}
    machine_type_str = data.get('machine_type', 'CPU')
    
    # Convert string to Machine enum
    try:
        machine_type = getattr(Machine, machine_type_str)
    except AttributeError:
        machine_type = Machine.CPU
    
    start_id = f"start_{int(time.time())}"
    
    # Store initial task status
    current_app.config['ASYNC_TASKS'][start_id] = {
        "status": "starting",
        "start_time": datetime.now().isoformat()
    }
    
    # Start async task with app context
    app = current_app._get_current_object()
    def start_async_with_context():
        with app.app_context():
            lightning_service = current_app.config['LIGHTNING_SERVICE']
            
            try:
                success, message = lightning_service.start_studio(machine_type)
                current_app.config['ASYNC_TASKS'][start_id] = {
                    "status": "completed",
                    "success": success,
                    "message": message
                }
            except Exception as e:
                current_app.config['ASYNC_TASKS'][start_id] = {
                    "status": "completed",
                    "success": False,
                    "error": str(e)
                }
    
    thread = threading.Thread(target=start_async_with_context)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "result": "start_initiated",
        "start_id": start_id
    })

@api_bp.route('/start/progress/<start_id>')
def start_progress(start_id):
    """Get start progress"""
    task = current_app.config['ASYNC_TASKS'].get(start_id)
    
    if not task:
        return jsonify({"error": "Start ID not found"}), 404
    
    if task['status'] == 'starting':
        elapsed = (datetime.now() - datetime.fromisoformat(task['start_time'])).total_seconds()
        return jsonify({
            "status": "starting",
            "elapsed_seconds": elapsed
        })
    else:
        return jsonify(task)

@api_bp.route('/stop', methods=['POST'])
def stop_studio():
    """Stop the studio"""
    lightning_service = current_app.config['LIGHTNING_SERVICE']
    
    try:
        success, message = lightning_service.stop_studio()
        return jsonify({
            "success": success,
            "message": message
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@api_bp.route('/restart', methods=['POST'])
def restart_studio():
    """Restart the studio"""
    data = request.get_json() or {}
    machine_type_str = data.get('machine_type', 'CPU')
    
    # Convert string to Machine enum
    try:
        machine_type = getattr(Machine, machine_type_str)
    except AttributeError:
        machine_type = Machine.CPU
    
    lightning_service = current_app.config['LIGHTNING_SERVICE']
    
    try:
        success, message = lightning_service.restart_studio(machine_type)
        return jsonify({
            "success": success,
            "message": message
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@api_bp.route('/machine-types')
def get_machine_types():
    """Get available machine types"""
    lightning_service = current_app.config['LIGHTNING_SERVICE']
    machine_types = lightning_service.get_machine_types()
    
    return jsonify(machine_types)

# Python interpreter session (from original code)
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
            import traceback
            return {"success": False, "error": str(e), "traceback": traceback.format_exc()}

    def reset(self):
        import os
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

# Global interpreter instance
python_interpreter = PythonInterpreter()

@api_bp.route('/terminal/python', methods=['POST'])
def execute_python():
    """Execute Python code in terminal"""
    data = request.get_json()
    if not data or 'code' not in data:
        return jsonify({"success": False, "error": "No code provided."}), 400
    
    return jsonify(python_interpreter.execute(data['code']))

@api_bp.route('/terminal/reset', methods=['POST'])
def reset_interpreter():
    """Reset Python interpreter"""
    python_interpreter.reset()
    return jsonify({"success": True, "message": "Python interpreter session has been reset."})