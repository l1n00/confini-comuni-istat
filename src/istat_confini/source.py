from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
import struct

import shapefile
from pyproj import CRS
from pyproj.exceptions import CRSError

from .config import LAYERS, layer_path
from .errors import SourceValidationError
from .manifest import SourceManifest, build_source_manifest


@dataclass(frozen=True)
class Municipality:
    code: str
    name: str
    alternative_name: str | None
    region_code: str
    region_name: str
    territorial_unit_code: str
    territorial_unit_name: str


@dataclass(frozen=True)
class SourceCatalog:
    manifest: SourceManifest
    municipalities: tuple[Municipality, ...]
    regional_record_count: int
    territorial_unit_record_count: int
    source_dbf_export_date: date


def verify_prj_crs(prj_path: Path, expected_epsg: int = 32632) -> None:
    try:
        actual = CRS.from_wkt(prj_path.read_text(encoding="utf-8", errors="strict"))
        if actual != CRS.from_epsg(expected_epsg):
            raise SourceValidationError(f"CRS mismatch: {prj_path.name}")
    except (CRSError, UnicodeError) as exc:
        raise SourceValidationError(f"CRS unreadable: {prj_path.name}") from exc


def numeric_code(value, width: int) -> str:
    text = str(value)
    if not re.fullmatch(r"[0-9]{1," + str(width) + r"}", text):
        raise SourceValidationError(f"invalid administrative code: {text!r}")
    return text.zfill(width)


def _read_dbf(path: Path, required: dict):
    try:
        with path.open("rb") as stream:
            head = stream.read(32)
        if len(head) != 32:
            raise SourceValidationError(f"truncated DBF: {path.name}")
        count, hlen, rlen = struct.unpack("<IHH", head[4:12])
        exported = date(1900 + head[1], head[2], head[3])
        if exported != date(2026, 2, 18):
            raise SourceValidationError(f"unexpected export date: {path.name}")
        if path.stat().st_size not in (hlen + count*rlen, hlen + count*rlen + 1):
            raise SourceValidationError(f"DBF length mismatch: {path.name}")
        with shapefile.Reader(dbf=str(path), encoding="utf-8", encodingErrors="strict") as reader:
            fields = {f[0]: f[1:] for f in reader.fields[1:]}
            for name, definition in required.items():
                if name not in fields or (definition is not None and fields[name] != list(definition)):
                    raise SourceValidationError(f"invalid field {name}: {path.name}")
            rows = [r.as_dict() for r in reader.iterRecords()]
            if len(rows) != count:
                raise SourceValidationError(f"deleted/missing DBF record: {path.name}")
        return rows, exported
    except (UnicodeError, shapefile.ShapefileException, struct.error, ValueError) as exc:
        if isinstance(exc, SourceValidationError):
            raise
        raise SourceValidationError(f"invalid UTF-8/DBF: {path.name}") from exc


def _lookup(rows, key, label, width):
    result = {}
    for row in rows:
        code = numeric_code(row[key], width)
        name = row[label].rstrip(" ")
        if code in result or not name:
            raise SourceValidationError(f"duplicate/blank lookup: {key}={code}")
        result[code] = name
    return result


def read_source_catalog(source_root: Path) -> SourceCatalog:
    manifest = build_source_manifest(source_root)
    for layer in LAYERS:
        verify_prj_crs(layer_path(source_root, layer, "prj"))
    regions, _ = _read_dbf(layer_path(source_root, "Reg", "dbf"), {"COD_REG": ("N", 10, 0), "DEN_REG": None})
    uts, _ = _read_dbf(layer_path(source_root, "ProvCM", "dbf"), {"COD_UTS": ("N", 10, 0), "DEN_UTS": None})
    regions = _lookup(regions, "COD_REG", "DEN_REG", 2)
    uts = _lookup(uts, "COD_UTS", "DEN_UTS", 3)
    rows, exported = _read_dbf(layer_path(source_root, "Com", "dbf"), {
        "PRO_COM_T": ("C", 6, 0), "PRO_COM": ("N", 10, 0),
        "COMUNE": ("C", 100, 0), "COMUNE_A": ("C", 100, 0),
        "COD_REG": ("N", 10, 0), "COD_UTS": ("N", 10, 0),
    })
    municipalities, seen, used_regions, used_uts = [], set(), set(), set()
    for row in rows:
        code, name = row["PRO_COM_T"], row["COMUNE"].rstrip(" ")
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code) or code in seen or not name:
            raise SourceValidationError(f"invalid/duplicate municipality: {code!r}")
        if numeric_code(row["PRO_COM"], 6) != code:
            raise SourceValidationError(f"PRO_COM mismatch: {code}")
        region, unit = numeric_code(row["COD_REG"], 2), numeric_code(row["COD_UTS"], 3)
        if region not in regions or unit not in uts:
            raise SourceValidationError(f"unresolved administrative join: {code}")
        used_regions.add(region)
        used_uts.add(unit)
        seen.add(code)
        municipalities.append(Municipality(code, name, row["COMUNE_A"].rstrip(" ") or None,
                                          region, regions[region], unit, uts[unit]))
    if used_regions != regions.keys() or used_uts != uts.keys():
        raise SourceValidationError("uncovered administrative lookup rows")
    return SourceCatalog(manifest, tuple(sorted(municipalities, key=lambda m: m.code)),
                         len(regions), len(uts), exported)


def enforce_national_source_counts(catalog: SourceCatalog) -> None:
    if (len(catalog.municipalities), catalog.regional_record_count, catalog.territorial_unit_record_count) != (7896, 20, 110):
        raise SourceValidationError("expected 7,896 municipalities, 20 regions, 110 territorial units")


def load_source_catalog(source_root: Path) -> SourceCatalog:
    catalog = read_source_catalog(source_root)
    enforce_national_source_counts(catalog)
    return catalog


def iter_source_polygons(source_root: Path):
    for layer in LAYERS:
        verify_prj_crs(layer_path(source_root, layer, "prj"))
    with shapefile.Reader(str(layer_path(source_root, "Com", "shp")),
                          encoding="utf-8", encodingErrors="strict") as reader:
        if reader.shapeType != shapefile.POLYGON or reader.numRecords != reader.numShapes:
            raise SourceValidationError("municipal shape type or record-count mismatch")
        for item in reader.iterShapeRecords():
            code = item.record["PRO_COM_T"]
            if item.shape.shapeType != shapefile.POLYGON:
                raise SourceValidationError(f"non-Polygon source: {code}")
            yield code, item.shape
