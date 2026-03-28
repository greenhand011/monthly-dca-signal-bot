from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json


@dataclass
class ReserveState:
    reserve_cash_rmb: int = 0
    last_run_at: str | None = None
    last_status: str | None = None
    last_recommendation_total_rmb: int | None = None


def load_state(path: str | Path) -> ReserveState:
    path = Path(path)
    if not path.exists():
        return ReserveState()

    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    return ReserveState(
        reserve_cash_rmb=int(raw.get("reserve_cash_rmb", 0)),
        last_run_at=raw.get("last_run_at"),
        last_status=raw.get("last_status"),
        last_recommendation_total_rmb=raw.get("last_recommendation_total_rmb"),
    )


def dump_state(state: ReserveState, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "reserve_cash_rmb": int(state.reserve_cash_rmb),
        "last_run_at": state.last_run_at,
        "last_status": state.last_status,
        "last_recommendation_total_rmb": state.last_recommendation_total_rmb,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
