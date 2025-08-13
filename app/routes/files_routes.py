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
    """Upload a file to workspace"""
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
        
        return jsonify({
            "success": True,
            "message": f"File '{filename}' uploaded successfully",
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
 
 @ f i l e s _ b p . r o u t e ( ' / e x e c u t e - l o c a l ' ,   m e t h o d s = [ ' P O S T ' ] ) 
 d e f   e x e c u t e _ f i l e _ l o c a l ( ) : 
         \  
 \ \ E x e c u t e  
 a  
 f i l e  
 l o c a l l y  
 o n  
 t h e  
 h o s t  
 m a c h i n e \ \ \ 
         t r y : 
                 d a t a   =   r e q u e s t . g e t _ j s o n ( ) 
                 f i l e _ p a t h   =   d a t a . g e t ( ' f i l e _ p a t h ' ) 
                 
                 i f   n o t   f i l e _ p a t h : 
                         r e t u r n   j s o n i f y ( { 
                                 \ s u c c e s s \ :   F a l s e , 
                                 \ e r r o r \ :   \ F i l e  
 p a t h  
 i s  
 r e q u i r e d \ 
                         } ) ,   4 0 0 
                 
                 f i l e _ s e r v i c e   =   c u r r e n t _ a p p . c o n f i g [ ' F I L E _ S E R V I C E ' ] 
                 r e s u l t   =   f i l e _ s e r v i c e . e x e c u t e _ f i l e _ l o c a l ( f i l e _ p a t h ) 
                 
                 r e t u r n   j s o n i f y ( r e s u l t ) 
                 
         e x c e p t   E x c e p t i o n   a s   e : 
                 r e t u r n   j s o n i f y ( { 
                         \ s u c c e s s \ :   F a l s e , 
                         \ e r r o r \ :   s t r ( e ) 
                 } ) ,   5 0 0 
 
 @ f i l e s _ b p . r o u t e ( ' / e x e c u t e - r e m o t e ' ,   m e t h o d s = [ ' P O S T ' ] ) 
 d e f   e x e c u t e _ f i l e _ r e m o t e ( ) : 
         \ \ \ E x e c u t e  
 a  
 f i l e  
 o n  
 t h e  
 r e m o t e  
 L i g h t n i n g  
 A I  
 S t u d i o \ \ \ 
         t r y : 
                 d a t a   =   r e q u e s t . g e t _ j s o n ( ) 
                 f i l e _ p a t h   =   d a t a . g e t ( ' f i l e _ p a t h ' ) 
                 
                 i f   n o t   f i l e _ p a t h : 
                         r e t u r n   j s o n i f y ( { 
                                 \ s u c c e s s \ :   F a l s e , 
                                 \ e r r o r \ :   \ F i l e  
 p a t h  
 i s  
 r e q u i r e d \ 
                         } ) ,   4 0 0 
                 
                 f i l e _ s e r v i c e   =   c u r r e n t _ a p p . c o n f i g [ ' F I L E _ S E R V I C E ' ] 
                 r e s u l t   =   f i l e _ s e r v i c e . e x e c u t e _ f i l e _ r e m o t e ( f i l e _ p a t h ) 
                 
                 r e t u r n   j s o n i f y ( r e s u l t ) 
                 
         e x c e p t   E x c e p t i o n   a s   e : 
                 r e t u r n   j s o n i f y ( { 
                         \ s u c c e s s \ :   F a l s e , 
                         \ e r r o r \ :   s t r ( e ) 
                 } ) ,   5 0 0 
 
 @ f i l e s _ b p . r o u t e ( ' / l i s t - r e m o t e ' ,   m e t h o d s = [ ' P O S T ' ] ) 
 d e f   l i s t _ r e m o t e _ f i l e s ( ) : 
         \ \ \ L i s t  
 f i l e s  
 o n  
 r e m o t e  
 L i g h t n i n g  
 A I  
 S t u d i o \ \ \ 
         t r y : 
                 d a t a   =   r e q u e s t . g e t _ j s o n ( ) 
                 p a t h   =   d a t a . g e t ( ' p a t h ' ,   N o n e ) 
                 
                 f i l e _ s e r v i c e   =   c u r r e n t _ a p p . c o n f i g [ ' F I L E _ S E R V I C E ' ] 
                 r e s u l t   =   f i l e _ s e r v i c e . l i s t _ r e m o t e _ f i l e s ( p a t h ) 
                 
                 r e t u r n   j s o n i f y ( r e s u l t ) 
                 
         e x c e p t   E x c e p t i o n   a s   e : 
                 r e t u r n   j s o n i f y ( { 
                         \ s u c c e s s \ :   F a l s e , 
                         \ e r r o r \ :   s t r ( e ) 
                 } ) ,   5 0 0 
 
 @ f i l e s _ b p . r o u t e ( ' / d o w n l o a d - l o c a l / < p a t h : f i l e _ p a t h > ' ) 
 d e f   d o w n l o a d _ l o c a l _ f i l e ( f i l e _ p a t h ) : 
         \ \ \ D o w n l o a d  
 a  
 l o c a l  
 f i l e \ \ \ 
         t r y : 
                 f r o m   f l a s k   i m p o r t   s e n d _ f i l e 
                 i m p o r t   o s 
                 
                 i f   n o t   o s . p a t h . e x i s t s ( f i l e _ p a t h ) : 
                         r e t u r n   j s o n i f y ( { 
                                 \ s u c c e s s \ :   F a l s e , 
                                 \ e r r o r \ :   \ F i l e  
 n o t  
 f o u n d \ 
                         } ) ,   4 0 4 
                 
                 r e t u r n   s e n d _ f i l e ( f i l e _ p a t h ,   a s _ a t t a c h m e n t = T r u e ) 
                 
         e x c e p t   E x c e p t i o n   a s   e : 
                 r e t u r n   j s o n i f y ( { 
                         \ s u c c e s s \ :   F a l s e , 
                         \ e r r o r \ :   s t r ( e ) 
                 } ) ,   5 0 0 
 
 @ f i l e s _ b p . r o u t e ( ' / d e l e t e - r e m o t e ' ,   m e t h o d s = [ ' P O S T ' ] ) 
 d e f   d e l e t e _ r e m o t e _ f i l e ( ) : 
         \ \ \ D e l e t e  
 a  
 f i l e  
 o n  
 r e m o t e  
 L i g h t n i n g  
 A I  
 S t u d i o \ \ \ 
         t r y : 
                 d a t a   =   r e q u e s t . g e t _ j s o n ( ) 
                 f i l e _ p a t h   =   d a t a . g e t ( ' f i l e _ p a t h ' ) 
                 
                 i f   n o t   f i l e _ p a t h : 
                         r e t u r n   j s o n i f y ( { 
                                 \ s u c c e s s \ :   F a l s e , 
                                 \ e r r o r \ :   \ F i l e  
 p a t h  
 i s  
 r e q u i r e d \ 
                         } ) ,   4 0 0 
                 
                 f i l e _ s e r v i c e   =   c u r r e n t _ a p p . c o n f i g [ ' F I L E _ S E R V I C E ' ] 
                 r e s u l t   =   f i l e _ s e r v i c e . d e l e t e _ r e m o t e _ f i l e ( f i l e _ p a t h ) 
                 
                 r e t u r n   j s o n i f y ( r e s u l t ) 
                 
         e x c e p t   E x c e p t i o n   a s   e : 
                 r e t u r n   j s o n i f y ( { 
                         \ s u c c e s s \ :   F a l s e , 
                         \ e r r o r \ :   s t r ( e ) 
                 } ) ,   5 0 0  
 