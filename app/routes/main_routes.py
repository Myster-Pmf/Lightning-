"""
Main routes for the enhanced Lightning AI dashboard
"""
from flask import Blueprint, render_template, current_app
from ..utils.logging_utils import get_logs

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def dashboard():
    """Enhanced dashboard with better UI"""
    return render_template('dashboard.html')

@main_bp.route('/scheduler')
def scheduler():
    """Scheduler management page"""
    scheduler_service = current_app.config['SCHEDULER_SERVICE']
    schedules = scheduler_service.get_schedules()
    return render_template('scheduler.html', schedules=schedules)

@main_bp.route('/files')
def files():
    """File management page"""
    file_service = current_app.config['FILE_SERVICE']
    files = file_service.get_workspace_files()
    execution_history = file_service.get_execution_history()
    return render_template('files.html', files=files, execution_history=execution_history)

@main_bp.route('/terminal')
def terminal():
    """Enhanced terminal page"""
    return render_template('terminal.html')

@main_bp.route('/logs')
def logs():
    """Enhanced logs page"""
    logs_data = get_logs(hours=24, limit=500)
    return render_template('logs.html', logs=logs_data)

@main_bp.route('/debug')
def debug():
    """Enhanced debug page"""
    lightning_service = current_app.config['LIGHTNING_SERVICE']
    
    # Get debug information
    debug_info = {
        'studio_name': current_app.config.get('STUDIO_NAME'),
        'teamspace': current_app.config.get('TEAMSPACE'),
        'username': current_app.config.get('USERNAME'),
        'supabase_url': current_app.config.get('SUPABASE_URL'),
        'supabase_api_key': '***SET***' if current_app.config.get('SUPABASE_API_KEY') else 'NOT SET'
    }
    
    # Get studio status
    status, error = lightning_service.get_status()
    debug_info['studio_status'] = status
    if error:
        debug_info['studio_error'] = error
    
    return render_template('debug.html', debug_info=debug_info)