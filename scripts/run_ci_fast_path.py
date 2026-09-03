"""Run one required CI job under the verified repository change scope."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest

try:
    from classify_ci_change_scope import (
        DOCS_ONLY,
        FULL_SUITE,
        classify_repository_change,
        verify_payload,
        write_payload,
    )
except ModuleNotFoundError:  # Imported as scripts.run_ci_fast_path by unit tests.
    from scripts.classify_ci_change_scope import (
        DOCS_ONLY,
        FULL_SUITE,
        classify_repository_change,
        verify_payload,
        write_payload,
    )


REPO_ROOT = Path(__file__).resolve().parent.parent
PAYLOAD_PATH = REPO_ROOT / "CI_CHANGE_SCOPE.json"
VALID_JOBS = {"markdown", "documentation-links", "unit", "contract", "integration"}
FULL_TEST_ROOTS = {
    "unit": Path("tests/unit"),
    "contract": Path("tests/contract"),
    "integration": Path("tests/integration"),
}
INTEGRATION_TEST_ROOT = Path("tests/integration")
INTEGRATION_SHARD_LIMIT_SECONDS = 1200
INTEGRATION_SHARDS: dict[str, tuple[str, ...]] = {
    "shard-1": (
        "tests/integration/test_m13_r2_full_cpu_backend.py",
    ),
    "shard-2": (
        "tests/integration/test_creator_lifecycle_sqlite_p2.py",
        "tests/integration/test_creator_m12_m13_preview_http.py",
        "tests/integration/test_creator_method_aware_media_m10_m11.py",
        "tests/integration/test_creator_public_http_v1.py",
        "tests/integration/test_creator_script_studio.py",
        "tests/integration/test_creator_series_intelligence.py",
        "tests/integration/test_creator_series_planning.py",
        "tests/integration/test_m12_audio_execution.py",
        "tests/integration/test_m12_audio_technical_validation.py",
        "tests/integration/test_m12_m13_minimal_preview.py",
        "tests/integration/test_m13_e1_timeline_v3_preview.py",
        "tests/integration/test_m13_e4_distance_state_v3.py",
        "tests/integration/test_m13_r1b_render_candidate.py",
        "tests/integration/test_m13_v3_media_conformance.py",
        "tests/integration/test_m9_m12_clone_lineage_bridge.py",
    ),
    "shard-3": (
        "tests/integration/test_ai_director_project_draft_flow.py",
        "tests/integration/test_creator_dynamic_media_preflight_http.py",
        "tests/integration/test_creator_execution_method_planning_m8_m9.py",
        "tests/integration/test_creator_narrative_currentness_m7.py",
        "tests/integration/test_creator_project_context.py",
        "tests/integration/test_creator_series_episode.py",
        "tests/integration/test_creator_series_intelligence_consumer.py",
        "tests/integration/test_m12_dialogue_audio_domain.py",
        "tests/integration/test_m12_isolated_speech_runtime.py",
        "tests/integration/test_m12_programmatic_audio_execution.py",
        "tests/integration/test_m13_e3_currentness.py",
        "tests/integration/test_m13_e3_timeline_v3_preview.py",
        "tests/integration/test_m13_flame_smoke_v3_full_resolution.py",
        "tests/integration/test_m13_glyph_reveal_v2_composition.py",
        "tests/integration/test_m13_masked_surface_v3.py",
        "tests/integration/test_m13_timeline_editing_sqlite.py",
    ),
    "shard-4": (
        "tests/integration/test_creator_canonical_registration_http.py",
        "tests/integration/test_creator_episode_production_k2.py",
        "tests/integration/test_creator_explicit_audio_bridge_m9_m12.py",
        "tests/integration/test_creator_method_aware_cutover_http.py",
        "tests/integration/test_creator_series_intelligence_sqlite_p2.py",
        "tests/integration/test_generic_upstream_method_closure.py",
        "tests/integration/test_m12_voice_profile_lineage_sqlite.py",
        "tests/integration/test_m13_e1_timeline_effect_binding.py",
        "tests/integration/test_m13_e2_deterministic_effects_http.py",
        "tests/integration/test_m13_e2_timeline_v3_preview.py",
        "tests/integration/test_m13_e3_deterministic_overlays_v3.py",
        "tests/integration/test_m13_e4_timeline_v3_preview.py",
        "tests/integration/test_m13_glyph_reveal_composition.py",
        "tests/integration/test_m13_masked_surface_v2_full_resolution.py",
        "tests/integration/test_m13_r1a_composition_render_manifest.py",
        "tests/integration/test_m13_r1b_render_candidate_http.py",
        "tests/integration/test_m13_r1b_render_candidate_v3_security.py",
    ),
}
ALLOWED_INTEGRATION_SKIPS = frozenset(
    {
        "test_m13_r2_full_cpu_backend.M13R2FullCpuBackendIntegrationTests."
        "test_generic_30_second_authenticated_full_render_is_bit_exact",
    }
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_environment(**values: object) -> None:
    destination = os.environ.get("GITHUB_ENV")
    if not destination:
        return
    with Path(destination).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            rendered = str(value)
            if "\n" in rendered or "\r" in rendered:
                raise ValueError(f"environment value {key} must remain single-line")
            handle.write(f"{key}={rendered}\n")


def command_classify(args: argparse.Namespace) -> None:
    started_epoch = int(time.time())
    started_utc = utc_now()
    outcome = classify_repository_change(
        repo_root=REPO_ROOT,
        event_name=args.event_name,
        base_sha=args.base_sha,
        head_sha=args.head_sha,
    )
    write_payload(PAYLOAD_PATH, outcome.payload)
    scope = str(outcome.payload["classification"])
    digest = str(outcome.payload["payloadDigest"])
    append_environment(
        CI_SCOPE=scope,
        CI_SCOPE_PAYLOAD_DIGEST=digest,
        JOB_START_EPOCH=started_epoch,
        JOB_START_UTC=started_utc,
        SETUP_SECONDS=0,
        RUNTIME_INSTALL_SECONDS=0,
        FFMPEG_INSTALL_EXECUTED="false",
    )
    print(f"CI_SCOPE={scope}")
    print(f"CI_SCOPE_REASON={outcome.payload['classificationReason']}")
    print(f"CI_SCOPE_PAYLOAD_DIGEST={digest}")
    print(f"JOB_START_UTC={started_utc}")
    if outcome.failed:
        print("CI_SCOPE_CONSISTENCY=FAIL")
        raise SystemExit(2)
    print("CI_SCOPE_CONSISTENCY=PASS")


def command_mark_setup(_: argparse.Namespace) -> None:
    started = required_epoch("JOB_START_EPOCH")
    setup_seconds = max(0, int(time.time()) - started)
    append_environment(SETUP_SECONDS=setup_seconds)
    print(f"SETUP_SECONDS={setup_seconds}")


def required_epoch(name: str) -> int:
    raw = os.environ.get(name)
    if raw is None:
        raise SystemExit(f"{name} is required")
    try:
        return int(raw)
    except ValueError as error:
        raise SystemExit(f"{name} must be an integer") from error


def load_and_verify_scope() -> tuple[str, dict[str, object]]:
    try:
        payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("payload root must be an object")
        verify_payload(payload)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"CI_SCOPE_CONSISTENCY=FAIL: {error}")
        raise SystemExit(2) from error

    expected_scope = os.environ.get("CI_SCOPE")
    expected_digest = os.environ.get("CI_SCOPE_PAYLOAD_DIGEST")
    if expected_scope != payload["classification"] or expected_digest != payload["payloadDigest"]:
        print("CI_SCOPE_CONSISTENCY=FAIL: environment and payload disagree")
        raise SystemExit(2)

    repeated = classify_repository_change(
        repo_root=REPO_ROOT,
        event_name=str(payload["eventName"]),
        base_sha=str(payload["baseSha"]),
        head_sha=str(payload["headSha"]),
    )
    if repeated.failed or repeated.payload != payload:
        print("CI_SCOPE_CONSISTENCY=FAIL: repeated classification disagrees")
        raise SystemExit(2)

    print("CI_SCOPE_CONSISTENCY=PASS")
    return str(payload["classification"]), payload


def run_checked(script: str) -> None:
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script)],
        cwd=REPO_ROOT,
        check=True,
    )


def run_classifier_fixtures() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.unit.test_ci_change_scope_classifier",
            "-v",
        ],
        cwd=REPO_ROOT,
        check=True,
    )


def run_docs_only_job(job: str) -> None:
    if job == "markdown":
        run_checked("validate_markdown.py")
        run_checked("validate_document_registry.py")
        run_checked("validate_current_state.py")
    elif job == "documentation-links":
        run_checked("validate_doc_links.py")
        run_checked("validate_document_supersession.py")
    elif job == "unit":
        run_classifier_fixtures()
        run_checked("validate_document_registry.py")
        run_checked("validate_current_state.py")
    elif job == "contract":
        run_checked("validate_current_state.py")
    elif job == "integration":
        run_checked("validate_document_registry.py")
        run_checked("validate_current_state.py")
        run_checked("validate_document_supersession.py")
    else:  # pragma: no cover - guarded by argparse
        raise AssertionError(job)


class TimingResult(unittest.TextTestResult):
    """Collect elapsed test time by source file without changing test behavior."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._started: dict[int, float] = {}
        self.file_seconds: dict[str, float] = defaultdict(float)

    def startTest(self, test: unittest.case.TestCase) -> None:  # noqa: N802
        self._started[id(test)] = time.monotonic()
        super().startTest(test)

    def stopTest(self, test: unittest.case.TestCase) -> None:  # noqa: N802
        started = self._started.pop(id(test), time.monotonic())
        duration = max(0.0, time.monotonic() - started)
        try:
            source = inspect.getsourcefile(test.__class__)
            if source:
                path = Path(source).resolve().relative_to(REPO_ROOT).as_posix()
            else:
                path = test.__class__.__module__
        except (OSError, ValueError, TypeError):
            path = test.__class__.__module__
        self.file_seconds[path] += duration
        super().stopTest(test)


def heartbeat(stop: threading.Event, started: float) -> None:
    while not stop.wait(120):
        elapsed = int(time.monotonic() - started)
        print("INTEGRATION_TESTS_RUNNING=true", flush=True)
        print(f"ELAPSED_SECONDS={elapsed}", flush=True)


def discover_suite(root: Path) -> unittest.TestSuite:
    absolute = REPO_ROOT / root
    if not absolute.is_dir():
        raise SystemExit(f"{root.as_posix()} does not exist in the repository checkout")
    suite = unittest.defaultTestLoader.discover(str(root), pattern="test_*.py")
    if suite.countTestCases() == 0:
        raise SystemExit(f"No tests were discovered under {root.as_posix()}")
    return suite


def discovered_integration_files() -> tuple[str, ...]:
    absolute = REPO_ROOT / INTEGRATION_TEST_ROOT
    return tuple(
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted(absolute.glob("test_*.py"))
        if path.is_file()
    )


def audit_integration_shard_files(
    shards: dict[str, tuple[str, ...]] = INTEGRATION_SHARDS,
    discovered: tuple[str, ...] | None = None,
) -> dict[str, object]:
    actual = discovered if discovered is not None else discovered_integration_files()
    assigned = tuple(path for files in shards.values() for path in files)
    counts = Counter(assigned)
    duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
    actual_set = set(actual)
    assigned_set = set(assigned)
    return {
        "discovered": actual,
        "assigned": assigned,
        "missing": tuple(sorted(actual_set - assigned_set)),
        "extra": tuple(sorted(assigned_set - actual_set)),
        "duplicateCount": duplicate_count,
    }


def require_complete_integration_shard_plan() -> dict[str, object]:
    audit = audit_integration_shard_files()
    print(f"INTEGRATION_SHARD_COUNT={len(INTEGRATION_SHARDS)}")
    print(f"DISCOVERED_INTEGRATION_TEST_FILE_COUNT={len(audit['discovered'])}")
    print(f"MISSING_TEST_FILE_COUNT={len(audit['missing'])}")
    print(f"DUPLICATE_TEST_FILE_COUNT={audit['duplicateCount']}")
    print(f"EXTRA_TEST_FILE_COUNT={len(audit['extra'])}")
    if audit["missing"] or audit["extra"] or audit["duplicateCount"]:
        print(f"MISSING_TEST_FILES={json.dumps(audit['missing'])}")
        print(f"EXTRA_TEST_FILES={json.dumps(audit['extra'])}")
        raise SystemExit("Integration shard file coverage is not exact")
    return audit


def discover_integration_files(files: tuple[str, ...]) -> unittest.TestSuite:
    suites: list[unittest.TestSuite] = []
    for path in files:
        candidate = Path(path)
        if candidate.parent != INTEGRATION_TEST_ROOT or not candidate.name.startswith("test_"):
            raise SystemExit(f"Invalid integration shard path: {path}")
        suites.append(
            unittest.defaultTestLoader.discover(
                str(INTEGRATION_TEST_ROOT),
                pattern=candidate.name,
            )
        )
    suite = unittest.TestSuite(suites)
    if suite.countTestCases() == 0:
        raise SystemExit("No integration tests were discovered for the shard")
    return suite


def integration_test_counts() -> tuple[int, dict[str, int]]:
    full_count = discover_suite(INTEGRATION_TEST_ROOT).countTestCases()
    shard_counts = {
        shard: discover_integration_files(files).countTestCases()
        for shard, files in INTEGRATION_SHARDS.items()
    }
    sharded_count = sum(shard_counts.values())
    print(f"DISCOVERED_INTEGRATION_TEST_COUNT={full_count}")
    print(f"SHARDED_DISCOVERED_TEST_COUNT={sharded_count}")
    if full_count != sharded_count:
        raise SystemExit(
            "Integration shard test-count mismatch: "
            f"discovered={full_count} sharded={sharded_count}"
        )
    return full_count, shard_counts


def current_process_group() -> int:
    return os.getpgrp()


def process_group_members(process_group: int) -> list[Path]:
    members: list[Path] = []
    for candidate in Path("/proc").iterdir():
        if not candidate.name.isdigit():
            continue
        try:
            stat = (candidate / "stat").read_text(encoding="utf-8")
            _, separator, trailing = stat.rpartition(") ")
            fields = trailing.split()
            if separator and len(fields) > 2 and int(fields[2]) == process_group:
                members.append(candidate)
        except (OSError, UnicodeError, ValueError):
            continue
    return members


def ffmpeg_process_count(process_group: int) -> int:
    count = 0
    for process in process_group_members(process_group):
        try:
            name = (process / "comm").read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            continue
        if name in {"ffmpeg", "ffprobe"}:
            count += 1
    return count


def listening_socket_inodes() -> set[str]:
    result: set[str] = set()
    for path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[1:]
        except (OSError, UnicodeError):
            continue
        for line in lines:
            fields = line.split()
            if len(fields) > 9 and fields[3] == "0A":
                result.add(fields[9])
    return result


def residual_listener_count(process_group: int) -> int:
    listening = listening_socket_inodes()
    held: set[str] = set()
    for process in process_group_members(process_group):
        fd_root = process / "fd"
        try:
            descriptors = list(fd_root.iterdir())
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            if target.startswith("socket:[") and target.endswith("]"):
                inode = target[8:-1]
                if inode in listening:
                    held.add(inode)
    return len(held)


def run_full_suite(job: str) -> None:
    if job == "markdown":
        run_docs_only_job(job)
        return
    if job == "documentation-links":
        run_docs_only_job(job)
        return

    suite = discover_suite(FULL_TEST_ROOTS[job])
    count = suite.countTestCases()
    print(f"DISCOVERED_TEST_COUNT={count}")
    if job != "integration":
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        if not result.wasSuccessful():
            raise SystemExit(1)
        return

    stop = threading.Event()
    test_started = time.monotonic()
    reporter = threading.Thread(
        target=heartbeat,
        args=(stop, test_started),
        name="integration-heartbeat",
        daemon=False,
    )
    reporter.start()
    result: TimingResult | None = None
    try:
        runner = unittest.TextTestRunner(verbosity=1, resultclass=TimingResult)
        result = runner.run(suite)
    finally:
        stop.set()
        reporter.join()

    if result is None:
        raise SystemExit("Integration runner did not produce a result")
    slowest = sorted(result.file_seconds.items(), key=lambda item: (-item[1], item[0]))[:20]
    print(f"SLOWEST_TEST_FILES_TOP_20={json.dumps(slowest, separators=(',', ':'))}")
    group = current_process_group()
    print(f"FFMPEG_PROCESS_COUNT_FINAL={ffmpeg_process_count(group)}")
    print(f"RESIDUAL_LISTENER_COUNT_FINAL={residual_listener_count(group)}")
    if not result.wasSuccessful():
        raise SystemExit(1)


def report_job_timing(scope: str, started_epoch: int, test_started: float) -> None:
    test_seconds = max(0, int(time.monotonic() - test_started))
    total_seconds = max(0, int(time.time()) - started_epoch)
    print(f"CI_SCOPE={scope}")
    print(f"JOB_START_UTC={os.environ.get('JOB_START_UTC', '')}")
    print(f"SETUP_SECONDS={os.environ.get('SETUP_SECONDS', '0')}")
    print(f"RUNTIME_INSTALL_SECONDS={os.environ.get('RUNTIME_INSTALL_SECONDS', '0')}")
    print(f"TEST_SECONDS={test_seconds}")
    print(f"JOB_TOTAL_SECONDS={total_seconds}")


def command_run_job(args: argparse.Namespace) -> None:
    scope, _ = load_and_verify_scope()
    started_epoch = required_epoch("JOB_START_EPOCH")
    test_started = time.monotonic()
    succeeded = False
    try:
        if scope == DOCS_ONLY:
            run_docs_only_job(args.job)
        elif scope == FULL_SUITE:
            run_full_suite(args.job)
        else:  # verify_payload already prevents this
            raise SystemExit(f"Unsupported CI scope {scope}")
        succeeded = True
    finally:
        report_job_timing(scope, started_epoch, test_started)
        if scope == DOCS_ONLY:
            print(f"DOCS_ONLY_FAST_PATH={'PASS' if succeeded else 'FAIL'}")
            print("FULL_SUITE_EXECUTED=false")
            print("FFMPEG_INSTALL_EXECUTED=false")
        else:
            print("FULL_SUITE_EXECUTED=true")
            print(
                "FFMPEG_INSTALL_EXECUTED="
                f"{os.environ.get('FFMPEG_INSTALL_EXECUTED', 'false')}"
            )


def command_run_integration_shard(args: argparse.Namespace) -> None:
    scope, _ = load_and_verify_scope()
    started_epoch = required_epoch("JOB_START_EPOCH")
    test_started = time.monotonic()
    succeeded = False
    try:
        if scope == DOCS_ONLY:
            print(f"INTEGRATION_SHARD={args.shard}")
            print("INTEGRATION_SHARD_EXECUTED=false")
            succeeded = True
            return
        if scope != FULL_SUITE:  # verify_payload already prevents this
            raise SystemExit(f"Unsupported CI scope {scope}")

        require_complete_integration_shard_plan()
        full_count, shard_counts = integration_test_counts()
        expected_count = shard_counts[args.shard]
        suite = discover_integration_files(INTEGRATION_SHARDS[args.shard])
        print(f"INTEGRATION_SHARD={args.shard}")
        print(f"DISCOVERED_INTEGRATION_TEST_COUNT={full_count}")
        print(f"SHARD_DISCOVERED_TEST_COUNT={expected_count}")

        stop = threading.Event()
        execution_started = time.monotonic()
        reporter = threading.Thread(
            target=heartbeat,
            args=(stop, execution_started),
            name=f"integration-heartbeat-{args.shard}",
            daemon=False,
        )
        reporter.start()
        result: TimingResult | None = None
        try:
            runner = unittest.TextTestRunner(verbosity=1, resultclass=TimingResult)
            result = runner.run(suite)
        finally:
            stop.set()
            reporter.join()

        wall_seconds = time.monotonic() - execution_started
        if result is None:
            raise SystemExit("Integration shard runner did not produce a result")
        slowest = sorted(
            result.file_seconds.items(), key=lambda item: (-item[1], item[0])
        )[:20]
        unexpected_skips = sorted(
            test.id()
            for test, _ in result.skipped
            if test.id() not in ALLOWED_INTEGRATION_SKIPS
        )
        group = current_process_group()
        ffmpeg_final = ffmpeg_process_count(group)
        listeners_final = residual_listener_count(group)
        print(f"SHARDED_EXECUTED_TEST_COUNT={result.testsRun}")
        print(f"TEST_SKIP_COUNT={len(result.skipped)}")
        print(f"UNEXPECTED_TEST_SKIP_COUNT={len(unexpected_skips)}")
        print(
            "TEST_SKIP_COUNT_NOT_INCREASED="
            f"{'true' if not unexpected_skips else 'false'}"
        )
        print(f"INTEGRATION_SHARD_WALL_TIME_SECONDS={wall_seconds:.3f}")
        print(f"INTEGRATION_SHARD_LIMIT_SECONDS={INTEGRATION_SHARD_LIMIT_SECONDS}")
        print(f"SLOWEST_TEST_FILES_TOP_20={json.dumps(slowest, separators=(',', ':'))}")
        print(f"FFMPEG_PROCESS_COUNT_FINAL={ffmpeg_final}")
        print(f"RESIDUAL_LISTENER_COUNT_FINAL={listeners_final}")
        if unexpected_skips:
            print(f"UNEXPECTED_TEST_SKIPS={json.dumps(unexpected_skips)}")
        succeeded = (
            result.wasSuccessful()
            and result.testsRun == expected_count
            and not unexpected_skips
            and wall_seconds <= INTEGRATION_SHARD_LIMIT_SECONDS
            and ffmpeg_final == 0
            and listeners_final == 0
        )
        if not succeeded:
            raise SystemExit(1)
    finally:
        report_job_timing(scope, started_epoch, test_started)
        if scope == DOCS_ONLY:
            print(f"DOCS_ONLY_FAST_PATH={'PASS' if succeeded else 'FAIL'}")
            print("FULL_SUITE_EXECUTED=false")
            print("FFMPEG_INSTALL_EXECUTED=false")
        else:
            print("FULL_SUITE_EXECUTED=true")
            print(
                "FFMPEG_INSTALL_EXECUTED="
                f"{os.environ.get('FFMPEG_INSTALL_EXECUTED', 'false')}"
            )


def command_aggregate_integration(args: argparse.Namespace) -> None:
    scope, _ = load_and_verify_scope()
    started_epoch = required_epoch("JOB_START_EPOCH")
    test_started = time.monotonic()
    succeeded = False
    try:
        if args.workers_result != "success":
            print(f"INTEGRATION_WORKERS_RESULT={args.workers_result}")
            print("INTEGRATION_AGGREGATOR=FAIL")
            raise SystemExit(1)
        if scope == DOCS_ONLY:
            run_docs_only_job("integration")
        elif scope == FULL_SUITE:
            require_complete_integration_shard_plan()
            full_count, shard_counts = integration_test_counts()
            sharded_count = sum(shard_counts.values())
            print(f"DISCOVERED_INTEGRATION_TEST_COUNT={full_count}")
            print(f"SHARDED_EXECUTED_TEST_COUNT={sharded_count}")
            print(f"COUNT_MATCH={'true' if full_count == sharded_count else 'false'}")
            print("TEST_SKIP_COUNT_NOT_INCREASED=true")
        else:  # verify_payload already prevents this
            raise SystemExit(f"Unsupported CI scope {scope}")
        print(f"INTEGRATION_WORKERS_RESULT={args.workers_result}")
        print("INTEGRATION_AGGREGATOR=PASS")
        succeeded = True
    finally:
        report_job_timing(scope, started_epoch, test_started)
        if scope == DOCS_ONLY:
            print(f"DOCS_ONLY_FAST_PATH={'PASS' if succeeded else 'FAIL'}")
            print("FULL_SUITE_EXECUTED=false")
            print("FFMPEG_INSTALL_EXECUTED=false")
        else:
            print("FULL_SUITE_EXECUTED=true")
            print("FFMPEG_INSTALL_EXECUTED=false")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    classify = commands.add_parser("classify")
    classify.add_argument("--event-name", required=True)
    classify.add_argument("--base-sha", default="")
    classify.add_argument("--head-sha", default="")
    classify.set_defaults(handler=command_classify)

    mark_setup = commands.add_parser("mark-setup")
    mark_setup.set_defaults(handler=command_mark_setup)

    run_job = commands.add_parser("run-job")
    run_job.add_argument("--job", choices=sorted(VALID_JOBS), required=True)
    run_job.set_defaults(handler=command_run_job)

    run_shard = commands.add_parser("run-integration-shard")
    run_shard.add_argument("--shard", choices=sorted(INTEGRATION_SHARDS), required=True)
    run_shard.set_defaults(handler=command_run_integration_shard)

    aggregate = commands.add_parser("aggregate-integration")
    aggregate.add_argument("--workers-result", required=True)
    aggregate.set_defaults(handler=command_aggregate_integration)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.chdir(REPO_ROOT)
    args.handler(args)


if __name__ == "__main__":
    main()
