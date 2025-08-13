"""
Enhanced Lightning AI Studio Dashboard
Main entry point for the application
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Import the enhanced dashboard
from app.dashboard import create_dashboard_app

# Create the enhanced dashboard app
app = create_dashboard_app()

if __name__ == "__main__":
    from app.utils.logging_utils import log_event
    log_event("startup", "Enhanced Lightning AI Dashboard starting")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)