from btc_contract_backtest.live.reconcile import build_detailed_reconcile_report


def test_detailed_reconcile_detects_order_and_position_mismatches():
    report = build_detailed_reconcile_report(
        local_position={"side": 1, "quantity": 1.0, "entry_price": 100.0},
        remote_positions=[{"contracts": 2.0, "entryPrice": 101.0}],
        local_orders=[
            {
                "order_id": "o1",
                "client_order_id": "c1",
                "exchange_order_id": "ex1",
                "side": "buy",
                "order_type": "market",
                "quantity": 1.0,
                "filled_quantity": 0.0,
                "status": "new",
                "reduce_only": False,
            }
        ],
        remote_orders=[
            {
                "id": "ex1",
                "clientOrderId": "c1",
                "side": "sell",
                "type": "market",
                "amount": 2.0,
                "filled": 1.0,
                "status": "open",
                "average": 100.5,
                "reduceOnly": True,
            }
        ],
    ).to_dict()

    assert report["ok"] is False
    assert report["position_mismatch"] is not None
    assert report["position_mismatch"]["classification"] == "position_mismatch"
    assert report["summary"]["order_mismatch_count"] == 1
    assert report["summary"]["position_mismatch_types"] == ["quantity", "entry_price"]
    assert report["summary"]["order_mismatch_classifications"] == ["order_partial_fill_divergence"]
    mismatch = report["order_mismatches"][0]
    assert "side" in mismatch["mismatch_types"]
    assert "quantity" in mismatch["mismatch_types"]
    assert "filled_quantity" in mismatch["mismatch_types"]
    assert "reduce_only" in mismatch["mismatch_types"]
    assert mismatch["classification"] == "order_partial_fill_divergence"


def test_detailed_reconcile_detects_orphan_orders():
    report = build_detailed_reconcile_report(
        local_position={"side": 0, "quantity": 0.0, "entry_price": None},
        remote_positions=[],
        local_orders=[{"order_id": "o1", "client_order_id": "c1", "side": "buy", "order_type": "limit", "quantity": 1.0, "filled_quantity": 0.0, "status": "new"}],
        remote_orders=[{"id": "ex2", "clientOrderId": "c2", "side": "buy", "type": "limit", "amount": 1.0, "filled": 0.0, "status": "open"}],
    ).to_dict()

    assert report["ok"] is False
    assert len(report["orphan_local_orders"]) == 1
    assert len(report["orphan_remote_orders"]) == 1
