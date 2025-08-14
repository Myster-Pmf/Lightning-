"""
Enhanced Lightning AI service with better error handling and monitoring
"""
import os
import time
import traceback
from datetime import datetime
from lightning_sdk import Studio, Machine
from ..utils.logging_utils import debug_print, log_event

class LightningService:
    """Enhanced Lightning AI service"""
    
    def __init__(self):
        self.studio = None
        self.last_known_status = None
        self._initialize_studio()
    
    def _initialize_studio(self):
        """Initialize the Studio object"""
        try:
            self.studio = Studio(
                os.getenv("STUDIO_NAME"),
                teamspace=os.getenv("TEAMSPACE"),
                user=os.getenv("USERNAME"),
                create_ok=True
            )
            debug_print("Studio object created successfully")
        except Exception as e:
            debug_print(f"Failed to create Studio object: {e}")
            self.studio = None
    
    def get_status(self):
        """Get current studio status"""
        try:
            if not self.studio:
                return "error", "Studio not initialized"
            
            status = str(self.studio.status)
            return status, None
            
        except Exception as e:
            error_msg = str(e)
            debug_print(f"Error getting studio status: {error_msg}")
            return "error", error_msg
    
    def get_uptime(self):
        """Get studio uptime using uptime -p command - simple method like terminal"""
        try:
            if not self.studio:
                return None, "Studio not initialized"
            
            status = str(self.studio.status)
            if status != 'running':
                return None, f"Studio is not running (status: {status})"
            
            # Use the same method as terminal - direct studio.run
            debug_print("Attempting to get uptime using studio.run('uptime -p')")
            result = self.studio.run("uptime -p")
            
            if result:
                uptime_output = str(result).strip()
                debug_print(f"Uptime command result: '{uptime_output}'")
                
                if uptime_output and not uptime_output.lower().startswith('error'):
                    # Clean up the output - remove any extra whitespace or newlines
                    cleaned_uptime = ' '.join(uptime_output.split())
                    return cleaned_uptime, None
                else:
                    return None, f"Invalid uptime output: {uptime_output}"
            else:
                debug_print("Uptime command returned None/empty result")
                return None, "Uptime command returned no output"
                
        except Exception as e:
            error_msg = str(e)
            debug_print(f"Error getting studio uptime: {error_msg}")
            traceback.print_exc()
            return None, error_msg
    
    def start_studio(self, machine_type=None):
        """Start the studio with specified machine type"""
        start_time = datetime.now()
        try:
            if not self.studio:
                raise Exception("Studio not initialized")
            
            # Default to CPU if no machine type specified
            if machine_type is None:
                machine_type = Machine.CPU
            
            log_event("studio_start_begin", f"Starting studio with {machine_type}", "event", {
                "machine_type": str(machine_type),
                "start_time": start_time.isoformat()
            })
            
            self.studio.start(machine_type)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            log_event("studio_start_success", f"Studio started successfully with {machine_type}", "event", {
                "machine_type": str(machine_type),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration
            })
            return True, "Studio start command sent successfully"
            
        except Exception as e:
            error_msg = str(e)
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            log_event("studio_start_error", f"Failed to start studio: {error_msg}", "error", {
                "machine_type": str(machine_type) if machine_type else "unknown",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "error": error_msg
            })
            return False, error_msg
    
    def stop_studio(self):
        """Stop the studio"""
        start_time = datetime.now()
        try:
            if not self.studio:
                raise Exception("Studio not initialized")
            
            log_event("studio_stop_begin", "Stopping studio", "event", {
                "start_time": start_time.isoformat()
            })
            
            self.studio.stop()
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            log_event("studio_stop_success", "Studio stop command sent successfully", "event", {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration
            })
            return True, "Studio stop command sent successfully"
            
        except Exception as e:
            error_msg = str(e)
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            log_event("studio_stop_error", f"Failed to stop studio: {error_msg}", "error", {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "error": error_msg
            })
            return False, error_msg
    
    def restart_studio(self, machine_type=None):
        """Restart the studio"""
        try:
            # First stop the studio
            stop_success, stop_message = self.stop_studio()
            if not stop_success:
                return False, f"Failed to stop studio: {stop_message}"
            
            # Wait a bit for the stop to take effect
            time.sleep(5)
            
            # Then start it again
            start_success, start_message = self.start_studio(machine_type)
            if not start_success:
                return False, f"Failed to start studio after stop: {start_message}"
            
            log_event("studio_restart_success", "Studio restarted successfully", "event")
            return True, "Studio restart initiated successfully"
            
        except Exception as e:
            error_msg = str(e)
            log_event("studio_restart_error", f"Failed to restart studio: {error_msg}", "error")
            return False, error_msg
    
    def get_machine_types(self):
        """Get available machine types"""
        return [
            {"name": "CPU", "value": "CPU", "description": "Basic CPU machine"},
            {"name": "GPU", "value": "GPU", "description": "GPU-enabled machine"},
            {"name": "GPU_FAST", "value": "GPU_FAST", "description": "High-performance GPU machine"},
        ]
    
    def monitor_loop(self):
        """Enhanced monitoring loop with better error handling"""
        debug_print("Starting enhanced monitor loop")
        
        while True:
            try:
                if not self.studio:
                    debug_print("Studio object is None, attempting to reinitialize...")
                    self._initialize_studio()
                    if not self.studio:
                        time.sleep(300)
                        continue
                
                # Get current status
                status, error = self.get_status()
                
                # Log heartbeat
                log_event(
                    "status_check", 
                    f"Current status: {status}",
                    "heartbeat",
                    {"status": status, "error": error}
                )
                
                # Log status changes
                if status != self.last_known_status:
                    log_event(
                        "state_change",
                        f"Status changed from '{self.last_known_status}' to '{status}'",
                        "event",
                        {"from": self.last_known_status, "to": status}
                    )
                    self.last_known_status = status
                
            except Exception as e:
                error_msg = f"Exception in monitor loop: {e}"
                debug_print(f"CRITICAL: {error_msg}\n{traceback.format_exc()}")
                log_event("monitor_error", error_msg, "error")
            
            # Wait before next check (5 minutes)
            time.sleep(300)