
"""
Routes for managing startup scripts
"""
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for

startup_scripts_bp = Blueprint('startup_scripts', __name__)

@startup_scripts_bp.route('/startup-scripts')
def startup_scripts():
    """Display the startup scripts management page"""
    try:
        return render_template('startup_scripts.html')
    except Exception as e:
        print(f"Error in startup_scripts route: {e}")
        return f"Error loading startup scripts page: {str(e)}"

@startup_scripts_bp.route('/api/startup-scripts/config', methods=['GET'])
def get_startup_script_config():
    """Get the startup script configuration"""
    try:
        startup_script_service = current_app.config['STARTUP_SCRIPT_SERVICE']
        config = startup_script_service.get_config()
        return jsonify({"success": True, "config": config})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@startup_scripts_bp.route('/api/startup-scripts/config', methods=['POST'])
def update_startup_script_config():
    """Update the startup script configuration"""
    try:
        data = request.get_json()
        startup_script_service = current_app.config['STARTUP_SCRIPT_SERVICE']
        startup_script_service.update_config(data)
        return jsonify({"success": True, "message": "Configuration updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@startup_scripts_bp.route('/api/startup-scripts/execute', methods=['POST'])
def execute_startup_script_now():
    """Execute the startup script now"""
    try:
        startup_script_service = current_app.config['STARTUP_SCRIPT_SERVICE']
        result = startup_script_service.execute_now()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
