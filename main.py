"""
Enhanced Lightning AI Studio Dashboard
Main entry point for the application
"""
import os
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import modules
from app.dashboard import create_dashboard_app
from app.utils.logging_utils import setup_logging

def create_app():
    """Create and configure the Flask application"""
    # Create dashboard app directly
    app = create_dashboard_app()
    
    # Configure app
    app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
    app.config['DEBUG'] = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Setup logging
    setup_logging()
    
    return app

# Create the app instance for Gunicorn
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=app.config['DEBUG'])