"""
Service for managing and executing startup scripts
"""
import os
import json
import time
import uuid
from threading import Lock, Thread
from ..utils.logging_utils import debug_print, log_event

class StartupScriptService:
    """Service for managing startup scripts"""

    def __init__(self, lightning_service, file_service):
        self.lightning_service = lightning_service
        self.file_service = file_service
        self.config = {}
        self.executions = {}
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
                    "commands": "",
                    "debug_mode": False
                }
                self._save_config()
        except Exception as e:
            debug_print(f"Error loading startup script config: {e}")
            self.config = {
                "enabled": False,
                "files": [],
                "commands": "",
                "debug_mode": False
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

        execution_id = str(uuid.uuid4())
        self.executions[execution_id] = {
            "status": "starting",
            "output": "",
            "start_time": time.time(),
            "end_time": None
        }

        thread = Thread(target=self._execute, args=(execution_id,))
        thread.start()

        return {"success": True, "execution_id": execution_id}

    def execute_on_startup(self):
        """Execute the startup script on studio startup"""
        if not self.config.get("enabled"):
            return

        log_event("startup_script_execution_triggered", "Startup script execution triggered on studio startup", "event")
        execution_id = str(uuid.uuid4())
        self.executions[execution_id] = {
            "status": "starting",
            "output": "",
            "start_time": time.time(),
            "end_time": None
        }

        thread = Thread(target=self._execute, args=(execution_id,))
        thread.start()

    def get_execution_status(self, execution_id):
        """Get the status of an execution"""
        return self.executions.get(execution_id)

    def _execute(self, execution_id):
        """The actual execution logic"""
        self.executions[execution_id]["status"] = "running"
        output = []

        def log_and_append(message):
            log_event("startup_script_execution", message, "event")
            output.append(message)
            self.executions[execution_id]["output"] = "\n".join(output)

        try:
            # Step 1: Check and install tmux
            log_and_append("Checking for tmux...")
            tmux_check_command = "command -v tmux"
            result = self.file_service.run_remote_command(tmux_check_command)
            if not result["success"] or not result["stdout"]:
                log_and_append("tmux not found, installing...")
                install_tmux_command = "apt-get update && apt-get install -y tmux"
                result = self.file_service.run_remote_command(install_tmux_command)
                if not result["success"]:
                    raise Exception(f"Failed to install tmux: {result['stderr']}")
            log_and_append("tmux is installed.")

            # Step 2: Upload files
            files_to_upload = self.config.get("files", [])
            if files_to_upload:
                log_and_append("Uploading files...")
                remote_dir, err = self.file_service.get_remote_working_directory()
                if err:
                    raise Exception(f"Could not determine remote working directory: {err}")

                for file_path in files_to_upload:
                    if os.path.exists(file_path):
                        file_name = os.path.basename(file_path)
                        remote_file_path = f"{remote_dir}/{file_name}"
                        log_and_append(f"Uploading {file_path} to {remote_file_path}...")
                        upload_result = self.file_service.upload_to_remote(file_path, remote_file_path)
                        if not upload_result["success"]:
                            raise Exception(f"Failed to upload {file_path}: {upload_result['error']}")
                    else:
                        log_and_append(f"File not found, skipping: {file_path}")
                log_and_append("File upload complete.")

            # Step 3: Execute commands in tmux
            commands = self.config.get("commands", "")
            if commands:
                log_and_append("Executing commands in tmux...")
                session_name = f"startup_script_{int(time.time())}"
                create_session_command = f"tmux new-session -d -s {session_name}"
                result = self.file_service.run_remote_command(create_session_command)
                if not result["success"]:
                    raise Exception(f"Failed to create tmux session: {result['stderr']}")

                for command in commands.splitlines():
                    if command.strip():
                        log_and_append(f"Executing: {command.strip()}")
                        send_command = f"tmux send-keys -t {session_name} '{command.strip()}' C-m"
                        result = self.file_service.run_remote_command(send_command)
                        if not result["success"]:
                            log_and_append(f"Failed to send command to tmux: {command}")

                # Capture output from tmux session
                if self.config.get("debug_mode"):
                    time.sleep(5) # Wait for commands to execute
                    capture_command = f"tmux capture-pane -p -t {session_name}"
                    result = self.file_service.run_remote_command(capture_command)
                    if result["success"]:
                        log_and_append("--- TMUX OUTPUT ---")
                        log_and_append(result["stdout"])

            log_and_append("Startup script executed successfully.")
            self.executions[execution_id]["status"] = "completed"

        except Exception as e:
            log_and_append(f"Error during startup script execution: {e}")
            self.executions[execution_id]["status"] = "failed"
        finally:
            self.executions[execution_id]["end_time"] = time.time()