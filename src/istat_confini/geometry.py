"""Convert raw rings without dropping, inserting, rounding or repairing vertices."""
from dataclasses import dataclass
import math

from pyproj.exceptions import ProjError
from shapely.geometry import Polygon, MultiPolygon
from shapely.validation import explain_validity

from .errors import GeometryValidationError


@dataclass(frozen=True)
class GeometryAudit:
    component_count: int
    ring_count: int
    position_count: int
    hole_count: int


@dataclass(frozen=True)
class ConvertedGeometry:
    geometry_type: str
    coordinates: tuple
    audit: GeometryAudit

    def as_geojson(self):
        return {"type": self.geometry_type, "coordinates": self.coordinates}


def signed_area(ring):
    # Translation avoids catastrophic cancellation at large projected eastings.
    x0, y0 = ring[0]
    return math.fsum((a[0]-x0)*(b[1]-y0) - (b[0]-x0)*(a[1]-y0)
                     for a, b in zip(ring, ring[1:])) / 2


def _valid(geom, code, stage):
    if geom.is_empty or not geom.is_valid:
        raise GeometryValidationError(f"{code}: {stage}: {explain_validity(geom)}")


def validate_bbox(bbox, *, code):
    if (not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or
            any(type(value) not in (int, float) for value in bbox)):
        raise GeometryValidationError(f"{code}: bbox must contain four numeric values")
    min_lon, min_lat, max_lon, max_lat = bbox
    if not all(math.isfinite(value) for value in bbox):
        raise GeometryValidationError(f"{code}: non-finite bbox")
    if not (-180 <= min_lon <= max_lon <= 180 and -90 <= min_lat <= max_lat <= 90):
        raise GeometryValidationError(f"{code}: bbox outside longitude/latitude bounds or incorrectly ordered")
    return [min_lon, min_lat, max_lon, max_lat]


def geometry_bbox(converted):
    coordinates = converted.coordinates
    rings = (coordinates if converted.geometry_type == "Polygon"
             else tuple(ring for polygon in coordinates for ring in polygon))
    points = (point for ring in rings for point in ring)
    first_x, first_y = next(points)
    min_lon = max_lon = first_x
    min_lat = max_lat = first_y
    for lon, lat in points:
        min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
        min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
    return validate_bbox([min_lon, min_lat, max_lon, max_lat], code="geometry")


def outward_bbox(converted, decimals=6):
    if type(decimals) is not int or not 0 <= decimals <= 15:
        raise GeometryValidationError("bbox decimals must be an integer between 0 and 15")
    scale = 10 ** decimals
    min_lon, min_lat, max_lon, max_lat = geometry_bbox(converted)
    rounded = [math.floor(min_lon*scale)/scale, math.floor(min_lat*scale)/scale,
               math.ceil(max_lon*scale)/scale, math.ceil(max_lat*scale)/scale]
    require_contains = (rounded[0] <= min_lon and rounded[1] <= min_lat and
                        rounded[2] >= max_lon and rounded[3] >= max_lat)
    if not require_contains:
        raise GeometryValidationError("outward bbox rounded inside geometry")
    return validate_bbox(rounded, code="geometry")


def convert_polygon(shape, transformer, *, code):
    def fail(reason):
        raise GeometryValidationError(f"{code}: {reason}")

    offsets = list(shape.parts) + [len(shape.points)]
    if len(offsets) < 2 or offsets[0] != 0 or any(b <= a for a, b in zip(offsets, offsets[1:])):
        fail("empty or malformed polygon parts")
    rings, shells, holes = [], [], []
    for start, end in zip(offsets, offsets[1:]):
        ring = tuple(tuple(p) for p in shape.points[start:end])
        if len(ring) < 4 or ring[0] != ring[-1]:
            fail("unclosed or short ring")
        if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in ring):
            fail("non-finite or non-2D position")
        area = signed_area(ring)
        if area == 0:
            fail("zero-area ring")
        _valid(Polygon(ring), code, "source ring")
        index = len(rings)
        rings.append(ring)
        (shells if area < 0 else holes).append(index)
    if not shells:
        fail("no exterior ring")
    shell_geoms = [Polygon(rings[i]) for i in shells]
    groups = [[i] for i in shells]
    for hole in holes:
        hole_geom = Polygon(rings[hole])
        owners = [j for j, shell in enumerate(shell_geoms)
                  if shell.contains(hole_geom) and shell.boundary.disjoint(hole_geom.boundary)]
        if len(owners) != 1:
            fail("hole must belong strictly to exactly one exterior")
        groups[owners[0]].append(hole)
    polygons = [Polygon(rings[g[0]], [rings[h] for h in g[1:]]) for g in groups]
    _valid(polygons[0] if len(polygons) == 1 else MultiPolygon(polygons), code, "source polygon")
    converted = []
    for i, ring in enumerate(rings):
        try:
            xs, ys = transformer.transform([p[0] for p in ring], [p[1] for p in ring], errcheck=True)
        except ProjError as exc:
            fail(f"projection error: {exc}")
        transformed = tuple(zip(xs, ys))
        if any(not math.isfinite(x) or not math.isfinite(y) or not -180 <= x <= 180 or not -90 <= y <= 90
               for x, y in transformed):
            fail("non-finite/out-of-range longitude or latitude")
        area = signed_area(transformed)
        if area == 0:
            fail("zero-area transformed ring")
        if (i in shells) != (area > 0):
            transformed = tuple(reversed(transformed))
        converted.append(transformed)
    coordinates = tuple(tuple(converted[i] for i in group) for group in groups)
    polygons = [Polygon(p[0], p[1:]) for p in coordinates]
    _valid(polygons[0] if len(polygons) == 1 else MultiPolygon(polygons), code, "transformed polygon")
    audit = GeometryAudit(len(shells), len(rings), sum(map(len, rings)), len(holes))
    return ConvertedGeometry("Polygon" if len(shells) == 1 else "MultiPolygon",
                             coordinates[0] if len(shells) == 1 else coordinates, audit)
