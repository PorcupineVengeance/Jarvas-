import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user
from app.api.files import extract_text
from app.api.chat import resolve_mode
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import StoredFile, Task, User


def delete_json(http: TestClient, path: str, payload: dict, headers: dict | None = None):
    merged = {"Content-Type": "application/json", **(headers or {})}
    return http.request("DELETE", path, content=json.dumps(payload), headers=merged)


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(User(open_id="test-user", display_name="Test Operator"))
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    def override_user():
        return User(open_id="test-user", display_name="Test Operator")

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as test_client:
        yield test_client, factory
    app.dependency_overrides.clear()
    engine.dispose()


ALLOWED_ORIGIN = {"Origin": "http://localhost:3000"}


def test_health_and_route_manifest_are_real_endpoints(client):
    http, _ = client
    health = http.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    manifest = http.get("/manus-routes.json")
    assert manifest.status_code == 200
    paths = {route["path"] for route in manifest.json()["routes"]}
    assert paths == {"/", "/chat", "/voice", "/tools", "/settings", "/about"}


def test_mutations_reject_missing_and_foreign_origins(client):
    http, factory = client
    assert http.post("/api/tasks", json={"title": "No Origin"}).status_code == 403
    assert http.post("/api/tasks", json={"title": "Foreign"}, headers={"Origin": "https://attacker.invalid"}).status_code == 403
    with factory() as db:
        assert db.scalar(select(Task.id)) is None


def test_task_crud_is_scoped_and_requires_delete_confirmation(client):
    http, factory = client
    response = http.post("/api/tasks", headers=ALLOWED_ORIGIN, json={"title": "Review launch brief", "priority": "high"})
    assert response.status_code == 201
    task = response.json()
    assert task["status"] == "open"
    listed = http.get("/api/tasks")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [task["id"]]
    updated = http.patch(f"/api/tasks/{task['id']}", headers=ALLOWED_ORIGIN, json={"status": "in_progress"})
    assert updated.status_code == 200 and updated.json()["status"] == "in_progress"
    assert delete_json(http, f"/api/tasks/{task['id']}", {"confirmed": False}, ALLOWED_ORIGIN).status_code == 409
    assert delete_json(http, f"/api/tasks/{task['id']}", {"confirmed": True}, ALLOWED_ORIGIN).status_code == 200
    with factory() as db:
        db.add(Task(id="other-user-task", owner_id="another-user", title="Private", status="open", priority="normal"))
        db.commit()
    assert http.patch("/api/tasks/other-user-task", headers=ALLOWED_ORIGIN, json={"title": "Changed"}).status_code == 404


def test_memory_crud_rejects_credentials(client):
    http, _ = client
    created = http.post("/api/memory", headers=ALLOWED_ORIGIN, json={"category": "preference", "content": "Prefers concise summaries"})
    assert created.status_code == 201
    memory_id = created.json()["id"]
    assert http.patch(f"/api/memory/{memory_id}", headers=ALLOWED_ORIGIN, json={"content": "Prefers thorough, structured summaries"}).status_code == 200
    rejected = http.patch(f"/api/memory/{memory_id}", headers=ALLOWED_ORIGIN, json={"content": "api_key=sk-ABCDEFGHIJKLMNOPQRST"})
    assert rejected.status_code == 422
    assert http.delete(f"/api/memory/{memory_id}", headers=ALLOWED_ORIGIN).status_code == 200
    assert http.get("/api/memory").json() == []


def test_file_record_removal_requires_confirmation_and_is_soft_delete(client):
    http, factory = client
    with factory() as db:
        db.add(StoredFile(id="file-1", owner_id="test-user", filename="notes.txt", object_key="jarvis/test/notes.txt", content_type="text/plain", size_bytes=5, extracted_text="hello"))
        db.commit()
    assert delete_json(http, "/api/files/file-1", {"confirmed": False}, ALLOWED_ORIGIN).status_code == 409
    removed = delete_json(http, "/api/files/file-1", {"confirmed": True}, ALLOWED_ORIGIN)
    assert removed.status_code == 200
    assert removed.json()["deletion"] == "metadata_hidden"
    assert http.get("/api/files/file-1").status_code == 404


def test_file_extraction_and_automatic_modes_are_bounded_and_real():
    assert "name | priority" in extract_text("tasks.csv", b"name,priority\nReview,high\n")
    assert '"priority": "high"' in extract_text("record.json", b'{"priority":"high"}')
    assert resolve_mode("Find the latest release notes and cite sources", "auto") == "research"
    assert resolve_mode("Explain this Python stack trace", "auto") == "developer"
    assert resolve_mode("Summarize my open tasks", "auto") == "assistant"
    assert resolve_mode("Open Chrome and take a screenshot", "auto") == "automation"
    assert resolve_mode("Make this answer concise", "focus") == "focus"
    # Voice/wake must promote into tool modes or the model falsely refuses access.
    assert resolve_mode("Open my Downloads folder", "voice") == "automation"
    assert resolve_mode("Control my laptop and check storage", "voice") == "automation"
    assert resolve_mode("Can you access my computer?", "voice") == "automation"
    assert resolve_mode("What's the weather right now?", "voice") == "research"
    assert resolve_mode("How much disk space do I have?", "voice") == "automation"


def test_desktop_info_reports_web_runtime_without_claiming_control(client):
    http, _ = client
    info = http.get("/api/desktop/info")
    assert info.status_code == 200
    body = info.json()
    assert body["is_desktop"] is False
    assert body["computer_control"] is False
    assert "downloads" in body
    blocked = http.put("/api/desktop/settings", headers=ALLOWED_ORIGIN, json={"computer_control": True, "allowed_paths": ["~/Desktop"]})
    assert blocked.status_code == 400


def test_no_database_write_is_needed_for_health():
    # A stable contract check for the app's public liveness endpoint, independent of managed DB state.
    with TestClient(app) as http:
        response = http.get("/api/health")
    assert response.status_code == 200
