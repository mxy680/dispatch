from database import models


def test_device_pairing_roundtrip(test_db):
    pairing = models.create_device_pairing(user_id="user-1", name="My Mac", platform="darwin")
    assert pairing["device_id"]
    assert pairing["pairing_code"]

    completed = models.complete_device_pairing(
        pairing_code=pairing["pairing_code"],
        device_name="My Mac",
        platform="darwin",
    )
    assert completed is not None
    assert completed["device_id"] == pairing["device_id"]
    assert completed["device_token"]

    device = models.get_device_by_token(completed["device_token"])
    assert device is not None
    assert device["id"] == pairing["device_id"]
    assert device["user_id"] == "user-1"


def test_device_project_link_and_claim_command(test_db):
    project_id = models.create_project("user-1", "Proj")
    pairing = models.create_device_pairing(user_id="user-1", name="PC", platform="windows")
    completed = models.complete_device_pairing(pairing_code=pairing["pairing_code"])
    assert completed is not None
    device_id = completed["device_id"]

    models.link_device_project(device_id=device_id, project_id=project_id, local_path="/tmp/proj")
    links = models.get_device_project_links(device_id)
    assert len(links) == 1
    assert links[0]["project_id"] == project_id

    session_id = models.create_terminal_session(
        user_id="user-1",
        project_id=project_id,
        name="Unified Session",
        instance_id=None,
    )
    command_id = models.create_terminal_command(
        session_id=session_id,
        user_id="user-1",
        command="echo hello",
        source="typed",
        provider="shell",
    )
    claimed = models.claim_next_queued_command_for_device(device_id=device_id)
    assert claimed is not None
    assert claimed["id"] == command_id
    assert claimed["status"] == "running"


def test_cursor_context_save_and_load(test_db):
    project_id = models.create_project("user-1", "Proj")
    pairing = models.create_device_pairing(user_id="user-1", name="PC", platform="windows")
    completed = models.complete_device_pairing(pairing_code=pairing["pairing_code"])
    assert completed is not None

    ctx_id = models.save_cursor_context(
        device_id=completed["device_id"],
        project_id=project_id,
        file_path="/tmp/proj/main.py",
        selection="print('hello')",
        diagnostics="warning: unused import",
    )
    assert ctx_id
    latest = models.get_latest_cursor_context(device_id=completed["device_id"], project_id=project_id)
    assert latest is not None
    assert latest["file_path"] == "/tmp/proj/main.py"

