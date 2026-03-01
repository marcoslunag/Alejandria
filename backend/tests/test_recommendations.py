"""Tests for the recommendations endpoint"""


def test_recommendations_empty_library(client, auth_headers):
    """Recommendations endpoint returns valid response even with empty library."""
    resp = client.get("/api/v1/recommendations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "recommendations" in data
    assert "total" in data
    assert isinstance(data["recommendations"], list)
    assert data["total"] == len(data["recommendations"])


def test_recommendations_requires_auth(client):
    """Recommendations endpoint requires authentication."""
    resp = client.get("/api/v1/recommendations")
    assert resp.status_code in (401, 403)


def test_recommendations_type_filter(client, auth_headers):
    """Type filter parameter is accepted."""
    for content_type in ("all", "manga", "comics", "books"):
        resp = client.get("/api/v1/recommendations",
                          params={"type": content_type}, headers=auth_headers)
        assert resp.status_code == 200, f"Failed for type={content_type}: {resp.text}"


def test_recommendations_invalid_type(client, auth_headers):
    """Invalid type filter returns 422."""
    resp = client.get("/api/v1/recommendations", params={"type": "invalid"}, headers=auth_headers)
    assert resp.status_code == 422
