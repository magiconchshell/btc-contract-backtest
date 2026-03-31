from btc_contract_backtest.live.event_stream import EventDrivenExecutionSource, EventRecorder


def test_event_stream_records_and_replays_sequence(tmp_path):
    recorder = EventRecorder(str(tmp_path / "events.jsonl"))
    source = EventDrivenExecutionSource(recorder)

    evt1 = source.emit("submit_intent_created", "2026-01-01T00:00:00+00:00", {"request_id": "r1"}, source="runtime")
    evt2 = source.emit("submit_intent_submitted", "2026-01-01T00:00:01+00:00", {"request_id": "r1"}, source="exchange")
    replay = source.replay()

    assert evt1["sequence"] == 1
    assert evt2["sequence"] == 2
    assert len(replay) == 2
    assert replay[1]["event_type"] == "submit_intent_submitted"
