from app.api.security import RateLimiter

AUTH = {"Authorization": "Bearer secret-key"}


def test_without_access_key_api_is_open(make_client) -> None:
    client = make_client([])
    assert client.get("/api/profiles").status_code == 200
    assert client.get("/api/auth/check").status_code == 204


def test_access_key_is_required_when_configured(make_client, profile_payload) -> None:
    client = make_client([], access_key="secret-key")

    assert client.get("/api/profiles").status_code == 401
    assert client.post("/api/profiles", json=profile_payload).status_code == 401
    assert client.post("/api/speech/synthesize", json={"text": "Hi"}).status_code == 401
    wrong = client.get("/api/auth/check", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    assert wrong.headers["WWW-Authenticate"] == "Bearer"

    assert client.get("/api/auth/check", headers=AUTH).status_code == 204
    assert client.post("/api/profiles", json=profile_payload, headers=AUTH).status_code == 201


def test_health_stays_public(make_client) -> None:
    client = make_client([], access_key="secret-key")
    assert client.get("/api/health").status_code == 200


def test_cors_preflight_allows_authorization_header(make_client) -> None:
    client = make_client([], access_key="secret-key")
    response = client.options(
        "/api/profiles",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_origin_regex(make_client) -> None:
    client = make_client([], cors_origin_regex=r"https://tutor-[a-z0-9]+\.vercel\.app")
    allowed = client.get("/api/health", headers={"Origin": "https://tutor-abc123.vercel.app"})
    denied = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://tutor-abc123.vercel.app"
    assert "access-control-allow-origin" not in denied.headers


def test_speech_is_rate_limited(make_client) -> None:
    client = make_client([], rate_limit_per_minute=2)
    for _ in range(2):
        assert client.post("/api/speech/synthesize", json={"text": "Hi"}).status_code == 200
    limited = client.post("/api/speech/synthesize", json={"text": "Hi"})
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"
    # Cheap read endpoints are not limited.
    assert client.get("/api/profiles").status_code == 200


def test_rate_limiter_window_slides() -> None:
    now = 0.0
    limiter = RateLimiter(2, window_seconds=60, clock=lambda: now)
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")  # limits are per client
    now = 61.0
    assert limiter.allow("a")
