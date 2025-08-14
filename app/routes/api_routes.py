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
    try:
        lightning_service = current_app.config['LIGHTNING_SERVICE']
        
        if not lightning_service:
            return jsonify({
                'status': 'error',
                'error': 'Lightning service not available',
                'uptime': None,
                'uptime_error': 'Service not initialized',
                'timestamp': datetime.now().isoformat()
            })
        
        status, error = lightning_service.get_status()
        
        # Get uptime if studio is running using the proper service method
        uptime = None
        uptime_error = None
        if 'running' in status.lower():
            uptime, uptime_error = lightning_service.get_uptime()
        
        return jsonify({
            'status': status,
            'error': error,
            'uptime': uptime,
            'uptime_error': uptime_error,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'API error: {str(e)}',
            'uptime': None,
            'uptime_error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@api_bp.route('/logs')
def get_logs_api():
    """Get logs for dashboard charts"""
    try:
        range_arg = request.args.get('range', '1h')
        hours = 1 if range_arg == '1h' else 24
        
        logs = get_logs(hours=hours, limit=2000)
        
        # Get current status
        lightning_service = current_app.config['LIGHTNING_SERVICE']
        
        if not lightning_service:
            return jsonify({
                'logs': logs,
                'live_status': {
                    'status': 'error',
                    'error': 'Lightning service not available',
                    'uptime': None,
                    'uptime_error': 'Service not initialized',
                    'timestamp': datetime.now().isoformat()
                }
            })
        
        current_status, error = lightning_service.get_status()
        
        # Get uptime if studio is running using the proper service method
        uptime = None
        uptime_error = None
        if 'running' in current_status.lower():
            uptime, uptime_error = lightning_service.get_uptime()
        
        return jsonify({
            'logs': logs,
            'live_status': {
                'status': current_status,
                'error': error,
                'uptime': uptime,
                'uptime_error': uptime_error,
                'timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({
            'logs': [],
            'live_status': {
                'status': 'error',
                'error': f'API error: {str(e)}',
                'uptime': None,
                'uptime_error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        }), 500

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

@api_bp.route('/debug/services')
def debug_services():
    """Debug endpoint to check service status"""
    try:
        lightning_service = current_app.config.get('LIGHTNING_SERVICE')
        scheduler_service = current_app.config.get('SCHEDULER_SERVICE')
        file_service = current_app.config.get('FILE_SERVICE')
        
        debug_info = {
            "lightning_service": {
                "available": lightning_service is not None,
                "studio_initialized": lightning_service.studio is not None if lightning_service else False
            },
            "scheduler_service": {
                "available": scheduler_service is not None,
                "schedules_count": len(scheduler_service.get_schedules()) if scheduler_service else 0
            },
            "file_service": {
                "available": file_service is not None
            },
            "pytz_available": False,
            "uptime_test": None
        }
        
        # Test pytz
        try:
            import pytz
            debug_info["pytz_available"] = True
        except ImportError:
            debug_info["pytz_available"] = False
        
        # Test uptime functionality
        if lightning_service:
            try:
                uptime, uptime_error = lightning_service.get_uptime()
                debug_info["uptime_test"] = {
                    "uptime": uptime,
                    "error": uptime_error
                }
            except Exception as e:
                debug_info["uptime_test"] = {"error": str(e)}
        
        return jsonify({
            "success": True,
            "debug_info": debug_info
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500