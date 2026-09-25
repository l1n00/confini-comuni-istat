from datetime import datetime, timezone
import importlib
import json
import pytest
from .factories import make_source
from istat_confini.source import read_source_catalog

STAMP = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def api(monkeypatch):
    mod = importlib.import_module("istat_confini.generate")
    monkeypatch.setattr(mod, "load_source_catalog", read_source_catalog)
    return mod


def test_exact_contract_unicode_and_deterministic_bytes(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source")
    mod = api(monkeypatch)
    mod.generate_dataset(source, tmp_path / "a", STAMP)
    mod.generate_dataset(source, tmp_path / "b", STAMP)
    files = sorted(p.relative_to(tmp_path / "a") for p in (tmp_path / "a").rglob("*") if p.is_file())
    assert len(files) == 4
    for rel in files:
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes()
    index = json.loads((tmp_path / "a/2026/index.json").read_bytes())
    assert index["schemaVersion"] == 1
    assert index["dataset"]["generatedAt"] == "2026-09-25T12:00:00Z"
    assert index["dataset"]["sourceDbfExportDate"] == "2026-02-18"
    assert index["municipalities"][0] == {
        "name": "Samone", "code": "001235", "region": {"code": "01", "name": "Piemonte"},
        "territorialUnit": {"code": "201", "name": "Torino"},
    }
    raw = (tmp_path / "a/2026/comuni/040012.geojson").read_bytes()
    assert "Forlì".encode() in raw and not raw.startswith(b"\xef\xbb\xbf")
    obj = json.loads(raw)
    assert set(obj) == {"type", "metadata", "features"}
    assert obj["type"] == "FeatureCollection" and len(obj["features"]) == 1
    feature = obj["features"][0]
    assert feature["id"] == feature["properties"]["code"] == obj["metadata"]["code"] == "040012"
    assert feature["properties"]["alternativeName"] is None
    assert feature["geometry"]["type"] == "Polygon"
    assert 9 < feature["geometry"]["coordinates"][0][0][0] < 10
    assert "crs" not in obj and "crs" not in feature
    assert obj["metadata"]["license"] == "https://creativecommons.org/licenses/by/4.0/"
    manifest = json.loads((tmp_path / "a/source-manifest.json").read_bytes())
    assert index["dataset"]["sourceManifestSha256"] == manifest["sha256"]


def test_existing_output_is_never_overwritten(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source")
    out = tmp_path / "out"
    out.mkdir()
    marker = out / "keep"
    marker.write_text("user")
    with pytest.raises(FileExistsError):
        api(monkeypatch).generate_dataset(source, out, STAMP)
    assert marker.read_text() == "user"


def test_no_writes_inside_source(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source")
    with pytest.raises(ValueError, match="overlap"):
        api(monkeypatch).generate_dataset(source, source / "output", STAMP)
    assert not (source / "output").exists()


def test_naive_timestamp_rejected(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source")
    with pytest.raises(ValueError, match="timezone"):
        api(monkeypatch).generate_dataset(source, tmp_path / "out", datetime(2026, 1, 1))


def test_failed_geometry_leaves_no_promoted_or_staging_output(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source")
    mod = api(monkeypatch)
    def fail(*args, **kwargs):
        raise ValueError("001235: invalid geometry")
    monkeypatch.setattr(mod, "convert_polygon", fail)
    with pytest.raises(ValueError, match="001235"):
        mod.generate_dataset(source, tmp_path / "out", STAMP)
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".generation-*"))


def test_source_mutation_during_build_blocks_promotion(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source")
    mod = api(monkeypatch)
    original = mod.iter_source_polygons
    def mutating(root):
        yield from original(root)
        p = root / "Reg01012026/Reg01012026_WGS84.prj"
        p.write_text(p.read_text() + " ")
    monkeypatch.setattr(mod, "iter_source_polygons", mutating)
    with pytest.raises(ValueError, match="changed"):
        mod.generate_dataset(source, tmp_path / "out", STAMP)
    assert not (tmp_path / "out").exists()
