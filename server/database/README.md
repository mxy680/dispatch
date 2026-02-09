# Database Documentation

## Overview
SQLite database for the Dispatch Voice Agent project. Stores projects, tasks, call sessions, and user preferences.

## Database Location
- **File:** `server/dispatch.db`
- **Type:** SQLite3
- **Initialized by:** `connection.py`

## Tables

### 1. Projects
Stores coding projects that users work on via voice commands.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | Primary key (UUID) |
| user_id | TEXT | User who owns the project |
| name | TEXT | Project name |
| file_path | TEXT | Local path to project files |
| status | TEXT | 'active' or 'paused' |
| created_at | TIMESTAMP | When project was created |
| last_accessed | TIMESTAMP | Last time project was used |

### 2. Tasks
Individual coding tasks within projects.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | Primary key (UUID) |
| project_id | TEXT | Foreign key to projects |
| description | TEXT | What needs to be done |
| status | TEXT | 'pending', 'in_progress', 'completed' |
| assigned_to_claude_instance | TEXT | Which Claude Code instance is working on it |
| created_at | TIMESTAMP | When task was created |
| completed_at | TIMESTAMP | When task was finished (null if pending) |

### 3. Call Sessions
Records of phone calls made to the system.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | Primary key (UUID) |
| user_id | TEXT | Who made the call |
| phone_number | TEXT | Caller's phone number |
| started_at | TIMESTAMP | When call began |
| ended_at | TIMESTAMP | When call ended (null if ongoing) |
| transcript | TEXT | Full conversation transcript |
| commands_executed | TEXT | List of commands run during call |

### 4. User Preferences
User settings and preferences.

| Column | Type | Description |
|--------|------|-------------|
| user_id | TEXT | Primary key |
| phone_number | TEXT | User's verified phone number |
| default_project | TEXT | Default project to use |
| voice_speed | TEXT | TTS speed preference ('slow', 'normal', 'fast') |
| email_notifications | INTEGER | 1 = enabled, 0 = disabled |
| sms_notifications | INTEGER | 1 = enabled, 0 = disabled |

## Usage

### Initialize the Database
```python
from database.connection import init_database

init_database()
```

### Working with Projects
```python
from database import models

# Create a new project
project_id = models.create_project(
    user_id="user@example.com",
    name="My React App",
    file_path="/Users/zeynep/projects/react-app"
)

# Get all projects for a user
projects = models.get_user_projects("user@example.com")

# Get specific project
project = models.get_project_by_id(project_id)
```

### Working with Tasks
```python
# Create a task
task_id = models.create_task(
    project_id="abc-123",
    description="Add user authentication"
)

# Get all tasks for a project
tasks = models.get_project_tasks("abc-123")

# Update task status
models.update_task_status(task_id, "completed")
```

### Working with Call Sessions
```python
# Start a call session
session_id = models.create_call_session(
    user_id="user@example.com",
    phone_number="+1234567890"
)

# End the call and save transcript
models.update_call_session(
    session_id=session_id,
    transcript="User asked to work on authentication feature",
    commands_executed="start_task, assign_claude"
)

# Get call history
history = models.get_user_call_history("user@example.com", limit=10)
```

## File Structure
```
database/
├── __init__.py          # Makes this a Python package
├── connection.py        # Database connection and initialization
├── models.py            # CRUD operations
├── schema.sql           # Table definitions
└── README.md            # This file
```

## Future Enhancements

- [ ] Add indexes for faster queries (user_id, project_id)
- [ ] Add migration system for schema changes
- [ ] Add data validation functions
- [ ] Add backup/restore utilities
- [ ] Switch to PostgreSQL for production deployment

## Notes

- SQLite is used for development only
- For production, migrate to PostgreSQL or MongoDB Atlas
- The `dispatch.db` file is gitignored (don't commit it to version control)
- All IDs use UUID4 for uniqueness across distributed systems