import hashlib
import importlib
import json
import pytest


def api():
    return importlib.import_module("istat_confini.manifest")


def tree(root):
    for layer in ("Com", "ProvCM", "Reg"):
        for ext in ("dbf", "prj", "shp", "shx"):
            p = root / f"{layer}01012026/{layer}01012026_WGS84.{ext}"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(f"{layer}-{ext}-Forlì".encode())


def test_manifest_exact_canonical_bytes_and_unicode(tmp_path):
    tree(tmp_path)
    m = api().build_source_manifest(tmp_path)
    assert len(m.files) == 12
    assert [f.relative_path for f in m.files] == sorted(f.relative_path for f in m.files)
    expected = b""
    for f in m.files:
        raw = (tmp_path / f.relative_path).read_bytes()
        expected += f"{f.relative_path}\t{len(raw)}\t{hashlib.sha256(raw).hexdigest()}\n".encode()
    assert api().canonical_manifest_bytes(m.files) == expected
    assert m.sha256 == hashlib.sha256(expected).hexdigest()
    out = tmp_path / "manifest.json"
    api().write_source_manifest(out, m)
    doc = json.loads(out.read_bytes())
    assert doc["sha256"] == m.sha256
    assert str(tmp_path) not in out.read_text()


def test_manifest_changes_when_source_changes_and_ignores_unconsumed(tmp_path):
    tree(tmp_path)
    first = api().build_source_manifest(tmp_path)
    (tmp_path / "unrelated.txt").write_bytes(b"ignore")
    assert api().build_source_manifest(tmp_path) == first
    (tmp_path / first.files[0].relative_path).write_bytes(b"changed")
    assert api().build_source_manifest(tmp_path).sha256 != first.sha256


def test_missing_component_fails(tmp_path):
    with pytest.raises(ValueError, match="missing source component"):
        api().build_source_manifest(tmp_path)
