"""
File service for managing and executing files on the Lightning AI studio
"""
import os
import json
import subprocess
import time
import tempfile
from datetime import datetime
from ..utils.logging_utils import debug_print, log_event

class FileService:
    """Service for managing file operations and executions"""
    
    def __init__(self):
        self.executions = []
        self.executions_file = "data/executions.json"
        self.studio = None  # Will be set by the app
        self._load_executions()
    
    def set_studio(self, studio):
        """Set the studio instance for remote operations"""
        self.studio = studio
    
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
            # Ensure directory exists (only if file_path contains a directory)
            dir_path = os.path.dirname(file_path)
            if dir_path and dir_path != '.':
                os.makedirs(dir_path, exist_ok=True)
            
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
        """Execute a file on the remote Lightning AI Studio"""
        execution_id = f"exec_{int(time.time())}"
        
        try:
            # Check if studio is available and running
            if not self.studio:
                return {"success": False, "error": "Studio not initialized", "execution_id": execution_id}
            
            # Check studio status
            try:
                status = str(self.studio.status)
                # Handle both enum formats: Status.Running and 'running'
                status_lower = status.lower().replace('status.', '')
                if status_lower not in ['running', 'started']:
                    return {"success": False, "error": f"Studio is not running (status: {status})", "execution_id": execution_id}
            except Exception as e:
                return {"success": False, "error": f"Cannot check studio status: {str(e)}", "execution_id": execution_id}
            
            if not os.path.exists(file_path):
                return {"success": False, "error": "File not found", "execution_id": execution_id}
            
            # Get file name and prepare remote path
            file_name = os.path.basename(file_path)
            remote_dir, err = self.get_remote_working_directory()
            if err:
                return {"success": False, "error": f"Could not determine remote working directory: {err}", "execution_id": execution_id}

            remote_file_path = f"{remote_dir}/{file_name}"
            
            log_event("file_execute_start", f"Uploading and executing {file_path} on remote studio", "event")
            
            start_time = time.time()
            
            # Step 1: Upload file to remote studio
            try:
                self.studio.upload_file(file_path, remote_file_path)
                debug_print(f"File uploaded to remote studio: {file_path} -> {remote_file_path}")
            except Exception as e:
                error_msg = f"Failed to upload file to remote studio: {str(e)}"
                log_event("file_upload_error", error_msg, "error")
                return {"success": False, "error": error_msg, "execution_id": execution_id}
            
            # Step 2: Build command for remote execution
            if interpreter == "python":
                command = f"cd {remote_dir} && python {file_name} {args}".strip()
            elif interpreter == "bash":
                command = f"cd {remote_dir} && bash {file_name} {args}".strip()
            elif interpreter == "node":
                command = f"cd {remote_dir} && node {file_name} {args}".strip()
            else:
                command = f"cd {remote_dir} && {interpreter} {file_name} {args}".strip()
            
            # Step 3: Execute command on remote studio
            try:
                debug_print(f"Executing command on remote studio: {command}")
                result = self.studio.run(command)
                
                end_time = time.time()
                execution_time = end_time - start_time
                
                debug_print(f"Raw result from studio.run(): {type(result)} - {result}")
                
                # Parse result - handle different return types from studio.run()
                if hasattr(result, 'returncode'):
                    # CompletedProcess-like object
                    return_code = result.returncode
                    stdout = getattr(result, 'stdout', str(result))
                    stderr = getattr(result, 'stderr', '')
                elif hasattr(result, 'exit_code'):
                    # Alternative format
                    return_code = result.exit_code
                    stdout = getattr(result, 'output', str(result))
                    stderr = getattr(result, 'error', '')
                else:
                    # If result is just a string output (successful execution)
                    return_code = 0
                    stdout = str(result) if result is not None else ""
                    stderr = ''
                
                success = return_code == 0
                debug_print(f"Parsed execution result: success={success}, return_code={return_code}, stdout_len={len(stdout)}, stderr_len={len(stderr)}")
                
            except Exception as e:
                end_time = time.time()
                execution_time = end_time - start_time
                error_msg = str(e)
                
                # Check if it's a timeout error
                if "timeout" in error_msg.lower():
                    return_code = -1
                    stdout = ""
                    stderr = f"Execution timed out after {timeout} seconds"
                    success = False
                else:
                    return_code = -1
                    stdout = ""
                    stderr = error_msg
                    success = False
            
            # Step 4: Clean up remote file (optional, but good practice)
            try:
                self.studio.run(f"rm -f {remote_file_path}")
                debug_print(f"Cleaned up remote file: {remote_file_path}")
            except Exception as e:
                debug_print(f"Warning: Could not clean up remote file {remote_file_path}: {e}")
            
            # Record execution
            execution_record = {
                "id": execution_id,
                "file_path": file_path,
                "remote_path": remote_file_path,
                "command": command,
                "timestamp": datetime.now().isoformat(),
                "execution_time": execution_time,
                "return_code": return_code,
                "stdout": stdout,
                "stderr": stderr,
                "success": success,
                "execution_location": "remote_studio"
            }
            
            self.executions.append(execution_record)
            self._save_executions()
            
            if success:
                log_event("file_execute_success", f"File executed successfully on remote studio: {file_path}", "event", {
                    "execution_time": execution_time,
                    "command": command,
                    "remote_path": remote_file_path
                })
            else:
                log_event("file_execute_error", f"File execution failed on remote studio: {file_path}", "error", {
                    "return_code": return_code,
                    "command": command,
                    "error": stderr[:500]
                })
            
            return {
                "success": success,
                "execution_id": execution_id,
                "stdout": stdout,
                "stderr": stderr,
                "return_code": return_code,
                "execution_time": execution_time,
                "execution_location": "remote_studio",
                "remote_path": remote_file_path
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
                "success": False,
                "execution_location": "remote_studio"
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
                "execution_time": 0,
                "execution_location": "remote_studio"
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

    def get_remote_working_directory(self):
        """Get the remote working directory"""
        try:
            if not self.studio:
                return None, "Studio not initialized"

            # Check studio status
            try:
                status = str(self.studio.status)
                status_lower = status.lower().replace('status.', '')
                if status_lower not in ['running', 'started']:
                    return None, f"Studio is not running (status: {status})"
            except Exception as e:
                return None, f"Cannot check studio status: {str(e)}"

            pwd_result = self.studio.run("pwd")
            if pwd_result:
                return str(pwd_result).strip(), None
            else:
                return None, "Could not determine remote working directory"

        except Exception as e:
            return None, str(e)
    
    def upload_to_remote(self, local_file_path, remote_file_path):
        """Upload a file to the remote Lightning AI Studio"""
        try:
            if not self.studio:
                return {"success": False, "error": "Studio not initialized"}
            
            # Check studio status
            try:
                status = str(self.studio.status)
                # Handle both enum formats: Status.Running and 'running'
                status_lower = status.lower().replace('status.', '')
                if status_lower not in ['running', 'started']:
                    return {"success": False, "error": f"Studio is not running (status: {status})"}
            except Exception as e:
                return {"success": False, "error": f"Cannot check studio status: {str(e)}"}
            
            if not os.path.exists(local_file_path):
                return {"success": False, "error": "Local file not found"}
            
            # Upload file
            self.studio.upload_file(local_file_path, remote_file_path)
            
            log_event("file_upload_success", f"File uploaded: {local_file_path} -> {remote_file_path}", "event")
            
            return {
                "success": True,
                "local_path": local_file_path,
                "remote_path": remote_file_path,
                "message": f"File uploaded successfully to {remote_file_path}"
            }
            
        except Exception as e:
            error_msg = str(e)
            log_event("file_upload_error", f"Upload failed: {local_file_path} - {error_msg}", "error")
            return {"success": False, "error": error_msg}
    
    def download_from_remote(self, remote_file_path, local_file_path=None):
        """Download a file from the remote Lightning AI Studio"""
        try:
            if not self.studio:
                return {"success": False, "error": "Studio not initialized"}
            
            # Check studio status
            try:
                status = str(self.studio.status)
                # Handle both enum formats: Status.Running and 'running'
                status_lower = status.lower().replace('status.', '')
                if status_lower not in ['running', 'started']:
                    return {"success": False, "error": f"Studio is not running (status: {status})"}
            except Exception as e:
                return {"success": False, "error": f"Cannot check studio status: {str(e)}"}
            
            # Default local path if not specified
            if local_file_path is None:
                file_name = os.path.basename(remote_file_path)
                local_file_path = f"downloads/{file_name}"
                
                # Ensure downloads directory exists
                os.makedirs("downloads", exist_ok=True)
            
            # Download file
            self.studio.download_file(remote_file_path, local_file_path)
            
            log_event("file_download_success", f"File downloaded: {remote_file_path} -> {local_file_path}", "event")
            
            return {
                "success": True,
                "remote_path": remote_file_path,
                "local_path": local_file_path,
                "message": f"File downloaded successfully to {local_file_path}"
            }
            
        except Exception as e:
            error_msg = str(e)
            log_event("file_download_error", f"Download failed: {remote_file_path} - {error_msg}", "error")
            return {"success": False, "error": error_msg}
    
    def run_remote_command(self, command, timeout=300):
        """Run a command directly on the remote Lightning AI Studio"""
        try:
            if not self.studio:
                return {"success": False, "error": "Studio not initialized"}
            
            # Check studio status
            try:
                status = str(self.studio.status)
                # Handle both enum formats: Status.Running and 'running'
                status_lower = status.lower().replace('status.', '')
                if status_lower not in ['running', 'started']:
                    return {"success": False, "error": f"Studio is not running (status: {status})"}
            except Exception as e:
                return {"success": False, "error": f"Cannot check studio status: {str(e)}"}
            
            log_event("remote_command_start", f"Running remote command: {command}", "event")
            
            start_time = time.time()
            
            # Execute command on remote studio
            result = self.studio.run(command)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Parse result
            if hasattr(result, 'returncode'):
                return_code = result.returncode
                stdout = getattr(result, 'stdout', str(result))
                stderr = getattr(result, 'stderr', '')
            else:
                return_code = 0
                stdout = str(result)
                stderr = ''
            
            success = return_code == 0
            
            if success:
                log_event("remote_command_success", f"Remote command executed successfully: {command}", "event", {
                    "execution_time": execution_time
                })
            else:
                log_event("remote_command_error", f"Remote command failed: {command}", "error", {
                    "return_code": return_code,
                    "error": stderr[:500]
                })
            
            return {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
                "return_code": return_code,
                "execution_time": execution_time,
                "command": command
            }
            
        except Exception as e:
            error_msg = str(e)
            log_event("remote_command_exception", f"Remote command exception: {command} - {error_msg}", "error")
            
            return {
                "success": False,
                "error": error_msg,
                "command": command
            }
    
    def execute_file_local(self, file_path):
        """Execute a file locally on the host machine"""
        import subprocess
        execution_id = f"local_exec_{int(time.time())}"
        
        try:
            if not os.path.exists(file_path):
                return {"success": False, "error": "File not found", "execution_id": execution_id}
            
            # Determine interpreter based on file extension
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.py':
                command = ['python', file_path]
            elif ext == '.sh':
                command = ['bash', file_path]
            elif ext == '.js':
                command = ['node', file_path]
            else:
                command = ['python', file_path]  # Default to python
            
            start_time = time.time()
            
            # Execute locally
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            success = result.returncode == 0
            
            # Record execution
            execution_record = {
                "id": execution_id,
                "file_path": file_path,
                "command": ' '.join(command),
                "timestamp": datetime.now().isoformat(),
                "execution_time": execution_time,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": success,
                "execution_location": "local_host"
            }
            
            self.executions.append(execution_record)
            self._save_executions()
            
            return {
                "success": success,
                "execution_id": execution_id,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "execution_time": execution_time,
                "execution_location": "local_host"
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "execution_id": execution_id,
                "error": "Execution timed out",
                "execution_time": 300,
                "execution_location": "local_host"
            }
        except Exception as e:
            return {
                "success": False,
                "execution_id": execution_id,
                "error": str(e),
                "execution_time": 0,
                "execution_location": "local_host"
            }
    
    def execute_file_remote(self, file_path):
        """Execute a file that already exists on the remote Lightning AI Studio"""
        try:
            if not self.studio:
                return {"success": False, "error": "Studio not initialized"}
            
            # Check studio status
            try:
                status = str(self.studio.status)
                status_lower = status.lower().replace('status.', '')
                if status_lower not in ['running', 'started']:
                    return {"success": False, "error": f"Studio is not running (status: {status})"}
            except Exception as e:
                return {"success": False, "error": f"Cannot check studio status: {str(e)}"}
            
            # Build command for remote execution
            file_name = os.path.basename(file_path)
            ext = os.path.splitext(file_name)[1].lower()
            
            if ext == '.py':
                command = f"python {file_path}"
            elif ext == '.sh':
                command = f"bash {file_path}"
            elif ext == '.js':
                command = f"node {file_path}"
            else:
                command = f"python {file_path}"  # Default to python
            
            start_time = time.time()
            
            # Execute on remote studio
            result = self.studio.run(command)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Parse result
            if hasattr(result, 'returncode'):
                return_code = result.returncode
                stdout = getattr(result, 'stdout', str(result))
                stderr = getattr(result, 'stderr', '')
            else:
                return_code = 0
                stdout = str(result) if result is not None else ""
                stderr = ''
            
            success = return_code == 0
            
            return {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
                "return_code": return_code,
                "execution_time": execution_time,
                "execution_location": "remote_studio"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "execution_location": "remote_studio"
            }
    
    def list_remote_files(self, path=None):
        """List files on the remote Lightning AI Studio"""
        try:
            if not self.studio:
                return {"success": False, "error": "Studio not initialized"}
            
            # Check studio status
            try:
                status = str(self.studio.status)
                status_lower = status.lower().replace('status.', '')
                if status_lower not in ['running', 'started']:
                    return {"success": False, "error": f"Studio is not running (status: {status})"}
            except Exception as e:
                return {"success": False, "error": f"Cannot check studio status: {str(e)}"}
            
            # If no path specified, get current working directory first
            if path is None:
                pwd_result = self.studio.run("pwd")
                if pwd_result:
                    path = str(pwd_result).strip()
                else:
                    path = "~"  # fallback to home directory
            
            debug_print(f"Listing remote files in path: {path}")
            
            # Use ls -la for detailed listing
            command = f"ls -la '{path}' 2>/dev/null || ls -la ."
            result = self.studio.run(command)
            
            debug_print(f"ls command result type: {type(result)}")
            debug_print(f"ls command result: {result}")
            
            output = str(result) if result else ""
            debug_print(f"ls output: {output}")
            
            if not output or "No such file or directory" in output:
                return {"success": False, "error": f"Directory '{path}' not found or not accessible"}
            
            files = []
            
            # Parse ls -la output
            lines = output.strip().split('\n')
            debug_print(f"Total lines: {len(lines)}")
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Skip total line and empty lines
                if line.startswith('total ') or i == 0:
                    continue
                    
                debug_print(f"Processing line {i}: {line}")
                
                # Split by whitespace, but be careful with filenames containing spaces
                parts = line.split()
                if len(parts) < 9:
                    debug_print(f"Skipping line with insufficient parts: {len(parts)}")
                    continue
                
                permissions = parts[0]
                links = parts[1]
                owner = parts[2]
                group = parts[3]
                size = parts[4]
                month = parts[5]
                day = parts[6]
                time_or_year = parts[7]
                
                # Handle filenames with spaces - everything after the 8th part
                name = ' '.join(parts[8:])
                
                # Skip . and .. directories
                if name in ['.', '..']:
                    continue
                
                # Determine file type
                file_type = 'directory' if permissions.startswith('d') else 'file'
                
                # Build full path
                if path.endswith('/'):
                    file_path = f"{path}{name}"
                else:
                    file_path = f"{path}/{name}"
                
                # Parse size
                file_size = 0
                try:
                    file_size = int(size) if size.isdigit() else 0
                except:
                    pass
                
                files.append({
                    "name": name,
                    "path": file_path,
                    "size": file_size,
                    "type": file_type,
                    "permissions": permissions,
                    "owner": owner,
                    "group": group,
                    "modified": f"{month} {day} {time_or_year}"
                })
                
                debug_print(f"Added file: {name} ({file_type})")
            
            debug_print(f"Total files found: {len(files)}")
            return {"success": True, "files": files, "path": path}
            
        except Exception as e:
            error_msg = str(e)
            debug_print(f"Error in list_remote_files: {error_msg}")
            return {"success": False, "error": error_msg}
    
    def delete_remote_file(self, file_path):
        """Delete a file on the remote Lightning AI Studio"""
        try:
            if not self.studio:
                return {"success": False, "error": "Studio not initialized"}
            
            # Check studio status
            try:
                status = str(self.studio.status)
                status_lower = status.lower().replace('status.', '')
                if status_lower not in ['running', 'started']:
                    return {"success": False, "error": f"Studio is not running (status: {status})"}
            except Exception as e:
                return {"success": False, "error": f"Cannot check studio status: {str(e)}"}
            
            # Run rm command
            command = f"rm -f {file_path}"
            result = self.studio.run(command)
            
            if hasattr(result, 'returncode') and result.returncode != 0:
                return {"success": False, "error": "Failed to delete remote file"}
            
            return {"success": True, "message": f"File {file_path} deleted successfully"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}