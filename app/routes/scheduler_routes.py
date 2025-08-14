"""
Scheduler routes for managing automated studio operations
"""
from flask import Blueprint, jsonify, request, current_app, redirect, url_for, flash

scheduler_bp = Blueprint('scheduler', __name__)

@scheduler_bp.route('/add', methods=['POST'])
def add_schedule():
    """Add a new schedule"""
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
            # Convert form data for post_start_commands and pre_stop_commands
            if 'post_start_commands' in data:
                data['post_start_commands'] = [cmd.strip() for cmd in data['post_start_commands'].split('\n') if cmd.strip()]
            if 'pre_stop_commands' in data:
                data['pre_stop_commands'] = [cmd.strip() for cmd in data['pre_stop_commands'].split('\n') if cmd.strip()]
            if 'days' in data:
                data['days'] = [day.strip() for day in data['days'].split(',') if day.strip()]
        
        scheduler_service = current_app.config['SCHEDULER_SERVICE']
        schedule_id = scheduler_service.add_schedule(data)
        
        if request.is_json:
            return jsonify({
                "success": True,
                "schedule_id": schedule_id,
                "message": "Schedule added successfully"
            })
        else:
            flash("Schedule added successfully", "success")
            return redirect(url_for('main.scheduler'))
            
    except Exception as e:
        if request.is_json:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500
        else:
            flash(f"Error adding schedule: {str(e)}", "error")
            return redirect(url_for('main.scheduler'))

@scheduler_bp.route('/delete/<schedule_id>', methods=['POST', 'DELETE'])
def delete_schedule(schedule_id):
    """Delete a schedule"""
    try:
        scheduler_service = current_app.config['SCHEDULER_SERVICE']
        scheduler_service.delete_schedule(schedule_id)
        
        if request.is_json:
            return jsonify({
                "success": True,
                "message": "Schedule deleted successfully"
            })
        else:
            flash("Schedule deleted successfully", "success")
            return redirect(url_for('main.scheduler'))
            
    except Exception as e:
        if request.is_json:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500
        else:
            flash(f"Error deleting schedule: {str(e)}", "error")
            return redirect(url_for('main.scheduler'))

@scheduler_bp.route('/toggle/<schedule_id>', methods=['POST'])
def toggle_schedule(schedule_id):
    """Toggle schedule enabled/disabled"""
    try:
        scheduler_service = current_app.config['SCHEDULER_SERVICE']
        enabled = scheduler_service.toggle_schedule(schedule_id)
        
        if enabled is None:
            if request.is_json:
                return jsonify({
                    "success": False,
                    "error": "Schedule not found"
                }), 404
            else:
                flash("Schedule not found", "error")
                return redirect(url_for('main.scheduler'))
        
        if request.is_json:
            return jsonify({
                "success": True,
                "enabled": enabled,
                "message": f"Schedule {'enabled' if enabled else 'disabled'}"
            })
        else:
            flash(f"Schedule {'enabled' if enabled else 'disabled'}", "success")
            return redirect(url_for('main.scheduler'))
            
    except Exception as e:
        if request.is_json:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500
        else:
            flash(f"Error toggling schedule: {str(e)}", "error")
            return redirect(url_for('main.scheduler'))

@scheduler_bp.route('/list')
def list_schedules():
    """Get list of all schedules"""
    try:
        scheduler_service = current_app.config['SCHEDULER_SERVICE']
        schedules = scheduler_service.get_schedules()
        
        return jsonify({
            "success": True,
            "schedules": schedules
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Auto-restart management routes
@scheduler_bp.route('/auto-restart/config', methods=['GET'])
def get_auto_restart_config():
    """Get auto-restart configuration"""
    try:
        scheduler_service = current_app.config['SCHEDULER_SERVICE']
        config = scheduler_service.get_auto_restart_config()
        
        return jsonify({
            "success": True,
            "config": config
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@scheduler_bp.route('/auto-restart/config', methods=['POST'])
def update_auto_restart_config():
    """Update auto-restart configuration"""
    try:
        data = request.get_json()
        scheduler_service = current_app.config['SCHEDULER_SERVICE']
        scheduler_service.update_auto_restart_config(data)
        
        return jsonify({
            "success": True,
            "message": "Auto-restart configuration updated"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@scheduler_bp.route('/auto-restart/history')
def get_auto_restart_history():
    """Get auto-restart history"""
    try:
        limit = request.args.get('limit', 20, type=int)
        scheduler_service = current_app.config['SCHEDULER_SERVICE']
        history = scheduler_service.get_auto_restart_history(limit)
        
        return jsonify({
            "success": True,
            "history": history
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@scheduler_bp.route('/timezones')
def get_timezones():
    """Get list of available timezones"""
    try:
        import pytz
        # Get common timezones
        common_timezones = [
            'UTC',
            'US/Eastern',
            'US/Central', 
            'US/Mountain',
            'US/Pacific',
            'Europe/London',
            'Europe/Paris',
            'Europe/Berlin',
            'Asia/Tokyo',
            'Asia/Shanghai',
            'Asia/Kolkata',
            'Australia/Sydney'
        ]
        
        return jsonify({
            "success": True,
            "timezones": common_timezones
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500