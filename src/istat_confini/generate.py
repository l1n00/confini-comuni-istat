from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import tempfile
import time

from pyproj import Transformer

from .config import SOURCE_PAGE, ARCHIVE_URL, LICENSE_URL, ATTRIBUTION, MODIFICATIONS
from .config import EXCLUDED_MUNICIPALITIES, exclusion_metadata
from .errors import SourceValidationError
from .geometry import convert_polygon, geometry_bbox
from .manifest import SourceManifest, build_source_manifest, write_source_manifest, write_utf8_json
from .source import load_source_catalog, iter_source_polygons


@dataclass(frozen=True)
class GenerationResult:
    output_root: Path
    manifest: SourceManifest
    generated_at: datetime
    build_seconds: float


def assert_disjoint(first: Path, second: Path):
    a, b = first.resolve(), second.resolve()
    if a.is_relative_to(b) or b.is_relative_to(a):
        raise ValueError("source/output/report paths must not overlap")


def index_entry(m, bbox):
    return {"name": m.name, "code": m.code,
            "region": {"code": m.region_code, "name": m.region_name},
            "territorialUnit": {"code": m.territorial_unit_code, "name": m.territorial_unit_name},
            "bbox": bbox}


def index_document(catalog, stamp, bboxes):
    included = [m for m in catalog.municipalities if m.code not in EXCLUDED_MUNICIPALITIES]
    return {"schemaVersion": 1, "dataset": {
        "referenceYear": 2026, "referenceDate": "2026-01-01",
        "sourceDbfExportDate": catalog.source_dbf_export_date.isoformat(),
        "recordCount": len(included), "sourceRecordCount": len(catalog.municipalities),
        "excludedMunicipalities": exclusion_metadata(catalog.municipalities),
        "sourceVariant": "non-generalized extracted shapefiles", "sourcePage": SOURCE_PAGE,
        "upstreamArchiveUrl": ARCHIVE_URL, "sourceManifestFile": "source-manifest.json",
        "sourceManifestFileCount": 12, "sourceManifestSha256": catalog.manifest.sha256,
        "generatedAt": stamp,
        "license": {"name": "Creative Commons Attribution 4.0 International", "url": LICENSE_URL},
        "attribution": ATTRIBUTION, "modifications": MODIFICATIONS,
    }, "municipalities": [index_entry(m, bboxes[m.code]) for m in included]}


def feature_document(m, geometry, catalog):
    return {"type": "FeatureCollection", "metadata": {
        "code": m.code, "referenceDate": "2026-01-01",
        "sourceDbfExportDate": catalog.source_dbf_export_date.isoformat(),
        "upstreamArchiveUrl": ARCHIVE_URL, "sourceManifestSha256": catalog.manifest.sha256,
        "license": LICENSE_URL, "attribution": ATTRIBUTION, "modifications": MODIFICATIONS,
    }, "features": [{"type": "Feature", "id": m.code, "properties": {
        "code": m.code, "name": m.name, "alternativeName": m.alternative_name,
        "regionCode": m.region_code, "regionName": m.region_name,
        "territorialUnitCode": m.territorial_unit_code, "territorialUnitName": m.territorial_unit_name,
    }, "geometry": geometry}]}


def generate_dataset(source_root: Path, output_root: Path, generated_at: datetime) -> GenerationResult:
    started = time.perf_counter()
    assert_disjoint(source_root, output_root)
    if output_root.exists():
        raise FileExistsError("output already exists; refusing replacement")
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at requires a timezone")
    stamp = generated_at.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    catalog = load_source_catalog(source_root)
    by_code = {m.code: m for m in catalog.municipalities}
    transformer = Transformer.from_crs(32632, 4326, always_xy=True)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".generation-", dir=output_root.parent))
    try:
        target = staging / "2026/comuni"
        target.mkdir(parents=True)
        seen, bboxes = set(), {}
        for code, shp in iter_source_polygons(source_root):
            if code not in by_code or code in seen:
                raise SourceValidationError(f"geometry identity mismatch: {code}")
            seen.add(code)
            if code in EXCLUDED_MUNICIPALITIES:
                if by_code[code].name != EXCLUDED_MUNICIPALITIES[code]:
                    raise SourceValidationError(f"excluded municipality identity changed: {code}")
                continue
            converted = convert_polygon(shp, transformer, code=code)
            bboxes[code] = geometry_bbox(converted)
            write_utf8_json(target / f"{code}.geojson", feature_document(by_code[code], converted.as_geojson(), catalog))
        if seen != by_code.keys():
            raise SourceValidationError("missing source geometries")
        write_utf8_json(staging / "2026/index.json", index_document(catalog, stamp, bboxes))
        write_source_manifest(staging / "source-manifest.json", catalog.manifest)
        for path in staging.rglob("*"):
            if path.is_file():
                json.loads(path.read_text(encoding="utf-8"))
        if build_source_manifest(source_root) != catalog.manifest:
            raise SourceValidationError("source changed during generation")
        # rename refuses a populated existing destination; never remove user output.
        if output_root.exists():
            raise FileExistsError("output appeared during generation")
        staging.rename(output_root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return GenerationResult(output_root, catalog.manifest, generated_at, time.perf_counter()-started)
