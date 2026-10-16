import json
import pytest
from shapely.geometry import shape as geo_shape
from .factories import make_source, self_intersecting
from .test_generate import STAMP
from istat_confini import generate
from istat_confini.config import REPAIR_METHOD, REPAIR_MODIFICATION, REPAIR_REASON
from istat_confini.errors import GeometryValidationError
from istat_confini.source import read_source_catalog
from istat_confini.validate import validate_correspondence


@pytest.fixture
def repaired_fixture(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source", codes=["040012", "072040"],
                         names=["Forlì", "Sannicandro di Bari"],
                         rings={1: [self_intersecting(501000)]})
    monkeypatch.setattr(generate, "load_source_catalog", read_source_catalog)
    return source, tmp_path / "dist"


def test_approved_invalid_geometry_is_repaired_published_and_disclosed(repaired_fixture):
    source, out = repaired_fixture
    generate.generate_dataset(source, out, STAMP)
    index = json.loads((out / "2026/index.json").read_bytes())
    assert [m["code"] for m in index["municipalities"]] == ["040012", "072040"]
    assert index["dataset"]["sourceRecordCount"] == index["dataset"]["recordCount"] == 2
    assert index["dataset"]["excludedMunicipalities"] == []
    assert index["dataset"]["repairedMunicipalities"] == [{
        "code": "072040", "name": "Sannicandro di Bari", "reason": REPAIR_REASON, "method": REPAIR_METHOD,
    }]
    assert REPAIR_MODIFICATION in index["dataset"]["modifications"]
    feature = json.loads((out / "2026/comuni/072040.geojson").read_bytes())
    assert REPAIR_MODIFICATION in feature["metadata"]["modifications"]
    geometry = geo_shape(feature["features"][0]["geometry"])
    assert geometry.is_valid and not geometry.is_empty
    untouched = json.loads((out / "2026/comuni/040012.geojson").read_bytes())
    assert REPAIR_MODIFICATION not in untouched["metadata"]["modifications"]
    assert validate_correspondence(source, out).counts["municipalityFiles"] == 2


def test_unapproved_invalid_geometry_still_blocks(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source", rings={1: [self_intersecting(501000)]})
    monkeypatch.setattr(generate, "load_source_catalog", read_source_catalog)
    with pytest.raises(GeometryValidationError, match="040012"):
        generate.generate_dataset(source, tmp_path / "dist", STAMP)
    assert not (tmp_path / "dist").exists()


def test_repaired_identity_must_match(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source", codes=["040012", "072040"], names=["Forlì", "Altro"])
    monkeypatch.setattr(generate, "load_source_catalog", read_source_catalog)
    with pytest.raises(ValueError, match="072040"):
        generate.generate_dataset(source, tmp_path / "dist", STAMP)


@pytest.mark.parametrize("change", ["hide-repair", "invent-repair", "exclude", "source-count"])
def test_repair_metadata_cannot_lie(repaired_fixture, change):
    source, out = repaired_fixture
    generate.generate_dataset(source, out, STAMP)
    p = out / "2026/index.json"
    doc = json.loads(p.read_bytes())
    dataset = doc["dataset"]
    if change == "hide-repair": dataset["repairedMunicipalities"] = []
    if change == "invent-repair": dataset["repairedMunicipalities"][0]["code"] = "999999"
    if change == "exclude": dataset["excludedMunicipalities"] = [{"code": "072040"}]
    if change == "source-count": dataset["sourceRecordCount"] = 3
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        validate_correspondence(source, out)
