from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Any
import os


PENDING_STATES = {"created", "pending_approval", "submit_pending", "submitted", "unknown"}
TERMINAL_STATES = {"blocked", "rejected", "filled", "canceled", "expired", "failed"}


@dataclass
class SubmitAttempt:
    timestamp: str
    action: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SubmitIntent:
    request_id: str
    client_order_id: str
    symbol: str
    signal: int
    quantity: float
    notional: float
    state: str = "created"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    exchange_order_id: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SubmitLedger:
    def __init__(self, path: str = "submit_ledger.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save({"intents": []})

    def load(self) -> dict[str, Any]:
        return json.loads(self.path.read_text())

    def save(self, payload: dict[str, Any]) -> None:
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        os.replace(tmp_path, self.path)

    def list_intents(self) -> list[dict[str, Any]]:
        return self.load().get("intents", [])

    def get(self, request_id: str) -> Optional[dict[str, Any]]:
        for item in self.list_intents():
            if item.get("request_id") == request_id:
                return item
        return None

    def get_by_client_order_id(self, client_order_id: str) -> Optional[dict[str, Any]]:
        for item in self.list_intents():
            if item.get("client_order_id") == client_order_id:
                return item
        return None

    def upsert(self, intent: Any) -> dict[str, Any]:
        payload = intent.to_dict() if isinstance(intent, SubmitIntent) else dict(intent)
        data = self.load()
        intents = data.setdefault("intents", [])
        for idx, existing in enumerate(intents):
            if existing.get("request_id") == payload.get("request_id") or (
                existing.get("client_order_id") == payload.get("client_order_id")
            ):
                payload.setdefault("attempts", existing.get("attempts", []))
                payload.setdefault("metadata", existing.get("metadata", {}))
                intents[idx] = payload
                self.save(data)
                return payload
        intents.append(payload)
        self.save(data)
        return payload

    def get_by_request_or_client_order_id(self, request_id: str, client_order_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        existing = self.get(request_id)
        if existing is not None:
            return existing
        if client_order_id is not None:
            return self.get_by_client_order_id(client_order_id)
        return None

    def is_pending(self, intent: dict[str, Any]) -> bool:
        return str(intent.get("state") or "").lower() in PENDING_STATES

    def is_terminal(self, intent: dict[str, Any]) -> bool:
        return str(intent.get("state") or "").lower() in TERMINAL_STATES

    def append_attempt(self, request_id: str, attempt: Any) -> Optional[dict[str, Any]]:
        data = self.load()
        intents = data.setdefault("intents", [])
        payload = attempt.to_dict() if isinstance(attempt, SubmitAttempt) else dict(attempt)
        for item in intents:
            if item.get("request_id") == request_id:
                item.setdefault("attempts", []).append(payload)
                item["updated_at"] = payload.get("timestamp") or item.get("updated_at")
                self.save(data)
                return item
        return None

    def mark_state(
        self,
        request_id: str,
        *,
        state: str,
        timestamp: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        data = self.load()
        intents = data.setdefault("intents", [])
        for item in intents:
            if item.get("request_id") == request_id:
                item["state"] = state
                if timestamp is not None:
                    item["updated_at"] = timestamp
                if exchange_order_id is not None:
                    item["exchange_order_id"] = exchange_order_id
                if error is not None:
                    item["error"] = error
                if metadata:
                    current = item.setdefault("metadata", {})
                    current.update(metadata)
                self.save(data)
                return item
        return None

    def pending_intents(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.list_intents()
            if self.is_pending(item)
        ]
