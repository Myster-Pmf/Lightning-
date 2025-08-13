"""
Enhanced Lightning AI Studio Dashboard
Main entry point for the application
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print(f"Python path: {sys.path}")
print(f"Current working directory: {os.getcwd()}")
print(f"Environment variables loaded")

try:
    # Import the enhanced dashboard
    from app.dashboard import create_dashboard_app
    print("Dashboard import successful")
    
    # Create the enhanced dashboard app
    app = create_dashboard_app()
    print("Dashboard app created successfully")
    
except Exception as e:
    print(f"Error creating dashboard app: {e}")
    import traceback
    traceback.print_exc()
    raise e  # Re-raise the exception so we can see what's wrong

if __name__ == "__main__":
    try:
        from app.utils.logging_utils import log_event
        log_event("startup", "Enhanced Lightning AI Dashboard starting")
    except:
        print("Could not log startup event")
    
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)