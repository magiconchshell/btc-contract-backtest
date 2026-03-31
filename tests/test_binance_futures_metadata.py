import json
from datetime import datetime, timedelta, timezone

import pytest

from btc_contract_backtest.config.models import ContractSpec
from btc_contract_backtest.live.binance_futures import (
    BINANCE_FUTURES_MAINNET,
    BINANCE_FUTURES_TESTNET,
    BinanceExchangeMetadataSnapshot,
    BinanceFuturesMetadataSync,
    build_binance_futures_runtime_paths,
    create_binance_futures_exchange,
    is_binance_mainnet_enabled,
    load_binance_futures_credentials,
    require_binance_profile_enabled,
    with_binance_symbol_rules,
)


SAMPLE_EXCHANGE_INFO = {
    "timezone": "UTC",
    "serverTime": 1710000000000,
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "pair": "BTCUSDT",
            "contractType": "PERPETUAL",
            "status": "TRADING",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "marginAsset": "USDT",
            "pricePrecision": 2,
            "quantityPrecision": 3,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "100"},
            ],
        }
    ],
}


def test_metadata_sync_parses_and_persists_symbol_rules(tmp_path):
    cache = tmp_path / "exchange_info.json"
    sync = BinanceFuturesMetadataSync(cache_path=str(cache))
    snapshot = sync.build_snapshot(SAMPLE_EXCHANGE_INFO)
    sync.save_snapshot(snapshot)

    reloaded = sync.load_snapshot()
    assert reloaded is not None
    rules = reloaded.get_symbol_rules("BTC/USDT")
    assert rules.tick_size == 0.1
    assert rules.lot_size == 0.001
    assert rules.min_notional == 100.0
    assert rules.price_precision == 2
    assert rules.quantity_precision == 3
    assert reloaded.source_url.endswith("/fapi/v1/exchangeInfo")
    assert reloaded.cache_path == str(cache)


def test_contract_spec_is_enriched_from_binance_rules(tmp_path):
    cache = tmp_path / "exchange_info.json"
    sync = BinanceFuturesMetadataSync(cache_path=str(cache))
    snapshot = sync.build_snapshot(SAMPLE_EXCHANGE_INFO)
    sync.save_snapshot(snapshot)
    rules = sync.get_symbol_rules("BTCUSDT")

    contract = with_binance_symbol_rules(
        ContractSpec(symbol="BTC/USDT", leverage=7, exchange_profile="binance_futures_testnet"),
        rules,
    )
    assert contract.symbol == "BTC/USDT"
    assert contract.exchange_profile == "binance_futures_testnet"
    assert contract.leverage == 7
    assert contract.tick_size == 0.1
    assert contract.lot_size == 0.001
    assert contract.min_notional == 100.0
    assert contract.quantity_precision == 3
    assert contract.metadata_source == "binance_futures_testnet"
    assert contract.metadata_as_of is not None


def test_exchange_factory_uses_profile_specific_endpoints():
    testnet = create_binance_futures_exchange(BINANCE_FUTURES_TESTNET.key)
    mainnet = create_binance_futures_exchange(BINANCE_FUTURES_MAINNET.key, allow_mainnet=True)

    assert testnet.options["defaultType"] == "future"
    assert testnet.urls["api"]["fapiPublic"].startswith(BINANCE_FUTURES_TESTNET.rest_base_url)
    assert mainnet.urls["api"]["fapiPublic"].startswith(BINANCE_FUTURES_MAINNET.rest_base_url)
    assert testnet.urls["api"]["fapiPublic"] != mainnet.urls["api"]["fapiPublic"]


def test_mainnet_requires_explicit_opt_in():
    assert is_binance_mainnet_enabled(BINANCE_FUTURES_TESTNET.key) is True
    assert is_binance_mainnet_enabled(BINANCE_FUTURES_MAINNET.key, environ={}) is False
    with pytest.raises(PermissionError):
        require_binance_profile_enabled(BINANCE_FUTURES_MAINNET.key, environ={})
    require_binance_profile_enabled(
        BINANCE_FUTURES_MAINNET.key,
        environ={"BINANCE_FUTURES_ENABLE_MAINNET": "true"},
    )


def test_credentials_loader_prefers_profile_specific_environment():
    creds = load_binance_futures_credentials(
        BINANCE_FUTURES_TESTNET.key,
        environ={
            "BINANCE_FUTURES_TESTNET_API_KEY": "test-key",
            "BINANCE_FUTURES_TESTNET_API_SECRET": "test-secret",
            "BINANCE_API_KEY": "fallback-key",
            "BINANCE_API_SECRET": "fallback-secret",
        },
    )
    assert creds.api_key == "test-key"
    assert creds.secret == "test-secret"
    assert creds.source == "environment"
    assert creds.configured is True


def test_runtime_paths_are_profile_and_symbol_scoped():
    paths = build_binance_futures_runtime_paths(
        BINANCE_FUTURES_TESTNET.key,
        "BTC/USDT",
        root_dir="var/test-runtime",
    )
    assert paths.metadata_cache_file == "var/test-runtime/binance_futures_testnet/exchange_info.json"
    assert paths.paper_state_file.endswith("binance_futures_testnet/btcusdt/paper_state.json")
    assert paths.shadow_audit_log.endswith("binance_futures_testnet/btcusdt/shadow_audit.jsonl")
    assert paths.execution_events_file.endswith("binance_futures_testnet/btcusdt/execution_events.jsonl")


def test_metadata_sync_marks_old_snapshots_stale(tmp_path):
    cache = tmp_path / "exchange_info.json"
    sync = BinanceFuturesMetadataSync(cache_path=str(cache), max_age_seconds=60)
    snapshot = BinanceExchangeMetadataSnapshot(
        profile=BINANCE_FUTURES_TESTNET.key,
        fetched_at=(datetime.now(timezone.utc) - timedelta(hours=8)).isoformat(),
        exchange_timezone="UTC",
        server_time=1710000000000,
        symbols={"BTC/USDT": {"symbol": "BTC/USDT", "exchange_symbol": "BTCUSDT", "status": "TRADING", "contract_type": "PERPETUAL", "tick_size": 0.1, "lot_size": 0.001, "market_lot_size": 0.001, "min_notional": 100.0, "min_quantity": 0.001, "max_quantity": 1000.0, "price_precision": 2, "quantity_precision": 3, "base_asset": "BTC", "quote_asset": "USDT", "margin_asset": "USDT", "metadata_source": BINANCE_FUTURES_TESTNET.key, "metadata_as_of": datetime.now(timezone.utc).isoformat()}},
    )
    cache.write_text(json.dumps(snapshot.to_dict()), encoding="utf-8")
    loaded = sync.load_snapshot()
    assert loaded is not None
    assert sync.snapshot_is_stale(loaded) is True
