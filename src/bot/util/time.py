from __future__ import annotations
from datetime import datetime, timezone

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def month_key(dt: datetime | None = None) -> str:
    d = dt or utcnow()
    return d.strftime("%Y-%m")
