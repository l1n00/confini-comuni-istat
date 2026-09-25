#!/usr/bin/env python3
"""Verify the public static API without changing it or following redirects."""
import argparse
import json
import re
import sys
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

KNOWN_CODES = ("001235", "022165", "113012", "001059", "058091", "040012")
UNKNOWN_CODES = ("999999", "12345")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def urllib_opener(url):
    opener = build_opener(NoRedirect())
    try:
        with opener.open(Request(url, headers={"User-Agent": "istat-confini-verifier/1.0"}), timeout=30) as response:
            return response.read(), response.status, dict(response.headers.items())
    except HTTPError as error:
        return error.read(), error.code, dict(error.headers.items())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _headers(headers):
    return {key.lower(): value for key, value in headers.items()}


def _check_common(url, status, headers, *, expected, json_media):
    require(status == expected, f"{url}: expected HTTP {expected}, got {status}")
    require(status != 302, f"{url}: redirects are not accepted")
    h = _headers(headers)
    require(h.get("access-control-allow-origin") == "*", f"{url}: wildcard CORS missing")
    require(h.get("etag") or h.get("last-modified"), f"{url}: cache validator missing")
    require("immutable" not in h.get("cache-control", "").lower(), f"{url}: /2026 must not be immutable")
    media = h.get("content-type", "").split(";", 1)[0].strip().lower()
    if expected == 404:
        allowed = {"application/json", "text/json", "text/html", "application/octet-stream"}
    else:
        allowed = {"application/json", "text/json", "application/geo+json"} if json_media else {"application/json", "text/json"}
    require(media in allowed, f"{url}: unacceptable media type {media!r}")


def verify(base_url, opener=urllib_opener):
    parsed = urlparse(base_url)
    require(parsed.scheme == "https" and parsed.netloc and parsed.path.strip("/") and
            not parsed.query and not parsed.fragment, "base must be an explicit HTTPS owner/repository Pages URL")
    base = base_url.rstrip("/")
    body, status, headers = opener(f"{base}/2026/index.json")
    _check_common(f"{base}/2026/index.json", status, headers, expected=200, json_media=True)
    require(not re.search(rb"[A-Za-z]:\\|/Users/|/home/|Downloads|gh[pousr]_[A-Za-z0-9]{20,}", body), "index exposes local/private content")
    try:
        index = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("index is not strict UTF-8 JSON") from exc
    rows = index["municipalities"]
    require(index["dataset"]["recordCount"] == len(rows), "index count mismatch")
    for row in rows:
        bbox = row["bbox"]
        require(isinstance(bbox, list) and len(bbox) == 4 and
                all(type(value) in (int, float) and re.fullmatch(r"-?\d+(?:\.\d+)?", str(value))
                    for value in bbox) and
                -180 <= bbox[0] <= bbox[2] <= 180 and -90 <= bbox[1] <= bbox[3] <= 90,
                f"invalid index bbox for {row.get('code')}")
    codes = {row["code"] for row in rows}
    for code in KNOWN_CODES:
        require(code in codes, f"representative code absent from index: {code}")
    for code in KNOWN_CODES:
        url = f"{base}/2026/comuni/{code}.geojson"
        raw, status, headers = opener(url)
        _check_common(url, status, headers, expected=200, json_media=True)
        require(not re.search(rb"[A-Za-z]:\\|/Users/|/home/|Downloads", raw), f"{url}: local/private content")
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{url}: not strict UTF-8 JSON") from exc
        require(doc["type"] == "FeatureCollection" and len(doc["features"]) == 1 and
                doc["features"][0]["id"] == code, f"{url}: representative content mismatch")
    for code in UNKNOWN_CODES:
        url = f"{base}/2026/comuni/{code}.geojson"
        raw, status, headers = opener(url)
        _check_common(url, status, headers, expected=404, json_media=True)
    return {"index": len(rows), "representativeFiles": len(KNOWN_CODES), "unknownFiles": len(UNKNOWN_CODES)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    args = parser.parse_args()
    try:
        result = verify(args.base_url)
    except ValueError as exc:
        print(f"Remote verification blocked: {exc}", file=sys.stderr)
        return 2
    print("Remote verification passed:", json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
