import importlib
import pytest


@pytest.mark.parametrize("size,timeout,want", [
    (900000000, False, "preferred"), (900000001, False, "conditional-owner-acceptance"),
    (1000000000, False, "conditional-owner-acceptance"), (1000000001, False, "do-not-publish"),
    (1, True, "do-not-publish"),
])
def test_pages_thresholds(size, timeout, want):
    mod = importlib.import_module("istat_confini.report")
    assert mod.pages_decision(size, deployment_timed_out=timeout) == want


def test_distribution_and_largest_are_measured():
    mod = importlib.import_module("istat_confini.report")
    files = tuple((f"{i:06}", i) for i in range(1, 7897))
    s = mod.size_distribution(files)
    assert s["minimum"] == 1
    assert s["median"] == 3948.5
    assert s["p95"] == 7502
    assert s["maximum"] == 7896
    assert len(s["largest20"]) == 20
    assert s["largest20"][0] == {"code": "007896", "bytes": 7896}


def test_report_measures_compression_runtime_and_writes_json(tmp_path):
    from datetime import datetime, timezone
    from istat_confini.validate import ValidationResult
    import json
    mod = importlib.import_module("istat_confini.report")
    v = ValidationResult("passed", "a"*64, "b"*64, {"municipalityFiles": 2}, 2000, 2100, 100,
                         (("001001", 900), ("002002", 1000)), 1000)
    report = mod.build_feasibility_report(v, generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                           build_seconds=2, validation_seconds=3)
    assert report["totalSeconds"] == 5
    assert report["fullDatasetDownloadsGzipEstimate"] == 100000000
    assert report["publicationApproved"] is False
    mod.write_reports(report, tmp_path)
    assert json.loads((tmp_path / "validation.json").read_text())["artifactSha256"] == "b"*64
    assert "Not published" in (tmp_path / "feasibility.md").read_text()
