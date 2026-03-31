from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import floor
from typing import Optional, Any

from btc_contract_backtest.config.models import ContractSpec


@dataclass
class ConstraintViolation:
    code: str
    message: str
    severity: str = "critical"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConstraintCheckResult:
    ok: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    normalized: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExchangeConstraintChecker:
    def __init__(self, contract: ContractSpec, min_notional: Optional[float] = None):
        self.contract = contract
        self.min_notional = contract.min_notional if min_notional is None else min_notional

    def _round_to_lot(self, quantity: float) -> float:
        lot = self.contract.lot_size
        if lot <= 0:
            return quantity
        units = floor(quantity / lot)
        return round(units * lot, 12)

    def _round_to_tick(self, price: Optional[float]) -> Optional[float]:
        if price is None:
            return None
        tick = self.contract.tick_size
        if tick <= 0:
            return price
        units = floor(price / tick)
        return round(units * tick, 12)

    def check(
        self,
        *,
        quantity: float,
        price: Optional[float],
        notional: float,
        available_margin: Optional[float] = None,
        leverage: Optional[int] = None,
        reduce_only: bool = False,
        position_side: int = 0,
        account_mode: str = "one_way",
        max_open_positions: Optional[int] = None,
        current_open_positions: int = 0,
    ) -> ConstraintCheckResult:
        violations: list[dict[str, Any]] = []
        normalized_quantity = self._round_to_lot(quantity)
        normalized_price = self._round_to_tick(price)
        normalized = {
            "quantity": normalized_quantity,
            "price": normalized_price,
            "notional": notional,
        }

        if quantity <= 0:
            violations.append(
                ConstraintViolation(
                    "non_positive_quantity",
                    "Quantity must be positive",
                ).to_dict()
            )
        if abs(normalized_quantity - quantity) > 1e-9:
            violations.append(
                ConstraintViolation(
                    "lot_size_violation",
                    "Quantity does not conform to lot size",
                    metadata={
                        "quantity": quantity,
                        "normalized_quantity": normalized["quantity"],
                        "lot_size": self.contract.lot_size,
                    },
                ).to_dict()
            )
        if price is not None and normalized_price is not None and abs(normalized_price - price) > 1e-9:
            violations.append(
                ConstraintViolation(
                    "tick_size_violation",
                    "Price does not conform to tick size",
                    metadata={
                        "price": price,
                        "normalized_price": normalized["price"],
                        "tick_size": self.contract.tick_size,
                    },
                ).to_dict()
            )
        if notional < self.min_notional:
            violations.append(
                ConstraintViolation(
                    "min_notional_violation",
                    "Notional below exchange minimum",
                    metadata={
                        "notional": notional,
                        "min_notional": self.min_notional,
                    },
                ).to_dict()
            )
        if self.contract.min_quantity is not None and quantity + 1e-12 < self.contract.min_quantity:
            violations.append(
                ConstraintViolation(
                    "min_quantity_violation",
                    "Quantity below exchange minimum",
                    metadata={
                        "quantity": quantity,
                        "min_quantity": self.contract.min_quantity,
                    },
                ).to_dict()
            )
        if self.contract.max_quantity is not None and quantity - 1e-12 > self.contract.max_quantity:
            violations.append(
                ConstraintViolation(
                    "max_quantity_violation",
                    "Quantity above exchange maximum",
                    metadata={
                        "quantity": quantity,
                        "max_quantity": self.contract.max_quantity,
                    },
                ).to_dict()
            )
        effective_leverage = leverage if leverage is not None else self.contract.leverage
        if effective_leverage != self.contract.leverage:
            violations.append(
                ConstraintViolation(
                    "leverage_mismatch",
                    "Requested leverage does not match contract configuration",
                    metadata={
                        "requested": effective_leverage,
                        "contract": self.contract.leverage,
                    },
                ).to_dict()
            )
        if available_margin is not None and effective_leverage > 0:
            margin_required = notional / effective_leverage
            if available_margin + 1e-12 < margin_required:
                violations.append(
                    ConstraintViolation(
                        "insufficient_margin",
                        "Available margin is insufficient",
                        metadata={
                            "available_margin": available_margin,
                            "required_margin": margin_required,
                        },
                    ).to_dict()
                )
        if reduce_only and position_side == 0:
            violations.append(
                ConstraintViolation(
                    "reduce_only_without_position",
                    "Reduce-only order has no open position to reduce",
                ).to_dict()
            )
        if account_mode not in {"one_way", "hedge"}:
            violations.append(
                ConstraintViolation(
                    "unknown_account_mode",
                    "Unsupported account mode",
                    metadata={"account_mode": account_mode},
                ).to_dict()
            )
        if max_open_positions is not None and current_open_positions > max_open_positions:
            violations.append(
                ConstraintViolation(
                    "max_open_positions_exceeded",
                    "Too many open positions",
                    metadata={
                        "current_open_positions": current_open_positions,
                        "max_open_positions": max_open_positions,
                    },
                ).to_dict()
            )

        return ConstraintCheckResult(
            ok=len(violations) == 0,
            violations=violations,
            normalized=normalized,
        )
