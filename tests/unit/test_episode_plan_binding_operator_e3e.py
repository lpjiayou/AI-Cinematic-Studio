import hashlib
import importlib
import importlib.util
import json
import copy
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from tests.unit.test_series_intelligence_consumer_m6_p3 import create_episode, seed_consumer_on


REPO = Path(__file__).resolve().parents[2]
MODULE = "apps.creator_workspace_mvp.episode_plan_binding_operator"
CONTENT_FIELDS = (
    "seriesConcept", "premise", "logline", "mainNarrativeDirection", "mainArcs",
    "subArcs", "characterArcIntents", "episodePlanItems", "narrativeRhythm",
    "worldIntent", "continuityIntent", "foreshadowingContext", "productionAssumptions",
)


def content_digest(version):
    content = {field: version[field] for field in CONTENT_FIELDS}
    if "episodePlanItemBindings" in version:
        content["episodePlanItemBindings"] = version["episodePlanItemBindings"]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def binding_fixture(directory):
    database = Path(directory) / "lifecycle.sqlite3"
    assembly = LifecycleAssembly.sqlite(database, initialize_or_upgrade=True)
    seed = seed_consumer_on(assembly, workspace="workspace-e3e", bind=False)
    scope = {field: seed["context"][field]
             for field in ("workspaceRef", "projectRef", "seriesRef")}
    initial = seed["initial"]
    config = {"targetRef": "e3e-test-target", "databasePath": str(database),
              "allowedScopes": [{**scope, "operationAuthorizationRefs": ["approval-e3e-test"]}]}
    command = {**scope, "targetRef": config["targetRef"],
               "seriesPlanRef": initial["plan"]["seriesPlanRef"],
               "expectedPlanVersion": initial["plan"]["version"],
               "sourceSeriesPlanVersionRef": initial["version"]["seriesPlanVersionRef"],
               "sourceContentDigest": content_digest(initial["version"]),
               "episodePlanItemBindings": [{"episodeRef": seed["context"]["episodeRef"],
                   "episodePlanItemRef": initial["version"]["episodePlanItems"][1]["episodePlanItemRef"]}],
               "operationAuthorizationRef": "approval-e3e-test"}
    return assembly, seed, config, command


def database_snapshot(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        return tuple(connection.iterdump())


class BindingOperatorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module(MODULE)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.assembly, self.seed, self.config, self.command = binding_fixture(self.temp.name)

    def operator(self, config=None):
        return self.module.EpisodePlanBindingOperator(config or self.config)

    def read(self):
        return self.assembly.series_planning.get_workspace(
            self.command["workspaceRef"], self.command["projectRef"], self.command["seriesRef"])

    def snapshot(self):
        return database_snapshot(self.config["databasePath"])

    def test_preflight_and_v1_to_v2_preserve_history_content_and_draft(self):
        before = self.read()
        snapshot = self.snapshot()
        operator = self.operator()
        ready = operator.execute(self.command)
        self.assertEqual("PREFLIGHT_READY", ready["status"])
        self.assertEqual(snapshot, self.snapshot())
        created = operator.execute(self.command, apply=True)
        after = self.read()
        self.assertEqual(2, len(after["versions"]))
        self.assertEqual(before["versions"][0], after["versions"][0])
        self.assertEqual({field: before["versions"][0][field] for field in CONTENT_FIELDS},
                         {field: created["version"][field] for field in CONTENT_FIELDS})
        self.assertEqual("v5.series-plan-version.v2", created["version"]["schemaVersion"])
        self.assertEqual("draft", created["plan"]["status"])
        self.assertTrue(created["BINDING_VERSION_CREATED"])
        self.assertTrue(created["BINDING_VERSION_CURRENT"])
        self.assertFalse(created["BINDING_VERSION_CONFIRMED"])
        self.assertEqual(before["plan"]["confirmedSeriesPlanVersionRef"],
                         created["plan"]["confirmedSeriesPlanVersionRef"])
        snapshot = self.snapshot()
        recovered = self.operator().execute(self.command, apply=True)
        self.assertEqual("BINDING_RESULT_RECOVERED_BY_AUTHORITATIVE_READBACK", recovered["status"])
        self.assertFalse(recovered["BINDING_VERSION_CREATED"])
        self.assertEqual(created["version"], recovered["version"])
        self.assertEqual(self.read()["plan"], recovered["plan"])
        self.assertFalse(recovered["BINDING_VERSION_CONFIRMED"])
        self.assertEqual(snapshot, self.snapshot())

    def test_v2_to_v2_requires_complete_explicit_input_and_rejects_later_retry(self):
        first = self.operator().execute(self.command, apply=True)
        command = {**self.command, "expectedPlanVersion": first["plan"]["version"],
                   "sourceSeriesPlanVersionRef": first["version"]["seriesPlanVersionRef"],
                   "sourceContentDigest": content_digest(first["version"]),
                   "episodePlanItemBindings": []}
        second = self.operator().execute(command, apply=True)
        self.assertEqual([], second["version"]["episodePlanItemBindings"])
        self.assertEqual("v5.series-plan-version.v2", second["version"]["schemaVersion"])
        self.assertEqual(3, len(self.read()["versions"]))
        self.assertEqual(first["version"], self.read()["versions"][1])
        before = self.snapshot()
        with self.assertRaisesRegex(self.module.BindingOperatorError, "CONFLICT"):
            self.operator().execute(self.command, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_explicit_pairs_use_source_item_order_without_episode_number_inference(self):
        second = create_episode(self.assembly, self.command["workspaceRef"], self.command["seriesRef"], 2)
        original = self.command["episodePlanItemBindings"][0]
        other = {"episodeRef": second["episodeRef"],
                 "episodePlanItemRef": self.seed["initial"]["version"]["episodePlanItems"][0]["episodePlanItemRef"]}
        result = self.operator().execute({**self.command, "episodePlanItemBindings": [original, other]}, apply=True)
        self.assertEqual([other, original], result["version"]["episodePlanItemBindings"])
        self.assertFalse(result["BINDING_VERSION_CONFIRMED"])

    def test_response_lost_after_commit_recovers_without_second_write(self):
        operator = self.operator()
        write = operator.assembly.series_planning.create_episode_plan_item_binding_version
        def lost(command):
            write(command)
            raise ConnectionError("simulated response loss")
        with patch.object(operator.assembly.series_planning, "create_episode_plan_item_binding_version",
                          side_effect=lost) as writer:
            recovered = operator.execute(self.command, apply=True)
        self.assertEqual(1, writer.call_count)
        self.assertEqual("BINDING_RESULT_RECOVERED_BY_AUTHORITATIVE_READBACK", recovered["status"])
        self.assertEqual(2, len(self.read()["versions"]))

    def test_real_cli_process_preflight_apply_and_fresh_process_readback(self):
        directory = Path(self.temp.name)
        config, command = directory / "config.json", directory / "command.json"
        config.write_text(json.dumps(self.config))
        command.write_text(json.dumps(self.command))
        args = [sys.executable, "scripts/episode_plan_item_binding.py", "--config", str(config), "--input", str(command)]
        before = self.snapshot()
        result = subprocess.run(args, cwd=REPO, capture_output=True, text=True, timeout=20, check=True)
        self.assertEqual("PREFLIGHT_READY", json.loads(result.stdout)["status"])
        self.assertEqual(before, self.snapshot())
        process = subprocess.Popen(args + ["--apply"], cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output, errors = process.communicate(timeout=20)
        self.assertEqual(0, process.returncode, errors)
        self.assertNotEqual(os.getpid(), process.pid)
        # The caller discards the successful response, then starts a fresh interpreter.
        before = self.snapshot()
        retry = subprocess.run(args + ["--apply"], cwd=REPO, capture_output=True, text=True, timeout=20, check=True)
        recovered = json.loads(retry.stdout)
        self.assertEqual("BINDING_RESULT_RECOVERED_BY_AUTHORITATIVE_READBACK", recovered["status"])
        self.assertEqual(2, len(self.read()["versions"]))
        self.assertEqual(before, self.snapshot())
        self.assertNotIn(str(directory), retry.stdout)

    def test_two_callers_issue_one_effective_cas_write(self):
        operators = [self.operator(), self.operator()]
        barrier = threading.Barrier(2)
        writes = []
        patches = []
        for operator in operators:
            write = operator.assembly.series_planning.create_episode_plan_item_binding_version
            def concurrent(command, write=write):
                barrier.wait(timeout=10)
                result = write(command)
                writes.append(result)
                return result
            patches.append(patch.object(operator.assembly.series_planning,
                "create_episode_plan_item_binding_version", side_effect=concurrent))
        def execute(operator):
            try:
                return operator.execute(self.command, apply=True)["status"]
            except self.module.BindingOperatorError as exc:
                return exc.code
        with patches[0], patches[1], ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(execute, operators))
        self.assertEqual(1, len(writes))
        self.assertEqual(2, len(self.read()["versions"]))
        self.assertIn("BINDING_VERSION_CREATED", results)
        self.assertTrue(set(results) <= {"BINDING_VERSION_CREATED", "BINDING_RESULT_RECOVERED_BY_AUTHORITATIVE_READBACK",
                                        "CONFLICT", "UNRESOLVED_OUTCOME"}, results)

    def test_cas_is_rechecked_after_preflight_without_refresh(self):
        operator = self.operator()
        operator.execute(self.command)
        self.operator().execute(self.command, apply=True)
        stale = {**self.command, "episodePlanItemBindings": []}
        before = self.snapshot()
        with self.assertRaisesRegex(self.module.BindingOperatorError, "CONFLICT"):
            operator.execute(stale, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_ambiguous_readback_and_confirmation_advance_fail_closed(self):
        created = self.operator().execute(self.command, apply=True)
        operator = self.operator()
        read = operator.assembly.series_planning.get_workspace
        def ambiguous(*args):
            value = read(*args)
            duplicate = {**created["version"], "seriesPlanVersionRef": "ambiguous-version"}
            value["versions"].append(duplicate)
            return value
        before = self.snapshot()
        with patch.object(operator.assembly.series_planning, "get_workspace", side_effect=ambiguous):
            with self.assertRaisesRegex(self.module.BindingOperatorError, "CONFLICT"):
                operator.execute(self.command, apply=True)
        self.assertEqual(before, self.snapshot())
        self.assembly.series_planning.confirm_version({
            "workspaceRef": self.command["workspaceRef"], "seriesPlanRef": self.command["seriesPlanRef"],
            "seriesPlanVersionRef": created["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": created["plan"]["version"], "humanConfirmed": True})
        before = self.snapshot()
        with self.assertRaisesRegex(self.module.BindingOperatorError, "CONFLICT"):
            self.operator().execute(self.command, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_invalid_input_scope_authorization_and_source_are_zero_write(self):
        variants = [
            {**self.command, "extra": "rejected"},
            {**self.command, "targetRef": "wrong-target"},
            {**self.command, "workspaceRef": "foreign"},
            {**self.command, "projectRef": "foreign"},
            {**self.command, "seriesRef": "foreign"},
            {**self.command, "operationAuthorizationRef": "self-authorized"},
            {**self.command, "sourceContentDigest": "0" * 64},
            {**self.command, "sourceSeriesPlanVersionRef": "unknown"},
            {**self.command, "seriesPlanRef": "foreign"},
        ]
        variants.extend({**self.command, "expectedPlanVersion": value}
                        for value in (True, False, 0, -1, 1.0, "1", None, float("nan"), float("inf")))
        binding = self.command["episodePlanItemBindings"][0]
        variants.extend({**self.command, "episodePlanItemBindings": value} for value in (
            None, {}, [binding, binding], [{**binding, "episodeRef": "foreign"}],
            [{**binding, "episodePlanItemRef": "unknown"}], [{**binding, "extra": 1}],
        ))
        before = self.snapshot()
        for value in variants:
            with self.subTest(value=value), self.assertRaises(self.module.BindingOperatorError):
                self.operator().execute(value, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_strict_json_rejects_duplicates_nonfinite_and_invalid_shape(self):
        for value in ('{"a": 1, "a": 2}', '{"a":{"b":1,"b":2}}',
                      '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}', '[]', 'null', '{'):
            with self.subTest(value=value), self.assertRaises(self.module.BindingOperatorError):
                self.module.load_operator_json(value)

    def test_missing_wrong_database_symlink_and_parent_symlink_never_initialize(self):
        directory = Path(self.temp.name)
        missing = directory / "absent.sqlite3"
        wrong = directory / "wrong.sqlite3"
        wrong.write_bytes(b"not a database")
        empty = directory / "empty.sqlite3"
        empty.touch()
        link = directory / "link.sqlite3"
        link.symlink_to(self.config["databasePath"])
        parent = directory / "linked-directory"
        parent.symlink_to(directory, target_is_directory=True)
        before = self.snapshot()
        for path in (missing, wrong, empty, link, parent / "lifecycle.sqlite3", directory, Path("relative.sqlite3")):
            with self.subTest(path=path), self.assertRaises(self.module.BindingOperatorError):
                self.operator({**self.config, "databasePath": str(path)})
        self.assertFalse(missing.exists())
        self.assertEqual(b"not a database", wrong.read_bytes())
        self.assertEqual(b"", empty.read_bytes())
        self.assertEqual(before, self.snapshot())


class BindingOperatorEntrypointTests(unittest.TestCase):
    def test_existing_core_binding_capability_is_present(self):
        with tempfile.TemporaryDirectory() as directory:
            assembly, seed, config, command = binding_fixture(directory)
            before = assembly.series_planning.get_workspace(
                command["workspaceRef"], command["projectRef"], command["seriesRef"])
            self.assertEqual(1, len(before["versions"]))
            fields = ("workspaceRef", "projectRef", "seriesRef", "seriesPlanRef",
                      "expectedPlanVersion", "episodePlanItemBindings")
            result = assembly.series_planning.create_episode_plan_item_binding_version(
                {field: command[field] for field in fields})
            self.assertEqual("episode-plan-item-binding", result["version"]["changeKind"])
            self.assertEqual("draft", result["plan"]["status"])

    def test_controlled_operator_has_default_readonly_entrypoint(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE),
                             "Core binding exists but the controlled application entrypoint is absent")
        module = importlib.import_module(MODULE)
        with tempfile.TemporaryDirectory() as directory:
            assembly, seed, config, command = binding_fixture(directory)
            before = Path(config["databasePath"]).read_bytes()
            result = module.EpisodePlanBindingOperator(config).execute(command)
            self.assertEqual("PREFLIGHT_READY", result["status"])
            self.assertFalse(result["BINDING_VERSION_CREATED"])
            self.assertEqual(before, Path(config["databasePath"]).read_bytes())


if __name__ == "__main__":
    unittest.main()
