"""
File management routes for the enhanced Lightning AI dashboard
"""
import os
from flask import Blueprint, jsonify, request, current_app, redirect, url_for, flash

files_bp = Blueprint('files', __name__)

@files_bp.route('/list')
def list_files():
    """List files in workspace"""
    try:
        path = request.args.get('path', '.')
        extensions = request.args.get('extensions')
        
        if extensions:
            extensions = [ext.strip() for ext in extensions.split(',')]
        
        file_service = current_app.config['FILE_SERVICE']
        files = file_service.get_workspace_files(path, extensions)
        
        return jsonify({
            "success": True,
            "files": files,
            "current_path": path
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/read/<path:file_path>')
def read_file(file_path):
    """Read file content"""
    try:
        file_service = current_app.config['FILE_SERVICE']
        content, error = file_service.read_file(file_path)
        
        if error:
            return jsonify({
                "success": False,
                "error": error
            }), 400
        
        return jsonify({
            "success": True,
            "content": content,
            "file_path": file_path
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/save', methods=['POST'])
def save_file():
    """Save file content"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        content = data.get('content', '')
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File path is required"
            }), 400
        
        file_service = current_app.config['FILE_SERVICE']
        success, message = file_service.save_file(file_path, content)
        
        return jsonify({
            "success": success,
            "message": message
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/delete/<path:file_path>', methods=['DELETE', 'POST'])
def delete_file(file_path):
    """Delete a file"""
    try:
        file_service = current_app.config['FILE_SERVICE']
        success, message = file_service.delete_file(file_path)
        
        if request.is_json:
            return jsonify({
                "success": success,
                "message": message
            })
        else:
            if success:
                flash(message, "success")
            else:
                flash(message, "error")
            return redirect(url_for('main.files'))
        
    except Exception as e:
        if request.is_json:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500
        else:
            flash(f"Error deleting file: {str(e)}", "error")
            return redirect(url_for('main.files'))

@files_bp.route('/execute', methods=['POST'])
def execute_file():
    """Execute a file"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        interpreter = data.get('interpreter', 'python')
        args = data.get('args', '')
        timeout = data.get('timeout', 300)
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File path is required"
            }), 400
        
        file_service = current_app.config['FILE_SERVICE']
        result = file_service.execute_file(file_path, interpreter, args, timeout)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/execution/<execution_id>')
def get_execution_result(execution_id):
    """Get execution result by ID"""
    try:
        file_service = current_app.config['FILE_SERVICE']
        result = file_service.get_execution_result(execution_id)
        
        if result is None:
            return jsonify({
                "success": False,
                "error": "Execution not found"
            }), 404
        
        return jsonify({
            "success": True,
            "result": result
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/execution-history')
def get_execution_history():
    """Get execution history"""
    try:
        limit = request.args.get('limit', 50, type=int)
        
        file_service = current_app.config['FILE_SERVICE']
        history = file_service.get_execution_history(limit)
        
        return jsonify({
            "success": True,
            "history": history
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/upload', methods=['POST'])
def upload_file():
    """Upload a file to workspace and remote"""
    try:
        if 'file' not in request.files:
            return jsonify({
                "success": False,
                "error": "No file provided"
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                "success": False,
                "error": "No file selected"
            }), 400
        
        # Save file to workspace
        filename = file.filename
        file_path = os.path.join('.', filename)
        file.save(file_path)
        
        file_service = current_app.config['FILE_SERVICE']
        
        # Also upload to remote
        remote_dir, err = file_service.get_remote_working_directory()
        if err:
            return jsonify({
                "success": False,
                "error": f"File uploaded to workspace, but could not determine remote working directory: {err}",
                "file_path": file_path
            })

        remote_path = f"{remote_dir}/{filename}"
        upload_result = file_service.upload_to_remote(file_path, remote_path)
        
        if upload_result['success']:
            return jsonify({
                "success": True,
                "message": f"File '{filename}' uploaded successfully to both workspace and remote",
                "file_path": file_path,
                "remote_path": remote_path
            })
        else:
            return jsonify({
                "success": False,
                "error": f"File uploaded to workspace, but failed to upload to remote: {upload_result['error']}",
                "file_path": file_path
            })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/upload-to-remote', methods=['POST'])
def upload_to_remote():
    """Upload a local file to the remote Lightning AI Studio"""
    try:
        data = request.get_json()
        local_file_path = data.get('local_file_path')
        remote_file_path = data.get('remote_file_path')
        
        if not local_file_path:
            return jsonify({
                "success": False,
                "error": "Local file path is required"
            }), 400
        
        file_service = current_app.config['FILE_SERVICE']
        result = file_service.upload_to_remote(local_file_path, remote_file_path)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/download-from-remote', methods=['POST'])
def download_from_remote():
    """Download a file from the remote Lightning AI Studio"""
    try:
        data = request.get_json()
        remote_file_path = data.get('remote_file_path')
        local_file_path = data.get('local_file_path')
        
        if not remote_file_path:
            return jsonify({
                "success": False,
                "error": "Remote file path is required"
            }), 400
        
        file_service = current_app.config['FILE_SERVICE']
        result = file_service.download_from_remote(remote_file_path, local_file_path)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/run-remote-command', methods=['POST'])
def run_remote_command():
    """Run a command on the remote Lightning AI Studio"""
    try:
        data = request.get_json()
        command = data.get('command')
        timeout = data.get('timeout', 300)
        
        if not command:
            return jsonify({
                "success": False,
                "error": "Command is required"
            }), 400
        
        file_service = current_app.config['FILE_SERVICE']
        result = file_service.run_remote_command(command, timeout)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/execute-local', methods=['POST'])
def execute_file_local():
    """Execute a file locally on the host machine"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File path is required"
            }), 400
        
        file_service = current_app.config['FILE_SERVICE']
        result = file_service.execute_file_local(file_path)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/execute-remote', methods=['POST'])
def execute_file_remote():
    """Execute a file on the remote Lightning AI Studio"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File path is required"
            }), 400
        
        file_service = current_app.config['FILE_SERVICE']
        result = file_service.execute_file_remote(file_path)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/list-remote', methods=['POST'])
def list_remote_files():
    """List files on remote Lightning AI Studio"""
    try:
        data = request.get_json()
        path = data.get('path', None)
        
        file_service = current_app.config['FILE_SERVICE']
        result = file_service.list_remote_files(path)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/download-local/<path:file_path>')
def download_local_file(file_path):
    """Download a local file"""
    try:
        from flask import send_file
        import os
        
        if not os.path.exists(file_path):
            return jsonify({
                "success": False,
                "error": "File not found"
            }), 404
        
        return send_file(file_path, as_attachment=True)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@files_bp.route('/delete-remote', methods=['POST'])
def delete_remote_file():
    """Delete a file on remote Lightning AI Studio"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({
                "success": False,
                "error": "File path is required"
            }), 400
        
        file_service = current_app.config['FILE_SERVICE']
        result = file_service.delete_remote_file(file_path)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500