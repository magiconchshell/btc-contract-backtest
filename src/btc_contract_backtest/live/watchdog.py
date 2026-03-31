from __future__ import annotations
from typing import Optional

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class WatchdogState:
    last_heartbeat_at: Optional[str] = None
    consecutive_failures: int = 0
    halted: bool = False
    halt_reason: Optional[str] = None


class HeartbeatWatchdog:
    def __init__(self, heartbeat_timeout_seconds: int, max_consecutive_failures: int):
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.max_consecutive_failures = max_consecutive_failures
        self.state = WatchdogState()

    def beat(self):
        self.state.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
        self.state.consecutive_failures = 0

    def record_failure(self, reason: str):
        self.state.consecutive_failures += 1
        if self.state.consecutive_failures >= self.max_consecutive_failures:
            self.state.halted = True
            self.state.halt_reason = reason

    def check_timeout(self, now_ts: datetime | None = None) -> bool:
        if self.state.last_heartbeat_at is None:
            return False
        now_ts = now_ts or datetime.now(timezone.utc)
        last = datetime.fromisoformat(self.state.last_heartbeat_at)
        elapsed = (now_ts - last).total_seconds()
        if elapsed > self.heartbeat_timeout_seconds:
            self.state.halted = True
            self.state.halt_reason = "heartbeat_timeout"
            return True
        return False
