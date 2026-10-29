from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_reports_demo_mode():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_requires_a_style_input():
    response = client.post("/api/style/analyze", data={"profile_json": "{}", "mode": "demo"})
    assert response.status_code == 422


def test_feedback_is_session_scoped():
    response = client.post("/api/feedback", json={"recommendation_id": "cos", "action": "like"})
    assert response.status_code == 200
    assert response.json()["session_only"] is True

