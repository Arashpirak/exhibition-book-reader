"""JSON persistence for Settings. Missing/corrupt file -> defaults."""
from __future__ import annotations

import json
import os

from .models import Settings


def load(path: str = "settings.json") -> Settings:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return Settings()
        defaults = Settings()
        s = Settings.from_dict(data)
        # Coerce values whose type does not match the default (corrupt edits).
        for k, dv in defaults.to_dict().items():
            v = getattr(s, k)
            if isinstance(dv, bool):
                ok = isinstance(v, bool)
            elif isinstance(dv, (int, float)):
                ok = isinstance(v, (int, float)) and not isinstance(v, bool)
            else:
                ok = isinstance(v, str)
            if not ok:
                setattr(s, k, dv)
        return s
    except (OSError, ValueError):
        return Settings()


def save(settings: Settings, path: str = "settings.json") -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
