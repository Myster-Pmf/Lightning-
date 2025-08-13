"""
Main routes for the enhanced Lightning AI dashboard
"""
from flask import Blueprint, render_template, current_app
from ..utils.logging_utils import get_logs

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def dashboard():
    """Enhanced dashboard with better UI"""
    try:
        return render_template('dashboard.html')
    except Exception as e:
        print(f"Error rendering dashboard: {e}")
        # Return a simple HTML response as fallback
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Lightning AI Dashboard</title></head>
        <body>
            <h1>Lightning AI Dashboard</h1>
            <p>Dashboard is starting up...</p>
            <p>Error: {str(e)}</p>
            <p><a href="/terminal">Terminal</a> | <a href="/files">Files</a> | <a href="/debug">Debug</a></p>
        </body>
        </html>
        """

@main_bp.route('/scheduler')
def scheduler():
    """Scheduler management page"""
    try:
        scheduler_service = current_app.config.get('SCHEDULER_SERVICE')
        if scheduler_service:
            schedules = scheduler_service.get_schedules()
        else:
            schedules = []
        return render_template('scheduler.html', schedules=schedules)
    except Exception as e:
        print(f"Error in scheduler route: {e}")
        return f"Error loading scheduler: {str(e)}"

@main_bp.route('/files')
def files():
    """File management page"""
    try:
        file_service = current_app.config.get('FILE_SERVICE')
        if file_service:
            files = file_service.get_workspace_files()
            execution_history = file_service.get_execution_history()
        else:
            files = []
            execution_history = []
        return render_template('files.html', files=files, execution_history=execution_history)
    except Exception as e:
        print(f"Error in files route: {e}")
        return f"Error loading files: {str(e)}"

@main_bp.route('/terminal')
def terminal():
    """Enhanced terminal page"""
    try:
        return render_template('terminal.html')
    except Exception as e:
        print(f"Error in terminal route: {e}")
        return f"Error loading terminal: {str(e)}"

@main_bp.route('/logs')
def logs():
    """Enhanced logs page"""
    try:
        logs_data = get_logs(hours=24, limit=500)
        return render_template('logs.html', logs=logs_data)
    except Exception as e:
        print(f"Error in logs route: {e}")
        return f"Error loading logs: {str(e)}"

@main_bp.route('/debug')
def debug():
    """Enhanced debug page"""
    try:
        lightning_service = current_app.config.get('LIGHTNING_SERVICE')
        
        # Get debug information
        debug_info = {
            'studio_name': current_app.config.get('STUDIO_NAME'),
            'teamspace': current_app.config.get('TEAMSPACE'),
            'username': current_app.config.get('USERNAME'),
            'logging_system': 'Local JSON Files',
            'logs_location': 'data/studio_logs.json'
        }
        
        # Get studio status
        if lightning_service:
            status, error = lightning_service.get_status()
            debug_info['studio_status'] = status
            if error:
                debug_info['studio_error'] = error
        else:
            debug_info['studio_status'] = 'Service not available'
        
        return render_template('debug.html', debug_info=debug_info)
    except Exception as e:
        print(f"Error in debug route: {e}")
        return f"Error loading debug page: {str(e)}"