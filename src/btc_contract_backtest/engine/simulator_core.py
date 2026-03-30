from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional
import math
import uuid

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.engine.execution_models import FillEvent, MarketSnapshot, Order, OrderSide, OrderStatus, OrderType, PositionState, RiskEvent


class SimulatorCore:
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        execution: ExecutionConfig,
        live_risk: Optional[LiveRiskConfig] = None,
    ):
        self.contract = contract
        self.account = account
        self.risk = risk
        self.execution = execution
        self.live_risk = live_risk or LiveRiskConfig()
        self.capital = account.initial_capital
        self.peak_equity = self.capital
        self.day_start_equity = self.capital
        self.position = PositionState(symbol=contract.symbol, leverage=contract.leverage)
        self.orders: dict[str, Order] = {}
        self.trades: list[dict] = []
        self.risk_events: list[dict] = []
        self.consecutive_failures = 0
        self.last_snapshot: Optional[MarketSnapshot] = None

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def snapshot_from_bar(self, timestamp, row) -> MarketSnapshot:
        close = float(row["close"])
        spread = close * (self.execution.simulated_spread_bps / 10000)
        bid = float(row.get("bid", close - spread / 2))
        ask = float(row.get("ask", close + spread / 2))
        mark_price = float(row.get("mark_price", close))
        funding_rate = row.get("funding_rate")
        depth_notional = float(row.get("depth_notional", self.execution.simulated_depth_notional))
        return MarketSnapshot(
            symbol=self.contract.symbol,
            timestamp=str(timestamp),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=close,
            volume=float(row.get("volume", 0.0)),
            bid=bid,
            ask=ask,
            mark_price=mark_price,
            funding_rate=None if funding_rate is None else float(funding_rate),
            latency_ms=self.execution.latency_ms,
            stale=bool(row.get("stale", False)),
        )

    def emit_risk_event(self, event_type: str, message: str, severity: str = "warning", metadata: Optional[dict] = None):
        evt = RiskEvent(event_type=event_type, message=message, severity=severity, timestamp=self.now_iso(), metadata=metadata or {})
        self.risk_events.append(asdict(evt))
        return evt

    def check_snapshot_safety(self, snapshot: MarketSnapshot) -> bool:
        if self.risk.kill_on_stale_data and snapshot.stale:
            self.emit_risk_event("stale_data", "Market snapshot marked stale; blocking execution", severity="critical")
            return False
        if self.execution.enforce_mark_bid_ask_consistency and snapshot.bid is not None and snapshot.ask is not None and snapshot.mark_price is not None:
            mid = (snapshot.bid + snapshot.ask) / 2
            deviation_bps = abs(snapshot.mark_price - mid) / mid * 10000 if mid else 0.0
            if deviation_bps > self.execution.stale_mark_deviation_bps:
                self.emit_risk_event("mark_inconsistency", "Mark price deviates too far from bid/ask midpoint", severity="critical", metadata={"deviation_bps": deviation_bps})
                return False
        self.last_snapshot = snapshot
        return True

    def _current_position_scale(self, current_equity: float) -> float:
        self.peak_equity = max(self.peak_equity, current_equity)
        if not self.risk.drawdown_position_scale:
            return 1.0
        drawdown_pct = 0.0 if self.peak_equity <= 0 else max(0.0, (self.peak_equity - current_equity) / self.peak_equity * 100)
        if drawdown_pct <= self.risk.max_drawdown_scale_start_pct:
            return 1.0
        excess = min(drawdown_pct - self.risk.max_drawdown_scale_start_pct, 100.0)
        scale = 1.0 - (excess / 100.0)
        return max(self.risk.max_drawdown_scale_floor, scale)

    def determine_notional(self, price: float, atr_value: Optional[float]) -> float:
        scale = self._current_position_scale(self.capital)
        base_cap = self.capital * self.risk.max_position_notional_pct * scale
        candidates = [base_cap]
        if self.risk.risk_per_trade_pct is not None and self.risk.stop_loss_pct is not None and self.risk.stop_loss_pct > 0:
            risk_budget = self.capital * self.risk.risk_per_trade_pct * scale
            stop_based_notional = risk_budget / (self.risk.stop_loss_pct * self.contract.leverage)
            candidates.append(stop_based_notional)
        if self.risk.atr_position_sizing_mult is not None and atr_value is not None and atr_value > 0 and price > 0:
            atr_pct = atr_value / price
            if atr_pct > 0:
                atr_based_notional = (self.capital * scale * self.risk.atr_position_sizing_mult) / (atr_pct * self.contract.leverage)
                candidates.append(atr_based_notional)
        if self.risk.max_symbol_exposure_pct is not None:
            candidates.append(self.capital * self.risk.max_symbol_exposure_pct)
        return max(0.0, min(candidates))

    def create_order(self, side: OrderSide, quantity: float, order_type: OrderType = OrderType.MARKET, price: Optional[float] = None, stop_price: Optional[float] = None, reduce_only: bool = False, client_order_id: Optional[str] = None) -> Order:
        oid = str(uuid.uuid4())
        order = Order(
            order_id=oid,
            symbol=self.contract.symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            reduce_only=reduce_only,
            client_order_id=client_order_id,
            created_at=self.now_iso(),
            updated_at=self.now_iso(),
        )
        self.orders[oid] = order
        return order

    def cancel_order(self, order_id: str) -> Optional[Order]:
        order = self.orders.get(order_id)
        if not order:
            return None
        if order.status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED}:
            return order
        order.status = OrderStatus.CANCELED
        order.updated_at = self.now_iso()
        return order

    def _depth_impact_bps(self, order_notional: float, depth_notional: float) -> float:
        if depth_notional <= 0:
            return self.execution.simulated_slippage_bps
        ratio = max(order_notional / depth_notional, 0.0)
        return self.execution.simulated_slippage_bps * math.pow(max(ratio, 1e-9), self.execution.impact_exponent)

    def _fill_price(self, snapshot: MarketSnapshot, side: OrderSide, order_type: OrderType, quantity: float) -> float:
        base = snapshot.ask if side == OrderSide.BUY else snapshot.bid
        if base is None:
            base = snapshot.close
        depth_notional = self.execution.simulated_depth_notional
        order_notional = quantity * snapshot.close
        slip_bps = self._depth_impact_bps(order_notional, depth_notional)
        slip = snapshot.close * (slip_bps / 10000)
        if order_type == OrderType.MARKET:
            return base + slip if side == OrderSide.BUY else base - slip
        return base

    def _fill_ratio(self, order: Order) -> float:
        if not self.execution.allow_partial_fills:
            return 1.0
        base = self.execution.max_fill_ratio_per_bar
        if self.execution.queue_priority_model == "probabilistic" and order.order_type == OrderType.LIMIT:
            return min(1.0, max(0.0, base * self.execution.maker_fill_probability))
        if self.execution.queue_priority_model == "conservative" and order.order_type == OrderType.LIMIT:
            return min(1.0, max(0.0, base * 0.5))
        return min(1.0, max(0.0, base))

    def funding_cost(self, snapshot: MarketSnapshot) -> float:
        if self.position.side == 0 or self.position.notional <= 0:
            return 0.0
        if self.execution.use_realistic_funding and snapshot.funding_rate is not None:
            return self.position.notional * snapshot.funding_rate
        return self.position.notional * (self.account.funding_rate_annual / (365 * (24 / max(self.execution.funding_interval_hours, 1))))

    def try_fill_order(self, order: Order, snapshot: MarketSnapshot) -> list[FillEvent]:
        fills: list[FillEvent] = []
        if order.status in {OrderStatus.CANCELED, OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.EXPIRED}:
            return fills
        remaining = order.quantity - order.filled_quantity
        if remaining <= 0:
            order.status = OrderStatus.FILLED
            return fills

        fill_ratio = self._fill_ratio(order)
        fill_qty = min(remaining, order.quantity * fill_ratio)
        price = self._fill_price(snapshot, order.side, order.order_type, fill_qty)
        fee_rate = self.account.taker_fee_rate if order.order_type in {OrderType.MARKET, OrderType.STOP_MARKET} else self.account.maker_fee_rate
        liquidity = "taker" if fee_rate == self.account.taker_fee_rate else "maker"
        fee = fill_qty * price * fee_rate
        fill = FillEvent(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            fill_quantity=fill_qty,
            fill_price=price,
            fee=fee,
            liquidity=liquidity,
            timestamp=snapshot.timestamp,
        )
        fills.append(fill)
        order.filled_quantity += fill_qty
        order.avg_fill_price = price if order.avg_fill_price is None else ((order.avg_fill_price * (order.filled_quantity - fill_qty)) + price * fill_qty) / order.filled_quantity
        order.updated_at = self.now_iso()
        order.status = OrderStatus.FILLED if order.filled_quantity >= order.quantity else OrderStatus.PARTIALLY_FILLED
        return fills

    def apply_fill(self, fill: FillEvent):
        signed_qty = fill.fill_quantity if fill.side == OrderSide.BUY else -fill.fill_quantity
        previous_qty = self.position.quantity
        new_qty = previous_qty + signed_qty
        fill_notional = fill.fill_quantity * fill.fill_price

        increasing_same_side = previous_qty == 0 or (previous_qty > 0 and signed_qty > 0) or (previous_qty < 0 and signed_qty < 0)
        reducing_or_closing = previous_qty != 0 and ((previous_qty > 0 and signed_qty < 0) or (previous_qty < 0 and signed_qty > 0))

        if increasing_same_side:
            total_notional = abs(previous_qty) * (self.position.entry_price or fill.fill_price) + fill_notional
            total_qty = abs(previous_qty) + fill.fill_quantity
            self.position.entry_price = total_notional / total_qty if total_qty else fill.fill_price
            self.position.entry_time = fill.timestamp
        elif reducing_or_closing:
            closed_qty = min(abs(previous_qty), fill.fill_quantity)
            side = 1 if previous_qty > 0 else -1
            entry_price = self.position.entry_price or fill.fill_price
            gross = ((fill.fill_price - entry_price) / entry_price) * (closed_qty * entry_price) * self.contract.leverage * side
            funding = 0.0
            pnl = gross - fill.fee - funding
            self.capital += pnl
            self.trades.append({
                "entry_time": self.position.entry_time,
                "exit_time": fill.timestamp,
                "entry_price": entry_price,
                "exit_price": fill.fill_price,
                "position": side,
                "bars_held": self.position.bars_held,
                "notional_closed": closed_qty * fill.fill_price,
                "remaining_notional": max(abs(new_qty) * fill.fill_price, 0.0),
                "reason": "execution_close",
                "is_partial": abs(new_qty) > 0 and (1 if new_qty > 0 else -1) == side,
                "gross_pnl": gross,
                "fees": fill.fee,
                "funding": funding,
                "pnl_after_costs": pnl,
            })
            if new_qty == 0:
                self.position.entry_price = None
                self.position.entry_time = None
                self.position.bars_held = 0
                self.position.peak_price = None
                self.position.trough_price = None
                self.position.break_even_armed = False
                self.position.partial_taken = False
                self.position.stepped_stop_anchor = None
                self.position.atr_at_entry = None
            elif (1 if new_qty > 0 else -1) != side:
                self.position.entry_price = fill.fill_price
                self.position.entry_time = fill.timestamp
                self.position.bars_held = 0
                self.position.peak_price = fill.fill_price
                self.position.trough_price = fill.fill_price
                self.position.break_even_armed = False
                self.position.partial_taken = False
                self.position.stepped_stop_anchor = None
                self.position.atr_at_entry = None

        self.position.quantity = new_qty
        self.position.side = 0 if new_qty == 0 else (1 if new_qty > 0 else -1)
        self.position.notional = abs(new_qty) * fill.fill_price
        self.position.margin_used = self.position.notional / self.contract.leverage if self.contract.leverage else self.position.notional
        if self.position.side != 0:
            self.position.peak_price = fill.fill_price if self.position.peak_price is None else max(self.position.peak_price, fill.fill_price)
            self.position.trough_price = fill.fill_price if self.position.trough_price is None else min(self.position.trough_price, fill.fill_price)

    def apply_periodic_funding(self, snapshot: MarketSnapshot):
        cost = self.funding_cost(snapshot)
        if cost == 0.0:
            return 0.0
        self.capital -= cost
        return cost

    def check_daily_loss_kill(self, current_equity: float) -> bool:
        if self.risk.max_daily_loss_pct is None:
            return False
        loss_pct = ((self.day_start_equity - current_equity) / self.day_start_equity) * 100 if self.day_start_equity else 0.0
        if loss_pct >= self.risk.max_daily_loss_pct:
            self.emit_risk_event("daily_loss_kill", "Daily loss threshold breached", severity="critical", metadata={"loss_pct": loss_pct})
            return True
        return False
