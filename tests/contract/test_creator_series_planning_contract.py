import ast
from importlib.util import resolve_name
import inspect
from pathlib import Path
import unittest

from services.v5_core_os import series_planning as public_package
from services.v5_core_os.series_planning import SeriesPlanningPublicBoundary
from tests.unit.test_series_planning_m5 import WORKSPACE, confirm, create_context


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "apps" / "creator_workspace_mvp" / "server.py"
APPLICATION = ROOT / "apps" / "creator_workspace_mvp" / "series_director.py"
APPS_ROOT = ROOT / "apps"
TEXT_GENERATION_ROOT = ROOT / "services" / "v5_core_os" / "text_generation"


def _imports_module(
    tree: ast.AST,
    target: str,
    *,
    current_package: str | None = None,
) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            candidates = (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                if current_package is None:
                    continue
                try:
                    module = resolve_name(f"{'.' * node.level}{module}", current_package)
                except (ImportError, ValueError):
                    continue
            candidates = (module, *(f"{module}.{alias.name}".lstrip(".") for alias in node.names))
        else:
            continue
        if any(name == target or name.startswith(f"{target}.") for name in candidates):
            return True
    return False


def _uses_dynamic_import(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in {"__import__", "import_module"}:
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
            return True
    return False


class CreatorSeriesPlanningContractTests(unittest.TestCase):
    def test_public_package_exports_only_stable_boundary_factories(self):
        self.assertEqual(
            public_package.__all__,
            [
                "SeriesPlanningPublicBoundary",
                "SeriesPlanningPublicError",
                "create_in_memory_boundary",
                "create_local_development_boundary",
                "create_local_development_boundary_from_environment",
            ],
        )
        self.assertTrue(inspect.isclass(SeriesPlanningPublicBoundary))

    def test_series_plan_identity_and_planned_episode_contract_are_v5_owned(self):
        series_boundary, _, planning, series, project = create_context()
        created = confirm(planning, series, project)
        version = created["version"]
        self.assertEqual(version["schemaVersion"], "v5.series-plan-version.v1")
        self.assertTrue(created["plan"]["seriesPlanRef"].startswith("series-plan-"))
        self.assertTrue(version["seriesPlanVersionRef"].startswith("series-plan-version-"))
        self.assertTrue(all("episodePlanItemRef" in item for item in version["episodePlanItems"]))
        self.assertTrue(all("episodeRef" not in item for item in version["episodePlanItems"]))
        self.assertEqual(series_boundary.list_series(WORKSPACE)[0]["episodes"], [])
        owner_path = Path(inspect.getfile(SeriesPlanningPublicBoundary)).resolve()
        self.assertIn("v5_core_os", owner_path.parts)
        self.assertNotIn("apps", owner_path.parts)

    def test_m6_bridge_preserves_lineage_and_contains_no_display_name_lookup(self):
        _, _, planning, series, project = create_context()
        created = confirm(planning, series, project)
        bridge = planning.build_m6_bootstrap(WORKSPACE, project["projectRef"], series["seriesRef"])
        self.assertEqual(bridge["schemaVersion"], "creator.series-plan.m6-bootstrap.v1")
        self.assertEqual(bridge["projectRef"], project["projectRef"])
        self.assertEqual(bridge["seriesRef"], series["seriesRef"])
        self.assertEqual(bridge["seriesPlanRef"], created["plan"]["seriesPlanRef"])
        self.assertEqual(bridge["seriesPlanVersionRef"], created["version"]["seriesPlanVersionRef"])
        self.assertNotIn("projectTitle", bridge)
        self.assertNotIn("seriesTitle", bridge)

    def test_application_uses_public_v5_boundaries_without_direct_v4_dependency(self):
        server = SERVER.read_text(encoding="utf-8")
        application = APPLICATION.read_text(encoding="utf-8")
        self.assertIn("from services.v5_core_os.series_planning import", server)
        self.assertNotIn("series_planning.foundation", server)
        self.assertNotIn("SqliteSeriesPlanningAdapter", server)
        self.assertIn("from services.v5_core_os.text_generation import", application)

    def test_all_application_sources_have_zero_static_or_textual_v4_imports(self):
        for path in APPS_ROOT.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            current_package = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertFalse(
                    _imports_module(
                        tree,
                        "services.v4_platform",
                        current_package=current_package,
                    )
                )
                self.assertFalse(_uses_dynamic_import(tree))
                self.assertNotIn("services.v4_platform", source)

    def test_only_v5_text_generation_public_implementation_may_import_v4(self):
        importers = []
        for path in TEXT_GENERATION_ROOT.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            current_package = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
            if (
                _imports_module(
                    tree,
                    "services.v4_platform",
                    current_package=current_package,
                )
                or "services.v4_platform" in source
            ):
                importers.append(path.relative_to(TEXT_GENERATION_ROOT).as_posix())
            if path.name != "public.py":
                self.assertFalse(_uses_dynamic_import(tree))
        self.assertEqual(importers, ["public.py"])

    def test_v4_import_guard_rejects_parent_from_alias_and_dynamic_forms(self):
        static_forms = (
            "import services.v4_platform",
            "import services.v4_platform as platform",
            "from services.v4_platform import TextProvider",
            "from services import v4_platform",
            "from services import v4_platform as platform",
        )
        for source in static_forms:
            with self.subTest(source=source):
                self.assertTrue(_imports_module(ast.parse(source), "services.v4_platform"))
        relative_forms = (
            "from ... import v4_platform",
            "from ...v4_platform import TextProvider",
        )
        for source in relative_forms:
            with self.subTest(source=source):
                self.assertTrue(
                    _imports_module(
                        ast.parse(source),
                        "services.v4_platform",
                        current_package="services.v5_core_os.text_generation",
                    )
                )
        dynamic_forms = (
            '__import__("services" + ".v4_platform")',
            'importlib.import_module("services" + ".v4_platform")',
            'import_module("services.v4_platform")',
        )
        for source in dynamic_forms:
            with self.subTest(source=source):
                self.assertTrue(_uses_dynamic_import(ast.parse(source)))

    def test_provider_failure_contract_exposes_only_safe_schema_diagnostics(self):
        server = SERVER.read_text(encoding="utf-8")
        block = server.split("def _send_series_director_product_error", 1)[1].split(
            "def _log_provider_error", 1
        )[0]
        self.assertIn('"validationIssues": issues', block)
        self.assertIn('for field, rule, _category in exc.validation_issues', block)
        for forbidden in ("raw provider", "Authorization", "PROVIDER_API_KEY", "response_body"):
            if forbidden == "raw provider":
                self.assertIn("Raw provider output", block)
            else:
                self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
