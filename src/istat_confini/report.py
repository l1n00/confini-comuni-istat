from dataclasses import asdict
import math
from pathlib import Path
import statistics

from .manifest import write_utf8_json


def pages_decision(size, *, deployment_timed_out=False):
    if size > 1_000_000_000 or deployment_timed_out:
        return "do-not-publish"
    return "preferred" if size <= 900_000_000 else "conditional-owner-acceptance"


def size_distribution(files):
    sizes = sorted(size for _, size in files)
    return {"count": len(sizes), "minimum": sizes[0], "median": statistics.median(sizes),
            "p95": sizes[math.ceil(.95*len(sizes))-1], "maximum": sizes[-1],
            "largest20": [{"code": c, "bytes": s} for c, s in sorted(files, key=lambda p: (-p[1], p[0]))[:20]]}


def build_feasibility_report(validation, *, generated_at, build_seconds, validation_seconds):
    report = {
        "status": "passed", "generatedAt": generated_at.isoformat(),
        "sourceBeforeSha256": validation.source_manifest_sha256,
        "sourceAfterSha256": validation.source_manifest_sha256,
        "artifactSha256": validation.artifact_sha256,
        "counts": validation.counts, "apiBytes": validation.api_bytes,
        "pagesArtifactBytes": validation.pages_artifact_bytes, "indexBytes": validation.index_bytes,
        "geojson": size_distribution(validation.geojson_sizes),
        "gzip9Bytes": validation.gzip9_bytes,
        "compressionMethod": "sum of per-file gzip-9 sizes; estimate, not a served encoding or archive",
        "softBandwidthBytes": 100_000_000_000,
        "fullDatasetDownloadsRaw": 100_000_000_000 // validation.pages_artifact_bytes,
        "fullDatasetDownloadsGzipEstimate": 100_000_000_000 // validation.gzip9_bytes,
        "buildSeconds": build_seconds, "validationSeconds": validation_seconds,
        "totalSeconds": build_seconds + validation_seconds,
        "pagesSizeDecision": pages_decision(validation.pages_artifact_bytes),
        "publicationApproved": False,
        "pending": ["owner/repository decision", "license and platform terms recheck", "traffic estimate",
                    "explicit publication approval", "deployment and remote HTTP checks"],
    }
    return report


def repository_candidate_bytes(root: Path):
    # Fixed allowlist avoids traversing environments, source data, caches or secrets.
    paths = [root / p for p in ("README.md", "NOTICE.md", "requirements.txt", "pyproject.toml", ".gitignore")]
    for folder in ("src", "tests", "scripts", "docs", ".github", "dist"):
        paths.extend(p for p in (root / folder).rglob("*") if p.is_file() and
                     "__pycache__" not in p.parts and p.suffix != ".pyc")
    return sum(p.stat().st_size for p in paths if p.is_file())


def write_reports(report, reports_root):
    reports_root.mkdir(parents=True, exist_ok=True)
    write_utf8_json(reports_root / "validation.json", report)
    lines = ["# Local validation and hosting feasibility", "",
             "Not published. Size eligibility is not publication approval.", "",
             f"- Full source validation: {report['status']}",
             f"- Source manifest SHA-256: `{report['sourceBeforeSha256']}`",
             f"- Artifact SHA-256: `{report['artifactSha256']}`",
             f"- Municipal files: {report['counts']['municipalityFiles']}",
             f"- Index bytes: {report['indexBytes']:,}",
             f"- API bytes: {report['apiBytes']:,}",
             f"- Pages artifact bytes: {report['pagesArtifactBytes']:,}",
             f"- Repository candidate bytes (excluding reports): {report.get('repositoryCandidateBytes', 0):,}",
             f"- Gzip-9 estimate: {report['gzip9Bytes']:,} bytes ({report['compressionMethod']})",
             f"- Full dataset downloads per soft 100 GB: {report['fullDatasetDownloadsRaw']} raw; {report['fullDatasetDownloadsGzipEstimate']} estimated gzip",
             f"- Build / validation seconds: {report['buildSeconds']:.2f} / {report['validationSeconds']:.2f}",
             f"- Pages size decision: {report['pagesSizeDecision']}", "",
             "## Per-municipality bytes", "",
             f"Min / median / p95 / max: {report['geojson']['minimum']} / {report['geojson']['median']} / {report['geojson']['p95']} / {report['geojson']['maximum']}",
             "", "| Code | Bytes |", "|---|---:|"]
    lines += [f"| {row['code']} | {row['bytes']} |" for row in report["geojson"]["largest20"]]
    lines += ["", "## Pending publication gates", ""] + [f"- {s}" for s in report["pending"]]
    (reports_root / "feasibility.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
