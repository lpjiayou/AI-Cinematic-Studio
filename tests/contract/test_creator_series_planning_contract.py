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


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if (
        isinstance(node, ast.FormattedValue)
        and node.conversion == -1
        and node.format_spec is None
    ):
        return _constant_string(node.value)
    if isinstance(node, ast.JoinedStr):
        values = tuple(_constant_string(value) for value in node.values)
        if all(value is not None for value in values):
            return "".join(value for value in values if value is not None)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _constant_string(node.left)
        right = _constant_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _simple_assignment_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
        targets = (node.target,)
    else:
        return ()
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def _binding_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.NamedExpr):
        return _binding_name(node.value)
    return None


def _uses_dynamic_import(tree: ast.AST) -> bool:
    importlib_bindings: set[str] = set()
    builtins_bindings: set[str] = set()
    primitive_bindings = {"__import__"}
    imported_primitive = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_bindings.add(alias.asname or "importlib")
                elif alias.name.startswith("importlib.") and alias.asname is None:
                    importlib_bindings.add("importlib")
                elif alias.name == "builtins":
                    builtins_bindings.add(alias.asname or "builtins")
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            module = node.module or ""
            if module not in {"importlib", "builtins"}:
                continue
            for alias in node.names:
                if alias.name == "*":
                    return True
                if (
                    module == "importlib"
                    and alias.name in {"import_module", "__import__"}
                ) or (module == "builtins" and alias.name == "__import__"):
                    primitive_bindings.add(alias.asname or alias.name)
                    imported_primitive = True

    if imported_primitive:
        return True

    # Resolve simple aliases of the imported modules before checking attribute access.
    # This is deliberately bounded data-flow analysis, not a Python sandbox.
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            names = _simple_assignment_names(node)
            if not names:
                continue
            value = node.value
            if isinstance(value, ast.Name) and value.id in importlib_bindings:
                for name in names:
                    if name not in importlib_bindings:
                        importlib_bindings.add(name)
                        changed = True
            elif isinstance(value, ast.Name) and value.id in builtins_bindings:
                for name in names:
                    if name not in builtins_bindings:
                        builtins_bindings.add(name)
                        changed = True

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in primitive_bindings
        ):
            return True
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            binding = _binding_name(node.value)
            if binding is not None:
                if (
                    binding in importlib_bindings
                    and node.attr in {"import_module", "__import__"}
                ):
                    return True
                if binding in builtins_bindings and node.attr == "__import__":
                    return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
        ):
            binding = _binding_name(node.args[0])
            attribute = _constant_string(node.args[1])
            if (
                binding in importlib_bindings
                and attribute in {"import_module", "__import__"}
            ):
                return True
            if binding in builtins_bindings and attribute == "__import__":
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

    def test_all_application_sources_have_zero_static_or_programmatic_v4_imports(self):
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
        rejected_programmatic_forms = (
            '__import__("services" + ".v4_platform")',
            'load = __import__\nload("services" + ".v4_platform")',
            '(load := __import__)("services" + ".v4_platform")',
            'import importlib\nimportlib.import_module("services" + ".v4_platform")',
            'import importlib as il\nil.import_module("services" + ".v4_platform")',
            'import importlib as il\nload = il.import_module\nload("services" + ".v4_platform")',
            'import importlib as il\nfirst = il.import_module\nsecond = first\nsecond("services" + ".v4_platform")',
            'import importlib\nmodule_loader = importlib\nmodule_loader.import_module("services" + ".v4_platform")',
            'import importlib\n(module_loader := importlib).import_module("services" + ".v4_platform")',
            'from importlib import import_module as load\nload("services" + ".v4_platform")',
            'import importlib\nimportlib.__import__("services" + ".v4_platform")',
            'from importlib import __import__ as load\nload("services" + ".v4_platform")',
            'import builtins as bi\nbi.__import__("services" + ".v4_platform")',
            'import builtins\n(module_loader := builtins).__import__("services" + ".v4_platform")',
            'from builtins import __import__ as load\nload("services" + ".v4_platform")',
            'import importlib\ngetattr(importlib, "import_" + "module")("services" + ".v4_platform")',
            'import importlib\ngetattr(importlib, f"import_module")("services" + ".v4_platform")',
            'import importlib\ngetattr(importlib, f"import_{\'module\'}")("services" + ".v4_platform")',
            'import importlib\ngetattr((module_loader := importlib), "import_module")("services" + ".v4_platform")',
            'import builtins\ngetattr(builtins, "__import__")("services" + ".v4_platform")',
            'from importlib import *',
            'from builtins import *',
        )
        for source in rejected_programmatic_forms:
            with self.subTest(source=source):
                self.assertTrue(_uses_dynamic_import(ast.parse(source)))

        allowed_same_name_forms = (
            'def import_module(value):\n    return value\nimport_module("not.a.module")',
            'catalog.import_module("business.plugin")',
            'import importlib\nimportlib.invalidate_caches()',
            'from importlib import invalidate_caches as refresh\nrefresh()',
            'import builtins\nbuiltins.len(items)',
            'ERROR = "services.v4_platform is forbidden"',
        )
        for source in allowed_same_name_forms:
            with self.subTest(source=source):
                self.assertFalse(_uses_dynamic_import(ast.parse(source)))

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
