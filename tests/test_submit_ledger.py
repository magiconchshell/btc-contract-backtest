from btc_contract_backtest.live.submit_ledger import SubmitAttempt, SubmitIntent, SubmitLedger


def test_submit_ledger_tracks_lifecycle(tmp_path):
    ledger = SubmitLedger(str(tmp_path / "submit_ledger.json"))
    ledger.upsert(
        SubmitIntent(
            request_id="r1",
            client_order_id="c1",
            symbol="BTC/USDT",
            signal=1,
            quantity=1.0,
            notional=100.0,
            state="created",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )
    ledger.append_attempt("r1", SubmitAttempt(timestamp="2026-01-01T00:00:01+00:00", action="submit", status="started"))
    ledger.mark_state("r1", state="submitted", timestamp="2026-01-01T00:00:02+00:00", exchange_order_id="ex1")

    payload = ledger.get("r1")
    assert payload is not None
    assert payload["state"] == "submitted"
    assert payload["exchange_order_id"] == "ex1"
    assert len(payload["attempts"]) == 1


def test_submit_ledger_dedupes_by_client_order_id(tmp_path):
    ledger = SubmitLedger(str(tmp_path / "submit_ledger.json"))
    ledger.upsert(
        SubmitIntent(
            request_id="r1",
            client_order_id="c1",
            symbol="BTC/USDT",
            signal=1,
            quantity=1.0,
            notional=100.0,
        )
    )
    ledger.upsert(
        SubmitIntent(
            request_id="r2",
            client_order_id="c1",
            symbol="BTC/USDT",
            signal=1,
            quantity=1.0,
            notional=100.0,
            state="submitted",
        )
    )

    intents = ledger.list_intents()
    assert len(intents) == 1
    assert intents[0]["request_id"] == "r2"
    assert intents[0]["state"] == "submitted"
