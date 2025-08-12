"""
File service for managing and executing files on the Lightning AI studio
"""
import os
import json
import subprocess
import time
from datetime import datetime
from ..utils.logging_utils import debug_print, log_event

class FileService:
    """Service for managing file operations and executions"""
    
    def __init__(self):
        self.executions = []
        self.executions_file = "data/executions.json"
        self._load_executions()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        os.makedirs("data", exist_ok=True)
    
    def _load_executions(self):
        """Load execution history from file"""
        self._ensure_data_dir()
        try:
            if os.path.exists(self.executions_file):
                with open(self.executions_file, 'r') as f:
                    self.executions = json.load(f)
                    debug_print(f"Loaded {len(self.executions)} execution records")
        except Exception as e:
            debug_print(f"Error loading executions: {e}")
            self.executions = []
    
    def _save_executions(self):
        """Save execution history to file"""
        self._ensure_data_dir()
        try:
            # Keep only last 1000 executions to prevent file from growing too large
            self.executions = self.executions[-1000:]
            with open(self.executions_file, 'w') as f:
                json.dump(self.executions, f, indent=2)
        except Exception as e:
            debug_print(f"Error saving executions: {e}")
    
    def get_workspace_files(self, path=".", extensions=None):
        """Get files in workspace directory"""
        files = []
        try:
            if not os.path.exists(path):
                return files
            
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                
                if os.path.isfile(item_path):
                    if extensions is None or any(item.endswith(ext) for ext in extensions):
                        stat = os.stat(item_path)
                        files.append({
                            "name": item,
                            "path": item_path,
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "type": "file"
                        })
                elif os.path.isdir(item_path) and not item.startswith('.'):
                    files.append({
                        "name": item,
                        "path": item_path,
                        "type": "directory"
                    })
        
        except Exception as e:
            debug_print(f"Error listing files: {e}")
        
        return sorted(files, key=lambda x: (x["type"] == "file", x["name"]))
    
    def read_file(self, file_path):
        """Read file content"""
        try:
            if not os.path.exists(file_path):
                return None, "File not found"
            
            if os.path.getsize(file_path) > 1024 * 1024:  # 1MB limit
                return None, "File too large to display"
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            return content, None
            
        except Exception as e:
            return None, str(e)
    
    def save_file(self, file_path, content):
        """Save file content"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            log_event("file_saved", f"File saved: {file_path}", "event")
            return True, "File saved successfully"
            
        except Exception as e:
            log_event("file_save_error", f"Error saving file {file_path}: {e}", "error")
            return False, str(e)
    
    def delete_file(self, file_path):
        """Delete a file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                log_event("file_deleted", f"File deleted: {file_path}", "event")
                return True, "File deleted successfully"
            else:
                return False, "File not found"
                
        except Exception as e:
            log_event("file_delete_error", f"Error deleting file {file_path}: {e}", "error")
            return False, str(e)
    
    def execute_file(self, file_path, interpreter="python", args="", timeout=300):
        """Execute a file with specified interpreter"""
        execution_id = f"exec_{int(time.time())}"
        
        try:
            if not os.path.exists(file_path):
                return {"success": False, "error": "File not found", "execution_id": execution_id}
            
            # Build command
            if interpreter == "python":
                command = f"python {file_path} {args}".strip()
            elif interpreter == "bash":
                command = f"bash {file_path} {args}".strip()
            elif interpreter == "node":
                command = f"node {file_path} {args}".strip()
            else:
                command = f"{interpreter} {file_path} {args}".strip()
            
            log_event("file_execute_start", f"Executing: {command}", "event")
            
            start_time = time.time()
            
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.path.dirname(file_path) if os.path.dirname(file_path) else "."
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Record execution
            execution_record = {
                "id": execution_id,
                "file_path": file_path,
                "command": command,
                "timestamp": datetime.now().isoformat(),
                "execution_time": execution_time,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0
            }
            
            self.executions.append(execution_record)
            self._save_executions()
            
            if result.returncode == 0:
                log_event("file_execute_success", f"File executed successfully: {file_path}", "event", {
                    "execution_time": execution_time,
                    "command": command
                })
            else:
                log_event("file_execute_error", f"File execution failed: {file_path}", "error", {
                    "return_code": result.returncode,
                    "command": command,
                    "error": result.stderr[:500]
                })
            
            return {
                "success": result.returncode == 0,
                "execution_id": execution_id,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "execution_time": execution_time
            }
            
        except subprocess.TimeoutExpired:
            error_msg = f"Execution timed out after {timeout} seconds"
            log_event("file_execute_timeout", f"File execution timeout: {file_path}", "error")
            
            execution_record = {
                "id": execution_id,
                "file_path": file_path,
                "command": command if 'command' in locals() else file_path,
                "timestamp": datetime.now().isoformat(),
                "execution_time": timeout,
                "return_code": -1,
                "stdout": "",
                "stderr": error_msg,
                "success": False
            }
            
            self.executions.append(execution_record)
            self._save_executions()
            
            return {
                "success": False,
                "execution_id": execution_id,
                "error": error_msg,
                "stdout": "",
                "stderr": error_msg,
                "return_code": -1,
                "execution_time": timeout
            }
            
        except Exception as e:
            error_msg = str(e)
            log_event("file_execute_exception", f"File execution exception: {file_path} - {error_msg}", "error")
            
            execution_record = {
                "id": execution_id,
                "file_path": file_path,
                "command": command if 'command' in locals() else file_path,
                "timestamp": datetime.now().isoformat(),
                "execution_time": 0,
                "return_code": -1,
                "stdout": "",
                "stderr": error_msg,
                "success": False
            }
            
            self.executions.append(execution_record)
            self._save_executions()
            
            return {
                "success": False,
                "execution_id": execution_id,
                "error": error_msg,
                "stdout": "",
                "stderr": error_msg,
                "return_code": -1,
                "execution_time": 0
            }
    
    def get_execution_history(self, limit=50):
        """Get execution history"""
        return self.executions[-limit:] if self.executions else []
    
    def get_execution_result(self, execution_id):
        """Get specific execution result"""
        for execution in reversed(self.executions):
            if execution["id"] == execution_id:
                return execution
        return None