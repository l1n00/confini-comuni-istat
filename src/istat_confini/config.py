LAYERS = ("Com", "ProvCM", "Reg")
SOURCE_COMPONENTS = tuple(sorted(
    f"{layer}01012026/{layer}01012026_WGS84.{ext}"
    for layer in LAYERS for ext in ("dbf", "prj", "shp", "shx")
))
SOURCE_PAGE = "https://www.istat.it/notizia/confini-delle-unita-amministrative-a-fini-statistici-al-1-gennaio-2018-2"
ARCHIVE_URL = "https://www.istat.it/storage/cartografia/confini_amministrativi/non_generalizzati/2026/Limiti01012026.zip"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
ATTRIBUTION = "Istat, Confini delle unità amministrative a fini statistici al 1° gennaio 2026, versione non generalizzata."
MODIFICATIONS = [
    "Converted from WGS 84 / UTM zone 32N (EPSG:32632) to RFC 7946 WGS 84 geographic coordinates.",
    "Converted from shapefile to per-municipality GeoJSON without geometry simplification.",
]
EXPECTED_COUNTS = {
    "municipalities": 7896, "indexEntries": 7896, "municipalityFiles": 7896,
    "rings": 8872, "positions": 6968899, "shapePartsOverOneRecords": 490,
    "multipartRecords": 438, "holeRecords": 71, "interiorRings": 121,
}
EXCLUDED_MUNICIPALITIES = {
    "072001": "Acquaviva delle Fonti",
    "072037": "Rutigliano",
    "072040": "Sannicandro di Bari",
    "081019": "Santa Ninfa",
    "087009": "Bronte",
}
EXCLUSION_REASON = "Invalid source geometry: ring self-intersection; omitted without repair."
# Measured from the exact source, including all rings (not only invalid rings).
EXCLUDED_GEOMETRY_COUNTS = {
    "rings": 14, "positions": 11714, "shapePartsOverOneRecords": 3,
    "multipartRecords": 2, "holeRecords": 2, "interiorRings": 2,
}
PUBLISHED_COUNTS = {
    key: value - (5 if key in ("municipalities", "indexEntries", "municipalityFiles")
                  else EXCLUDED_GEOMETRY_COUNTS[key])
    for key, value in EXPECTED_COUNTS.items()
}


def exclusion_metadata(municipalities):
    return [{"code": m.code, "name": m.name, "reason": EXCLUSION_REASON}
            for m in municipalities if m.code in EXCLUDED_MUNICIPALITIES]


def layer_path(root, layer, extension):
    return root / f"{layer}01012026/{layer}01012026_WGS84.{extension}"
