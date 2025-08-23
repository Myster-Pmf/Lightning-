
"""
Service for managing and executing startup scripts
"""
import os
import json
import time
from threading import Lock
from ..utils.logging_utils import debug_print, log_event

class StartupScriptService:
    """Service for managing startup scripts"""

    def __init__(self, lightning_service, file_service):
        self.lightning_service = lightning_service
        self.file_service = file_service
        self.config = {}
        self.lock = Lock()
        self.config_file = "data/startup_scripts.json"
        self._load_config()

    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        os.makedirs("data", exist_ok=True)

    def _load_config(self):
        """Load config from file"""
        self._ensure_data_dir()
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
                    debug_print(f"Loaded startup script config")
            else:
                self.config = {
                    "enabled": False,
                    "files": [],
                    "commands": ""
                }
                self._save_config()
        except Exception as e:
            debug_print(f"Error loading startup script config: {e}")
            self.config = {
                "enabled": False,
                "files": [],
                "commands": ""
            }

    def _save_config(self):
        """Save config to file"""
        self._ensure_data_dir()
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            debug_print(f"Error saving startup script config: {e}")

    def get_config(self):
        """Get the startup script config"""
        with self.lock:
            return self.config.copy()

    def update_config(self, config_data):
        """Update the startup script config"""
        with self.lock:
            self.config.update(config_data)
            self._save_config()
            log_event("startup_script_config_updated", "Startup script configuration updated", "event", config_data)

    def execute_now(self):
        """Execute the startup script now"""
        if not self.lightning_service.studio:
            return {"success": False, "error": "Studio not initialized"}

        status, error = self.lightning_service.get_status()
        if "running" not in status.lower():
            return {"success": False, "error": "Studio is not running"}

        return self._execute()

    def execute_on_startup(self):
        """Execute the startup script on studio startup"""
        if not self.config.get("enabled"):
            return

        log_event("startup_script_execution_triggered", "Startup script execution triggered on studio startup", "event")
        result = self._execute()
        if not result["success"]:
            log_event("startup_script_execution_failed", f"Startup script execution failed: {result['error']}", "error")

    def _execute(self):
        """The actual execution logic"""
        # Step 1: Check and install tmux
        tmux_check_command = "command -v tmux"
        result = self.file_service.run_remote_command(tmux_check_command)
        if not result["success"] or not result["stdout"]:
            log_event("startup_script_installing_tmux", "tmux not found, installing...", "event")
            install_tmux_command = "apt-get update && apt-get install -y tmux"
            result = self.file_service.run_remote_command(install_tmux_command)
            if not result["success"]:
                return {"success": False, "error": f"Failed to install tmux: {result['stderr']}"}

        # Step 2: Upload files
        files_to_upload = self.config.get("files", [])
        if files_to_upload:
            remote_dir, err = self.file_service.get_remote_working_directory()
            if err:
                return {"success": False, "error": f"Could not determine remote working directory: {err}"}

            for file_path in files_to_upload:
                if os.path.exists(file_path):
                    file_name = os.path.basename(file_path)
                    remote_file_path = f"{remote_dir}/{file_name}"
                    upload_result = self.file_service.upload_to_remote(file_path, remote_file_path)
                    if not upload_result["success"]:
                        return {"success": False, "error": f"Failed to upload {file_path}: {upload_result['error']}"}
                else:
                    log_event("startup_script_file_not_found", f"File not found, skipping: {file_path}", "warning")

        # Step 3: Execute commands in tmux
        commands = self.config.get("commands", "")
        if commands:
            session_name = f"startup_script_{int(time.time())}"
            # Create a new detached tmux session
            create_session_command = f"tmux new-session -d -s {session_name}"
            result = self.file_service.run_remote_command(create_session_command)
            if not result["success"]:
                return {"success": False, "error": f"Failed to create tmux session: {result['stderr']}"}

            # Send commands to the tmux session
            for command in commands.splitlines():
                if command.strip():
                    # Send the command to the tmux session
                    send_command = f"tmux send-keys -t {session_name} '{command.strip()}' C-m"
                    result = self.file_service.run_remote_command(send_command)
                    if not result["success"]:
                        log_event("startup_script_command_failed", f"Failed to send command to tmux: {command}", "error")

        return {"success": True, "message": "Startup script executed successfully"}
