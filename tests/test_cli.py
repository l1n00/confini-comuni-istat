import importlib
import json
from pathlib import Path
import pytest
from .factories import make_source


def api():
    return importlib.import_module("istat_confini.cli")


def test_small_source_fails_national_gate_and_writes_safe_failure(tmp_path, capsys):
    source = make_source(tmp_path / "source")
    code = api().main(["build", "--source-root", str(source), "--output-root", str(tmp_path / "dist"),
                       "--reports-root", str(tmp_path / "reports")])
    assert code == 2
    assert not (tmp_path / "dist").exists()
    failure = (tmp_path / "reports/build-failure.json").read_text()
    assert json.loads(failure)["status"] == "failed"
    assert str(tmp_path) not in failure
    assert "7,896" in capsys.readouterr().err


def test_reports_cannot_overlap_source(tmp_path):
    source = make_source(tmp_path / "source")
    assert api().main(["build", "--source-root", str(source), "--output-root", str(tmp_path / "dist"),
                       "--reports-root", str(source / "reports")]) == 2
    assert not (source / "reports").exists()


def test_missing_or_stale_report_prevents_release(tmp_path):
    assert api().main(["verify-release", "--project-root", str(tmp_path)]) == 2


def test_tampered_artifact_cannot_pass_release_binding(tmp_path, monkeypatch):
    # A passing report is necessary but not sufficient: release verification must
    # compare the current artifact digest to the full-source-verified digest.
    from istat_confini.cli import verify_release
    from istat_confini.validate import ValidationResult
    reports = tmp_path / "reports"
    dist = tmp_path / "dist"
    reports.mkdir()
    dist.mkdir()
    (reports / "validation.json").write_text(json.dumps({
        "status": "passed", "artifactSha256": "a"*64,
        "sourceBeforeSha256": "b"*64, "sourceAfterSha256": "b"*64,
        "counts": {"municipalityFiles": 1},
    }), encoding="utf-8")
    current = ValidationResult("passed", "b"*64, "c"*64, {"municipalityFiles": 1},
                               1, 1, 1, (("001001", 1),), 1)
    monkeypatch.setattr(api(), "validate_artifact_only", lambda _root: current)
    with pytest.raises(ValueError, match="no longer matches"):
        verify_release(tmp_path)


def test_help_exits_successfully():
    with pytest.raises(SystemExit) as exc:
        api().main(["--help"])
    assert exc.value.code == 0
