import asyncio
import sqlite3
from datetime import timedelta

import httpx
import pytest
from langchain_core.messages import AIMessage
from langgraph.store.sqlite.aio import AsyncSqliteStore

from app.auth import cli
from app.auth import store as store_module
from app.auth.passwords import PasswordPolicyError, check_policy, hash_password, is_breached
from app.auth.store import UserStore, hash_token
from app.storage import memory
from tests.conftest import STRONG_PASSWORD, sign_up
from tests.test_lessons import _send, _start_lesson

CREDENTIALS = {"email": "anna@example.com", "password": STRONG_PASSWORD}


def _login(client, email="anna@example.com", password=STRONG_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- Signup ----------------------------------------------------------------------


def test_signup_signs_in_and_normalizes_the_email(make_client) -> None:
    client = make_client([], signed_in=False)
    body = sign_up(client, email="  Anna@Example.COM ")
    assert body["account"]["email"] == "anna@example.com"
    assert body["account"]["has_profile"] is False
    assert client.get("/api/auth/me").json()["email"] == "anna@example.com"


def test_signup_rejects_a_taken_email_in_any_case(make_client) -> None:
    client = make_client([], signed_in=False)
    sign_up(client)
    again = client.post(
        "/api/auth/signup", json={"email": "ANNA@example.com", "password": STRONG_PASSWORD}
    )
    assert again.status_code == 409


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("short pass", "at least 15 characters"),
        ("aaaaaaaaaaaaaaaaaaaa", "too repetitive"),
        ("anna is learning english fast", "your email"),
    ],
)
def test_signup_password_policy(make_client, password: str, message: str) -> None:
    client = make_client([], signed_in=False)
    response = client.post(
        "/api/auth/signup", json={"email": "anna@example.com", "password": password}
    )
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_signup_rejects_invalid_email(make_client) -> None:
    client = make_client([], signed_in=False)
    response = client.post(
        "/api/auth/signup", json={"email": "not-an-email", "password": STRONG_PASSWORD}
    )
    assert response.status_code == 422


def test_signup_rejects_breached_password(make_client, monkeypatch) -> None:
    async def breached(password, client):
        return True

    monkeypatch.setattr("app.api.auth.is_breached", breached)
    client = make_client([], signed_in=False, password_breach_check=True)
    response = client.post("/api/auth/signup", json=CREDENTIALS)
    assert response.status_code == 422
    assert "data breach" in response.json()["detail"]


def test_signups_are_limited_per_network(make_client) -> None:
    client = make_client([], signed_in=False, signups_per_ip_per_hour=2)
    for index in range(2):
        sign_up(client, email=f"user{index}@example.com")
    blocked = client.post(
        "/api/auth/signup", json={"email": "user9@example.com", "password": STRONG_PASSWORD}
    )
    assert blocked.status_code == 429


def test_passwords_and_tokens_are_stored_hashed(make_client, tmp_path) -> None:
    client = make_client([], signed_in=False)
    token = sign_up(client)["token"]
    db = sqlite3.connect(tmp_path / "users.db")
    (password_hash,) = db.execute("SELECT password_hash FROM users").fetchone()
    tokens = [row[0] for row in db.execute("SELECT token_hash FROM sessions")]
    assert password_hash.startswith("$argon2id$")
    assert STRONG_PASSWORD not in password_hash
    assert tokens == [hash_token(token)]


# --- Login, logout, password change ------------------------------------------------


def test_login_with_correct_and_wrong_credentials(make_client) -> None:
    client = make_client([], signed_in=False)
    sign_up(client)
    ok = _login(client, email="ANNA@example.com")
    assert ok.status_code == 200
    assert ok.json()["token"] != client.headers["Authorization"].removeprefix("Bearer ")

    wrong_password = _login(client, password="wrong password but long enough")
    unknown_email = _login(client, email="nobody@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    # The same message, so the response does not reveal which emails have accounts.
    assert wrong_password.json() == unknown_email.json()


def test_failed_logins_are_limited_per_account(make_client) -> None:
    client = make_client([], signed_in=False)
    sign_up(client)
    for _ in range(10):
        assert _login(client, password="wrong password but long enough").status_code == 401
    # Even the right password is refused until the window passes.
    assert _login(client).status_code == 429


def test_logout_ends_only_this_session(make_client) -> None:
    client = make_client([])
    other_token = _login(client).json()["token"]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    other = {"Authorization": f"Bearer {other_token}"}
    assert client.get("/api/auth/me", headers=other).status_code == 200


def test_change_password(make_client) -> None:
    client = make_client([])
    other_token = _login(client).json()["token"]
    new_password = "a completely different phrase"

    wrong = client.post(
        "/api/auth/password",
        json={"current_password": "not my password at all", "new_password": new_password},
    )
    assert wrong.status_code == 403
    weak = client.post(
        "/api/auth/password", json={"current_password": STRONG_PASSWORD, "new_password": "short"}
    )
    assert weak.status_code == 422

    changed = client.post(
        "/api/auth/password",
        json={"current_password": STRONG_PASSWORD, "new_password": new_password},
    )
    assert changed.status_code == 204
    assert client.get("/api/auth/me").status_code == 200  # this session stays
    other = {"Authorization": f"Bearer {other_token}"}
    assert client.get("/api/auth/me", headers=other).status_code == 401  # others end
    assert _login(client).status_code == 401
    assert _login(client, password=new_password).status_code == 200


# --- Ownership ---------------------------------------------------------------------


def test_users_cannot_see_each_others_lessons(make_client, profile_payload) -> None:
    client = make_client([AIMessage("Hi Anna!")])
    lesson_id = _start_lesson(client, profile_payload)
    _send(client, lesson_id, None)
    anna = client.headers["Authorization"]

    sign_up(client, email="bob@example.com")  # now acting as Bob
    assert client.get("/api/profile").status_code == 404
    assert client.get("/api/lessons").json() == []
    assert client.get(f"/api/lessons/{lesson_id}").status_code == 404
    send = client.post(f"/api/lessons/{lesson_id}/messages", json={"content": "Hi"})
    assert send.status_code == 404
    assert client.post(f"/api/lessons/{lesson_id}/end").status_code == 404

    client.headers["Authorization"] = anna
    assert client.get(f"/api/lessons/{lesson_id}").status_code == 200


# --- Sessions (store level) ----------------------------------------------------------


def test_sessions_slide_and_hit_the_absolute_limit(tmp_path, monkeypatch) -> None:
    start = store_module._now()
    clock = {"now": start}
    monkeypatch.setattr(store_module, "_now", lambda: clock["now"])

    async def scenario() -> None:
        async with UserStore.open(
            tmp_path / "users.db", timedelta(days=30), timedelta(days=90)
        ) as users:
            user = await users.create_user("anna@example.com", "hash")
            token = await users.create_session(user.id)
            for day in (20, 40, 60, 80):  # used every 20 days: idle limit never hit
                clock["now"] = start + timedelta(days=day)
                assert await users.authenticate(token) is not None
            clock["now"] = start + timedelta(days=91)  # past the absolute maximum
            assert await users.authenticate(token) is None

            idle = await users.create_session(user.id)
            clock["now"] += timedelta(days=31)  # unused for longer than the idle limit
            assert await users.authenticate(idle) is None

    asyncio.run(scenario())


# --- Password helpers ------------------------------------------------------------------


def test_policy_accepts_a_long_passphrase() -> None:
    check_policy("purple elephants dance at noon", "anna@example.com")
    with pytest.raises(PasswordPolicyError):
        check_policy("x" * 129, "anna@example.com")


def _hibp(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_breach_check_uses_k_anonymity() -> None:
    # SHA-1("password") = 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, text="1E4C9B93F3F0682250B6CF8331B7EE68FD8:3861493\r\nAAAA:0")

    assert asyncio.run(is_breached("password", _hibp(handler))) is True
    assert seen["url"].endswith("/range/5BAA6")  # only 5 characters leave the server
    assert asyncio.run(is_breached("purple elephants dance", _hibp(handler))) is False


def test_breach_check_fails_open() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    assert asyncio.run(is_breached("password", _hibp(handler))) is False


# --- Admin commands ----------------------------------------------------------------------


def test_cli_claim_profile_and_reset_password(tmp_path, capsys) -> None:
    profile = memory.ProfileCreate(name="Old Anna", level="B1", main_topic="Travel")

    async def scenario() -> None:
        async with (
            UserStore.open(tmp_path / "users.db") as users,
            AsyncSqliteStore.from_conn_string(str(tmp_path / "memory.db")) as store,
        ):
            await store.setup()
            older = await memory.create_profile(store, profile)
            recent = await memory.create_profile(store, profile.model_copy(update={"name": "B"}))
            await memory.create_lesson(store, recent.id, "Travel")
            user = await users.create_user("anna@example.com", hash_password(STRONG_PASSWORD))

            await cli.claim_profile(users, store, "Anna@example.com", None, force=False)
            linked = await users.get_user(user.id)
            assert linked.profile_id == recent.id  # the most recently used profile
            assert older.id not in await users.linked_profile_ids()

            session = await users.create_session(user.id)
            await cli.reset_password(users, "anna@example.com")
            assert await users.authenticate(session) is None  # sessions are signed out

    asyncio.run(scenario())
    output = capsys.readouterr().out
    assert "Linked 'B'" in output
    assert "Temporary password for anna@example.com:" in output
