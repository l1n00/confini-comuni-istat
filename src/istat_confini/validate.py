"""Strict artifact inspection plus source correspondence; never repairs geometry."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

from pyproj import Transformer
from shapely.geometry import shape
from shapely.validation import explain_validity

from .config import SOURCE_COMPONENTS, PUBLISHED_COUNTS, LICENSE_URL
from .config import EXCLUDED_MUNICIPALITIES, EXCLUSION_REASON
from .errors import ArtifactValidationError
from .generate import feature_document, index_document
from .geometry import GeometryAudit, convert_polygon, signed_area
from .manifest import SourceFile, canonical_manifest_bytes, build_source_manifest
from .source import read_source_catalog, enforce_national_source_counts, iter_source_polygons


@dataclass(frozen=True)
class ValidationResult:
    status: str
    source_manifest_sha256: str
    artifact_sha256: str
    counts: dict
    api_bytes: int
    pages_artifact_bytes: int
    index_bytes: int
    geojson_sizes: tuple
    gzip9_bytes: int


def require(condition, message):
    if not condition:
        raise ArtifactValidationError(message)


def strict_json(path):
    def invalid(value):
        raise ArtifactValidationError(f"non-JSON value: {value}")

    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, "duplicate JSON key")
            result[k] = v
        return result

    try:
        raw = path.read_bytes()
        require(not raw.startswith(b"\xef\xbb\xbf"), f"BOM: {path.name}")
        text = raw.decode("utf-8", errors="strict")
        require(not re.search(r"[A-Za-z]:\\|/Users/|/home/|gh[pousr]_[A-Za-z0-9]{20,}", text),
                f"private path/token-like content: {path.name}")
        return json.loads(text, parse_constant=invalid, object_pairs_hook=pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"unreadable UTF-8 JSON: {path.name}") from exc


def inspect_geometry(geometry, code):
    require(set(geometry) == {"type", "coordinates"}, f"{code}: geometry schema")
    kind, coordinates = geometry["type"], geometry["coordinates"]
    require(kind in ("Polygon", "MultiPolygon"), f"{code}: polygon type")
    polygons = [coordinates] if kind == "Polygon" else coordinates
    require(isinstance(polygons, list) and polygons, f"{code}: empty geometry")
    require(kind != "MultiPolygon" or len(polygons) > 1, f"{code}: multipart identity")
    rings = positions = holes = 0
    for polygon in polygons:
        require(isinstance(polygon, list) and polygon, f"{code}: empty polygon")
        holes += len(polygon)-1
        for i, ring in enumerate(polygon):
            require(isinstance(ring, list) and len(ring) >= 4 and ring[0] == ring[-1], f"{code}: ring closure")
            for p in ring:
                require(isinstance(p, list) and len(p) == 2 and all(type(v) in (float, int) and math.isfinite(v) for v in p),
                        f"{code}: position type")
                require(-180 <= p[0] <= 180 and -90 <= p[1] <= 90, f"{code}: lon/lat bounds")
            area = signed_area(ring)
            require(area > 0 if i == 0 else area < 0, f"{code}: winding")
            rings += 1
            positions += len(ring)
    geom = shape(geometry)
    require(geom.is_valid and not geom.is_empty, f"{code}: invalid geometry: {explain_validity(geom)}")
    return GeometryAudit(len(polygons), rings, positions, holes)


def _manifest(doc):
    require(set(doc) == {"schemaVersion", "sha256", "files"} and doc["schemaVersion"] == 1, "manifest schema")
    files = doc["files"]
    require([f["path"] for f in files] == list(SOURCE_COMPONENTS), "manifest paths")
    for f in files:
        require(set(f) == {"path", "bytes", "sha256"} and type(f["bytes"]) is int and f["bytes"] > 0
                and re.fullmatch("[0-9a-f]{64}", f["sha256"]), "manifest entry")
    entries = tuple(SourceFile(f["path"], f["bytes"], f["sha256"]) for f in files)
    require(hashlib.sha256(canonical_manifest_bytes(entries)).hexdigest() == doc["sha256"], "manifest digest")
    return entries


def _inspect(root):
    index = strict_json(root / "2026/index.json")
    manifest = strict_json(root / "source-manifest.json")
    _manifest(manifest)
    require(set(index) == {"schemaVersion", "dataset", "municipalities"} and index["schemaVersion"] == 1, "index schema")
    dataset, rows = index["dataset"], index["municipalities"]
    exclusions = dataset["excludedMunicipalities"]
    require(isinstance(exclusions, list), "exclusion list schema")
    excluded_codes = set()
    for entry in exclusions:
        require(set(entry) == {"code", "name", "reason"} and entry["code"] not in excluded_codes
                and entry["code"] in EXCLUDED_MUNICIPALITIES
                and entry["name"] == EXCLUDED_MUNICIPALITIES[entry["code"]]
                and entry["reason"] == EXCLUSION_REASON, "unapproved or incorrect exclusion")
        excluded_codes.add(entry["code"])
    require(dataset["sourceRecordCount"] == len(rows) + len(exclusions), "source/published count accounting")
    stamp = datetime.fromisoformat(dataset["generatedAt"].replace("Z", "+00:00"))
    require(stamp.tzinfo is not None, "timestamp timezone")
    require(dataset["sourceManifestSha256"] == manifest["sha256"], "manifest/index mismatch")
    require(dataset["recordCount"] == len(rows) and dataset["sourceManifestFileCount"] == 12,
            "index record/manifest count")
    require(dataset["referenceDate"] == "2026-01-01" and dataset["sourceDbfExportDate"] == "2026-02-18"
            and dataset["license"]["url"] == LICENSE_URL, "index provenance")
    by_code = {}
    for row in rows:
        require(set(row) == {"name", "code", "region", "territorialUnit"}, "index entry schema")
        code = row["code"]
        require(isinstance(code, str) and re.fullmatch("[0-9]{6}", code) and code not in by_code, "duplicate/invalid index code")
        require(code not in EXCLUDED_MUNICIPALITIES, f"{code}: excluded code advertised as available")
        require(isinstance(row["name"], str) and row["name"], f"{code}: blank name")
        for key, width in (("region", 2), ("territorialUnit", 3)):
            entry = row[key]
            require(set(entry) == {"name", "code"} and isinstance(entry["name"], str) and entry["name"]
                    and re.fullmatch(f"[0-9]{{{width}}}", entry["code"]), f"{code}: administrative label")
        by_code[code] = row
    expected = {"source-manifest.json", "2026/index.json"} | {f"2026/comuni/{c}.geojson" for c in by_code}
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    require(all(not p.is_symlink() for p in root.rglob("*")), "symlink in artifact")
    require({p.relative_to(root).as_posix() for p in paths} == expected, "artifact file coverage")
    counts = {"municipalities": len(rows), "indexEntries": len(rows), "municipalityFiles": len(rows),
              "rings": 0, "positions": 0, "shapePartsOverOneRecords": 0,
              "multipartRecords": 0, "holeRecords": 0, "interiorRings": 0}
    audits, sizes = {}, []
    for code, row in by_code.items():
        p = root / f"2026/comuni/{code}.geojson"
        doc = strict_json(p)
        require(set(doc) == {"type", "metadata", "features"} and doc["type"] == "FeatureCollection"
                and len(doc["features"]) == 1, f"{code}: feature collection schema")
        feature, meta = doc["features"][0], doc["metadata"]
        require(set(feature) == {"type", "id", "properties", "geometry"}
                and feature["type"] == "Feature" and feature["id"] == meta["code"] == code, f"{code}: feature identity")
        props = feature["properties"]
        require(set(props) == {"code", "name", "alternativeName", "regionCode", "regionName", "territorialUnitCode", "territorialUnitName"},
                f"{code}: property schema")
        require(props["code"] == code and props["name"] == row["name"] and
                props["regionCode"] == row["region"]["code"] and props["regionName"] == row["region"]["name"] and
                props["territorialUnitCode"] == row["territorialUnit"]["code"] and
                props["territorialUnitName"] == row["territorialUnit"]["name"], f"{code}: index/feature mismatch")
        require(props["alternativeName"] is None or isinstance(props["alternativeName"], str), f"{code}: alternative name")
        require(meta["sourceManifestSha256"] == manifest["sha256"] and meta["license"] == LICENSE_URL
                and meta["referenceDate"] == "2026-01-01" and meta["attribution"] and meta["modifications"], f"{code}: provenance")
        audit = inspect_geometry(feature["geometry"], code)
        audits[code] = audit
        counts["rings"] += audit.ring_count
        counts["positions"] += audit.position_count
        counts["shapePartsOverOneRecords"] += audit.ring_count > 1
        counts["multipartRecords"] += audit.component_count > 1
        counts["holeRecords"] += audit.hole_count > 0
        counts["interiorRings"] += audit.hole_count
        sizes.append((code, p.stat().st_size))
    artifact_hash = hashlib.sha256()
    total = api_bytes = gzip_bytes = 0
    for p in paths:
        raw, relative = p.read_bytes(), p.relative_to(root).as_posix()
        total += len(raw)
        api_bytes += len(raw) if relative.startswith("2026/") else 0
        gzip_bytes += len(gzip.compress(raw, compresslevel=9, mtime=0))
        artifact_hash.update(f"{relative}\t{len(raw)}\t{hashlib.sha256(raw).hexdigest()}\n".encode())
    result = ValidationResult("passed", manifest["sha256"], artifact_hash.hexdigest(), counts,
                              api_bytes, total, (root / "2026/index.json").stat().st_size, tuple(sizes), gzip_bytes)
    return result, index, manifest, audits


def _checked_inspect(root):
    try:
        return _inspect(root)
    except (KeyError, TypeError, IndexError) as exc:
        raise ArtifactValidationError("malformed artifact schema") from exc


def _canonical_geometry(geometry):
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    def ring(r):
        return tuple(tuple(p) for p in r)
    return tuple(sorted((ring(p[0]), tuple(sorted(ring(h) for h in p[1:]))) for p in polygons))


def validate_correspondence(source_root: Path, artifact_root: Path) -> ValidationResult:
    catalog = read_source_catalog(source_root)
    result, index, manifest, _ = _checked_inspect(artifact_root)
    require(result.source_manifest_sha256 == catalog.manifest.sha256, "source manifest mismatch")
    require(index == index_document(catalog, index["dataset"]["generatedAt"]), "source/index mismatch")
    by_code = {m.code: m for m in catalog.municipalities}
    transformer = Transformer.from_crs(32632, 4326, always_xy=True)
    seen = set()
    for code, shp in iter_source_polygons(source_root):
        require(code in by_code and code not in seen, "source geometry code coverage")
        seen.add(code)
        if code in EXCLUDED_MUNICIPALITIES:
            require(by_code[code].name == EXCLUDED_MUNICIPALITIES[code], "source exclusion identity mismatch")
            continue
        converted = convert_polygon(shp, transformer, code=code)
        expected = feature_document(by_code[code], converted.as_geojson(), catalog)
        actual = strict_json(artifact_root / f"2026/comuni/{code}.geojson")
        actual_geom = actual["features"][0].pop("geometry")
        expected_geom = expected["features"][0].pop("geometry")
        require(actual == expected, f"{code}: source/feature metadata mismatch")
        require(actual_geom["type"] == expected_geom["type"] and
                _canonical_geometry(actual_geom) == _canonical_geometry(expected_geom), f"{code}: source vertex correspondence")
    require(seen == by_code.keys(), "source geometry coverage")
    require(build_source_manifest(source_root) == catalog.manifest, "source manifest changed during validation")
    return result


def _national(result, index, audits):
    require(result.counts == PUBLISHED_COUNTS, f"published geometry/count baseline mismatch: {result.counts}")
    require(index["dataset"]["sourceRecordCount"] == 7896 and
            {e["code"] for e in index["dataset"]["excludedMunicipalities"]} == EXCLUDED_MUNICIPALITIES.keys(),
            "national source/exclusion count baseline")
    require(audits["113012"].component_count == 69 and audits["001059"].hole_count == 3, "island/hole baseline")
    names = Counter(row["name"] for row in index["municipalities"])
    require({k: v for k, v in names.items() if v > 1} ==
            {"Samone": 2, "Livo": 2, "Peglio": 2, "Castro": 2, "San Teodoro": 2}, "duplicate-name baseline")
    by_code = {r["code"]: r["name"] for r in index["municipalities"]}
    require(by_code["040012"] == "Forlì" and by_code["021004"] == "Appiano sulla strada del vino/Eppan an der Weinstraße", "Unicode baseline")


def validate_source_and_artifact(source_root: Path, artifact_root: Path) -> ValidationResult:
    enforce_national_source_counts(read_source_catalog(source_root))
    result = validate_correspondence(source_root, artifact_root)
    checked, index, _, audits = _checked_inspect(artifact_root)
    require(checked.artifact_sha256 == result.artifact_sha256, "artifact changed during validation")
    _national(result, index, audits)
    return result


def validate_artifact_only(artifact_root: Path) -> ValidationResult:
    result, index, _, audits = _checked_inspect(artifact_root)
    _national(result, index, audits)
    return result
