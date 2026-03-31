import json

from btc_contract_backtest.config.models import ContractSpec
from btc_contract_backtest.live.binance_futures import (
    BINANCE_FUTURES_MAINNET,
    BINANCE_FUTURES_TESTNET,
    BinanceFuturesMetadataSync,
    create_binance_futures_exchange,
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
    mainnet = create_binance_futures_exchange(BINANCE_FUTURES_MAINNET.key)

    assert testnet.options["defaultType"] == "future"
    assert testnet.urls["api"]["fapiPublic"].startswith(BINANCE_FUTURES_TESTNET.rest_base_url)
    assert mainnet.urls["api"]["fapiPublic"].startswith(BINANCE_FUTURES_MAINNET.rest_base_url)
    assert testnet.urls["api"]["fapiPublic"] != mainnet.urls["api"]["fapiPublic"]
