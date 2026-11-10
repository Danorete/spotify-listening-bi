"""API key storage in the macOS Keychain (decision D14). No file or environment fallback."""

from __future__ import annotations

SERVICE = "career-companion"
ACCOUNT = "anthropic-api-key"


def get_api_key() -> str | None:
    try:
        import keyring

        return keyring.get_password(SERVICE, ACCOUNT) or None
    except Exception:
        return None


def set_api_key(value: str) -> None:
    import keyring

    keyring.set_password(SERVICE, ACCOUNT, value)


def delete_api_key() -> None:
    import keyring

    try:
        keyring.delete_password(SERVICE, ACCOUNT)
    except Exception:
        pass
