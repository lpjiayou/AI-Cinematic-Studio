from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from threading import Thread
import unittest

from scripts.k2_m6_draft_operator import (
    M6DraftOperatorError,
    _validate_origin,
    validate_candidate,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "k2_m6_draft_operator.py"
SOURCE_CANDIDATE = (
    REPOSITORY_ROOT
    / "experiments"
    / "k2-001-m6-draft"
    / "k2-001-m6-draft-candidate.v1.json"
)
TOKEN = "test-only-k2-m6-operator-token"
EPISODE_PLAN_ITEM_REF = "episode-plan-item-real-canonical-ref"


class _FakeCreatorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format, *args):
        del args

    def _json(self, status: int, payload: dict) -> None:
        value = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(value)))
        self.end_headers()
        self.wfile.write(value)

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {TOKEN}"

    def do_GET(self) -> None:
        if not self._authorized():
            self._json(401, {"ok": False, "error": {"code": "unauthorized"}})
            return
        path = self.path.split("?", 1)[0]
        self.server.state["get_paths"].append(self.path)
        if path.endswith("/series-planning-workspaces/m6-bootstrap"):
            self._json(
                200,
                {
                    "ok": True,
                    "bootstrap": {
                        "schemaVersion": "creator.series-plan.m6-bootstrap.v1",
                        **self.server.state["scope"],
                        "seriesPlanRef": "series-plan-canonical-ref",
                        "seriesPlanVersionRef": "series-plan-version-canonical-ref",
                        "episodePlanItems": [
                            {"episodePlanItemRef": EPISODE_PLAN_ITEM_REF}
                        ],
                    },
                },
            )
            return
        if path.endswith("/series-intelligence-workspaces"):
            self._json(200, {"ok": True, "workspace": self.server.state["workspace"]})
            return
        self._json(404, {"ok": False, "error": {"code": "not_found"}})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"ok": False, "error": {"code": "unauthorized"}})
            return
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size).decode("utf-8"))
        self.server.state["posts"].append((self.path, payload))
        scope = self.server.state["scope"]
        workspace = self.server.state["workspace"]
        if self.path.endswith("/series-intelligence/bible-versions"):
            content = {"schemaVersion": "v5.series-bible-content.v1", **payload["content"]}
            root = {
                **scope,
                "seriesBibleRef": "series-bible-k2-001",
                "currentSeriesBibleVersionRef": "series-bible-version-k2-001-v1",
                "confirmedSeriesBibleVersionRef": None,
                "revision": 1,
            }
            version = {
                **scope,
                "seriesBibleRef": root["seriesBibleRef"],
                "seriesBibleVersionRef": root["currentSeriesBibleVersionRef"],
                "versionNumber": 1,
                "content": content,
                "contentDigest": "1" * 64,
                "status": "CANDIDATE",
                "approvalRef": None,
            }
            workspace["seriesBible"] = root
            workspace["seriesBibleVersions"] = [version]
            self._json(201, {"ok": True, "result": {"root": root, "version": version}})
            return
        if self.path.endswith("/series-intelligence/character-versions"):
            bible_root = workspace["seriesBible"]
            bible_version = workspace["seriesBibleVersions"][0]
            content = {
                "schemaVersion": "v5.character-continuity-content.v1",
                **payload["content"],
            }
            root = {
                **scope,
                "characterContinuityRef": "character-continuity-k2-001",
                "currentCharacterContinuityVersionRef": "character-continuity-version-k2-001-v1",
                "confirmedCharacterContinuityVersionRef": None,
                "revision": 1,
            }
            version = {
                **scope,
                "characterContinuityRef": root["characterContinuityRef"],
                "characterContinuityVersionRef": root[
                    "currentCharacterContinuityVersionRef"
                ],
                "seriesBibleRef": bible_root["seriesBibleRef"],
                "seriesBibleVersionRef": bible_version["seriesBibleVersionRef"],
                "seriesBibleVersionDigest": bible_version["contentDigest"],
                "versionNumber": 1,
                "content": content,
                "contentDigest": "2" * 64,
                "status": "CANDIDATE",
                "approvalRef": None,
            }
            workspace["characterContinuity"] = root
            workspace["characterContinuityVersions"] = [version]
            self._json(201, {"ok": True, "result": {"root": root, "version": version}})
            return
        self._json(404, {"ok": False, "error": {"code": "not_found"}})


class K2M6DraftOperatorTests(unittest.TestCase):
    def test_checked_in_candidate_is_strictly_valid_and_non_loopback_is_rejected(self):
        candidate = validate_candidate(SOURCE_CANDIDATE)

        self.assertEqual(candidate.value["packageId"], "k2-001-m6-draft-v1")
        self.assertEqual(candidate.value["characterCandidate"]["contentTemplate"]["identityBindings"], [])
        with self.assertRaisesRegex(M6DraftOperatorError, "base_url_must_be_loopback"):
            _validate_origin("https://creator.example.com:8765")

    def test_bible_apply_writes_only_candidate_and_secret_free_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path, bundle_path, candidate = self._inputs(root)
            state = self._empty_state(candidate["scope"])
            with self._server(state) as base_url:
                receipt = root / "bible-receipt.json"
                result = self._run(
                    candidate_path,
                    bundle_path,
                    base_url,
                    "bible-candidate",
                    receipt,
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("K2_M6_DRAFT_APPLY=PASS", result.stdout)
            self.assertEqual(len(state["posts"]), 1)
            path, payload = state["posts"][0]
            self.assertTrue(path.endswith("/series-intelligence/bible-versions"))
            self.assertNotIn("workspaceRef", payload)
            self.assertTrue(payload["candidate"])
            self.assertNotIn("schemaVersion", payload["content"])
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
            receipt_text = receipt.read_text(encoding="utf-8")
            self.assertNotIn(TOKEN, receipt_text)
            recorded = json.loads(receipt_text)
            self.assertEqual(recorded["exitState"]["seriesBibleStatus"], "CANDIDATE")
            self.assertEqual(
                recorded["exitState"]["characterContinuityStatus"], "NOT_CREATED"
            )
            self.assertFalse(recorded["exitState"]["publicationAllowed"])

    def test_default_bible_preflight_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path, bundle_path, candidate = self._inputs(root)
            state = self._empty_state(candidate["scope"])
            with self._server(state) as base_url:
                result = self._run(
                    candidate_path,
                    bundle_path,
                    base_url,
                    "bible-candidate",
                    None,
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("K2_M6_DRAFT_PREFLIGHT=PASS", result.stdout)
            self.assertIn("K2_M6_DRAFT_APPLY_REQUIRED=true", result.stdout)
            self.assertEqual(state["posts"], [])

    def test_character_stage_fails_closed_until_bible_is_confirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path, bundle_path, candidate = self._inputs(root)
            state = self._empty_state(candidate["scope"])
            state["workspace"]["seriesBible"] = {
                **candidate["scope"],
                "seriesBibleRef": "series-bible-k2-001",
                "currentSeriesBibleVersionRef": "series-bible-version-k2-001-v1",
                "confirmedSeriesBibleVersionRef": None,
                "revision": 1,
            }
            state["workspace"]["seriesBibleVersions"] = [
                {
                    **candidate["scope"],
                    "seriesBibleRef": "series-bible-k2-001",
                    "seriesBibleVersionRef": "series-bible-version-k2-001-v1",
                    "versionNumber": 1,
                    "content": {},
                    "contentDigest": "1" * 64,
                    "status": "CANDIDATE",
                    "approvalRef": None,
                }
            ]
            with self._server(state) as base_url:
                result = self._run(
                    candidate_path,
                    bundle_path,
                    base_url,
                    "character-candidate",
                    root / "must-not-exist.json",
                )

            self.assertEqual(result.returncode, 2)
            self.assertIn("confirmed_bible_version_required", result.stderr)
            self.assertEqual(state["posts"], [])

    def test_character_apply_uses_real_m5_ref_and_never_calls_approval_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path, bundle_path, candidate = self._inputs(root)
            state = self._confirmed_bible_state(candidate)
            with self._server(state) as base_url:
                receipt = root / "character-receipt.json"
                result = self._run(
                    candidate_path,
                    bundle_path,
                    base_url,
                    "character-candidate",
                    receipt,
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(state["posts"]), 1)
            path, payload = state["posts"][0]
            self.assertTrue(path.endswith("/series-intelligence/character-versions"))
            self.assertNotIn("workspaceRef", payload)
            self.assertNotIn("schemaVersion", payload["content"])
            self.assertEqual(
                {
                    item["startEpisodePlanItemRef"]
                    for item in payload["content"]["stateIntervals"]
                },
                {EPISODE_PLAN_ITEM_REF},
            )
            self.assertEqual(
                {
                    item["startEpisodePlanItemRef"]
                    for item in payload["content"]["relationships"]
                },
                {EPISODE_PLAN_ITEM_REF},
            )
            self.assertFalse(
                any(
                    "confirmation" in posted_path or "baseline" in posted_path
                    for posted_path, _payload in state["posts"]
                )
            )
            recorded = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(recorded["exitState"]["seriesBibleStatus"], "CONFIRMED")
            self.assertEqual(
                recorded["exitState"]["characterContinuityStatus"], "CANDIDATE"
            )
            self.assertEqual(recorded["exitState"]["identityLockStatus"], "NOT_CREATED")

    @staticmethod
    def _empty_state(scope: dict) -> dict:
        return {
            "scope": scope,
            "workspace": {
                "schemaVersion": "v5.series-intelligence.workspace.v1",
                "scope": scope,
                "seriesBible": None,
                "seriesBibleVersions": [],
                "characterContinuity": None,
                "characterContinuityVersions": [],
                "activeBaseline": None,
                "baselineHistory": [],
                "sourceCompatibility": "NO_ACTIVE_BASELINE",
            },
            "posts": [],
            "get_paths": [],
        }

    @classmethod
    def _confirmed_bible_state(cls, candidate: dict) -> dict:
        state = cls._empty_state(candidate["scope"])
        content = {
            "schemaVersion": "v5.series-bible-content.v1",
            **candidate["bibleCandidate"]["content"],
        }
        root = {
            **candidate["scope"],
            "seriesBibleRef": "series-bible-k2-001",
            "currentSeriesBibleVersionRef": "series-bible-version-k2-001-v1",
            "confirmedSeriesBibleVersionRef": "series-bible-version-k2-001-v1",
            "revision": 2,
        }
        state["workspace"]["seriesBible"] = root
        state["workspace"]["seriesBibleVersions"] = [
            {
                **candidate["scope"],
                "seriesBibleRef": root["seriesBibleRef"],
                "seriesBibleVersionRef": root["confirmedSeriesBibleVersionRef"],
                "versionNumber": 1,
                "content": content,
                "contentDigest": "1" * 64,
                "status": "CONFIRMED",
                "approvalRef": "approval-bible-human-k2-001",
            }
        ]
        return state

    @staticmethod
    def _inputs(root: Path) -> tuple[Path, Path, dict]:
        candidate = json.loads(SOURCE_CANDIDATE.read_text(encoding="utf-8"))
        bundle = {
            "schemaVersion": "v5.external-m6-authority-bundle.v1",
            "authorityRef": candidate["authorityRef"],
            "scopes": [candidate["scope"]],
            "approvals": [],
        }
        bundle_path = root / "m6-scope-authority.json"
        bundle_path.write_text(
            json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        candidate["authorityBundleSha256"] = sha256(bundle_path.read_bytes()).hexdigest()
        candidate_path = root / "candidate.json"
        candidate_path.write_text(
            json.dumps(candidate, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return candidate_path, bundle_path, candidate

    @staticmethod
    def _server(state: dict):
        class _ServerContext:
            def __enter__(self):
                self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeCreatorHandler)
                self.server.state = state
                self.thread = Thread(target=self.server.serve_forever, daemon=True)
                self.thread.start()
                host, port = self.server.server_address
                return f"http://{host}:{port}"

            def __exit__(self, exc_type, exc, traceback):
                del exc_type, exc, traceback
                self.server.shutdown()
                self.server.server_close()
                self.thread.join(timeout=5)

        return _ServerContext()

    @staticmethod
    def _run(
        candidate: Path,
        bundle: Path,
        base_url: str,
        phase: str,
        receipt: Path | None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["K2_CREATOR_API_BEARER_TOKEN"] = TOKEN
        command = [
            sys.executable,
            str(SCRIPT),
            "--phase",
            phase,
            "--base-url",
            base_url,
            "--m6-bundle",
            str(bundle),
            "--candidate",
            str(candidate),
        ]
        if receipt is not None:
            command.extend(["--output", str(receipt), "--apply"])
        return subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=environment,
        )


if __name__ == "__main__":
    unittest.main()
