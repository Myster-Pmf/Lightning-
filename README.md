# Enhanced Lightning AI Studio Dashboard

A comprehensive web dashboard for managing Lightning AI studios with advanced features including scheduling, file management, and automation.

## Features

### 🎛️ Enhanced Dashboard
- Real-time studio status monitoring
- Interactive activity timeline with Chart.js
- Quick action buttons for start/stop/restart
- Machine type selection (CPU, GPU, GPU_FAST)
- Beautiful modern UI with Tailwind CSS

### ⏰ Advanced Scheduler
- Schedule studio start/stop operations
- Support for one-time, daily, and weekly schedules 
- Post-start command execution
- Pre-stop command execution
- Enable/disable schedules
- Visual schedule management

### 📁 File Manager
- Browse workspace files
- Built-in code editor
- Execute files with multiple interpreters (Python, Bash, Node.js)
- File upload functionality
- Execution history tracking
- Real-time execution results

### 💻 Enhanced Terminal
- Interactive Python terminal with persistent state
- Pre-loaded Lightning SDK objects
- Quick command presets
- Syntax highlighting
- Multi-line command support

### 📊 Comprehensive Logging
- Real-time activity monitoring
- Advanced log filtering and search
- Export functionality
- Detailed log viewer
- Health check monitoring

### 🔧 Debug Tools
- System status overview
- Environment configuration display
- Database health checks
- Service status monitoring
- Performance statistics

## Installation

1. Clone or create the project structure:
```bash
mkdir lightning-dashboard
cd lightning-dashboard
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Create the data directory:
```bash
mkdir data
```

## Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# Lightning AI Configuration
STUDIO_NAME=your-studio-name
TEAMSPACE=your-teamspace
USERNAME=your-username

# Supabase Configuration (for logging)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_API_KEY=your-supabase-api-key

# Application Configuration
SECRET_KEY=your-secret-key-change-this
DEBUG=False
PORT=8080
```

### Supabase Setup

Create a table named `studio_logs` in your Supabase database:

```sql
CREATE TABLE studio_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(255) NOT NULL,
    note TEXT,
    type VARCHAR(50) DEFAULT 'event',
    metadata JSONB
);

-- Create an index for better performance
CREATE INDEX idx_studio_logs_timestamp ON studio_logs(timestamp);
CREATE INDEX idx_studio_logs_type ON studio_logs(type);
```

## Running the Application

### Development
```bash
python main.py
```

### Production with Gunicorn
```bash
gunicorn main:app --bind 0.0.0.0:8080 --workers 1 --timeout 120
```

### Using Procfile (for deployment platforms)
The included `Procfile` allows easy deployment to platforms like Heroku:
```
web: gunicorn main:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
```

## Usage

### Dashboard
- Access the main dashboard at `/`
- Monitor real-time studio status
- Use quick action buttons for immediate control
- View activity timeline with different time ranges

### Scheduler
- Access scheduler at `/scheduler`
- Create automated start/stop schedules
- Configure post-start and pre-stop commands
- Manage existing schedules

### File Manager
- Access file manager at `/files`
- Browse and edit workspace files
- Execute scripts with different interpreters
- Upload new files
- View execution history

### Terminal
- Access Python terminal at `/terminal`
- Interactive Python environment with Lightning SDK
- Persistent variable state
- Quick command presets

### Logs
- Access logs at `/logs`
- Filter by event type and time range
- Search through log entries
- Export logs for analysis

### Debug
- Access debug info at `/debug`
- View system status and configuration
- Run health checks
- Monitor service statistics

## Project Structure

```
├── main.py                 # Application entry point
├── app/
│   ├── __init__.py
│   ├── dashboard.py        # Main dashboard application
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── main_routes.py  # Main page routes
│   │   ├── api_routes.py   # API endpoints
│   │   ├── scheduler_routes.py  # Scheduler management
│   │   └── files_routes.py # File management
│   ├── services/
│   │   ├── __init__.py
│   │   ├── lightning_service.py    # Lightning AI integration
│   │   ├── scheduler_service.py    # Scheduling logic
│   │   └── file_service.py         # File operations
│   └── utils/
│       ├── __init__.py
│       └── logging_utils.py        # Logging utilities
├── templates/
│   ├── base.html           # Base template
│   ├── dashboard.html      # Main dashboard
│   ├── scheduler.html      # Scheduler interface
│   ├── files.html          # File manager
│   ├── terminal.html       # Python terminal
│   ├── logs.html           # Log viewer
│   └── debug.html          # Debug information
├── data/                   # Data storage (created automatically)
├── requirements.txt        # Python dependencies
├── Procfile               # Deployment configuration
├── .env.example           # Environment variables template
└── README.md              # This file
```

## Features in Detail

### Scheduler Service
- **One-time schedules**: Execute actions at specific date/time
- **Daily schedules**: Repeat actions daily at specified time
- **Weekly schedules**: Repeat actions on specific days of the week
- **Command execution**: Run custom commands before/after studio operations
- **Persistent storage**: Schedules stored in JSON files

### File Service
- **Multi-interpreter support**: Python, Bash, Node.js, and custom interpreters
- **Execution tracking**: Complete history of all file executions
- **Real-time results**: Live output display during execution
- **File management**: Create, edit, delete, and upload files
- **Security**: Configurable timeouts and execution limits

### Lightning Service
- **Enhanced monitoring**: Continuous status checking with state change detection
- **Multiple machine types**: Support for CPU, GPU, and GPU_FAST machines
- **Error handling**: Robust error handling and recovery
- **Async operations**: Non-blocking start/stop operations with progress tracking

## Security Considerations

- Set strong `SECRET_KEY` in production
- Disable `DEBUG` mode in production
- Secure your Supabase API keys
- Consider implementing authentication for production use
- Review file execution permissions and timeouts

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is provided as-is for educational and development purposes.
