import importlib
import json
import pytest
from .factories import make_source
from .test_generate import STAMP
from istat_confini import generate
from istat_confini.source import read_source_catalog


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source")
    monkeypatch.setattr(generate, "load_source_catalog", read_source_catalog)
    generate.generate_dataset(source, tmp_path / "dist", STAMP)
    return source, tmp_path / "dist"


def api():
    return importlib.import_module("istat_confini.validate")


def test_fresh_source_matches_all_artifact_fields(dataset):
    source, out = dataset
    result = api().validate_correspondence(source, out)
    assert result.status == "passed"
    assert result.counts == {"municipalities": 2, "indexEntries": 2, "municipalityFiles": 2,
                             "positions": 10, "rings": 2, "shapePartsOverOneRecords": 0,
                             "multipartRecords": 0, "holeRecords": 0, "interiorRings": 0}
    assert result.pages_artifact_bytes == sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    assert len(result.artifact_sha256) == 64


def test_national_validation_rejects_fixture(dataset):
    with pytest.raises(ValueError, match="7,896"):
        api().validate_source_and_artifact(*dataset)


@pytest.mark.parametrize("change", [
    "missing", "extra", "index-missing", "index-duplicate", "index-name", "index-label",
    "digest", "vertex", "remove-position", "reverse", "hole", "type", "utf8", "bom",
    "nan", "json", "path", "feature-id", "metadata-code", "license", "extra-dist", "manifest", "bbox",
])
def test_corruption_blocks_validation(dataset, change):
    source, out = dataset
    p = out / "2026/comuni/001235.geojson"
    idx = out / "2026/index.json"
    doc = json.loads(p.read_bytes())
    feature = doc["features"][0]
    if change == "missing":
        p.unlink()
    elif change == "extra":
        (p.parent / "999999.geojson").write_bytes(p.read_bytes())
    elif change.startswith("index-"):
        index = json.loads(idx.read_bytes())
        rows = index["municipalities"]
        if change == "index-missing": rows.pop()
        if change == "index-duplicate": rows[1] = rows[0]
        if change == "index-name": rows[0]["name"] = "wrong"
        if change == "index-label": rows[0]["region"]["name"] = "wrong"
        idx.write_text(json.dumps(index), encoding="utf-8")
    elif change in ("utf8", "bom", "nan", "json"):
        p.write_bytes({"utf8": b"\xff", "bom": b"\xef\xbb\xbf" + p.read_bytes(),
                       "nan": b'{"x":NaN}', "json": b"{"}[change])
    elif change == "extra-dist":
        (out / "secret.txt").write_text("not for publication")
    elif change == "manifest":
        m = out / "source-manifest.json"
        obj = json.loads(m.read_bytes())
        obj["files"][0]["bytes"] += 1
        m.write_text(json.dumps(obj))
    else:
        if change == "digest": doc["metadata"]["sourceManifestSha256"] = "0"*64
        if change == "vertex": feature["geometry"]["coordinates"][0][1][0] += .0000001
        if change == "remove-position": feature["geometry"]["coordinates"][0].pop(1)
        if change == "reverse": feature["geometry"]["coordinates"][0].reverse()
        if change == "hole": feature["geometry"]["coordinates"].append(feature["geometry"]["coordinates"][0])
        if change == "type": feature["geometry"]["type"] = "MultiPolygon"
        if change == "path": feature["properties"]["name"] = "C:\\Users\\private"
        if change == "feature-id": feature["id"] = "999999"
        if change == "metadata-code": doc["metadata"]["code"] = "999999"
        if change == "license": doc["metadata"].pop("license")
        if change == "bbox":
            index_path = out / "2026/index.json"
            index = json.loads(index_path.read_bytes())
            index["municipalities"][0]["bbox"][0] += .001
            index_path.write_text(json.dumps(index), encoding="utf-8")
        p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        api().validate_correspondence(source, out)


def test_source_change_invalidates_manifest(dataset):
    source, out = dataset
    p = source / "Reg01012026/Reg01012026_WGS84.prj"
    p.write_text(p.read_text() + " ")
    with pytest.raises(ValueError, match="manifest"):
        api().validate_correspondence(source, out)
