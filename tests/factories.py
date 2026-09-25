from pathlib import Path
import shapefile
from pyproj import CRS

FIELDS = [
    ("COD_RIP", "N", 10, 0), ("COD_REG", "N", 10, 0),
    ("COD_PROV", "N", 10, 0), ("COD_CM", "N", 10, 0),
    ("COD_UTS", "N", 10, 0), ("PRO_COM", "N", 10, 0),
    ("PRO_COM_T", "C", 6), ("COMUNE", "C", 100), ("COMUNE_A", "C", 100),
    ("CC_UTS", "N", 10, 0), ("Shape_Leng", "F", 19, 11), ("Shape_Area", "F", 19, 11),
]


def clockwise(x=500000, y=5000000, side=100):
    return [(x, y), (x, y+side), (x+side, y+side), (x+side, y), (x, y)]


def polygon(rings):
    parts, points = [], []
    for ring in rings:
        parts.append(len(points))
        points.extend(ring)
    return shapefile.Shape(shapeType=shapefile.POLYGON, points=points, parts=parts)


def make_source(root: Path, *, names=None, codes=None, region_keys=None, uts_keys=None,
                municipal_regions=None, municipal_uts=None, fields=None):
    names = ["Samone", "Forlì"] if names is None else names
    codes = ["001235", "040012"] if codes is None else codes
    region_keys = [1, 8] if region_keys is None else region_keys
    uts_keys = [201, 40] if uts_keys is None else uts_keys
    municipal_regions = [1, 8] if municipal_regions is None else municipal_regions
    municipal_uts = [201, 40] if municipal_uts is None else municipal_uts
    for layer in ("Com", "Reg", "ProvCM"):
        base = root / f"{layer}01012026/{layer}01012026_WGS84"
        base.parent.mkdir(parents=True, exist_ok=True)
        with shapefile.Writer(str(base), shapeType=shapefile.POLYGON, encoding="utf-8") as writer:
            if layer == "Com":
                for field in (FIELDS if fields is None else fields):
                    writer.field(*field)
                for i, (name, code) in enumerate(zip(names, codes)):
                    writer.shape(polygon([clockwise(500000 + i * 1000)]))
                    writer.record(1, municipal_regions[i], 1, 0, municipal_uts[i],
                                  int(code or "0"), code, name, "", 0, 0, 0)
            else:
                key = "COD_REG" if layer == "Reg" else "COD_UTS"
                label = "DEN_REG" if layer == "Reg" else "DEN_UTS"
                writer.field(key, "N", 10, 0)
                writer.field(label, "C", 100)
                keys = region_keys if layer == "Reg" else uts_keys
                labels = ["Piemonte", "Emilia-Romagna"] if layer == "Reg" else ["Torino", "Forlì-Cesena"]
                for k, name in zip(keys, labels):
                    writer.null()
                    writer.record(k, name)
        dbf = base.with_suffix(".dbf")
        raw = bytearray(dbf.read_bytes())
        raw[1:4] = bytes([126, 2, 18])
        dbf.write_bytes(raw)
        base.with_suffix(".prj").write_text(CRS.from_epsg(32632).to_wkt(), encoding="utf-8")
    return root
