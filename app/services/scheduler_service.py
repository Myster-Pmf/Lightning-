"""
Enhanced scheduler service for automated studio management
"""
import os
import json
import time
import subprocess
from datetime import datetime, timedelta
from threading import Lock
from ..utils.logging_utils import debug_print, log_event

class SchedulerService:
    """Service for scheduling studio operations and executing commands"""
    
    def __init__(self):
        self.schedules = []
        self.lock = Lock()
        self.schedules_file = "data/schedules.json"
        self._load_schedules()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        os.makedirs("data", exist_ok=True)
    
    def _load_schedules(self):
        """Load schedules from file"""
        self._ensure_data_dir()
        try:
            if os.path.exists(self.schedules_file):
                with open(self.schedules_file, 'r') as f:
                    self.schedules = json.load(f)
                    debug_print(f"Loaded {len(self.schedules)} schedules")
        except Exception as e:
            debug_print(f"Error loading schedules: {e}")
            self.schedules = []
    
    def _save_schedules(self):
        """Save schedules to file"""
        self._ensure_data_dir()
        try:
            with open(self.schedules_file, 'w') as f:
                json.dump(self.schedules, f, indent=2)
        except Exception as e:
            debug_print(f"Error saving schedules: {e}")
    
    def add_schedule(self, schedule_data):
        """Add a new schedule"""
        with self.lock:
            schedule_id = f"schedule_{int(time.time())}"
            schedule = {
                "id": schedule_id,
                "name": schedule_data.get("name", "Unnamed Schedule"),
                "action": schedule_data.get("action"),  # start, stop, restart
                "schedule_type": schedule_data.get("schedule_type"),  # once, daily, weekly
                "datetime": schedule_data.get("datetime"),  # For 'once' type
                "time": schedule_data.get("time"),  # For daily/weekly
                "days": schedule_data.get("days", []),  # For weekly
                "machine_type": schedule_data.get("machine_type", "CPU"),
                "post_start_commands": schedule_data.get("post_start_commands", []),
                "pre_stop_commands": schedule_data.get("pre_stop_commands", []),
                "enabled": True,
                "created_at": datetime.now().isoformat(),
                "last_run": None,
                "next_run": self._calculate_next_run(schedule_data)
            }
            
            self.schedules.append(schedule)
            self._save_schedules()
            
            log_event("schedule_added", f"Schedule '{schedule['name']}' added", "event", schedule)
            return schedule_id
    
    def _calculate_next_run(self, schedule_data):
        """Calculate the next run time for a schedule"""
        now = datetime.now()
        
        if schedule_data.get("schedule_type") == "once":
            datetime_str = schedule_data.get("datetime")
            if datetime_str:
                try:
                    return datetime.fromisoformat(datetime_str.replace('Z', '+00:00')).isoformat()
                except:
                    return None
        
        elif schedule_data.get("schedule_type") == "daily":
            time_str = schedule_data.get("time")
            if time_str:
                try:
                    hour, minute = map(int, time_str.split(':'))
                    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if next_run <= now:
                        next_run += timedelta(days=1)
                    return next_run.isoformat()
                except:
                    return None
        
        elif schedule_data.get("schedule_type") == "weekly":
            time_str = schedule_data.get("time")
            days = schedule_data.get("days", [])
            if time_str and days:
                try:
                    hour, minute = map(int, time_str.split(':'))
                    weekday_map = {
                        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                        'friday': 4, 'saturday': 5, 'sunday': 6
                    }
                    
                    target_weekdays = [weekday_map[day.lower()] for day in days if day.lower() in weekday_map]
                    if not target_weekdays:
                        return None
                    
                    # Find next occurrence
                    for days_ahead in range(7):
                        candidate = now + timedelta(days=days_ahead)
                        if candidate.weekday() in target_weekdays:
                            next_run = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            if next_run > now:
                                return next_run.isoformat()
                    
                    # If no valid time found in next 7 days, schedule for next week
                    next_week = now + timedelta(days=7)
                    target_weekday = min(target_weekdays)
                    days_until_target = (target_weekday - next_week.weekday()) % 7
                    next_run = next_week + timedelta(days=days_until_target)
                    next_run = next_run.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    return next_run.isoformat()
                except:
                    return None
        
        return None
    
    def get_schedules(self):
        """Get all schedules"""
        with self.lock:
            return self.schedules.copy()
    
    def delete_schedule(self, schedule_id):
        """Delete a schedule"""
        with self.lock:
            self.schedules = [s for s in self.schedules if s["id"] != schedule_id]
            self._save_schedules()
            log_event("schedule_deleted", f"Schedule {schedule_id} deleted", "event")
    
    def toggle_schedule(self, schedule_id):
        """Toggle schedule enabled/disabled"""
        with self.lock:
            for schedule in self.schedules:
                if schedule["id"] == schedule_id:
                    schedule["enabled"] = not schedule["enabled"]
                    self._save_schedules()
                    log_event("schedule_toggled", f"Schedule {schedule_id} {'enabled' if schedule['enabled'] else 'disabled'}", "event")
                    return schedule["enabled"]
        return None
    
    def execute_post_start_commands(self, commands):
        """Execute post-start commands"""
        for command in commands:
            try:
                debug_print(f"Executing post-start command: {command}")
                result = subprocess.run(
                    command, 
                    shell=True, 
                    capture_output=True, 
                    text=True, 
                    timeout=300
                )
                
                if result.returncode == 0:
                    log_event("command_success", f"Command executed: {command}", "event", {
                        "command": command,
                        "output": result.stdout[:500]  # Limit output length
                    })
                else:
                    log_event("command_error", f"Command failed: {command}", "error", {
                        "command": command,
                        "error": result.stderr[:500]
                    })
                    
            except subprocess.TimeoutExpired:
                log_event("command_timeout", f"Command timed out: {command}", "error")
            except Exception as e:
                log_event("command_exception", f"Command exception: {command} - {e}", "error")
    
    def run_scheduler(self):
        """Main scheduler loop"""
        debug_print("Starting scheduler service")
        
        while True:
            try:
                now = datetime.now()
                
                with self.lock:
                    for schedule in self.schedules:
                        if not schedule["enabled"]:
                            continue
                        
                        next_run_str = schedule.get("next_run")
                        if not next_run_str:
                            continue
                        
                        try:
                            next_run = datetime.fromisoformat(next_run_str.replace('Z', '+00:00'))
                            if now >= next_run:
                                self._execute_schedule(schedule)
                        except Exception as e:
                            debug_print(f"Error parsing next_run for schedule {schedule['id']}: {e}")
                
            except Exception as e:
                debug_print(f"Error in scheduler loop: {e}")
                log_event("scheduler_error", f"Scheduler loop error: {e}", "error")
            
            # Check every minute
            time.sleep(60)
    
    def _execute_schedule(self, schedule):
        """Execute a scheduled task"""
        try:
            from flask import current_app
            lightning_service = current_app.config.get('LIGHTNING_SERVICE')
            
            if not lightning_service:
                debug_print("Lightning service not available for scheduled task")
                return
            
            action = schedule["action"]
            schedule_id = schedule["id"]
            schedule_name = schedule["name"]
            
            log_event("schedule_execute", f"Executing schedule '{schedule_name}' - {action}", "event", schedule)
            
            if action == "start":
                machine_type = getattr(Machine, schedule.get("machine_type", "CPU"), Machine.CPU)
                success, message = lightning_service.start_studio(machine_type)
                
                if success and schedule.get("post_start_commands"):
                    # Execute post-start commands after a delay
                    import threading
                    def delayed_commands():
                        time.sleep(30)  # Wait for studio to be ready
                        self.execute_post_start_commands(schedule["post_start_commands"])
                    
                    threading.Thread(target=delayed_commands, daemon=True).start()
            
            elif action == "stop":
                if schedule.get("pre_stop_commands"):
                    self.execute_post_start_commands(schedule["pre_stop_commands"])
                    time.sleep(10)  # Wait for commands to complete
                
                success, message = lightning_service.stop_studio()
            
            elif action == "restart":
                machine_type = getattr(Machine, schedule.get("machine_type", "CPU"), Machine.CPU)
                success, message = lightning_service.restart_studio(machine_type)
            
            else:
                success, message = False, f"Unknown action: {action}"
            
            # Update schedule
            schedule["last_run"] = datetime.now().isoformat()
            
            # Calculate next run for recurring schedules
            if schedule["schedule_type"] != "once":
                schedule["next_run"] = self._calculate_next_run(schedule)
            else:
                schedule["enabled"] = False  # Disable one-time schedules after execution
            
            self._save_schedules()
            
            log_event(
                "schedule_completed",
                f"Schedule '{schedule_name}' completed - {message}",
                "event" if success else "error",
                {"schedule_id": schedule_id, "success": success, "message": message}
            )
            
        except Exception as e:
            error_msg = f"Error executing schedule {schedule.get('id', 'unknown')}: {e}"
            debug_print(error_msg)
            log_event("schedule_error", error_msg, "error")