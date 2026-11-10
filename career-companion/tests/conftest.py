"""Shared fixtures. All data here is synthetic; nothing describes a real person."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from companion.ai import MockAI
from companion.config import Settings
from companion.db import Database
from companion.security import COOKIE_NAME, CSRF_HEADER

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", port=PORT, ai_mode="mock")


@pytest.fixture
def db(settings):
    d = Database(settings.db_path)
    yield d
    d.close()


@pytest.fixture
def mock_ai():
    return MockAI()


@pytest.fixture
def app(settings, mock_ai):
    from companion.app import create_app

    return create_app(settings, ai_client=mock_ai)


@pytest.fixture
def anon(app):
    """A browser with no session."""
    return TestClient(app, base_url=BASE)


@pytest.fixture
def client(app):
    """A signed-in browser: session cookie, CSRF header, same-origin Origin."""
    sid, csrf = app.state.security.new_session_for_tests()
    c = TestClient(app, base_url=BASE, headers={CSRF_HEADER: csrf, "origin": BASE})
    c.cookies.set(COOKIE_NAME, sid)
    return c
