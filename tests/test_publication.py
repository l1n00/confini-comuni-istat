import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/pages.yml"
SCRIPT = ROOT / "scripts/verify_published_api.py"


def load_script():
    spec = importlib.util.spec_from_file_location("verify_published_api", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow():
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_has_only_manual_confirmation_gated_source_free_path():
    text = workflow()
    assert "workflow_dispatch:" in text
    assert "I_APPROVED_PUBLICATION" in text
    assert "\n  push:" not in text
    assert "Downloads" not in text
    assert "istat_confini.cli build" not in text
    assert "path: dist" in text
    assert "  group: pages\n  cancel-in-progress: false" in text
    assert "cancel_in_progress" not in text
    assert "verify-release --project-root ." in text
    assert "upload-pages-artifact" in text


def test_verifier_accepts_complete_mocked_server():
    module = load_script()
    index = {"schemaVersion": 2, "dataset": {"recordCount": 6, "bboxPrecisionDecimals": 6,
                "bboxOrder": ["minLon", "minLat", "maxLon", "maxLat"]},
             "municipalities": [{"code": code, "bbox": [9.0, 45.0, 10.0, 46.0]} for code in
               ("001235", "022165", "113012", "001059", "058091", "040012")]}
    responses = {"https://owner.github.io/repo/2026/index.json":
                 (200, "application/json; charset=utf-8", json.dumps(index).encode())}
    for code in ("001235", "022165", "113012", "001059", "058091", "040012"):
        doc = {"type": "FeatureCollection", "features": [{"id": code}]}
        responses[f"https://owner.github.io/repo/2026/comuni/{code}.geojson"] = (
            200, "application/geo+json", json.dumps(doc).encode())
    responses["https://owner.github.io/repo/2026/comuni/999999.geojson"] = (404, "text/html", b"not found")
    responses["https://owner.github.io/repo/2026/comuni/12345.geojson"] = (404, "text/html", b"not found")
    def opener(url):
        status, content_type, body = responses[url]
        return body, status, {"Content-Type": content_type, "Access-Control-Allow-Origin": "*",
                               "ETag": '"test"', "Cache-Control": "public, max-age=300"}
    result = module.verify("https://owner.github.io/repo", opener)
    assert result == {"index": 6, "representativeFiles": 6, "unknownFiles": 2}


@pytest.mark.parametrize("mutation", ["http", "status", "media", "cors", "validator", "immutable", "body", "redirect", "bbox"])
def test_verifier_rejects_each_publication_failure(mutation):
    module = load_script()
    index = {"schemaVersion": 2, "dataset": {"recordCount": 1, "bboxPrecisionDecimals": 6,
                "bboxOrder": ["minLon", "minLat", "maxLon", "maxLat"]},
             "municipalities": [{"code": "001235", "bbox": [9.0, 45.0, 10.0, 46.0]}]}
    if mutation == "bbox":
        index["municipalities"][0]["bbox"] = [10.0, 46.0, 9.0, 45.0]
        index_body = json.dumps(index).encode()
    status, kind, body = 200, "application/geo+json", b'{"type":"FeatureCollection"}'
    headers = {"Content-Type": kind, "Access-Control-Allow-Origin": "*", "ETag": '"test"'}
    if mutation == "http": index_body = b"x"
    else: index_body = json.dumps(index).encode()
    if mutation == "status": status = 500
    if mutation == "media": headers["Content-Type"] = "application/octet-stream"
    if mutation == "cors": headers["Access-Control-Allow-Origin"] = "https://evil.example"
    if mutation == "validator": headers.pop("ETag")
    if mutation == "immutable": headers["Cache-Control"] = "public, max-age=31536000, immutable"
    if mutation == "body": body = b"C:\\Users\\private"
    def opener(url):
        if url.endswith("index.json"):
            return index_body, 200, {**headers, "Content-Type": "application/json"}
        if "999999" in url or "12345" in url:
            return b"{}", 404, {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*",
                                "ETag": '"missing"', "Cache-Control": "public, max-age=300"}
        if mutation == "redirect":
            return b"", 302, {"Location": "https://owner.github.io/repo/2026/comuni/001235.geojson"}
        return body, status, headers
    with pytest.raises(ValueError):
        module.verify("http://owner.github.io/repo" if mutation == "http" else
                      "https://owner.github.io/repo", opener)
