"""Settings. Everything has a safe default; environment variables override a few."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

LOOPBACK_HOST = "127.0.0.1"
AI_MODES = ("mock", "live", "off")


def default_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CareerCompanion"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "career-companion"


@dataclass
class Settings:
    data_dir: Path = field(default_factory=default_data_dir)
    host: str = LOOPBACK_HOST
    port: int = 8765
    ai_mode: str = "mock"
    monthly_budget_usd: float = 20.0
    hard_stop_usd: float = 16.0
    warn_usd: tuple[float, ...] = (10.0, 13.0)
    session_cap_usd: float = 1.0
    day_cap_usd: float = 2.0
    timezone: str = "America/New_York"
    transcript_days: int = 30

    def __post_init__(self) -> None:
        if self.host != LOOPBACK_HOST:
            raise ValueError("The app only binds to 127.0.0.1.")
        if self.ai_mode not in AI_MODES:
            raise ValueError(f"ai_mode must be one of {AI_MODES}")
        if not 0 < self.hard_stop_usd <= self.monthly_budget_usd:
            raise ValueError("hard_stop_usd must be positive and within the monthly budget.")
        self.data_dir = Path(self.data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "companion.sqlite3"

    @classmethod
    def from_env(cls) -> "Settings":
        kwargs: dict = {}
        if os.environ.get("COMPANION_DATA_DIR"):
            kwargs["data_dir"] = Path(os.environ["COMPANION_DATA_DIR"])
        if os.environ.get("COMPANION_PORT"):
            kwargs["port"] = int(os.environ["COMPANION_PORT"])
        if os.environ.get("COMPANION_AI_MODE"):
            kwargs["ai_mode"] = os.environ["COMPANION_AI_MODE"]
        if os.environ.get("COMPANION_TIMEZONE"):
            kwargs["timezone"] = os.environ["COMPANION_TIMEZONE"]
        return cls(**kwargs)
