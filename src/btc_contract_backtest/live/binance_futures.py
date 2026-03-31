from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.request import urlopen

from btc_contract_backtest.config.models import ContractSpec


DEFAULT_BINANCE_FUTURES_RUNTIME_ROOT = "var/exchanges/binance_futures"
DEFAULT_METADATA_MAX_AGE_SECONDS = 6 * 60 * 60


def _decimal_to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", False):
        return default
    return float(Decimal(str(value)))


def _slugify_symbol(symbol: str) -> str:
    return normalize_binance_symbol(symbol).lower() or "unknown_symbol"


@dataclass(frozen=True)
class BinanceFuturesProfile:
    key: str
    label: str
    rest_base_url: str
    ccxt_id: str = "binance"
    default_type: str = "future"
    testnet: bool = False
    api_key_env: str = ""
    secret_env: str = ""
    mainnet_opt_in_env: Optional[str] = None


BINANCE_FUTURES_TESTNET = BinanceFuturesProfile(
    key="binance_futures_testnet",
    label="Binance USDⓈ-M Futures Testnet",
    rest_base_url="https://testnet.binancefuture.com",
    testnet=True,
    api_key_env="BINANCE_FUTURES_TESTNET_API_KEY",
    secret_env="BINANCE_FUTURES_TESTNET_API_SECRET",
)

BINANCE_FUTURES_MAINNET = BinanceFuturesProfile(
    key="binance_futures_mainnet",
    label="Binance USDⓈ-M Futures Mainnet",
    rest_base_url="https://fapi.binance.com",
    testnet=False,
    api_key_env="BINANCE_FUTURES_MAINNET_API_KEY",
    secret_env="BINANCE_FUTURES_MAINNET_API_SECRET",
    mainnet_opt_in_env="BINANCE_FUTURES_ENABLE_MAINNET",
)


BINANCE_FUTURES_PROFILES = {
    BINANCE_FUTURES_TESTNET.key: BINANCE_FUTURES_TESTNET,
    BINANCE_FUTURES_MAINNET.key: BINANCE_FUTURES_MAINNET,
}


@dataclass(frozen=True)
class BinanceFuturesCredentials:
    api_key: Optional[str] = None
    secret: Optional[str] = None
    source: str = "none"

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret)


@dataclass(frozen=True)
class BinanceFuturesRuntimePaths:
    root_dir: str
    profile: str
    symbol: str
    profile_dir: str
    symbol_dir: str
    metadata_cache_file: str
    paper_state_file: str
    shadow_state_file: str
    live_state_file: str
    live_audit_log: str
    shadow_audit_log: str
    governance_state_file: str
    approval_file: str
    alerts_file: str
    submit_ledger_file: str
    execution_events_file: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class BinanceSymbolRules:
    symbol: str
    exchange_symbol: str
    status: str
    contract_type: str
    tick_size: float
    lot_size: float
    market_lot_size: float
    min_notional: float
    min_quantity: float
    max_quantity: float
    price_precision: Optional[int]
    quantity_precision: Optional[int]
    base_asset: str
    quote_asset: str
    margin_asset: str
    metadata_source: str
    metadata_as_of: str
    leverage: Optional[int] = None
    margin_mode: str = "isolated"
    position_mode: str = "one_way"

    def to_contract_spec(self, leverage: int = 5, profile: str = BINANCE_FUTURES_TESTNET.key) -> ContractSpec:
        return ContractSpec(
            symbol=self.symbol,
            market_type="perpetual",
            quote_currency=self.quote_asset,
            exchange_id="binance",
            exchange_profile=profile,
            leverage=self.leverage or leverage,
            tick_size=self.tick_size,
            lot_size=self.lot_size,
            min_notional=self.min_notional,
            min_quantity=self.min_quantity,
            max_quantity=self.max_quantity,
            price_precision=self.price_precision,
            quantity_precision=self.quantity_precision,
            margin_mode=self.margin_mode,
            position_mode=self.position_mode,
            metadata_source=self.metadata_source,
            metadata_as_of=self.metadata_as_of,
        )


@dataclass
class BinanceExchangeMetadataSnapshot:
    profile: str
    fetched_at: str
    exchange_timezone: str
    server_time: Optional[int]
    symbols: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_url: Optional[str] = None
    cache_path: Optional[str] = None

    def get_symbol_rules(self, symbol: str) -> BinanceSymbolRules:
        payload = self.symbols[symbol]
        return BinanceSymbolRules(**payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_binance_futures_profile(profile: str) -> BinanceFuturesProfile:
    try:
        return BINANCE_FUTURES_PROFILES[profile]
    except KeyError as exc:
        raise ValueError(f"Unsupported Binance Futures profile: {profile}") from exc


def normalize_binance_symbol(symbol: str) -> str:
    raw = symbol.upper().replace("-", "").replace("_", "")
    if "/" in symbol:
        base, quote = symbol.upper().split("/", 1)
        return f"{base}{quote}"
    return raw


def load_binance_futures_credentials(
    profile: str,
    api_key: Optional[str] = None,
    secret: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> BinanceFuturesCredentials:
    env = environ or os.environ
    selected = get_binance_futures_profile(profile)
    direct_key = api_key or env.get(selected.api_key_env) or env.get("BINANCE_API_KEY")
    direct_secret = secret or env.get(selected.secret_env) or env.get("BINANCE_API_SECRET")
    if api_key or secret:
        source = "arguments"
    elif direct_key or direct_secret:
        source = "environment"
    else:
        source = "none"
    return BinanceFuturesCredentials(api_key=direct_key, secret=direct_secret, source=source)


def is_binance_mainnet_enabled(
    profile: str,
    *,
    allow_mainnet: bool = False,
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    selected = get_binance_futures_profile(profile)
    if selected.testnet:
        return True
    if allow_mainnet:
        return True
    env = environ or os.environ
    token = str(env.get(selected.mainnet_opt_in_env or "", "")).strip().lower()
    return token in {"1", "true", "yes", "on", "enable", "enabled"}


def require_binance_profile_enabled(
    profile: str,
    *,
    allow_mainnet: bool = False,
    environ: Optional[Mapping[str, str]] = None,
) -> None:
    if is_binance_mainnet_enabled(profile, allow_mainnet=allow_mainnet, environ=environ):
        return
    selected = get_binance_futures_profile(profile)
    raise PermissionError(
        f"{selected.label} is disabled by default. Re-run with explicit "
        f"mainnet opt-in or set {selected.mainnet_opt_in_env}=true."
    )


def build_binance_futures_runtime_paths(
    profile: str,
    symbol: str,
    root_dir: str = DEFAULT_BINANCE_FUTURES_RUNTIME_ROOT,
) -> BinanceFuturesRuntimePaths:
    selected = get_binance_futures_profile(profile)
    root = Path(root_dir)
    profile_dir = root / selected.key
    symbol_dir = profile_dir / _slugify_symbol(symbol)
    return BinanceFuturesRuntimePaths(
        root_dir=str(root),
        profile=selected.key,
        symbol=symbol,
        profile_dir=str(profile_dir),
        symbol_dir=str(symbol_dir),
        metadata_cache_file=str(profile_dir / "exchange_info.json"),
        paper_state_file=str(symbol_dir / "paper_state.json"),
        shadow_state_file=str(symbol_dir / "shadow_state.json"),
        live_state_file=str(symbol_dir / "live_state.json"),
        live_audit_log=str(symbol_dir / "live_governance_audit.jsonl"),
        shadow_audit_log=str(symbol_dir / "shadow_audit.jsonl"),
        governance_state_file=str(symbol_dir / "governance_state.json"),
        approval_file=str(symbol_dir / "operator_approvals.json"),
        alerts_file=str(symbol_dir / "live_alerts.jsonl"),
        submit_ledger_file=str(symbol_dir / "submit_ledger.json"),
        execution_events_file=str(symbol_dir / "execution_events.jsonl"),
    )


def create_binance_futures_exchange(
    profile: str,
    api_key: Optional[str] = None,
    secret: Optional[str] = None,
    *,
    allow_mainnet: bool = False,
    environ: Optional[Mapping[str, str]] = None,
) -> Any:
    selected = get_binance_futures_profile(profile)
    require_binance_profile_enabled(profile, allow_mainnet=allow_mainnet, environ=environ)
    credentials = load_binance_futures_credentials(profile, api_key=api_key, secret=secret, environ=environ)
    import ccxt

    exchange = ccxt.binance(
        {
            "apiKey": credentials.api_key,
            "secret": credentials.secret,
            "enableRateLimit": True,
            "options": {"defaultType": selected.default_type},
            "urls": {
                "api": {
                    "fapiPublic": selected.rest_base_url + "/fapi/v1",
                    "fapiPrivate": selected.rest_base_url + "/fapi/v1",
                    "fapiPrivateV2": selected.rest_base_url + "/fapi/v2",
                    "fapiPrivateV3": selected.rest_base_url + "/fapi/v3",
                }
            },
        }
    )
    return exchange


class BinanceFuturesMetadataSync:
    def __init__(
        self,
        profile: str = BINANCE_FUTURES_TESTNET.key,
        cache_path: str = "var/binance_futures_exchange_info.json",
        max_age_seconds: int = DEFAULT_METADATA_MAX_AGE_SECONDS,
    ):
        self.profile = get_binance_futures_profile(profile)
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_age_seconds = max_age_seconds

    def _exchange_info_url(self) -> str:
        return self.profile.rest_base_url + "/fapi/v1/exchangeInfo"

    def fetch_exchange_info(self) -> dict[str, Any]:
        with urlopen(self._exchange_info_url(), timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def _parse_symbol(self, row: dict[str, Any], fetched_at: str) -> Optional[BinanceSymbolRules]:
        if str(row.get("contractType", "")).upper() not in {"PERPETUAL", "CURRENT_QUARTER", "NEXT_QUARTER"}:
            return None
        filters = {item.get("filterType"): item for item in row.get("filters", [])}
        price_filter = filters.get("PRICE_FILTER", {})
        lot_filter = filters.get("LOT_SIZE", {})
        market_lot_filter = filters.get("MARKET_LOT_SIZE", lot_filter)
        notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}

        base = row.get("baseAsset") or ""
        quote = row.get("quoteAsset") or ""
        normalized_symbol = f"{base}/{quote}" if base and quote else str(row.get("symbol") or "")

        return BinanceSymbolRules(
            symbol=normalized_symbol,
            exchange_symbol=str(row.get("symbol") or normalized_symbol.replace("/", "")),
            status=str(row.get("status") or "UNKNOWN"),
            contract_type=str(row.get("contractType") or "PERPETUAL"),
            tick_size=_decimal_to_float(price_filter.get("tickSize"), 0.0),
            lot_size=_decimal_to_float(lot_filter.get("stepSize"), 0.0),
            market_lot_size=_decimal_to_float(
                market_lot_filter.get("stepSize"),
                _decimal_to_float(lot_filter.get("stepSize"), 0.0),
            ),
            min_notional=_decimal_to_float(
                notional_filter.get("notional") or notional_filter.get("minNotional"),
                5.0,
            ),
            min_quantity=_decimal_to_float(lot_filter.get("minQty"), 0.0),
            max_quantity=_decimal_to_float(lot_filter.get("maxQty"), 0.0),
            price_precision=row.get("pricePrecision"),
            quantity_precision=row.get("quantityPrecision"),
            base_asset=base,
            quote_asset=quote,
            margin_asset=str(row.get("marginAsset") or quote),
            metadata_source=self.profile.key,
            metadata_as_of=fetched_at,
        )

    def build_snapshot(self, exchange_info: dict[str, Any]) -> BinanceExchangeMetadataSnapshot:
        fetched_at = datetime.now(timezone.utc).isoformat()
        symbols = {}
        for row in exchange_info.get("symbols", []):
            parsed = self._parse_symbol(row, fetched_at)
            if parsed is None:
                continue
            symbols[parsed.symbol] = asdict(parsed)
        return BinanceExchangeMetadataSnapshot(
            profile=self.profile.key,
            fetched_at=fetched_at,
            exchange_timezone=str(exchange_info.get("timezone") or "UTC"),
            server_time=exchange_info.get("serverTime"),
            symbols=symbols,
            source_url=self._exchange_info_url(),
            cache_path=str(self.cache_path),
        )

    def save_snapshot(self, snapshot: BinanceExchangeMetadataSnapshot) -> Path:
        self.cache_path.write_text(json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False))
        return self.cache_path

    def load_snapshot(self) -> Optional[BinanceExchangeMetadataSnapshot]:
        if not self.cache_path.exists():
            return None
        payload = json.loads(self.cache_path.read_text())
        return BinanceExchangeMetadataSnapshot(**payload)

    def snapshot_is_stale(self, snapshot: Optional[BinanceExchangeMetadataSnapshot]) -> bool:
        if snapshot is None:
            return True
        try:
            fetched_at = datetime.fromisoformat(snapshot.fetched_at)
        except Exception:
            return True
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        return age > self.max_age_seconds

    def sync(self) -> BinanceExchangeMetadataSnapshot:
        snapshot = self.build_snapshot(self.fetch_exchange_info())
        self.save_snapshot(snapshot)
        return snapshot

    def get_symbol_rules(
        self,
        symbol: str,
        allow_stale: bool = True,
        refresh_on_miss: bool = True,
    ) -> BinanceSymbolRules:
        snapshot = self.load_snapshot()
        if snapshot is None:
            if refresh_on_miss:
                snapshot = self.sync()
            else:
                raise KeyError(f"No Binance metadata snapshot available for profile: {self.profile.key}")
        elif allow_stale and self.snapshot_is_stale(snapshot):
            snapshot = self.sync()
        if symbol in snapshot.symbols:
            return snapshot.get_symbol_rules(symbol)
        target = normalize_binance_symbol(symbol)
        for candidate, payload in snapshot.symbols.items():
            candidate_exchange_symbol = str(payload.get("exchange_symbol") or "")
            if normalize_binance_symbol(candidate) == target or candidate_exchange_symbol == target:
                return BinanceSymbolRules(**payload)
        if allow_stale and refresh_on_miss:
            snapshot = self.sync()
            if symbol in snapshot.symbols:
                return snapshot.get_symbol_rules(symbol)
            for candidate, payload in snapshot.symbols.items():
                candidate_exchange_symbol = str(payload.get("exchange_symbol") or "")
                if normalize_binance_symbol(candidate) == target or candidate_exchange_symbol == target:
                    return BinanceSymbolRules(**payload)
        raise KeyError(f"Symbol not found in Binance metadata snapshot: {symbol}")


def with_binance_symbol_rules(contract: ContractSpec, rules: BinanceSymbolRules) -> ContractSpec:
    return ContractSpec(
        symbol=rules.symbol,
        market_type=contract.market_type,
        quote_currency=rules.quote_asset,
        exchange_id=contract.exchange_id,
        exchange_profile=contract.exchange_profile,
        leverage=contract.leverage,
        tick_size=rules.tick_size or contract.tick_size,
        lot_size=rules.lot_size or contract.lot_size,
        min_notional=rules.min_notional or contract.min_notional,
        min_quantity=rules.min_quantity or contract.min_quantity,
        max_quantity=rules.max_quantity or contract.max_quantity,
        price_precision=rules.price_precision,
        quantity_precision=rules.quantity_precision,
        margin_mode=contract.margin_mode,
        position_mode=contract.position_mode,
        metadata_source=rules.metadata_source,
        metadata_as_of=rules.metadata_as_of,
    )
