"""Unit tests for TimeFeatureDetector — pure-logic, no MQTT or matplotlib."""

from subscriber.time_features import TimeFeatureDetector


def _record(ts=1000.0, **overrides):
    """Build a minimal telemetry record. Override fields as needed."""
    rec = {
        "timestamp": ts,
        "vpt_nwkr": 24.0, "vpt_rwkr": 24.0,
        "nwkr": 0, "rwkr": 0, "nwcr": 0, "rwcr": 0,
        "vpt_110_n": 110.0, "vpt_110_r": 110.0,
        "ipt_n": 0.0, "ipt_r": 0.0,
        "vpt_24_n": 24.0, "vpt_24_r": 24.0,
        "vib_x": 0.0,
        "tpt_n": 0.0, "tpt_r": 0.0,
    }
    rec.update(overrides)
    return rec


def test_normal_stroke_via_tpt_n():
    det = TimeFeatureDetector()
    # First sample establishes baseline
    assert det.update(_record(ts=1000.0)) is None
    # Second sample: tpt_n becomes non-zero → stroke event
    event = det.update(_record(ts=1001.0, tpt_n=5.0))
    assert event is not None
    assert event["side"] == "N"
    assert event["op_time"] == 5.0
    assert event["slipping"] is False
    assert event["stroke_count"] == 1
    assert event["slip_count"] == 0


def test_slipping_stroke_via_tpt_n():
    det = TimeFeatureDetector()
    assert det.update(_record(ts=1000.0)) is None
    event = det.update(_record(ts=1001.0, tpt_n=9.5))
    assert event["slipping"] is True
    assert event["slip_count"] == 1
    assert event["stroke_count"] == 1


def test_vdrop_accumulation_on_vpt_110_n():
    det = TimeFeatureDetector()
    # Below-threshold dip starts at ts=1000.0
    for i in range(5):
        det.update(_record(ts=1000.0 + i * 0.2, vpt_110_n=85.0))
    # Recovery at ts=1001.0 → closes the interval (1001.0 - 1000.0 = 1.0 s)
    det.update(_record(ts=1001.0, vpt_110_n=110.0))
    snap = det.snapshot_counters()
    assert abs(snap["vdrop_seconds"]["vpt_110_n"] - 1.0) < 1e-6
    # Other rails untouched
    assert snap["vdrop_seconds"]["vpt_110_r"] == 0.0


def test_relay_edge_fallback_stroke():
    """tpt fields stay 0; stroke timing derived from relay rising edges."""
    det = TimeFeatureDetector()
    # Baseline: all zero
    assert det.update(_record(ts=1000.0)) is None
    # Contactor energises Normal side
    assert det.update(_record(ts=1000.2, nwcr=1)) is None
    # ... still mid-stroke
    assert det.update(_record(ts=1003.5, nwcr=1)) is None
    # Position relay picks up → stroke completes
    event = det.update(_record(ts=1004.0, nwcr=1, nwkr=1))
    assert event is not None
    assert event["side"] == "N"
    assert abs(event["op_time"] - 3.8) < 1e-6
    assert event["slipping"] is False


def test_relay_edge_fallback_opposite_relay_discards_stroke():
    """If wrong-side position relay rises mid-stroke, drop the in-flight stroke."""
    det = TimeFeatureDetector()
    det.update(_record(ts=1000.0))
    det.update(_record(ts=1000.2, nwcr=1))
    # Wrong side rises → discard
    event = det.update(_record(ts=1001.0, nwcr=1, rwkr=1))
    assert event is None
    # Next valid Normal completion should NOT use the discarded start
    det.update(_record(ts=1002.0, nwcr=1, rwkr=1))   # rwkr stays high, no edge
    det.update(_record(ts=1002.5, nwcr=0, rwkr=1))
    det.update(_record(ts=1003.0, nwcr=1, rwkr=1))   # fresh nwcr rising edge
    event = det.update(_record(ts=1005.0, nwcr=1, nwkr=1, rwkr=1))
    assert event is not None
    assert event["side"] == "N"
    assert abs(event["op_time"] - 2.0) < 1e-6


def test_relay_edge_fallback_stroke_r_side():
    """Mirror of test_relay_edge_fallback_stroke for the R side."""
    det = TimeFeatureDetector()
    assert det.update(_record(ts=2000.0)) is None
    assert det.update(_record(ts=2000.2, rwcr=1)) is None
    assert det.update(_record(ts=2003.5, rwcr=1)) is None
    event = det.update(_record(ts=2004.0, rwcr=1, rwkr=1))
    assert event is not None
    assert event["side"] == "R"
    assert abs(event["op_time"] - 3.8) < 1e-6
    assert event["slipping"] is False
