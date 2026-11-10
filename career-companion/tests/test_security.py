"""Local endpoint protection (decision D2)."""

import pytest
from fastapi.testclient import TestClient

from companion.config import Settings
from companion.security import COOKIE_NAME, CSRF_HEADER
from tests.conftest import BASE

MEMORY = {"kind": "goal", "text": "synthetic goal"}


def test_refuses_to_bind_anything_but_loopback(tmp_path):
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, host="0.0.0.0")


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1:9999", "attacker.test:8765", ""])
def test_dns_rebinding_host_header_is_rejected(app, host):
    c = TestClient(app, base_url=BASE)
    assert c.get("/", headers={"host": host}).status_code == 400


def test_api_requires_a_session(anon):
    assert anon.get("/api/bootstrap").status_code == 401
    assert anon.get("/api/export").status_code == 401
    r = anon.post("/api/memory", json=MEMORY, headers={"origin": BASE})
    assert r.status_code == 401


def test_signed_in_request_works(client):
    assert client.get("/api/bootstrap").status_code == 200
    assert client.post("/api/memory", json=MEMORY).status_code == 200


def test_cross_origin_post_is_rejected_even_with_valid_cookie_and_token(client):
    r = client.post("/api/memory", json=MEMORY, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/memory", json=MEMORY, headers={"origin": "null"})
    assert r.status_code == 403


def test_cross_site_fetch_metadata_is_rejected(client):
    assert client.get("/api/memory", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.get("/api/memory", headers={"sec-fetch-site": "same-site"}).status_code == 403
    assert client.get("/api/memory", headers={"sec-fetch-site": "same-origin"}).status_code == 200


def test_state_change_without_origin_is_rejected(app, client):
    sid = client.cookies.get(COOKIE_NAME)
    bare = TestClient(app, base_url=BASE, headers={CSRF_HEADER: client.headers[CSRF_HEADER]})
    bare.cookies.set(COOKIE_NAME, sid)
    assert bare.post("/api/memory", json=MEMORY).status_code == 403


def test_csrf_header_is_required_and_checked(app, client):
    sid = client.cookies.get(COOKIE_NAME)
    for headers in ({"origin": BASE}, {"origin": BASE, CSRF_HEADER: "wrong"}):
        c = TestClient(app, base_url=BASE, headers=headers)
        c.cookies.set(COOKIE_NAME, sid)
        assert c.post("/api/memory", json=MEMORY).status_code == 403


def test_form_posts_are_rejected(client):
    """A cross-site HTML form can only send form encodings, never JSON."""
    r = client.post("/api/memory", content="kind=goal&text=x",
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415
    r = client.post("/api/memory", content='{"kind":"goal","text":"x"}', headers={"content-type": "text/plain"})
    assert r.status_code == 415


def test_no_cors_and_no_preflight(client):
    r = client.options("/api/memory", headers={"origin": "https://evil.example",
                                               "access-control-request-method": "POST"})
    assert r.status_code in (403, 405)
    ok = client.get("/api/memory")
    assert "access-control-allow-origin" not in {k.lower() for k in ok.headers}


def test_oversized_body_is_rejected(client):
    r = client.post("/api/imports", content=b"x" * 1_000_001, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_security_headers_on_every_response(client, anon):
    for resp in (client.get("/api/bootstrap"), anon.get("/"), anon.get("/api/bootstrap"),
                 anon.get("/static/app.js")):
        csp = resp.headers["content-security-policy"]
        assert "default-src 'none'" in csp and "script-src 'self'" in csp and "unsafe-inline" not in csp
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["cache-control"] == "no-store"


def test_launch_token_is_single_use(app, anon):
    token = app.state.security.launch_token
    assert anon.post("/auth/exchange", json={"token": "wrong"}, headers={"origin": BASE}).status_code == 403
    r = anon.post("/auth/exchange", json={"token": token}, headers={"origin": BASE})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert anon.get("/api/bootstrap").status_code == 200  # cookie now set
    again = TestClient(app, base_url=BASE)
    assert again.post("/auth/exchange", json={"token": token}, headers={"origin": BASE}).status_code == 403


def test_token_guessing_locks_out(app, anon):
    for _ in range(5):
        anon.post("/auth/exchange", json={"token": "guess"}, headers={"origin": BASE})
    r = anon.post("/auth/exchange", json={"token": app.state.security.launch_token}, headers={"origin": BASE})
    assert r.status_code == 403


def test_exchange_rejects_cross_origin(app, anon):
    r = anon.post("/auth/exchange", json={"token": app.state.security.launch_token},
                  headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_unsigned_visitor_gets_login_page_not_app(anon):
    r = anon.get("/")
    assert r.status_code == 200 and "login.js" in r.text and "app.js" not in r.text


def test_api_docs_are_not_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_unknown_fields_are_rejected(client):
    assert client.post("/api/memory", json={**MEMORY, "provenance": "user_confirmed"}).status_code == 422


def test_delete_needs_origin_and_csrf_too(app, client):
    mid = client.post("/api/memory", json=MEMORY).json()["id"]
    sid = client.cookies.get(COOKIE_NAME)
    for headers in ({}, {"origin": BASE}, {"origin": "https://evil.example", CSRF_HEADER: client.headers[CSRF_HEADER]}):
        c = TestClient(app, base_url=BASE, headers=headers)
        c.cookies.set(COOKIE_NAME, sid)
        assert c.delete(f"/api/memory/{mid}").status_code == 403
    assert client.delete(f"/api/memory/{mid}").json()["deleted"]
