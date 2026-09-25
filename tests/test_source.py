import importlib
from datetime import date
import pytest
from .factories import make_source, FIELDS


def api():
    return importlib.import_module("istat_confini.source")


def test_catalog_exact_unicode_codes_joins_and_export_date(tmp_path):
    root = make_source(tmp_path)
    catalog = api().read_source_catalog(root)
    assert catalog.source_dbf_export_date == date(2026, 2, 18)
    first, second = catalog.municipalities
    assert (first.code, first.name, first.region_code, first.region_name) == ("001235", "Samone", "01", "Piemonte")
    assert (first.territorial_unit_code, first.territorial_unit_name) == ("201", "Torino")
    assert (second.name, second.alternative_name) == ("Forlì", None)
    assert len(list(api().iter_source_polygons(root))) == 2


def test_national_counts_fail_for_small_source(tmp_path):
    with pytest.raises(ValueError, match="7,896"):
        api().load_source_catalog(make_source(tmp_path))


@pytest.mark.parametrize("options", [
    {"codes": ["001235", "001235"]}, {"codes": ["", "040012"]},
    {"codes": ["1235", "040012"]}, {"names": ["", "Forlì"]},
    {"region_keys": [1, 1]}, {"uts_keys": [201, 201]},
    {"municipal_regions": [99, 8]}, {"municipal_uts": [999, 40]},
    {"municipal_regions": [1, 1]},
])
def test_bad_attributes_block(options, tmp_path):
    with pytest.raises(ValueError):
        api().read_source_catalog(make_source(tmp_path, **options))


def test_duplicate_names_preserved(tmp_path):
    catalog = api().read_source_catalog(make_source(tmp_path, names=["Samone", "Samone"]))
    assert [m.name for m in catalog.municipalities] == ["Samone", "Samone"]


@pytest.mark.parametrize("change", ["utf8", "date", "code-width", "missing-name", "deleted"])
def test_dbf_corruption_blocks(tmp_path, change):
    root = make_source(tmp_path)
    path = root / "Com01012026/Com01012026_WGS84.dbf"
    raw = bytearray(path.read_bytes())
    if change == "utf8":
        raw[raw.index("Forlì".encode())] = 255
    elif change == "date":
        raw[2] = 13
    elif change == "code-width":
        pos = raw.index(b"PRO_COM_T")
        raw[pos + 16] = 5
    elif change == "missing-name":
        pos = raw.index(b"COMUNE\x00")
        raw[pos:pos + 6] = b"WRONG\x00"
    else:
        raw[int.from_bytes(raw[8:10], "little")] = ord("*")
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        api().read_source_catalog(root)


@pytest.mark.parametrize("layer", ["Com", "Reg", "ProvCM"])
@pytest.mark.parametrize("wkt", ["nonsense", "EPSG:4326"])
def test_every_layer_crs_is_checked(tmp_path, layer, wkt):
    root = make_source(tmp_path)
    (root / f"{layer}01012026/{layer}01012026_WGS84.prj").write_text(wkt)
    with pytest.raises(ValueError, match="CRS"):
        api().read_source_catalog(root)
