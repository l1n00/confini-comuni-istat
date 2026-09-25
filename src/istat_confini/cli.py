import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import tempfile
import time

from .errors import ValidationError
from .generate import assert_disjoint, generate_dataset
from .manifest import write_utf8_json
from .report import build_feasibility_report, write_reports, repository_candidate_bytes, pages_decision
from .validate import validate_source_and_artifact, validate_artifact_only, strict_json, require


def verify_release(project_root):
    report = strict_json(project_root / "reports/validation.json")
    require(report["status"] == "passed", "local validation report not passed")
    result = validate_artifact_only(project_root / "dist")
    require(result.artifact_sha256 == report["artifactSha256"] and
            result.source_manifest_sha256 == report["sourceBeforeSha256"] == report["sourceAfterSha256"] and
            result.counts == report["counts"], "artifact no longer matches full-source verification report")
    require(pages_decision(result.pages_artifact_bytes) != "do-not-publish", "Pages size gate")
    return result, report


def refresh_feasibility_report(project_root, reports_root):
    require(reports_root.resolve() == (project_root / "reports").resolve(), "reports must be project reports directory")
    result, report = verify_release(project_root)
    report["repositoryCandidateBytes"] = repository_candidate_bytes(project_root)
    report["refreshedAt"] = datetime.now(timezone.utc).isoformat()
    write_reports(report, reports_root)


def _build(args):
    source, output, reports = args.source_root.resolve(), args.output_root.resolve(), args.reports_root.resolve()
    assert_disjoint(source, output)
    assert_disjoint(source, reports)
    assert_disjoint(output, reports)
    if output.exists():
        raise FileExistsError("output already exists; choose a new output root")
    started = time.perf_counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=".generation-", dir=output.parent))
    candidate = workspace / "candidate"
    stamp = datetime.now(timezone.utc)
    try:
        generated = generate_dataset(source, candidate, stamp)
        checking = time.perf_counter()
        validation = validate_source_and_artifact(source, candidate)
        report = build_feasibility_report(validation, generated_at=stamp,
                                          build_seconds=generated.build_seconds,
                                          validation_seconds=time.perf_counter()-checking)
        if output.exists():
            raise FileExistsError("output appeared during validation")
        candidate.rename(output)
        report["repositoryCandidateBytes"] = repository_candidate_bytes(output.parent)
        write_reports(report, reports)
        print(f"Validated {validation.counts['municipalityFiles']} municipalities; "
              f"Pages bytes {validation.pages_artifact_bytes:,}; index bytes {validation.index_bytes:,}; "
              f"size decision {report['pagesSizeDecision']}. Not published.")
    except ValidationError as exc:
        reports.mkdir(parents=True, exist_ok=True)
        write_utf8_json(reports / "build-failure.json", {
            "status": "failed", "category": type(exc).__name__, "message": str(exc),
            "elapsedSeconds": time.perf_counter()-started,
        })
        raise
    finally:
        shutil.rmtree(workspace)


def main(argv=None):
    parser = argparse.ArgumentParser(description="ISTAT 2026 full-detail static API generator")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    for flag in ("source-root", "output-root", "reports-root"):
        build.add_argument(f"--{flag}", type=Path, required=True)
    artifact = commands.add_parser("validate-artifact")
    artifact.add_argument("--artifact-root", type=Path, required=True)
    verify = commands.add_parser("verify-release")
    verify.add_argument("--project-root", type=Path, required=True)
    refresh = commands.add_parser("refresh-report")
    refresh.add_argument("--project-root", type=Path, required=True)
    refresh.add_argument("--reports-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            _build(args)
        elif args.command == "validate-artifact":
            result = validate_artifact_only(args.artifact_root)
            print(f"Artifact checks passed: {result.artifact_sha256}; not a source-correspondence check.")
        elif args.command == "verify-release":
            result, _ = verify_release(args.project_root)
            print(f"Artifact matches full-source verification: {result.artifact_sha256}; not publication approval.")
        else:
            refresh_feasibility_report(args.project_root, args.reports_root)
            print("Report totals refreshed; original source-validation identity retained.")
        return 0
    except (ValueError, FileExistsError) as exc:
        print(f"Blocked: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Blocked by filesystem operation: {type(exc).__name__}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Unexpected failure: {type(exc).__name__}; no success claimed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
