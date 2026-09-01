from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "tests" / "fixtures" / "m13" / "r2" / "manifest.json"
MANIFEST_SHA256 = "8bebad142ed6d7475bd82f697bb527ae07a36f327be18ee4080502602e960aad"
PRODUCTION_ROOTS = (
    ROOT / "services" / "v3_render_core",
    ROOT / "services" / "v4_platform",
    ROOT / "services" / "v5_core_os" / "episode_production",
)


class _ConditionalLiteralVisitor(ast.NodeVisitor):
    def __init__(self, forbidden: tuple[str, ...]) -> None:
        self.forbidden = tuple(item.casefold() for item in forbidden)
        self.findings: list[tuple[int, str]] = []

    def _scan(self, node: ast.AST | None) -> None:
        if node is None:
            return
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                folded = child.value.casefold()
                if any(item in folded for item in self.forbidden):
                    self.findings.append((child.lineno, child.value))

    def visit_If(self, node: ast.If) -> None:
        self._scan(node.test)
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._scan(node.test)
        self.generic_visit(node)

    def visit_match_case(self, node: ast.match_case) -> None:
        self._scan(node.pattern)
        self._scan(node.guard)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        for condition in node.ifs:
            self._scan(condition)
        self.generic_visit(node)


class M13R2AcceptanceContractTests(unittest.TestCase):
    def test_machine_manifest_is_pinned_and_closes_the_acceptance_surface(self):
        raw = MANIFEST.read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), MANIFEST_SHA256)
        value = json.loads(raw)
        self.assertEqual(value["full"]["frameCount"], 720)
        self.assertEqual(value["full"]["executedRenderProfile"], [704, 1280])
        self.assertEqual(len(value["tracks"]), 4)
        self.assertEqual(len(value["audioRoles"]), 5)
        self.assertEqual(
            value["audioFixtureLabels"],
            [
                "NOT_PRODUCTION_TTS",
                "NOT_VOICE_CLONE",
                "NOT_VOICE_IDENTITY_EVIDENCE",
                "NOT_ADMITTED",
            ],
        )
        self.assertEqual(len(value["effects"]), 8)
        self.assertEqual(
            value["labels"],
            [
                "TECHNICAL_FIXTURE_ONLY",
                "NOT_LIVE_K2",
                "NOT_ADMITTED",
                "NOT_SELECTED",
                "NOT_MASTER",
                "NOT_EXPORT",
            ],
        )
        self.assertFalse(value["publicationAllowed"])

    def test_production_has_no_project_specific_conditional_hardcoding(self):
        forbidden = tuple(
            json.loads(MANIFEST.read_text(encoding="utf-8"))[
                "forbiddenFullFixtureValues"
            ]
        )
        findings: list[str] = []
        for root in PRODUCTION_ROOTS:
            for path in sorted(root.rglob("*.py")):
                visitor = _ConditionalLiteralVisitor(forbidden)
                visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
                findings.extend(
                    f"{path.relative_to(ROOT)}:{line}:{literal}"
                    for line, literal in visitor.findings
                )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
