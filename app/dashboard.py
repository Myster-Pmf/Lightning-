"""
Main dashboard application with enhanced UI and functionality
"""
import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, Blueprint, render_template, jsonify, request, redirect, url_for, flash
from lightning_sdk import Studio, Machine

from .routes.main_routes import main_bp
from .routes.api_routes import api_bp
from .routes.scheduler_routes import scheduler_bp
from .routes.files_routes import files_bp
from .services.lightning_service import LightningService
from .services.scheduler_service import SchedulerService
from .services.file_service import FileService
from .utils.logging_utils import log_event

def create_dashboard_app():
    """Create the enhanced dashboard application"""
    # Get the correct template and static directories
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(os.path.dirname(current_dir), 'templates')
    static_dir = os.path.join(os.path.dirname(current_dir), 'static')
    
    print(f"Template directory: {template_dir}")
    print(f"Static directory: {static_dir}")
    print(f"Template dir exists: {os.path.exists(template_dir)}")
    
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir if os.path.exists(static_dir) else None)
    
    # Configure Flask app
    app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
    app.config['DEBUG'] = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Set environment variables for services
    app.config['STUDIO_NAME'] = os.getenv('STUDIO_NAME')
    app.config['TEAMSPACE'] = os.getenv('TEAMSPACE') 
    app.config['USERNAME'] = os.getenv('USERNAME')
    
    # Initialize services with error handling
    try:
        lightning_service = LightningService()
        print("Lightning service initialized successfully")
    except Exception as e:
        print(f"Error initializing Lightning service: {e}")
        lightning_service = None
    
    try:
        scheduler_service = SchedulerService()
        print("Scheduler service initialized successfully")
    except Exception as e:
        print(f"Error initializing Scheduler service: {e}")
        scheduler_service = None
    
    try:
        file_service = FileService()
        print("File service initialized successfully")
    except Exception as e:
        print(f"Error initializing File service: {e}")
        file_service = None
    
    # Pass studio instance to file service for remote operations
    if file_service and lightning_service and lightning_service.studio:
        file_service.set_studio(lightning_service.studio)
        print("Studio instance passed to file service")
    
    # Store services in app config for access in routes
    app.config['LIGHTNING_SERVICE'] = lightning_service
    app.config['SCHEDULER_SERVICE'] = scheduler_service
    app.config['FILE_SERVICE'] = file_service
    app.config['ASYNC_TASKS'] = {}
    
    # Pass lightning service to scheduler for execution
    if scheduler_service and lightning_service:
        scheduler_service.set_lightning_service(lightning_service)
        print("Lightning service passed to scheduler")
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(scheduler_bp, url_prefix='/scheduler')
    app.register_blueprint(files_bp, url_prefix='/files')
    
    # Start background services
    def start_background_services():
        try:
            # Start monitor thread
            if lightning_service:
                monitor_thread = threading.Thread(target=lightning_service.monitor_loop)
                monitor_thread.daemon = True
                monitor_thread.start()
                print("Monitor thread started")
        except Exception as e:
            print(f"Error starting monitor thread: {e}")
        
        try:
            # Start scheduler thread
            if scheduler_service:
                scheduler_thread = threading.Thread(target=scheduler_service.run_scheduler)
                scheduler_thread.daemon = True
                scheduler_thread.start()
                print("Scheduler thread started")
        except Exception as e:
            print(f"Error starting scheduler thread: {e}")
    
    # Start services after a short delay to ensure app is ready
    try:
        threading.Timer(1.0, start_background_services).start()
        log_event("startup", "Enhanced Lightning AI Dashboard starting")
    except Exception as e:
        print(f"Warning: Could not start background services: {e}")
    
    return app