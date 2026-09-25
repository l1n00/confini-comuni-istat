import importlib
from pyproj import Transformer
from .factories import polygon, clockwise


def test_diagnostic_distinguishes_raw_ring_failure_from_projection():
    api = importlib.import_module("istat_confini.diagnose")
    bad = polygon([[(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)]])
    good = polygon([clockwise(0, 0, 10)])
    result = api.audit_shapes([("001001", bad), ("001002", good)],
                              {"001001": "Bad", "001002": "Good"},
                              Transformer.from_crs(4326, 4326, always_xy=True))
    assert result["recordsChecked"] == 2
    assert result["validRecords"] == 1
    assert result["failures"][0]["code"] == "001001"
    assert result["failures"][0]["rawInvalidRings"]
    assert result["failures"][0]["pyshpGeometryValid"] is False
    assert result["failures"][0]["name"] == "Bad"
    assert result["failures"][0]["rawGeometryCounts"] == {"rings": 1, "positions": 5, "components": 1, "holes": 0}
