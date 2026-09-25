import json
import pytest
from .factories import make_source
from .test_generate import STAMP
from istat_confini import generate
from istat_confini.source import read_source_catalog
from istat_confini.validate import validate_correspondence


@pytest.fixture
def excluded_fixture(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source", codes=["072001", "040012"],
                         names=["Acquaviva delle Fonti", "Forlì"])
    monkeypatch.setattr(generate, "load_source_catalog", read_source_catalog)
    return source, tmp_path / "dist"


def test_only_approved_code_is_omitted_and_disclosed(excluded_fixture):
    source, out = excluded_fixture
    generate.generate_dataset(source, out, STAMP)
    index = json.loads((out / "2026/index.json").read_bytes())
    assert [m["code"] for m in index["municipalities"]] == ["040012"]
    assert index["municipalities"][0]["bbox"] == [9.012721, 45.153476, 9.013995, 45.154377]
    assert not (out / "2026/comuni/072001.geojson").exists()
    assert index["dataset"]["sourceRecordCount"] == 2
    assert index["dataset"]["recordCount"] == 1
    assert index["dataset"]["excludedMunicipalities"] == [{
        "code": "072001", "name": "Acquaviva delle Fonti",
        "reason": "Invalid source geometry: ring self-intersection; omitted without repair.",
    }]
    result = validate_correspondence(source, out)
    assert result.counts["municipalityFiles"] == 1
    assert result.counts["positions"] == 5


def test_omitted_geometry_is_never_converted(excluded_fixture, monkeypatch):
    source, out = excluded_fixture
    original = generate.convert_polygon
    def guarded(shp, transformer, *, code):
        assert code != "072001", "excluded shape reached converter"
        return original(shp, transformer, code=code)
    monkeypatch.setattr(generate, "convert_polygon", guarded)
    generate.generate_dataset(source, out, STAMP)


@pytest.mark.parametrize("change", ["hide-exclusion", "invent-exclusion", "source-count", "name"])
def test_exclusion_metadata_cannot_lie(excluded_fixture, change):
    source, out = excluded_fixture
    generate.generate_dataset(source, out, STAMP)
    p = out / "2026/index.json"
    doc = json.loads(p.read_bytes())
    # Set fields explicitly so the pre-feature failure is validation accepting the mutation.
    doc["dataset"]["sourceRecordCount"] = 2
    doc["dataset"]["excludedMunicipalities"] = [{
        "code": "072001", "name": "Acquaviva delle Fonti",
        "reason": "Invalid source geometry: ring self-intersection; omitted without repair.",
    }]
    if change == "hide-exclusion": doc["dataset"]["excludedMunicipalities"] = []
    if change == "invent-exclusion": doc["dataset"]["excludedMunicipalities"][0]["code"] = "999999"
    if change == "source-count": doc["dataset"]["sourceRecordCount"] = 1
    if change == "name": doc["dataset"]["excludedMunicipalities"][0]["name"] = "Wrong"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        validate_correspondence(source, out)


def test_unapproved_conversion_error_still_blocks(excluded_fixture, monkeypatch):
    source, out = excluded_fixture
    def fail(shp, transformer, *, code):
        raise ValueError(f"{code}: new invalid geometry")
    monkeypatch.setattr(generate, "convert_polygon", fail)
    with pytest.raises(ValueError, match="040012"):
        generate.generate_dataset(source, out, STAMP)
    assert not out.exists()
