from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Any

from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.restart_convergence import build_startup_convergence_report, summarize_replay_state
from btc_contract_backtest.live.submit_ledger import SubmitLedger


TERMINAL_REPLAY_STATES = {"filled", "canceled", "rejected", "expired"}
TERMINAL_LOCAL_STATES = TERMINAL_REPLAY_STATES | {"failed"}


@dataclass
class RecoveryReport:
    ok: bool
    recovered_intents: list[dict[str, Any]] = field(default_factory=list)
    unresolved_intents: list[dict[str, Any]] = field(default_factory=list)
    remote_only_orders: list[dict[str, Any]] = field(default_factory=list)
    local_only_orders: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    startup_convergence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecoveryOrchestrator:
    def __init__(self, adapter: ExchangeExecutionAdapter, submit_ledger: SubmitLedger):
        self.adapter = adapter
        self.submit_ledger = submit_ledger

    def _resolve_remote_position(self, positions: list[dict[str, Any]]) -> dict[str, Any]:
        for position in positions:
            qty = float(
                position.get("contracts")
                or position.get("positionAmt")
                or position.get("quantity")
                or position.get("pa")
                or 0.0
            )
            if qty != 0:
                return position
        return positions[0] if positions else {}

    @staticmethod
    def _replay_terminal_details(replay_order: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not isinstance(replay_order, dict):
            return None
        state = str(replay_order.get("state") or "").lower()
        if state not in TERMINAL_REPLAY_STATES:
            return None
        return {
            "state": state,
            "exchange_order_id": replay_order.get("order_id"),
            "metadata": {
                "recovered_by": "event_replay",
                "replay_last_sequence": replay_order.get("last_sequence"),
                "replay_last_timestamp": replay_order.get("last_timestamp"),
                "replay_filled_quantity": replay_order.get("filled_quantity"),
                "replay_average_price": replay_order.get("average_price"),
            },
        }

    def recover(
        self,
        *,
        local_orders: Optional[list[dict[str, Any]]] = None,
        local_position: Optional[dict[str, Any]] = None,
        events: Optional[list[dict[str, Any]]] = None,
        event_boundary: Optional[dict[str, Any]] = None,
        environment: str = "testnet",
    ) -> RecoveryReport:
        local_orders = local_orders or []
        local_position = local_position or {}
        events = events or []
        replay_state = summarize_replay_state(events)
        replay_orders = replay_state.get("orders_by_client_order_id") or {}

        open_result = self.adapter.fetch_open_orders()
        if not open_result.ok:
            return RecoveryReport(
                ok=False,
                notes=[f"fetch_open_orders_failed:{open_result.error}"],
            )

        positions_result = self.adapter.fetch_positions()
        if not positions_result.ok:
            return RecoveryReport(
                ok=False,
                notes=[f"fetch_positions_failed:{positions_result.error}"],
            )

        remote_orders = open_result.payload if isinstance(open_result.payload, list) else []
        remote_positions = positions_result.payload if isinstance(positions_result.payload, list) else []
        recovered_intents = []
        unresolved_intents = []
        remote_only_orders = []
        local_only_orders = []
        notes = []

        local_keys = set()
        local_terminal_keys = set()
        for order in local_orders:
            key = order.get("client_order_id") or order.get("exchange_order_id") or order.get("order_id")
            if key:
                local_keys.add(key)
            status = str(order.get("state") or order.get("status") or "").lower()
            if key and status in TERMINAL_LOCAL_STATES:
                local_terminal_keys.add(key)

        remote_keys = set()
        for order in remote_orders:
            key = order.get("clientOrderId") or order.get("id")
            if key:
                remote_keys.add(key)
            if key and key not in local_keys and key not in local_terminal_keys:
                remote_only_orders.append(order)

        for order in local_orders:
            key = order.get("client_order_id") or order.get("exchange_order_id") or order.get("order_id")
            status = str(order.get("state") or order.get("status") or "").lower()
            replay_order = replay_orders.get(str(order.get("client_order_id") or key or ""))
            replay_terminal = self._replay_terminal_details(replay_order)
            if replay_terminal is not None:
                continue
            if key and key not in remote_keys and status not in TERMINAL_LOCAL_STATES:
                local_only_orders.append(order)

        for intent in self.submit_ledger.pending_intents():
            client_order_id = intent.get("client_order_id")
            request_id = intent["request_id"]
            replay_order = replay_orders.get(str(client_order_id or "")) if client_order_id else None
            replay_terminal = self._replay_terminal_details(replay_order)
            if replay_terminal is not None:
                self.submit_ledger.mark_state(
                    request_id,
                    state=replay_terminal["state"],
                    exchange_order_id=replay_terminal["exchange_order_id"],
                    metadata=replay_terminal["metadata"],
                )
                recovered = self.submit_ledger.get(request_id)
                if recovered is not None:
                    recovered_intents.append(recovered)
                continue
            if not client_order_id:
                unresolved_intents.append(intent)
                continue
            lookup = self.adapter.fetch_open_orders_by_client_order_id(client_order_id)
            recovered_orders = lookup.payload if isinstance(lookup.payload, list) else []
            if lookup.ok and recovered_orders:
                remote = recovered_orders[0]
                self.submit_ledger.mark_state(
                    request_id,
                    state="submitted",
                    exchange_order_id=remote.get("id"),
                    metadata={"recovered_by": "recovery_orchestrator"},
                )
                recovered = self.submit_ledger.get(request_id)
                if recovered is not None:
                    recovered_intents.append(recovered)
                continue
            self.submit_ledger.mark_state(
                request_id,
                state="unknown",
                metadata={"recovery_lookup": "not_found"},
            )
            unresolved = self.submit_ledger.get(request_id)
            if unresolved is not None:
                unresolved_intents.append(unresolved)

        if remote_only_orders:
            notes.append("remote_only_orders_detected")
        if local_only_orders:
            notes.append("local_only_orders_detected")
        if unresolved_intents:
            notes.append("unresolved_submit_intents")

        startup_convergence = build_startup_convergence_report(
            environment=environment,
            local_position=local_position,
            remote_position=self._resolve_remote_position(remote_positions),
            unresolved_intents=unresolved_intents,
            remote_only_orders=remote_only_orders,
            local_only_orders=local_only_orders,
            events=events,
            boundary=event_boundary,
        ).to_dict()
        if not startup_convergence.get("ok", False):
            notes.append("startup_convergence_blocked")

        return RecoveryReport(
            ok=len(unresolved_intents) == 0 and bool(startup_convergence.get("ok", False)),
            recovered_intents=recovered_intents,
            unresolved_intents=unresolved_intents,
            remote_only_orders=remote_only_orders,
            local_only_orders=local_only_orders,
            notes=notes,
            startup_convergence=startup_convergence,
        )
