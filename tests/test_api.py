from marketplace.api import create_app


def test_health_endpoint(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
