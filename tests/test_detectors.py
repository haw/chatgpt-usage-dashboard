import textwrap

from app.detectors import DetectionContext, Detector, Signal, build_detector_set, register, registered


def usage(day: int, chat_tokens: int = 100, chat_dau: int = 5) -> dict:
    tokens = {"chat": chat_tokens, "codex": 20, "work": 10}
    return {
        "date": f"2026-09-{day:02d}",
        "active_users": {"chat": chat_dau, "codex": 3, "work": 1},
        "tokens": {**tokens, "total": sum(tokens.values())},
    }


def test_builtin_detectors_are_registered():
    assert {"token_spike", "dau_change"} <= set(registered())


def test_missing_config_uses_every_builtin_with_defaults(tmp_path):
    detectors = build_detector_set(tmp_path / "missing.toml")
    assert detectors.errors == []
    assert {d["id"] for d in detectors.describe()} == set(registered())


def test_config_disables_reparametrises_and_duplicates_detectors(tmp_path):
    config = tmp_path / "detectors.toml"
    config.write_text(textwrap.dedent("""
        [[detectors]]
        id = "dau_change"
        enabled = false

        [[detectors]]
        id = "token_spike"
        [detectors.params]
        z = 200.0

        [[detectors]]
        id = "token_spike_loose"
        use = "token_spike"
        [detectors.params]
        z = 1.0
    """))
    detectors = build_detector_set(config)
    assert detectors.errors == []
    assert [d["id"] for d in detectors.describe()] == ["token_spike", "token_spike_loose"]
    noisy = [100, 110, 90, 105, 95, 100, 110]  # MAD > 0 so z controls the threshold
    rows = [usage(day, chat_tokens=noisy[day - 1]) for day in range(1, 8)] + [usage(8, chat_tokens=1000)]
    signals = detectors.run(DetectionContext(rows=rows))
    assert {s["detector"] for s in signals if s["severity"] != "info"} == {"token_spike_loose"}
    assert not any(s["type"].startswith("dau") for s in signals)


def test_config_errors_are_reported_without_breaking_detection(tmp_path):
    config = tmp_path / "detectors.toml"
    config.write_text(textwrap.dedent("""
        [[detectors]]
        id = "token_spike"
        [detectors.params]
        bogus = 1

        [[detectors]]
        id = "ghost"

        [[detectors]]
        id = "broken_plugin"
        module = "does_not_exist"

        [[detectors]]
        id = "dau_change"
    """))
    detectors = build_detector_set(config)
    assert [d["id"] for d in detectors.describe()] == ["dau_change"]
    assert len(detectors.errors) == 3
    assert any("bogus" in error for error in detectors.errors)
    assert any("ghost" in error for error in detectors.errors)
    assert any("does_not_exist" in error for error in detectors.errors)


def test_plugin_module_is_loaded_from_plugins_dir(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "always_fire.py").write_text(textwrap.dedent("""
        from app.detectors import DetectionContext, Detector, Signal, register

        @register
        class AlwaysFire(Detector):
            id = "always_fire"
            label = "常に検出"
            group = "tokens"
            default_params = {"severity": "info"}

            def detect(self, ctx):
                return [Signal(detector=self.id, type="always", severity=self.params["severity"],
                               metric="テスト", date=row["date"], value=0) for row in ctx.rows]
    """))
    config = tmp_path / "detectors.toml"
    config.write_text('[[detectors]]\nid = "always_fire"\nmodule = "always_fire"\n[detectors.params]\nseverity = "high"\n')
    detectors = build_detector_set(config, plugins)
    assert detectors.errors == []
    signals = detectors.run(DetectionContext(rows=[usage(1)]))
    assert signals == [{
        "detector": "always_fire", "type": "always", "severity": "high", "metric": "テスト",
        "date": "2026-09-01", "value": 0, "product": None, "baseline": None, "threshold": None,
        "score": None, "reason": "", "span_days": None,
    }]


def test_failing_detector_is_isolated():
    @register
    class Explodes(Detector):
        id = "explodes_in_test"
        label = "壊れた検知器"

        def detect(self, ctx):
            raise RuntimeError("boom")

    try:
        from app.detectors.registry import DetectorSet
        from app.detectors.builtin.token_spike import TokenSpike

        detectors = DetectorSet([Explodes(), TokenSpike()], [])
        rows = [usage(day) for day in range(1, 8)] + [usage(8, chat_tokens=1000)]
        signals = detectors.run(DetectionContext(rows=rows))
        assert any(s["type"] == "token_spike" for s in signals)
        assert detectors.errors == ["explodes_in_test: boom"]
    finally:
        from app.detectors import registry
        registry._REGISTRY.pop("explodes_in_test", None)


def test_signal_rejects_unknown_severity():
    try:
        Signal(detector="x", type="y", severity="critical", metric="m", date="2026-09-01", value=1)
    except ValueError as exc:
        assert "severity" in str(exc)
    else:
        raise AssertionError("expected ValueError")
