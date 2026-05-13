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
