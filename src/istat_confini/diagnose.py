"""Read-only source failure inventory; never creates or repairs boundary output."""
import argparse
from pathlib import Path
import time

from pyproj import Transformer
from shapely.geometry import Polygon, shape
from shapely.validation import explain_validity

from .errors import GeometryValidationError
from .generate import assert_disjoint
from .geometry import convert_polygon, signed_area
from .manifest import build_source_manifest, write_utf8_json
from .source import load_source_catalog, iter_source_polygons


def audit_shapes(shapes, names, transformer):
    failures, checked = [], 0
    for code, shp in shapes:
        checked += 1
        try:
            convert_polygon(shp, transformer, code=code)
        except GeometryValidationError as exc:
            raw_invalid = []
            offsets = list(shp.parts) + [len(shp.points)]
            for index, (start, end) in enumerate(zip(offsets, offsets[1:])):
                ring = shp.points[start:end]
                geom = Polygon(ring)
                if not geom.is_valid:
                    raw_invalid.append({"ringIndex": index, "positions": len(ring),
                                        "reason": explain_validity(geom)})
            independent = shape(shp.__geo_interface__)
            holes = sum(signed_area(shp.points[a:b]) > 0 for a, b in zip(offsets, offsets[1:]))
            failures.append({"code": code, "name": names[code], "conversionFailure": str(exc),
                             "rawInvalidRings": raw_invalid,
                             "rawGeometryCounts": {"rings": len(shp.parts), "positions": len(shp.points),
                                                   "components": len(shp.parts)-holes, "holes": holes},
                             "pyshpGeometryValid": bool(independent.is_valid),
                             "pyshpGeometryReason": explain_validity(independent)})
    return {"recordsChecked": checked, "validRecords": checked-len(failures), "failures": failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    assert_disjoint(args.source_root, args.report)
    if args.report.exists():
        raise FileExistsError("diagnostic report already exists")
    started = time.perf_counter()
    catalog = load_source_catalog(args.source_root)
    report = audit_shapes(iter_source_polygons(args.source_root),
                          {m.code: m.name for m in catalog.municipalities},
                          Transformer.from_crs(32632, 4326, always_xy=True))
    after = build_source_manifest(args.source_root)
    if after != catalog.manifest:
        raise ValueError("source changed during audit")
    report.update({"sourceBeforeSha256": catalog.manifest.sha256, "sourceAfterSha256": after.sha256,
                   "elapsedSeconds": time.perf_counter()-started, "repairsApplied": False})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_utf8_json(args.report, report)
    print(f"Checked {report['recordsChecked']}; valid {report['validRecords']}; failures {len(report['failures'])}; no repairs.")
    for failure in report["failures"]:
        print(f"{failure['code']} {failure['name']}: {failure['conversionFailure']}; raw counts {failure['rawGeometryCounts']}")


if __name__ == "__main__":
    main()
