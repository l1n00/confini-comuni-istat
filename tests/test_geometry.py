import importlib
import math
import pytest
from pyproj import Transformer
from shapely.geometry import shape as geo_shape
from .factories import polygon, clockwise

IDENTITY = Transformer.from_crs(4326, 4326, always_xy=True)


def api():
    return importlib.import_module("istat_confini.geometry")


def test_polygon_keeps_every_coordinate_reverses_only_winding():
    ring = clockwise(0, 0, 10)
    result = api().convert_polygon(polygon([ring]), IDENTITY, code="001235")
    assert result.geometry_type == "Polygon"
    assert result.coordinates == (tuple(reversed(ring)),)
    assert result.audit == api().GeometryAudit(1, 1, 5, 0)
    assert api().signed_area(result.coordinates[0]) > 0


def test_multipart_holes_group_correctly_even_when_input_interleaved():
    outer1, outer2 = clockwise(0, 0, 10), clockwise(20, 0, 10)
    hole1, hole2 = list(reversed(clockwise(2, 2, 2))), list(reversed(clockwise(22, 2, 2)))
    result = api().convert_polygon(polygon([hole2, outer1, hole1, outer2]), IDENTITY, code="113012")
    assert result.geometry_type == "MultiPolygon"
    assert result.audit == api().GeometryAudit(2, 4, 20, 2)
    assert result.coordinates == ((tuple(reversed(outer1)), tuple(reversed(hole1))),
                                  (tuple(reversed(outer2)), tuple(reversed(hole2))))
    assert geo_shape(result.as_geojson()).is_valid


def test_projection_has_known_longitude_and_preserves_vertices():
    ring = clockwise(500000, 0, 100)
    result = api().convert_polygon(polygon([ring]), Transformer.from_crs(32632, 4326, always_xy=True), code="058091")
    assert result.coordinates[0][0] == pytest.approx((9.0, 0.0))
    assert result.audit.position_count == len(ring)
    assert geo_shape(result.as_geojson()).is_valid


@pytest.mark.parametrize("rings", [
    [],
    [clockwise(0, 0, 10)[:-1]],
    [[(0, 0), (1, 1), (0, 0)]],
    [[(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)]],
    [clockwise(0, 0, 10), list(reversed(clockwise(20, 20, 2)))],
    [clockwise(0, 0, 10), clockwise(1, 1, 10), list(reversed(clockwise(3, 3, 2)))],
    [clockwise(0, 0, 10), list(reversed(clockwise(0, 0, 2)))],
    [[(0, 0), (0, 10), (math.inf, 10), (10, 0), (0, 0)]],
    [clockwise(180, 0, 10)],
    [clockwise(0, 90, 10)],
])
def test_invalid_geometry_fails_without_repair_and_names_code(rings):
    with pytest.raises(ValueError, match="001235"):
        api().convert_polygon(polygon(rings), IDENTITY, code="001235")


def test_outward_bbox_uses_six_decimals_without_losing_vertices():
    result = api().convert_polygon(polygon([clockwise(0.12345649, 0.12345651, 2)]), IDENTITY, code="001235")
    exact = api().geometry_bbox(result)
    outward = api().outward_bbox(result, decimals=6)
    assert exact == [0.12345649, 0.12345651, 2.12345649, 2.12345651]
    assert outward == [0.123456, 0.123456, 2.123457, 2.123457]
    assert all(outward[0] <= value <= outward[2] for ring in result.coordinates for value in [ring[0][0]])
    assert all(outward[1] <= value <= outward[3] for ring in result.coordinates for value in [ring[0][1]])


def test_outward_bbox_never_rounds_inside():
    result = api().convert_polygon(polygon([clockwise(9.0000001, 45.0000009, .5)]), IDENTITY, code="001235")
    exact = api().geometry_bbox(result)
    outward = api().outward_bbox(result, decimals=6)
    assert outward[0] <= exact[0] and outward[1] <= exact[1]
    assert outward[2] >= exact[2] and outward[3] >= exact[3]


def test_bbox_covers_multipolygon_and_distant_island():
    outer1, outer2 = clockwise(0, 0, 2), clockwise(20, 0, 2)
    result = api().convert_polygon(polygon([outer1, outer2]), IDENTITY, code="113012")
    assert api().geometry_bbox(result) == [0.0, 0.0, 22.0, 2.0]


def test_bbox_rejects_non_finite_or_out_of_range_values():
    converted = api().convert_polygon(polygon([clockwise(0, 0, 2)]), IDENTITY, code="001235")
    for bad in ([float("nan"), 0.0, 2.0, 2.0], [0.0, -91.0, 2.0, 2.0],
                [3.0, 0.0, 2.0, 2.0], [0.0, 2.0, 2.0, 1.0]):
        with pytest.raises(ValueError):
            api().validate_bbox(bad, code="001235")


def test_projected_large_values_keep_small_ring_orientation():
    ring = clockwise(1000000, 5000000, .01)
    assert api().signed_area(ring) < 0
