from marketplace.api import create_app


def test_health_endpoint(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "database": "ok"}


def test_metrics_and_paginated_products_endpoints(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    client = app.test_client()

    products = client.get("/api/v1/products?limit=2&offset=0")
    metrics = client.get("/api/v1/metrics")
    assert products.status_code == 200
    assert products.json == {"items": [], "limit": 2, "offset": 0}
    assert metrics.status_code == 200
    assert b"marketplace_pages_total" in metrics.data


def test_missing_route_remains_a_404(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    assert app.test_client().get("/does-not-exist").status_code == 404


def test_invalid_match_decision_is_a_400(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    response = app.test_client().post(
        "/api/v1/match-candidates/1/decision", json={"decision": "maybe"}
    )
    assert response.status_code == 400
