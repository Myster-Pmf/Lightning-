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
    app = Flask(__name__)
    
    # Initialize services
    lightning_service = LightningService()
    scheduler_service = SchedulerService()
    file_service = FileService()
    
    # Store services in app config for access in routes
    app.config['LIGHTNING_SERVICE'] = lightning_service
    app.config['SCHEDULER_SERVICE'] = scheduler_service
    app.config['FILE_SERVICE'] = file_service
    app.config['ASYNC_TASKS'] = {}
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(scheduler_bp, url_prefix='/scheduler')
    app.register_blueprint(files_bp, url_prefix='/files')
    
    # Start background services
    def start_background_services():
        # Start monitor thread
        monitor_thread = threading.Thread(target=lightning_service.monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Start scheduler thread
        scheduler_thread = threading.Thread(target=scheduler_service.run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
    
    # Start services after a short delay to ensure app is ready
    threading.Timer(1.0, start_background_services).start()
    
    log_event("startup", "Enhanced Lightning AI Dashboard starting")
    
    return app