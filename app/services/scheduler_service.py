"""
Enhanced scheduler service for automated studio management
"""
import os
import json
import time
import subprocess
try:
    import pytz
except ImportError:
    print("Warning: pytz not available, timezone features will be limited")
    pytz = None
from datetime import datetime, timedelta
from threading import Lock
from ..utils.logging_utils import debug_print, log_event

class SchedulerService:
    """Service for scheduling studio operations and executing commands"""
    
    def __init__(self):
        self.schedules = []
        self.lock = Lock()
        self.schedules_file = "data/schedules.json"
        self.auto_restart_file = "data/auto_restart.json"
        self.auto_restart_history_file = "data/auto_restart_history.json"
        self.auto_restart_config = None
        self.last_uptime_check = None
        self._load_schedules()
        self._load_auto_restart_config()
    
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
            user_timezone = schedule_data.get("timezone", "UTC")
            
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
                "timezone": user_timezone,
                "enabled": True,
                "created_at": datetime.now().isoformat(),
                "last_run": None,
                "next_run": self._calculate_next_run(schedule_data, user_timezone)
            }
            
            self.schedules.append(schedule)
            self._save_schedules()
            
            log_event("schedule_added", f"Schedule '{schedule['name']}' added", "event", schedule)
            return schedule_id
    
    def _calculate_next_run(self, schedule_data, user_timezone='UTC'):
        """Calculate the next run time for a schedule with timezone conversion"""
        # Fallback to simple datetime if pytz is not available
        if not pytz:
            now = datetime.now()
            debug_print(f"Warning: pytz not available, using local time for schedule calculation")
        else:
            try:
                # Get timezone objects
                user_tz = pytz.timezone(user_timezone) if user_timezone != 'UTC' else pytz.UTC
                server_tz = pytz.UTC
                
                now_utc = datetime.now(server_tz)
                now_user = now_utc.astimezone(user_tz)
                now = now_user
                debug_print(f"Using timezone: {user_timezone}, current time: {now}")
            except Exception as e:
                debug_print(f"Error with timezone {user_timezone}: {e}, falling back to UTC")
                now = datetime.now(pytz.UTC)
        
        if schedule_data.get("schedule_type") == "once":
            datetime_str = schedule_data.get("datetime")
            if datetime_str:
                try:
                    # Parse user's local datetime
                    user_dt = datetime.fromisoformat(datetime_str.replace('Z', ''))
                    # Localize to user timezone
                    user_dt = user_tz.localize(user_dt)
                    if pytz:
                        # Convert to UTC
                        utc_dt = user_dt.astimezone(server_tz)
                        return utc_dt.isoformat()
                    else:
                        return user_dt.isoformat()
                except Exception as e:
                    debug_print(f"Error parsing datetime: {e}")
                    return None
        
        elif schedule_data.get("schedule_type") == "daily":
            time_str = schedule_data.get("time")
            if time_str:
                try:
                    hour, minute = map(int, time_str.split(':'))
                    # Create next run in user timezone
                    next_run_user = now_user.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if next_run_user <= now_user:
                        next_run_user += timedelta(days=1)
                    # Convert to UTC
                    next_run_utc = next_run_user.astimezone(server_tz)
                    return next_run_utc.isoformat()
                except Exception as e:
                    debug_print(f"Error calculating daily schedule: {e}")
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
                    
                    # Find next occurrence in user timezone
                    for days_ahead in range(7):
                        candidate = now_user + timedelta(days=days_ahead)
                        if candidate.weekday() in target_weekdays:
                            next_run_user = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
                            if next_run_user > now_user:
                                # Convert to UTC
                                next_run_utc = next_run_user.astimezone(server_tz)
                                return next_run_utc.isoformat()
                    
                    # If no valid time found in next 7 days, schedule for next week
                    next_week = now_user + timedelta(days=7)
                    target_weekday = min(target_weekdays)
                    days_until_target = (target_weekday - next_week.weekday()) % 7
                    next_run_user = next_week + timedelta(days=days_until_target)
                    next_run_user = next_run_user.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    # Convert to UTC
                    next_run_utc = next_run_user.astimezone(server_tz)
                    return next_run_utc.isoformat()
                except Exception as e:
                    debug_print(f"Error calculating weekly schedule: {e}")
                    return None
        
        return None
    
    def _load_auto_restart_config(self):
        """Load auto-restart configuration"""
        self._ensure_data_dir()
        try:
            if os.path.exists(self.auto_restart_file):
                with open(self.auto_restart_file, 'r') as f:
                    self.auto_restart_config = json.load(f)
                    debug_print(f"Loaded auto-restart config: {self.auto_restart_config}")
            else:
                # Default auto-restart config
                self.auto_restart_config = {
                    "enabled": False,
                    "method": "interval",  # "interval" or "uptime"
                    "interval_minutes": 210,  # 3.5 hours
                    "uptime_threshold": "3 hours 50 minutes",
                    "post_restart_commands": [],
                    "last_restart": None,
                    "next_restart": None
                }
                self._save_auto_restart_config()
        except Exception as e:
            debug_print(f"Error loading auto-restart config: {e}")
            self.auto_restart_config = {
                "enabled": False,
                "method": "interval",
                "interval_minutes": 210,
                "uptime_threshold": "3 hours 50 minutes",
                "post_restart_commands": [],
                "last_restart": None,
                "next_restart": None
            }

    def _save_auto_restart_config(self):
        """Save auto-restart configuration"""
        self._ensure_data_dir()
        try:
            with open(self.auto_restart_file, 'w') as f:
                json.dump(self.auto_restart_config, f, indent=2)
        except Exception as e:
            debug_print(f"Error saving auto-restart config: {e}")

    def _save_auto_restart_history(self, history_entry):
        """Save auto-restart history entry"""
        self._ensure_data_dir()
        try:
            history = []
            if os.path.exists(self.auto_restart_history_file):
                with open(self.auto_restart_history_file, 'r') as f:
                    history = json.load(f)
            
            history.append(history_entry)
            # Keep only last 50 entries
            if len(history) > 50:
                history = history[-50:]
            
            with open(self.auto_restart_history_file, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            debug_print(f"Error saving auto-restart history: {e}")

    def get_schedules(self):
        """Get all schedules with countdown timers"""
        with self.lock:
            schedules = self.schedules.copy()
            now = datetime.now(pytz.UTC)
            
            for schedule in schedules:
                if schedule.get("next_run"):
                    try:
                        next_run = datetime.fromisoformat(schedule["next_run"].replace('Z', '+00:00'))
                        if next_run.tzinfo is None:
                            next_run = pytz.UTC.localize(next_run)
                        
                        time_diff = next_run - now
                        if time_diff.total_seconds() > 0:
                            schedule["countdown_seconds"] = int(time_diff.total_seconds())
                            schedule["countdown_text"] = self._format_countdown(time_diff.total_seconds())
                        else:
                            schedule["countdown_seconds"] = 0
                            schedule["countdown_text"] = "Overdue"
                    except Exception as e:
                        debug_print(f"Error calculating countdown for schedule {schedule['id']}: {e}")
                        schedule["countdown_seconds"] = 0
                        schedule["countdown_text"] = "Error"
            
            return schedules

    def _format_countdown(self, seconds):
        """Format countdown seconds into human readable text"""
        if seconds <= 0:
            return "Overdue"
        
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 and days == 0:  # Only show seconds if less than a day
            parts.append(f"{secs}s")
        
        return " ".join(parts) if parts else "0s"
    
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
        """Main scheduler loop with auto-restart functionality"""
        debug_print("Starting scheduler service with auto-restart")
        
        while True:
            try:
                now = datetime.now(pytz.UTC)
                
                # Check auto-restart
                self._check_auto_restart(now)
                
                # Check regular schedules
                with self.lock:
                    for schedule in self.schedules:
                        if not schedule["enabled"]:
                            continue
                        
                        next_run_str = schedule.get("next_run")
                        if not next_run_str:
                            continue
                        
                        try:
                            next_run = datetime.fromisoformat(next_run_str.replace('Z', '+00:00'))
                            if next_run.tzinfo is None:
                                next_run = pytz.UTC.localize(next_run)
                            
                            if now >= next_run:
                                self._execute_schedule(schedule)
                        except Exception as e:
                            debug_print(f"Error parsing next_run for schedule {schedule['id']}: {e}")
                
            except Exception as e:
                debug_print(f"Error in scheduler loop: {e}")
                log_event("scheduler_error", f"Scheduler loop error: {e}", "error")
            
            # Check every 5 minutes
            time.sleep(300)
    
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
                user_timezone = schedule.get("timezone", "UTC")
                schedule["next_run"] = self._calculate_next_run(schedule, user_timezone)
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

    def _check_auto_restart(self, now):
        """Check if auto-restart should be triggered"""
        if not self.auto_restart_config or not self.auto_restart_config.get("enabled"):
            return

        try:
            from flask import current_app
            lightning_service = current_app.config.get('LIGHTNING_SERVICE')
            
            if not lightning_service:
                return

            # Get current studio status
            status, error = lightning_service.get_status()
            if status != 'running':
                return  # Only restart if studio is running

            method = self.auto_restart_config.get("method", "interval")
            
            if method == "interval":
                self._check_interval_restart(now, lightning_service)
            elif method == "uptime":
                self._check_uptime_restart(now, lightning_service)
                
        except Exception as e:
            debug_print(f"Error in auto-restart check: {e}")

    def _check_interval_restart(self, now, lightning_service):
        """Check interval-based auto-restart"""
        interval_minutes = self.auto_restart_config.get("interval_minutes", 210)
        last_restart = self.auto_restart_config.get("last_restart")
        
        if last_restart:
            last_restart_dt = datetime.fromisoformat(last_restart.replace('Z', '+00:00'))
            if last_restart_dt.tzinfo is None:
                last_restart_dt = pytz.UTC.localize(last_restart_dt)
            
            time_since_restart = now - last_restart_dt
            if time_since_restart.total_seconds() >= (interval_minutes * 60):
                self._execute_auto_restart(lightning_service, "interval")
        else:
            # No previous restart, set the timer
            self.auto_restart_config["last_restart"] = now.isoformat()
            self._save_auto_restart_config()

    def _check_uptime_restart(self, now, lightning_service):
        """Check uptime-based auto-restart"""
        uptime, uptime_error = lightning_service.get_uptime()
        
        if uptime_error or not uptime:
            return
        
        # Parse uptime threshold (e.g., "3 hours 50 minutes")
        threshold = self.auto_restart_config.get("uptime_threshold", "3 hours 50 minutes")
        threshold_seconds = self._parse_uptime_threshold(threshold)
        
        # Parse current uptime
        current_uptime_seconds = self._parse_uptime_output(uptime)
        
        if current_uptime_seconds >= threshold_seconds:
            self._execute_auto_restart(lightning_service, "uptime")

    def _parse_uptime_threshold(self, threshold):
        """Parse uptime threshold string to seconds"""
        try:
            parts = threshold.lower().split()
            total_seconds = 0
            
            i = 0
            while i < len(parts):
                if i + 1 < len(parts):
                    value = int(parts[i])
                    unit = parts[i + 1]
                    
                    if 'hour' in unit:
                        total_seconds += value * 3600
                    elif 'minute' in unit:
                        total_seconds += value * 60
                    elif 'day' in unit:
                        total_seconds += value * 86400
                    
                    i += 2
                else:
                    i += 1
            
            return total_seconds
        except:
            return 13800  # Default: 3 hours 50 minutes

    def _parse_uptime_output(self, uptime):
        """Parse uptime -p output to seconds"""
        try:
            # uptime -p output: "up 2 hours, 30 minutes"
            parts = uptime.lower().replace(',', '').split()
            total_seconds = 0
            
            i = 0
            while i < len(parts):
                if i + 1 < len(parts) and parts[i].isdigit():
                    value = int(parts[i])
                    unit = parts[i + 1]
                    
                    if 'hour' in unit:
                        total_seconds += value * 3600
                    elif 'minute' in unit:
                        total_seconds += value * 60
                    elif 'day' in unit:
                        total_seconds += value * 86400
                    
                    i += 2
                else:
                    i += 1
            
            return total_seconds
        except:
            return 0

    def _execute_auto_restart(self, lightning_service, trigger_type):
        """Execute auto-restart"""
        start_time = datetime.now(pytz.UTC)
        
        try:
            log_event("auto_restart_begin", f"Auto-restart triggered by {trigger_type}", "event", {
                "trigger_type": trigger_type,
                "start_time": start_time.isoformat()
            })
            
            # Execute restart
            success, message = lightning_service.restart_studio()
            
            if success:
                # Execute post-restart commands after delay
                commands = self.auto_restart_config.get("post_restart_commands", [])
                if commands:
                    import threading
                    def delayed_commands():
                        time.sleep(60)  # Wait for studio to be ready
                        command_start = datetime.now(pytz.UTC)
                        self.execute_post_start_commands(commands)
                        command_end = datetime.now(pytz.UTC)
                        command_duration = (command_end - command_start).total_seconds()
                        
                        # Update history with command execution time
                        end_time = datetime.now(pytz.UTC)
                        total_duration = (end_time - start_time).total_seconds()
                        
                        history_entry = {
                            "timestamp": start_time.isoformat(),
                            "trigger_type": trigger_type,
                            "success": True,
                            "total_duration_seconds": total_duration,
                            "command_duration_seconds": command_duration,
                            "commands_executed": len(commands),
                            "message": message
                        }
                        self._save_auto_restart_history(history_entry)
                    
                    threading.Thread(target=delayed_commands, daemon=True).start()
                else:
                    # No commands, save history immediately
                    end_time = datetime.now(pytz.UTC)
                    total_duration = (end_time - start_time).total_seconds()
                    
                    history_entry = {
                        "timestamp": start_time.isoformat(),
                        "trigger_type": trigger_type,
                        "success": True,
                        "total_duration_seconds": total_duration,
                        "command_duration_seconds": 0,
                        "commands_executed": 0,
                        "message": message
                    }
                    self._save_auto_restart_history(history_entry)
                
                # Update last restart time
                self.auto_restart_config["last_restart"] = start_time.isoformat()
                self._save_auto_restart_config()
                
                log_event("auto_restart_success", "Auto-restart completed successfully", "event", {
                    "trigger_type": trigger_type,
                    "duration_seconds": (datetime.now(pytz.UTC) - start_time).total_seconds()
                })
            else:
                # Save failed restart to history
                end_time = datetime.now(pytz.UTC)
                total_duration = (end_time - start_time).total_seconds()
                
                history_entry = {
                    "timestamp": start_time.isoformat(),
                    "trigger_type": trigger_type,
                    "success": False,
                    "total_duration_seconds": total_duration,
                    "command_duration_seconds": 0,
                    "commands_executed": 0,
                    "message": message
                }
                self._save_auto_restart_history(history_entry)
                
                log_event("auto_restart_error", f"Auto-restart failed: {message}", "error", {
                    "trigger_type": trigger_type,
                    "error": message
                })
                
        except Exception as e:
            error_msg = str(e)
            log_event("auto_restart_exception", f"Auto-restart exception: {error_msg}", "error", {
                "trigger_type": trigger_type,
                "error": error_msg
            })

    # Auto-restart management methods
    def get_auto_restart_config(self):
        """Get auto-restart configuration"""
        return self.auto_restart_config.copy() if self.auto_restart_config else None

    def update_auto_restart_config(self, config_data):
        """Update auto-restart configuration"""
        with self.lock:
            self.auto_restart_config.update(config_data)
            self._save_auto_restart_config()
            log_event("auto_restart_config_updated", "Auto-restart configuration updated", "event", config_data)

    def get_auto_restart_history(self, limit=20):
        """Get auto-restart history"""
        try:
            if os.path.exists(self.auto_restart_history_file):
                with open(self.auto_restart_history_file, 'r') as f:
                    history = json.load(f)
                # Return most recent entries first
                return history[-limit:] if len(history) > limit else history
            return []
        except Exception as e:
            debug_print(f"Error loading auto-restart history: {e}")
            return []