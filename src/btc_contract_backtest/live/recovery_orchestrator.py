from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Any

from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.submit_ledger import SubmitLedger


@dataclass
class RecoveryReport:
    ok: bool
    recovered_intents: list[dict[str, Any]] = field(default_factory=list)
    unresolved_intents: list[dict[str, Any]] = field(default_factory=list)
    remote_only_orders: list[dict[str, Any]] = field(default_factory=list)
    local_only_orders: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecoveryOrchestrator:
    def __init__(self, adapter: ExchangeExecutionAdapter, submit_ledger: SubmitLedger):
        self.adapter = adapter
        self.submit_ledger = submit_ledger

    def recover(self, *, local_orders: Optional[list[dict[str, Any]]] = None) -> RecoveryReport:
        local_orders = local_orders or []
        open_result = self.adapter.fetch_open_orders()
        if not open_result.ok:
            return RecoveryReport(ok=False, notes=[f"fetch_open_orders_failed:{open_result.error}"])

        remote_orders = open_result.payload or []
        recovered_intents = []
        unresolved_intents = []
        remote_only_orders = []
        local_only_orders = []
        notes = []

        local_keys = set()
        for order in local_orders:
            key = order.get("client_order_id") or order.get("exchange_order_id") or order.get("order_id")
            if key:
                local_keys.add(key)

        remote_keys = set()
        for order in remote_orders:
            key = order.get("clientOrderId") or order.get("id")
            if key:
                remote_keys.add(key)
            if key and key not in local_keys:
                remote_only_orders.append(order)

        for order in local_orders:
            key = order.get("client_order_id") or order.get("exchange_order_id") or order.get("order_id")
            status = str(order.get("state") or order.get("status") or "").lower()
            if key and key not in remote_keys and status not in {"filled", "canceled", "rejected", "expired"}:
                local_only_orders.append(order)

        for intent in self.submit_ledger.pending_intents():
            client_order_id = intent.get("client_order_id")
            if not client_order_id:
                unresolved_intents.append(intent)
                continue
            lookup = self.adapter.fetch_open_orders_by_client_order_id(client_order_id)
            if lookup.ok and lookup.payload:
                remote = lookup.payload[0]
                self.submit_ledger.mark_state(
                    intent["request_id"],
                    state="submitted",
                    exchange_order_id=remote.get("id"),
                    metadata={"recovered_by": "recovery_orchestrator"},
                )
                recovered = self.submit_ledger.get(intent["request_id"])
                if recovered is not None:
                    recovered_intents.append(recovered)
                continue
            self.submit_ledger.mark_state(intent["request_id"], state="unknown", metadata={"recovery_lookup": "not_found"})
            unresolved = self.submit_ledger.get(intent["request_id"])
            if unresolved is not None:
                unresolved_intents.append(unresolved)

        if remote_only_orders:
            notes.append("remote_only_orders_detected")
        if local_only_orders:
            notes.append("local_only_orders_detected")
        if unresolved_intents:
            notes.append("unresolved_submit_intents")

        return RecoveryReport(
            ok=len(unresolved_intents) == 0,
            recovered_intents=recovered_intents,
            unresolved_intents=unresolved_intents,
            remote_only_orders=remote_only_orders,
            local_only_orders=local_only_orders,
            notes=notes,
        )
