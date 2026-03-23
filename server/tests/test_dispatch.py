import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from main import app
from database import models

client = TestClient(app)

@pytest.fixture
def mock_supabase_user():
    """Mock the Depends(get_current_user) dependency."""
    class MockUser:
        id = "test-user-123"
        email = "test@example.com"
        phone = None
    
    # We override the dependency in the app
    from main import get_current_user
    app.dependency_overrides[get_current_user] = lambda: MockUser()
    yield MockUser()
    app.dependency_overrides.clear()

@patch("main.parse_intent", new_callable=AsyncMock)
@patch("main.models.get_user_projects")
@patch("main.models.create_project")
@patch("main.get_terminal_access")
@patch("main.models.upsert_user")
def test_transcribe_text_create_project(mock_upsert, mock_get_terminal, mock_create_proj, mock_get_proj, mock_parse_intent, mock_supabase_user):
    """Test the core workflow of parsing a text command to create a project."""
    mock_get_terminal.return_value = False
    
    mock_get_proj.return_value = []
    mock_parse_intent.return_value = {
        "intent": "create_project",
        "project_name": "My New App",
        "task_description": None
    }
    mock_create_proj.return_value = "proj-123"
    
    response = client.post("/transcribe-text", json={"text": "create a project called My New App"})
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "success"
    assert data["intent"]["intent"] == "create_project"
    assert data["created"]["project_id"] == "proj-123"
    
    mock_upsert.assert_called_once()
    mock_parse_intent.assert_called_once()
    mock_create_proj.assert_called_once_with("test-user-123", "My New App")

@patch("main.parse_intent", new_callable=AsyncMock)
@patch("main.models.get_user_projects")
@patch("main.models.get_project_by_name")
@patch("main.models.touch_project")
@patch("main.models.create_task")
@patch("main.models.log_agent_event_task")
@patch("main.agent_dispatch_task")
@patch("main.get_terminal_access")
@patch("main.models.upsert_user")
def test_transcribe_text_create_task(
    mock_upsert, mock_get_terminal, mock_dispatch, mock_log_task, mock_create_task, mock_touch,
    mock_get_proj_name, mock_get_proj, mock_parse_intent, mock_supabase_user
):
    """Test the core workflow of parsing a text command to create and dispatch a task."""
    mock_get_terminal.return_value = False
    
    # Mock existing project
    mock_get_proj.return_value = [{"id": "proj-123", "name": "My App"}]
    mock_get_proj_name.return_value = {"id": "proj-123", "name": "My App"}
    
    mock_parse_intent.return_value = {
        "intent": "create_task",
        "project_name": "My App",
        "task_description": "add a login button"
    }
    mock_create_task.return_value = "task-456"
    mock_log_task.return_value = "log-789"
    
    response = client.post("/transcribe-text", json={"text": "in My App add a login button"})
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "success"
    assert data["intent"]["intent"] == "create_task"
    assert data["created"]["task_id"] == "task-456"
    assert data["agent_status"] == "dispatching"
    
    mock_create_task.assert_called_once()
    assert mock_create_task.call_args.kwargs["project_id"] == "proj-123"
    assert mock_create_task.call_args.kwargs["user_id"] == "test-user-123"
    
    # Verify the background task was dispatched
    # Note: TestClient runs BackgroundTasks synchronously after the response is returned
    # But because we mocked agent_dispatch_task, it just gets called.
    mock_dispatch.assert_called_once()
    assert mock_dispatch.call_args[0][0] == "task-456"
