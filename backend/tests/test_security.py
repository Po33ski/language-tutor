from langchain_core.messages import AIMessage

from app.api.security import RateLimiter
from tests.test_lessons import _send, _start_lesson


def test_only_health_signup_and_login_are_public(make_client) -> None:
    client = make_client([], signed_in=False)
    assert client.get("/api/health").status_code == 200
    for method, path in [
        ("get", "/api/auth/me"),
        ("get", "/api/profile"),
        ("get", "/api/lessons"),
        ("post", "/api/lessons"),
        ("get", "/api/lessons/some-id"),
        ("post", "/api/speech/synthesize"),
    ]:
        response = client.request(method, path, json={})
        assert response.status_code == 401, path
        assert response.headers["WWW-Authenticate"] == "Bearer"
    bad_token = client.get("/api/auth/me", headers={"Authorization": "Bearer made-up"})
    assert bad_token.status_code == 401


def test_cors_preflight_allows_authorization_header(make_client) -> None:
    client = make_client([], signed_in=False)
    response = client.options(
        "/api/profile",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_origin_regex(make_client) -> None:
    client = make_client(
        [], signed_in=False, cors_origin_regex=r"https://tutor-[a-z0-9]+\.vercel\.app"
    )
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
    assert client.get("/api/auth/me").status_code == 200
    # Each endpoint group has its own budget: transcription still works.
    files = {"audio": ("answer.webm", b"audio", "audio/webm")}
    assert client.post("/api/speech/transcribe", files=files).status_code == 200


def test_daily_transcription_limit_per_user(make_client) -> None:
    client = make_client([], user_daily_transcriptions=2)
    files = {"audio": ("answer.webm", b"audio", "audio/webm")}
    for _ in range(2):
        assert client.post("/api/speech/transcribe", files=files).status_code == 200
    limited = client.post("/api/speech/transcribe", files=files)
    assert limited.status_code == 429
    assert "today's limit" in limited.json()["detail"]


def test_daily_tutor_turn_limit_for_the_whole_app(make_client, profile_payload) -> None:
    client = make_client([AIMessage("Hi Anna!")], daily_tutor_turns_total=1)
    lesson_id = _start_lesson(client, profile_payload)
    _send(client, lesson_id, None)  # the kickoff is the one allowed turn
    limited = client.post(f"/api/lessons/{lesson_id}/messages", json={"content": "Hello"})
    assert limited.status_code == 429
    assert "busy" in limited.json()["detail"]


def test_rate_limiter_window_slides() -> None:
    now = 0.0
    limiter = RateLimiter(2, window_seconds=60, clock=lambda: now)
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")  # limits are per client
    now = 61.0
    assert limiter.allow("a")


def test_rate_limiter_counts_only_recorded_events() -> None:
    now = 0.0
    limiter = RateLimiter(2, window_seconds=60, clock=lambda: now)
    assert not limiter.is_limited("a")
    limiter.record("a")
    limiter.record("a")
    assert limiter.is_limited("a")
    now = 61.0
    assert not limiter.is_limited("a")
