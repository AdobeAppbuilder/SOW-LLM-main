"""In-memory request context store.

Purpose: keep the existing function signatures intact while enabling
accuracy checks that need access to the original SOW text and deterministic
detections.

Note: Designed for single-process use (typical local dev / demo). If you later
host this behind multiple workers, replace with a shared cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import time

@dataclass
class RequestContext:
    request_id: str
    sow_text_raw: str
    sow_text_norm: str
    detected: dict
    created_at: float

_store: Dict[str, RequestContext] = {}
DEFAULT_TTL_SECONDS = 60 * 30


def set_context(request_id: str, *, sow_text_raw: str, sow_text_norm: str, detected: dict) -> None:
    _gc()
    _store[request_id] = RequestContext(
        request_id=request_id,
        sow_text_raw=sow_text_raw,
        sow_text_norm=sow_text_norm,
        detected=detected,
        created_at=time.time(),
    )


def get_context(request_id: str) -> Optional[RequestContext]:
    _gc()
    return _store.get(request_id)


def _gc() -> None:
    now = time.time()
    expired = [k for k, v in _store.items() if now - v.created_at > DEFAULT_TTL_SECONDS]
    for k in expired:
        _store.pop(k, None)
