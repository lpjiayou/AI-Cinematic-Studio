import json
import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPOSITORY_ROOT / "apps" / "creator-workspace-mvp"
INDEX_PATH = APP_ROOT / "index.html"
STYLES_PATH = APP_ROOT / "styles.css"
SCRIPT_PATH = APP_ROOT / "app.js"


class CreatorWorkspaceMvpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = INDEX_PATH.read_text(encoding="utf-8")
        cls.styles = STYLES_PATH.read_text(encoding="utf-8")
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")
        match = re.search(
            r'<script type="application/json" id="creator-fixture">\s*(.*?)\s*</script>',
            cls.index,
            flags=re.DOTALL,
        )
        if match is None:
            raise AssertionError("Embedded Creator Workspace fixture was not found")
        cls.fixture = json.loads(match.group(1))

    def assert_markers_in_order(self, text, markers):
        positions = [text.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions), markers)

    def test_static_application_files_exist(self):
        self.assertTrue(INDEX_PATH.is_file())
        self.assertTrue(STYLES_PATH.is_file())
        self.assertTrue(SCRIPT_PATH.is_file())

    def test_shell_002_metadata_and_exact_canonical_route_contract(self):
        self.assertEqual(self.fixture["meta"]["taskId"], "ACS-CREATOR-SHELL-002")
        self.assertEqual(
            self.fixture["meta"]["implementationVersion"],
            "Frontend Skeleton V1.0",
        )
        expected_routes = [
            "/creator",
            "/creator/ai-director",
            "/creator/projects",
            "/creator/projects/new",
            "/creator/assets",
            "/creator/create",
            "/creator/works",
            "/creator/projects/:projectRef/overview",
            "/creator/projects/:projectRef/planning/director",
            "/creator/projects/:projectRef/planning/series",
            "/creator/projects/:projectRef/planning/bible",
            "/creator/projects/:projectRef/planning/characters",
            "/creator/projects/:projectRef/planning/continuity",
            "/creator/projects/:projectRef/episodes",
            "/creator/projects/:projectRef/episodes/:episodeRef",
            "/creator/projects/:projectRef/episodes/:episodeRef/story",
            "/creator/projects/:projectRef/episodes/:episodeRef/script",
            "/creator/projects/:projectRef/episodes/:episodeRef/consistency",
            "/creator/projects/:projectRef/production/storyboard",
            "/creator/projects/:projectRef/production/shots",
            "/creator/projects/:projectRef/production/scenes",
            "/creator/projects/:projectRef/production/assets",
            "/creator/projects/:projectRef/production/jobs",
            "/creator/projects/:projectRef/post/timeline",
            "/creator/projects/:projectRef/post/preview",
            "/creator/projects/:projectRef/post/qc",
            "/creator/projects/:projectRef/post/approvals",
            "/creator/projects/:projectRef/delivery/masters",
            "/creator/projects/:projectRef/delivery/exports",
            "/creator/projects/:projectRef/delivery/series",
            "/creator/projects/:projectRef/delivery/release",
            "/creator/projects/:projectRef/delivery/analytics",
        ]
        route_block = re.search(
            r"const canonicalRouteTemplates = Object\.freeze\(\[(.*?)\]\);",
            self.script,
            flags=re.DOTALL,
        ).group(1)
        actual_routes = re.findall(r'"(/creator(?:/[^\"]*)?)"', route_block)
        self.assertEqual(actual_routes, expected_routes)
        self.assertEqual(self.fixture["meta"]["canonicalRouteCount"], 32)
        self.assertNotIn(":id", route_block)
        self.assertIn(":projectRef", route_block)

    def test_shell_implements_exact_primary_navigation_order(self):
        expected_routes = [
            '/creator',
            '/creator/ai-director',
            '/creator/projects',
            '/creator/assets',
            '/creator/create',
            '/creator/works',
        ]
        primary_nav = re.search(
            r'<nav class="primary-nav".*?</nav>', self.index, flags=re.DOTALL
        ).group(0)
        self.assertEqual(
            re.findall(r'data-route="([^"]+)"', primary_nav), expected_routes
        )
        self.assert_markers_in_order(
            primary_nav,
            ("首页", "AI导演", "项目", "资产库", "创作中心", "作品"),
        )
        for forbidden in ("账户", "通知", "搜索", "任务"):
            self.assertNotIn(forbidden, primary_nav)

    def test_creation_center_has_exact_six_planned_modules_and_routes(self):
        routes = (
            "/creator/create/generation",
            "/creator/create/templates",
            "/creator/create/prompt-lab",
            "/creator/create/audio",
            "/creator/create/models",
            "/creator/create/tools",
        )
        labels = (
            "图片与视频",
            "模板",
            "提示词实验",
            "声音实验",
            "创意实验",
            "快捷工具",
        )
        creation_block = self.script.split("const creationModules", 1)[1].split("]);", 1)[0]
        self.assert_markers_in_order(creation_block, routes)
        self.assert_markers_in_order(creation_block, labels)
        self.assertIn("探索创意能力，不越过制作门禁", self.script)
        self.assertIn('class="creation-r1-grid"', self.script)
        self.assertIn("creationModules.map", self.script)
        self.assertIn("尚未启用", self.script)
        self.assertNotIn("即将上线", self.script)

    def test_project_workspace_includes_script_studio_and_default_pipeline(self):
        keys = (
            'key: "overview"',
            'key: "project-director"',
            'key: "series-planning"',
            'key: "bible"',
            'key: "characters"',
            'key: "continuity"',
            'key: "episodes"',
            'key: "story"',
            'key: "script"',
            'key: "consistency"',
            'key: "storyboard"',
            'key: "shots"',
            'key: "scenes"',
            'key: "project-assets"',
            'key: "jobs"',
            'key: "timeline"',
            'key: "preview"',
            'key: "qc"',
            'key: "approvals"',
            'key: "masters"',
            'key: "exports"',
            'key: "series-delivery"',
            'key: "release"',
            'key: "analytics"',
        )
        self.assert_markers_in_order(self.script, keys)
        self.assertIn('const projectShellBase = "/creator/project-shell"', self.script)
        self.assertIn("resolveSelectedProductionContext", self.script)
        self.assertIn("renderEpisodeSelector", self.script)
        self.assertNotIn('Project Context = NULL', self.script)
        self.assertNotIn("fixture-project-x2-e001", f"{self.index}\n{self.script}")
        self.assertNotIn("projectRef", self.fixture["referenceContext"])

    def test_pipeline_has_exact_eleven_stages_and_non_orchestration_boundary(self):
        stages = self.fixture["pipeline"]
        self.assertEqual(
            [stage["label"] for stage in stages],
            [
                "Idea",
                "Story",
                "IP Bible",
                "Character",
                "Storyboard",
                "Assets",
                "Audio",
                "Timeline",
                "Preview",
                "Approval",
                "Export",
            ],
        )
        required_fields = {
            "localKey",
            "label",
            "status",
            "source",
            "blocker",
            "evidence",
            "route",
            "allowed",
            "forbidden",
        }
        self.assertTrue(all(required_fields <= set(stage) for stage in stages))
        self.assertIn("PIPELINE VIEW / NO ORCHESTRATION", self.script)
        self.assertIn("页面不会自动推进", self.script)
        self.assertNotIn('data-action="advance-pipeline-stage"', self.script)

    def test_feature_states_and_navigation_badges_are_separated(self):
        state_block = re.search(
            r"const featureStates = Object\.freeze\(\{(.*?)\}\);",
            self.script,
            flags=re.DOTALL,
        ).group(1)
        self.assert_markers_in_order(
            state_block,
            ('available:', 'fixture:', 'development:', 'planned:', 'disabled:'),
        )
        self.assertIn('label: "Available"', state_block)
        self.assertIn('label: "Available - Fixture Only"', state_block)
        self.assertIn('label: "In Development"', state_block)
        self.assertIn('label: "Planned"', state_block)
        self.assertIn('label: "Disabled"', state_block)
        self.assertIn('available: { label: "Available", badge: ""', state_block)
        for badge in ("Fixture Only", "In Development", "Planned", "Disabled"):
            self.assertIn(badge, state_block)
        self.assertIn("governance-badge", self.script)

    def test_fixture_boundary_is_persistent_and_machine_readable(self):
        self.assertIn("FIXTURE ONLY", self.index)
        self.assertIn("NOT A DOMAIN FACT", self.index)
        self.assertIn('v5Connection": "not-connected"', self.index)
        self.assertNotIn("V5 NOT CONNECTED", self.index.split('<script type="application/json"', 1)[0])
        self.assertEqual(
            self.fixture["meta"]["classification"],
            ["FIXTURE ONLY", "NOT A DOMAIN FACT"],
        )
        self.assertEqual(self.fixture["meta"]["mode"], "fixture-only")
        self.assertEqual(self.fixture["meta"]["persistence"], "session-only")
        self.assertEqual(self.fixture["meta"]["v5Connection"], "not-connected")
        self.assertFalse(self.fixture["meta"]["domainFact"])

    def test_fixture_keys_are_explicitly_non_domain_keys(self):
        keys = [
            self.fixture["workspace"]["localKey"],
            self.fixture["referenceContext"]["localKey"],
            self.fixture["character"]["localKey"],
            self.fixture["preview"]["localKey"],
            *[stage["localKey"] for stage in self.fixture["pipeline"]],
            *[asset["localKey"] for asset in self.fixture["assets"]],
            *[shot["localKey"] for shot in self.fixture["shots"]],
        ]
        self.assertTrue(all(key.startswith("fixture-") for key in keys))
        self.assertNotIn('localKey: `local-project-${state.localDraftCounter}`', self.script)

    def test_episode_fixture_has_six_contiguous_shots_and_45_seconds(self):
        shots = self.fixture["shots"]
        self.assertEqual(len(shots), 6)
        self.assertEqual(
            [shot["code"] for shot in shots],
            ["F01", "F02", "F03", "F04", "F05", "F06"],
        )
        self.assertEqual(sum(shot["duration"] for shot in shots), 45)
        self.assertEqual(shots[0]["start"], 0)
        self.assertEqual(shots[-1]["end"], 45)
        for index, shot in enumerate(shots):
            self.assertEqual(shot["end"] - shot["start"], shot["duration"])
            if index:
                self.assertEqual(shots[index - 1]["end"], shot["start"])
        self.assertEqual(shots[-1]["secondaryCaptionWindow"], "42.0–45.0s")
        self.assertEqual(
            shots[-1]["secondaryCaption"],
            "虚构角色 · 情绪内容不替代专业支持",
        )

    def test_asset_library_has_exact_tabs_and_planned_generation_history(self):
        tabs = (
            '["basic", "基础信息"]',
            '["versions", "版本"]',
            '["usage", "使用记录"]',
            '["rights", "权利"]',
            '["history", "生成记录"]',
        )
        self.assert_markers_in_order(self.script, tabs)
        self.assertIn("生成记录 · 尚未启用", self.script)
        self.assertIn("当前没有可展示记录", self.script)
        self.assertNotIn("Prompt 001", self.script)

    def test_media_fixture_paths_resolve_to_current_local_evidence(self):
        relative_sources = [
            self.fixture["character"]["referenceImage"],
            self.fixture["preview"]["src"],
            self.fixture["preview"]["poster"],
            *[asset["src"] for asset in self.fixture["assets"]],
            *[shot["image"] for shot in self.fixture["shots"]],
        ]
        missing = [
            source
            for source in relative_sources
            if not (APP_ROOT / source).resolve().is_file()
        ]
        self.assertEqual(missing, [])

    def test_preview_is_bound_to_verified_local_candidate(self):
        preview = self.fixture["preview"]
        self.assertEqual(preview["duration"], "45.0 秒")
        self.assertEqual(preview["dimensions"], "1080 × 1920")
        self.assertEqual(preview["frameRate"], "30 fps")
        self.assertEqual(preview["audio"], "无音轨")
        self.assertEqual(
            preview["sha256"],
            "102A8CFCAAAE9D86D70A2E5BC7C0D03738B6FB6FE71BC734EE1DFD97FFE74D47",
        )
        self.assertIn("候选预览", self.script)
        self.assertIn("尚未正式导出", self.script)
        self.assertIn('id="candidate-video"', self.script)

    def test_export_page_and_actions_are_disabled(self):
        self.assertIn('key: "exports", label: "导出"', self.script)
        self.assertIn('type: "export-shell", status: "disabled"', self.script)
        self.assertIn('"export-shell": ["导出", "未来从已接受成片建立交付产物。"', self.script)
        self.assertIn('route.status === "disabled"', self.script)
        self.assertNotIn("download=", self.index)

    def test_sticky_bar_is_the_only_page_level_primary_action(self):
        self.assertIn('<footer class="sticky-action-bar"', self.index)
        self.assertIn('function renderStickyBar(route)', self.script)
        whitelist = self.script.split("function shouldRenderStickyBar(route)", 1)[1].split(
            "function renderStickyBar(route)", 1
        )[0]
        for route_type in ("dashboard", "ai-director", "episode-project", "script-studio"):
            self.assertIn(f'"{route_type}"', whitelist)
        for route_type in ("projects", "assets", "creation", "creation-preview", "works", "project-overview"):
            self.assertNotIn(f'"{route_type}"', whitelist)
        self.assertIn('stickyActionBar.hidden = !visible', self.script)
        self.assertIn('classList.toggle("no-sticky-bar", !visible)', self.script)

    def test_app_shell_exposes_required_regions_and_components(self):
        shell_markers = (
            'class="sidebar"',
            'class="global-header"',
            'id="context-navigation"',
            'id="app-content"',
            'class="inspector"',
            'class="sticky-action-bar"',
        )
        for marker in shell_markers:
            self.assertIn(marker, self.index)
        component_markers = (
            ".button",
            ".card",
            ".badge",
            ".modal",
            ".inspector",
            ".toast",
            ".empty-state",
            ".loading-state",
            ".error-state",
            ".phone-frame",
            ".sticky-action-bar",
            ".button-text",
            ".button-danger",
            ".button-spinner",
        )
        for marker in component_markers:
            self.assertIn(marker, self.styles)

    def test_design_tokens_include_required_semantic_and_lifecycle_groups(self):
        for token in (
            "--color-brand: #165dff",
            "--color-page: #f5f7fa",
            "--color-surface: #ffffff",
            "--color-text: #1d2129",
            "--color-border: #e5e6eb",
            "--radius-control: 8px",
            "--radius-card: 12px",
            "--creator-lifecycle-candidate",
            "--creator-lifecycle-preview",
            "--creator-lifecycle-approved",
            "--creator-lifecycle-export",
            "--creator-governance-rights-blocked",
            "--font-sans",
            "--type-title-size",
            "--type-body-size",
            "--type-caption-size",
            "--creator-feature-available",
            "--creator-feature-fixture-only",
            "--creator-feature-in-development",
            "--creator-feature-planned",
            "--creator-feature-disabled",
        ):
            self.assertIn(token, self.styles)

    def test_ui_polish_presentation_contract_is_explicit_and_non_authoritative(self):
        self.assertEqual(
            self.fixture["meta"]["presentationTaskId"],
            "ACS-CREATOR-UI-POLISH-001",
        )
        self.assertEqual(
            self.fixture["meta"]["presentationVersion"],
            "High Fidelity UI Presentation V1.0",
        )
        for token in (
            "--color-background",
            "--color-canvas",
            "--color-panel",
            "--type-display-size",
            "--type-section-size",
            "--radius-panel",
            "--creator-lifecycle-fixture-only",
        ):
            self.assertIn(token, self.styles)
        for marker in (
            "enterprise-hero",
            "把创意推进为可确认的制作成果",
            "project-context-bar",
            "enterprise-shell-page",
            "workflow-action-bar",
            "asset-r1-layout",
            "尚未建立项目上下文",
        ):
            self.assertIn(marker, self.script)
        self.assertEqual(
            self.fixture["meta"]["v2PresentationTaskId"],
            "ACS-CREATOR-UI-V2-IMPLEMENTATION-001",
        )
        self.assertEqual(len(self.fixture["pipeline"]), 11)
        self.assertEqual(self.fixture["meta"]["canonicalRouteCount"], 32)
        self.assertFalse(self.fixture["meta"]["domainFact"])

    def test_v2_presentation_metadata_is_explicit(self):
        self.assertEqual(
            self.fixture["meta"]["v2PresentationTaskId"],
            "ACS-CREATOR-UI-V2-IMPLEMENTATION-001",
        )
        self.assertEqual(
            self.fixture["meta"]["v2PresentationVersion"],
            "Creator UI V2.0 High Fidelity Presentation",
        )
        self.assertFalse(self.fixture["meta"]["domainFact"])

    def test_v2_primary_navigation_uses_chinese_product_labels(self):
        primary_nav = re.search(
            r'<nav class="primary-nav".*?</nav>', self.index, flags=re.DOTALL
        ).group(0)
        self.assert_markers_in_order(
            primary_nav,
            ("首页", "AI导演", "项目", "资产库", "创作中心", "作品"),
        )
        for forbidden in ("Dashboard", "Projects", "Asset Library", "Works"):
            self.assertNotIn(forbidden, primary_nav)
        self.assertLessEqual(primary_nav.count('<span class="badge'), 1)

    def test_v2_dashboard_is_a_creation_cockpit(self):
        dashboard_block = self.script.split("function renderDashboard()", 1)[1].split(
            "function renderProjects", 1
        )[0]
        for marker in (
            "enterprise-hero",
            "制作指挥中心",
            "command-metrics",
            "最近分集",
            "真实存在的制作记录",
        ):
            self.assertIn(marker, dashboard_block)
        self.assertNotIn("统计仪表盘", dashboard_block)

    def test_v2_asset_library_uses_chinese_visual_categories(self):
        asset_block = self.script.split("function renderAssets()", 1)[1].split(
            "function renderCreationCenter", 1
        )[0]
        for label in ("角色", "场景", "图片", "视频", "音频", "模板"):
            self.assertIn(f'"{label}"', asset_block)
        for label in ("基础信息", "版本", "使用记录", "权利", "生成记录"):
            self.assertIn(f'"{label}"', asset_block)
        self.assertIn("asset-feature-card", asset_block)

    def test_v2_ai_director_uses_three_column_studio_contract(self):
        director_block = self.script.split("function renderAiDirector()", 1)[1].split(
            "function findPersistedEpisode", 1
        )[0]
        for marker in (
            "director-studio-grid",
            "director-brief-panel",
            "director-canvas-panel",
            "renderDirectorPlanning()",
        ):
            self.assertIn(marker, director_block)
        self.assertNotIn("chat", director_block.lower())

    def test_v2_preview_keeps_candidate_and_export_status_separate(self):
        preview_block = self.script.split("function renderPreview()", 1)[1].split(
            "function renderWorks", 1
        )[0]
        self.assertIn("candidate-preview-ribbon", preview_block)
        self.assertIn("候选预览", preview_block)
        self.assertIn("尚未正式导出", preview_block)
        self.assertIn('id="candidate-video"', preview_block)
        self.assertNotIn("正式成片", preview_block)

    def test_v2_engineering_boundary_is_machine_readable_but_not_static_visual_copy(self):
        static_shell = re.sub(
            r'<script type="application/json".*?</script>',
            "",
            self.index,
            flags=re.DOTALL,
        )
        static_shell = re.sub(
            r'<span class="sr-only">.*?</span>',
            "",
            static_shell,
            flags=re.DOTALL,
        )
        for forbidden in (
            "FIXTURE ONLY",
            "NOT A DOMAIN FACT",
            "V5 NOT CONNECTED",
            "SESSION ONLY",
            "ASSET LIBRARY",
            "Generation History",
            "Rights HOLD",
            "Inspector",
            "Dashboard",
            "Projects",
            "Works",
        ):
            self.assertIsNone(
                re.search(rf"\b{re.escape(forbidden)}\b", static_shell),
                forbidden,
            )
        self.assertIn("FIXTURE ONLY", self.index)
        self.assertIn("NOT A DOMAIN FACT", self.index)

    def test_ai_director_fixture_metadata_and_status_contract(self):
        self.assertEqual(
            self.fixture["meta"]["capabilityTaskId"],
            "ACS-CREATOR-AI-DIRECTOR-001",
        )
        self.assertEqual(
            self.fixture["meta"]["capabilityVersion"],
            "AI Director Real Intelligence Phase 1",
        )
        director = self.fixture["aiDirector"]
        self.assertEqual(director["route"], "/creator/ai-director")
        self.assertEqual(director["featureStatus"], "In Development")
        self.assertEqual(director["pageStatus"], "Available")
        self.assertEqual(
            director["classification"],
            ["CANDIDATE CREATIVE PLAN", "HUMAN CONFIRMATION REQUIRED", "SESSION ONLY"],
        )
        self.assertEqual(director["persistence"], "session-only")

    def test_ai_director_route_is_a_fixture_renderer_not_a_placeholder(self):
        self.assertIn(
            '{ key: "ai-director", path: "/creator/ai-director", label: "AI导演", english: "AI Director", status: "available" }',
            self.script,
        )
        self.assertIn('type: "ai-director"', self.script)
        self.assertIn('"ai-director": renderAiDirector', self.script)
        self.assertIn('function renderAiDirector()', self.script)
        self.assertIn('aria-label="AI导演"', self.index)

    def test_ai_director_creative_brief_has_all_local_fixture_fields(self):
        defaults = self.fixture["aiDirector"]["briefDefaults"]
        self.assertEqual(
            defaults,
            {
                "topic": "孤独与陪伴",
                "theme": "情感短片",
                "audience": "短视频用户",
                "duration": "30秒",
                "platform": "短视频平台",
                "style": "电影感",
                "character": "晚灯 WANLIGHT",
            },
        )
        for field in defaults:
            self.assertIn(f'["{field}",', self.script)
            self.assertIn(f'name="${{escapeHtml(key)}}"', self.script)
        self.assertIn('id="ai-director-form"', self.script)
        self.assertIn("通过安全服务整理方案，结果需人工确认", self.script)
        self.assertNotIn("NO AI MODEL CONNECTED", self.index)

    def test_ai_director_canvas_uses_validated_candidate_plan(self):
        self.assertNotIn("output", self.fixture["aiDirector"])
        self.assertIn("state.aiDirectorPlan", self.script)
        self.assertIn('plan.schemaVersion === "creator.ai-director.plan.v1"', self.script)
        for marker in (
            "故事方向",
            "剧本草案",
            "分镜规划",
            "视觉风格",
            "制作规划",
        ):
            self.assertIn(marker, self.script)

    def test_ai_director_handoff_uses_v5_owned_series_episode_objects(self):
        for marker in (
            'const seriesEndpoint = "/creator/internal/series"',
            'const confirmCreativePlanEndpoint = "/creator/internal/creative-plans/confirm"',
            'const episodesEndpoint = "/creator/internal/episodes"',
            "function createSeriesEpisode(form)",
            "creativePlanRef: state.confirmedCreativePlan.creativePlanRef",
            'navigate(`/creator/projects/${encodeURIComponent(episodePayload.episode.episodeRef)}`)',
            'type: "episode-project"',
            "系列与单集来自正式应用边界",
            "当前不是正式项目，也不会创建制作任务",
        ):
            self.assertIn(marker, f"{self.index}\n{self.script}")
        self.assertNotIn("createProjectEntity(", self.script)
        self.assertNotIn("Creator Application Project", self.script)

    def test_ai_director_uses_only_same_origin_application_endpoints(self):
        combined = f"{self.index}\n{self.script}"
        forbidden = (
            "OpenAI",
            "DeepSeek",
            "modelRouter",
            "promptBackend",
            "XMLHttpRequest",
            "localStorage",
            "sessionStorage",
            "/api/",
        )
        for marker in forbidden:
            self.assertNotIn(marker, combined)
        self.assertEqual(self.script.count("fetch("), 1)
        self.assertIn('const aiDirectorEndpoint = "/creator/internal/ai-director/plan"', self.script)
        self.assertIn('const seriesEndpoint = "/creator/internal/series"', self.script)
        self.assertNotIn("api.deepseek.com", combined)
        self.assertNotIn("PROVIDER_API_KEY", combined)

    def test_ai_director_polish_has_chinese_header_and_statuses(self):
        for marker in (
            "AI导演",
            "从创意输入到导演方案与制作规划，在一个工作台里完成",
            "开发中",
            "演示版本",
        ):
            self.assertIn(marker, f"{self.index}\n{self.script}")

    def test_ai_director_polish_has_exact_chinese_brief_labels(self):
        director_block = self.script.split("function renderAiDirector()", 1)[1].split(
            "function findPersistedEpisode", 1
        )[0]
        for label in (
            "主题",
            "类型",
            "目标用户",
            "视频时长",
            "发布平台",
            "视觉风格",
            "角色设定",
        ):
            self.assertIn(f'"{label}"', director_block)
        self.assertIn("生成创意方案", director_block)
        self.assertIn("通过安全服务整理方案，结果需人工确认", director_block)

    def test_ai_director_polish_has_four_product_cards_without_repeated_demo_labels(self):
        canvas_block = self.script.split("function renderDirectorCanvas()", 1)[1].split(
            "function renderAiDirector", 1
        )[0]
        self.assertEqual(canvas_block.count('class="director-output-card'), 4)
        self.assertEqual(canvas_block.count('class="director-card-labels"'), 0)
        for marker in (
            "故事方向",
            "剧本草案",
            "分镜规划",
            "视觉风格",
        ):
            self.assertIn(marker, canvas_block)
        self.assertIn("制作规划", self.script)

    def test_ai_director_polish_hides_english_boundary_statuses_from_user_views(self):
        visible_director_blocks = "\n".join(
            (
                self.script.split("function renderDirectorCanvas()", 1)[1].split(
                    "function renderAiDirector", 1
                )[0],
                self.script.split("function renderAiDirector()", 1)[1].split(
                    "function findPersistedEpisode", 1
                )[0],
            )
        )
        for marker in (
            "Fixture Only",
            "NOT A DOMAIN FACT",
            "NO AI MODEL CONNECTED",
            "SESSION ONLY",
        ):
            self.assertNotIn(marker, visible_director_blocks)

    def test_ai_director_feedback_preserves_candidate_and_non_canonical_boundaries(self):
        for marker in (
            "候选导演方案已生成 · 请完成人工确认",
            "导演方案已完成人工确认",
            "系列与集数已创建",
            "不建立正式项目",
            "不会建立正式项目或启动制作任务",
        ):
            self.assertIn(marker, self.script)
        for prohibited_claim in (
            "AI已生成",
            "生成完成",
            "正式方案",
            "生产计划完成",
        ):
            self.assertNotIn(prohibited_claim, self.script)

    def test_ai_director_presentation_components_are_styled(self):
        for marker in (
            ".director-status-rail",
            ".director-workspace",
            ".director-brief-form",
            ".director-canvas-panel",
            ".director-output-grid",
            ".director-handoff-callout",
            ".draft-handoff-card",
        ):
            self.assertIn(marker, self.styles)
        self.assertIn('@media (max-width: 760px)', self.styles)

    def test_v21_product_polish_metadata_is_explicit_and_bounded(self):
        meta = self.fixture["meta"]
        self.assertEqual(meta["v21PolishTaskId"], "ACS-CREATOR-UI-V2-POLISH-002")
        self.assertEqual(meta["v21PresentationVersion"], "Creator UI V2.1 Product Polish")
        self.assertEqual(meta["v2CloseoutTaskId"], "ACS-CREATOR-UI-V2-FINAL-CLOSEOUT-003")
        self.assertEqual(meta["v2CloseoutVersion"], "Creator UI V2 Final Visual Closeout")
        self.assertEqual(meta["mode"], "fixture-only")
        self.assertFalse(meta["domainFact"])
        self.assertEqual(meta["v5Connection"], "not-connected")

    def test_v21_has_one_primary_demo_status_entry_without_sidebar_noise(self):
        body_before_fixture = self.index.split(
            '<script type="application/json" id="creator-fixture">', 1
        )[0]
        self.assertEqual(body_before_fixture.count("<strong>内部内容实验室</strong>"), 1)
        self.assertNotIn("Internal Content Lab", body_before_fixture)
        self.assertEqual(body_before_fixture.count('class="global-demo-status fixture-banner"'), 1)
        self.assertNotIn('class="scope-card"', body_before_fixture)
        self.assertIn('class="sr-only page-fixture-contract">演示数据', self.script)
        self.assertIn("if (statusKey === \"fixture\") return '<span class=\"sr-only\">", self.script)

    def test_v21_eight_review_surfaces_have_dedicated_renderers(self):
        renderer_block = self.script.split("const renderers = {", 1)[1].split("};", 1)[0]
        for marker in (
            "dashboard: renderDashboard",
            '"ai-director": renderAiDirector',
            "assets: renderAssetsR1",
            "creation: renderCreationCenterR1",
            "works: renderWorksR1",
            '"project-overview": () => renderEnterpriseShellPage(resolved)',
            '"storyboard-shell": () => renderEnterpriseShellPage(resolved)',
            '"preview-shell": () => renderEnterpriseShellPage(resolved)',
        ):
            self.assertIn(marker, renderer_block)
        for route in (
            "/creator",
            "/creator/ai-director",
            "/creator/projects/:projectRef/overview",
            "/creator/assets",
            "/creator/projects/:projectRef/production/storyboard",
            "/creator/projects/:projectRef/post/preview",
            "/creator/create",
            "/creator/works",
        ):
            self.assertIn(route, self.script)

    def test_v21_inspector_is_collapsible_and_compact_width_uses_drawer(self):
        for marker in (
            'class="inspector-fab"',
            'class="button button-secondary inspector-toggle-label"',
            "function applyInspectorState()",
            'button.textContent = label',
            'inspector.setAttribute("aria-hidden", String(!open))',
            'window.matchMedia("(max-width: 1439px)")',
            '@media (max-width: 1439px)',
            '.inspector.is-open',
            'transform: translateX(105%)',
            'inspectorOpen: false',
            'state.inspectorOpen = !compactInspectorQuery.matches && ["project-shell", "episode"].includes(resolved.context)',
            '.workbench.has-context-nav.inspector-closed',
        ):
            self.assertIn(marker, f"{self.index}\n{self.script}\n{self.styles}")
        self.assertIn("grid-template-columns: var(--context-width) minmax(0, 1fr);", self.styles)

    def test_v21_product_copy_preserves_fixture_and_export_boundaries(self):
        for marker in (
            "正式项目记录",
            "统一管理角色、场景、图片、视频和声音资产。",
            "让复杂创作变得更简单",
            "候选预览",
            "尚未正式导出",
            "制作中",
            "可预览",
            "完成作品",
            "当前不会生成文件、下载内容或执行发布",
        ):
            self.assertIn(marker, self.script)
        for marker in (
            "AI已生成",
            "生成完成",
            "正式方案",
            "生产计划完成",
        ):
            self.assertNotIn(marker, self.script)

    def test_closeout_removes_human_authority_engineering_label_from_visible_ui(self):
        self.assertNotIn("HUMAN AUTHORITY REQUIRED", self.script)
        self.assertIn('localizedStatusBadge("需要人工确认", "neutral")', self.script)
        self.assertIn("该页面用于展示人工确认要求。界面和技术检查不会自动完成批准。", self.script)
        self.assertIn("等待人工确认", self.script)

    def test_closeout_keeps_engineering_boundaries_out_of_default_visual_layer(self):
        self.assertIn('class="sr-only page-fixture-contract">演示数据', self.script)
        self.assertIn('class="sr-only">导出能力尚未实现', self.script)
        self.assertIn('document.title = `${resolved.label || "创作空间"} · AI Cinematic Studio`', self.script)
        self.assertNotIn("· Creator Workspace`", self.script)

    def test_closeout_generation_center_is_a_product_preview_not_generic_placeholder(self):
        self.assertIn('type: "creation-preview"', self.script)
        for marker in (
            "把文字、参考画面和创作意图转化为可使用的影视素材。",
            "图片生成",
            "视频生成",
            "声音生成",
            "描述你想创建的画面……",
            'id="generation-preview-input" disabled',
        ):
            self.assertIn(marker, self.script)

    def test_closeout_template_library_has_six_non_executable_previews(self):
        block = self.script.split('if (route.key === "templates")', 1)[1].split(
            'if (route.key === "ip-studio")', 1
        )[0]
        for marker in (
            "情绪短片",
            "角色独白",
            "商品电影广告",
            "奇幻叙事",
            "人物预告片",
            "竖屏剧情片",
            "尚未启用",
        ):
            self.assertIn(marker, block)
        self.assertIn("template-preview-grid", block)

    def test_closeout_ip_studio_uses_only_existing_wanlight_fixture_structure(self):
        block = self.script.split('if (route.key === "ip-studio")', 1)[1].split(
            'if (route.key === "memory")', 1
        )[0]
        for marker in (
            "IP工作室",
            "晚灯",
            "陪伴型夜灯角色",
            "夜晚书桌 / 安静陪伴",
            "深蓝兜帽 / 暖色灯面 / 月牙标识",
            "人物关系",
            "时间线",
        ):
            self.assertIn(marker, block)

    def test_closeout_workflow_preview_has_six_stages_and_no_engine_actions(self):
        block = self.script.split('if (route.key === "workflow-presets")', 1)[1].split(
            'const charts =', 1
        )[0]
        for marker in ("创意", "角色", "分镜", "画面", "声音", "预览"):
            self.assertIn(marker, block)
        self.assertIn("情绪短片流程", block)
        self.assertIn("角色故事流程", block)
        self.assertEqual(block.count('type="button" disabled'), 2)
        self.assertNotIn("startWorkflow", block)

    def test_closeout_analytics_is_an_honest_empty_state_without_fake_metrics(self):
        block = self.script.split('const charts = ["作品表现趋势"', 1)[1].split(
            "function renderDirectorBriefField", 1
        )[0]
        self.assertIn("暂无真实数据", block)
        self.assertIn("当前没有可展示的真实运营数据", block)
        for marker in ("播放量", "GMV", "收入", "转化率", "粉丝增长"):
            self.assertNotIn(marker, block)

    def test_closeout_ai_director_empty_state_previews_four_outputs_without_loading(self):
        block = self.script.split('if (state.aiDirectorPhase === "input")', 1)[1].split(
            'if (state.aiDirectorPhase === "generating")', 1
        )[0]
        self.assertIn("导演方案将在这里生成", block)
        self.assertIn("完成左侧创意输入后", block)
        for marker in ("故事方向", "剧本草案", "分镜规划", "视觉风格"):
            self.assertIn(marker, block)
        self.assertIn("director-preview-tiles", block)
        self.assertNotIn("renderLoadingState", block)

    def test_closeout_localizes_pipeline_evidence_instead_of_rendering_raw_fixture_text(self):
        block = self.script.split("function renderPipeline()", 1)[1].split(
            "function renderAssetGrid", 1
        )[0]
        self.assertIn("const evidenceLabels =", block)
        self.assertIn("evidenceLabels[selected.label]", block)
        self.assertNotIn("selected.evidence", block)

    def test_closeout_localizes_asset_usage_instead_of_rendering_raw_fixture_text(self):
        block = self.script.split("function assetTabContent()", 1)[1].split(
            "function renderAssets", 1
        )[0]
        self.assertIn("const usageLabel =", block)
        self.assertIn("usageLabel(asset)", block)
        self.assertNotIn("asset.usedBy", block)

    def test_closeout_inspector_controls_only_render_on_supported_routes(self):
        self.assertIn("function routeSupportsInspector(route)", self.script)
        self.assertIn("const showInspectorControl = routeSupportsInspector(route)", self.script)
        self.assertIn("inspectorFab.hidden = open || !supported", self.script)
        self.assertIn("compactInspectorQuery.matches && state.inspectorOpen", self.script)

    def test_application_has_no_network_persistence_or_lower_layer_imports(self):
        combined = f"{self.index}\n{self.script}"
        forbidden = (
            "XMLHttpRequest",
            "WebSocket",
            "EventSource",
            "sendBeacon",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "services/v5_core_os",
            "/api/",
            "V3.5 Audio Core",
            "Final Composition",
        )
        for marker in forbidden:
            self.assertNotIn(marker, combined)
        self.assertEqual(self.script.count("fetch("), 1)
        self.assertIn('requestApplicationJson(aiDirectorEndpoint, {', self.script)
        self.assertIn('requestApplicationJson(withWorkspace(seriesEndpoint))', self.script)
        self.assertIn('const aiDirectorEndpoint = "/creator/internal/ai-director/plan"', self.script)
        self.assertNotIn("https://", self.script)

    def test_page_has_no_remote_runtime_dependencies(self):
        remote_references = re.findall(r'(?:src|href)="https?://', self.index)
        self.assertEqual(remote_references, [])
        self.assertNotIn("import(", self.script)
        self.assertNotIn("require(", self.script)

    def test_accessibility_and_responsive_contract_markers_exist(self):
        for marker in (
            'class="skip-link"',
            'aria-live="polite"',
            'aria-label="上下文导航"',
            'aria-label="详情"',
            'aria-labelledby="project-dialog-title"',
            "prefers-reduced-motion",
            ":focus-visible",
        ):
            self.assertIn(marker, f"{self.index}\n{self.styles}")
        self.assertIn('projectDialog.addEventListener("close"', self.script)
        self.assertIn('event.key === "Escape"', self.script)
        self.assertIn('aria-controls="asset-detail-panel"', self.script)
        self.assertIn('aria-labelledby="asset-tab-${escapeHtml(state.assetTab)}"', self.script)
        for key in ("ArrowLeft", "ArrowRight", "Home", "End"):
            self.assertIn(f'"{key}"', self.script)
        self.assertIn("sidebar.inert = mobile && !open", self.script)
        self.assertIn("inspector.inert = !open", self.script)
        self.assertIn(
            'window.matchMedia("(max-width: 1439px)")', self.script
        )
        self.assertIn("state.mobileSidebarOpen && event.key === \"Tab\"", self.script)
        self.assertNotIn(
            ".sidebar-collapsed .brand-copy,\n.sidebar-collapsed .sidebar-collapse-button,",
            self.styles,
        )
        primary_nav = re.search(
            r'<nav class="primary-nav".*?</nav>', self.index, flags=re.DOTALL
        ).group(0)
        self.assertEqual(primary_nav.count('aria-label='), 7)
        self.assertIn('aria-label="项目创建步骤"', self.index)
        self.assertIn('aria-label="版本、任务与活动"', self.index)

    def test_loading_and_error_states_do_not_claim_backend_progress(self):
        self.assertIn("function renderLoadingState(label)", self.script)
        self.assertIn("function renderErrorState(title, description)", self.script)
        self.assertIn("function renderButtonLoading(label)", self.script)
        self.assertIn('aria-busy="true"', self.script)
        self.assertIn('id="preview-error" hidden', self.script)
        self.assertIn('role="alert"', self.script)
        self.assertNotIn("progressPercent", self.script)

    def test_m3_script_studio_is_project_scoped_and_uses_same_origin_application_boundary(self):
        self.assertIn('key: "script", label: "剧本"', self.script)
        self.assertIn('if (pageKey === "script") return { ...baseRoute, type: "script-studio" };', self.script)
        for endpoint in (
            'const scriptWorkspaceEndpoint = "/creator/internal/script-studio"',
            '`${scriptWorkspaceEndpoint}/generate`',
            '`${scriptWorkspaceEndpoint}/manual-version`',
            '`${scriptWorkspaceEndpoint}/rewrite-scene`',
            '`${scriptWorkspaceEndpoint}/confirm`',
            '`${scriptWorkspaceEndpoint}/storyboard-bootstrap`',
        ):
            self.assertIn(endpoint, self.script)
        self.assertNotIn("deepseek.com", self.script.lower())
        self.assertNotIn("PROVIDER_API_KEY", self.script)

    def test_m3_script_studio_renders_source_editor_version_and_confirmation_states(self):
        for marker in (
            'data-script-state="${generating ? "generating" : state.scriptError ? "error" : "empty"}"',
            'state.scriptPhase === "generating"',
            'id="script-edit-form"',
            'id="script-rewrite-form"',
            'data-action="generate-script"',
            'data-action="select-script-version"',
            'data-action="select-script-scene"',
            'data-action="confirm-script-version"',
            "生成正式剧本",
            "保存为新版本",
            "改写当前场景",
            "版本历史",
            "等待人工确认",
        ):
            self.assertIn(marker, self.script)
        self.assertIn("保存会创建新的不可变剧本版本", self.script)

    def test_m3_script_studio_preserves_human_and_downstream_gates(self):
        self.assertIn("生成成功不代表人工确认", self.script)
        self.assertIn("确认只更新引用，不会改写任何历史版本", self.script)
        self.assertIn("草稿版本不会开放分镜输入", self.script)
        self.assertIn("仍需角色与 IP 能力完成绑定，不会开始分镜生产", self.script)
        self.assertNotIn("开始分镜生产</button>", self.script)

    def test_m3_script_studio_styles_are_capability_scoped_and_responsive(self):
        for selector in (
            ".script-source-layout",
            ".script-studio-layout",
            ".script-scenes-panel",
            ".script-editor-panel",
            ".script-versions-panel",
            ".script-rewrite-form",
            ".storyboard-bridge-card",
        ):
            self.assertIn(selector, self.styles)
        self.assertIn("@media (max-width: 900px)", self.styles)

    def test_story_route_renders_read_only_confirmed_plan_projection(self):
        self.assertIn('key: "story", label: "故事"', self.script)
        self.assertIn('if (pageKey === "story") return { ...baseRoute, type: "story-view" };', self.script)
        self.assertIn('type: "story-shell"', self.script)
        self.assertIn('"story-view": () => renderStoryView(resolved)', self.script)
        self.assertIn('const storyViewSchemaVersion = "creator.story-view.v1"', self.script)
        for marker in (
            "function buildStoryProjection(route)",
            "episode.confirmedPlanBinding",
            "binding.sourcePlan",
            "seriesRef: series.seriesRef",
            "episodeRef: episode.episodeRef",
            "sourcePlanRef: binding.sourcePlanRef",
            "sourcePlanSchemaVersion: binding.sourcePlanSchemaVersion",
            "sourcePlanVersion: binding.sourcePlanVersion",
        ):
            self.assertIn(marker, self.script)

    def test_story_projection_does_not_create_provider_or_fixture_authority(self):
        projection = self.script.split("function buildStoryProjection(route)", 1)[1].split(
            "function renderStoryView(route)", 1
        )[0]
        for forbidden in (
            "fixture.",
            "fetch(",
            "provider",
            "DeepSeek",
            "StoryRepository",
            "localStorage",
            "sessionStorage",
        ):
            self.assertNotIn(forbidden, projection)
        self.assertNotIn("StoryRepository", self.script)
        self.assertNotIn("creator.story.entity", self.script)

    def test_story_missing_binding_has_upstream_empty_state_not_placeholder(self):
        story_renderer = self.script.split("function renderStoryView(route)", 1)[1].split(
            "function renderEpisodeProject(route)", 1
        )[0]
        for marker in (
            "尚未确认故事方案",
            "前往 AI导演",
            'data-story-state="missing-confirmed-plan"',
        ):
            self.assertIn(marker, story_renderer)
        self.assertNotIn("即将上线", story_renderer)

    def test_story_to_script_navigation_preserves_episode_reference_without_text_copy(self):
        story_renderer = self.script.split("function renderStoryView(route)", 1)[1].split(
            "function renderEpisodeProject(route)", 1
        )[0]
        self.assertIn('href="#${escapeHtml(route.episodeBase || productionContextBase(route.persisted))}/script"', story_renderer)
        self.assertIn("继续使用同一单集", story_renderer)
        self.assertNotIn("URLSearchParams", story_renderer)
        for selector in (
            ".story-view",
            ".story-overview-card",
            ".story-beat-list",
            ".story-context-card",
            ".story-lineage-card",
        ):
            self.assertIn(selector, self.styles)

    def test_ui_r1_metadata_and_accepted_base_contract(self):
        self.assertEqual(
            self.fixture["meta"]["uiR1TaskId"],
            "ACS-CREATOR-UI-R1-ENTERPRISE-REBASELINE-001",
        )
        self.assertEqual(
            self.fixture["meta"]["uiR1Version"],
            "Enterprise Dark Cinematic Visual Baseline",
        )
        self.assertEqual(self.fixture["meta"]["canonicalRouteCount"], 32)

    def test_ui_r1_dark_token_values_are_final_cascade_authority(self):
        required = (
            "--acs-bg: #0f1318",
            "--acs-sidebar: #161c23",
            "--acs-surface: #1e252d",
            "--acs-surface-deep: #11171d",
            "--acs-surface-hover: #252e37",
            "--acs-surface-selected: #193b39",
            "--acs-border: #2c353f",
            "--acs-border-strong: #3a4652",
            "--acs-primary: #22d1b6",
            "--acs-accent: #e8a868",
            "--acs-text-primary: #f4f7fa",
            "--acs-text-secondary: #cbd5e1",
            "--acs-text-muted: #8894a3",
            "--acs-danger: #e55959",
            "--acs-success: #36d399",
            "--acs-info: #5dade2",
            "--acs-overlay: rgba(5, 8, 12, 0.72)",
        )
        for token in required:
            self.assertIn(token, self.styles)
        self.assertGreater(self.styles.index("UI-R1 — Enterprise"), self.styles.index("Creator UI V2"))

    def test_ui_r1_primary_shell_and_footer_inventory(self):
        primary = re.search(r'<nav class="primary-nav".*?</nav>', self.index, re.DOTALL).group(0)
        self.assertEqual(re.findall(r'data-route="([^"]+)"', primary), [
            "/creator", "/creator/ai-director", "/creator/projects",
            "/creator/assets", "/creator/create", "/creator/works",
        ])
        for marker in ("工作空间", "设置", "帮助", "任务", "通知", "内部内容实验室"):
            self.assertIn(marker, f"{self.index}\n{self.script}")
        for forbidden_visible in ("Internal Content Lab", ">Workspace<", ">Settings<", ">Help<"):
            self.assertNotIn(forbidden_visible, self.index.split('<script type="application/json"', 1)[0])
        for forbidden in ("GPU", "Queue", "Worker", "Server", "Debug"):
            self.assertNotIn(forbidden, self.index.split('<script type="application/json"', 1)[0])

    def test_ui_r1_project_navigator_freezes_six_groups_and_twenty_five_pages(self):
        nav_block = self.script.split("const projectNavigationGroups", 1)[1].split("const projectPages", 1)[0]
        self.assert_markers_in_order(nav_block, ('label: "概览"', 'label: "策划"', 'label: "内容"', 'label: "制作"', 'label: "后期"', 'label: "交付"'))
        self.assertEqual(nav_block.count("type:"), 25)
        for marker in ("项目概览", "AI导演", "系列规划", "IP圣经", "角色", "世界与连续性", "分集", "故事", "剧本", "一致性", "分镜", "镜头", "场景", "项目资产", "生成任务", "时间线", "预览", "质检", "审批", "成片", "导出", "系列管理", "发布", "数据"):
            self.assertIn(marker, nav_block)

    def test_m4_project_context_resolves_real_project_series_and_episode_identity(self):
        self.assertNotIn("projectRef", self.fixture["referenceContext"])
        self.assertIn('const projectShellBase = "/creator/project-shell"', self.script)
        for marker in (
            'const projectsEndpoint = "/creator/internal/projects"',
            "projectRecords",
            "findProject",
            "projectForSeries",
            "projectProductionContext",
            "selectedSeriesRef",
            "selectedEpisodeRef",
            "resolveSelectedProductionContext",
            "rememberProductionContext",
            "renderEpisodeSelector",
            "正式项目",
        ):
            self.assertIn(marker, self.script)
        self.assertNotIn('Project Context = NULL', self.script)
        self.assertNotIn('不会生成 projectRef', self.script)
        self.assertNotIn("fixture-project-x2-e001", f"{self.index}\n{self.script}")
        self.assertIn('data-action="wizard-submit" hidden', self.index)

    def test_ui_r1_dashboard_uses_real_series_episode_state_only(self):
        block = self.script.split("function renderDashboard()", 1)[1].split("function renderProjects", 1)[0]
        for marker in ("state.seriesRecords", "confirmedPlanBinding", "制作指挥中心", "最近分集"):
            self.assertIn(marker, block)
        for forbidden in ("fixture.project", "fixture.character", "fixture.assets", "project-cinema-card"):
            self.assertNotIn(forbidden, block)

    def test_m4_new_project_wizard_creates_through_same_origin_project_boundary(self):
        for marker in ("选择项目类型", "基本信息", "制作默认值", "检查并创建", "projectType", "seriesRef", "contentType", "episodeCount", "aspectRatio", "productionPreset"):
            self.assertIn(marker, f"{self.index}\n{self.script}")
        self.assertIn('>创建项目</button>', self.index)
        self.assertIn("async function createProjectFromWizard()", self.script)
        self.assertIn("requestApplicationJson(projectsEndpoint", self.script)
        self.assertIn("contentProfileRef,", self.script)
        self.assertIn("seriesRef: values.seriesRef", self.script)
        self.assertNotIn("createCanonicalProject", self.script)

    def test_ui_r1_future_pages_use_structured_shells_not_generic_coming_soon(self):
        for renderer in ("renderShellCanvas", "renderEnterpriseShellPage", "renderProjectContextBar"):
            self.assertIn(f"function {renderer}", self.script)
        for kind in ("summary", "detail", "table", "board", "timeline", "player", "editor"):
            self.assertIn(f'kind === "{kind}"', self.script)
        shell_block = self.script.split("function renderEnterpriseShellPage", 1)[1].split("function renderAssetsR1", 1)[0]
        self.assertNotIn("即将上线", shell_block)

    def test_ui_r1_story_and_script_compatibility_routes_keep_episode_lineage(self):
        for marker in (
            'if (pageKey === "story") return { ...baseRoute, type: "story-view" };',
            'if (pageKey === "script") return { ...baseRoute, type: "script-studio" };',
            "episode.confirmedPlanBinding",
            "sourcePlanRef: binding.sourcePlanRef",
            'href="#${escapeHtml(route.episodeBase || productionContextBase(route.persisted))}/script"',
            'const canonicalProjectMatch = normalized.match',
            'projectProductionContext(project, decodeURIComponent(episodeMatch[1]))',
        ):
            self.assertIn(marker, self.script)
        self.assertNotIn("StoryRepository", self.script)

    def test_ui_r1_works_and_delivery_do_not_promote_reference_candidate(self):
        block = self.script.split("function renderWorksR1()", 1)[1].split("function renderPlaceholder", 1)[0]
        self.assertIn("还没有正式作品", block)
        self.assertIn("内部参考候选片不会出现在作品库", block)
        self.assertNotIn("fixture.preview", block)
        self.assertIn('type: "master-shell", status: "planned"', self.script)
        self.assertIn('type: "export-shell", status: "disabled"', self.script)

    def test_ui_r1_correction_sidebar_collapse_changes_real_layout_width(self):
        correction = self.styles.split(
            "/* UI-R1 product integration correction: terminal layout and form authority. */",
            1,
        )[1]
        for marker in (
            "--sidebar-width: 240px",
            "--sidebar-collapsed-width: 72px",
            ".app-shell.sidebar-collapsed",
            "grid-template-columns: var(--sidebar-collapsed-width) minmax(0, 1fr)",
            ".app-shell.sidebar-collapsed .sidebar",
            "width: var(--sidebar-collapsed-width)",
            "display: none",
        ):
            self.assertIn(marker, f"{self.styles}\n{correction}")
        self.assertNotIn("visibility: hidden", correction)
        self.assertIn('classList.toggle("sidebar-collapsed", state.sidebarCollapsed)', self.script)
        self.assertIn('state.sidebarCollapsed = !state.sidebarCollapsed', self.script)

    def test_ui_r1_correction_dark_form_and_autofill_rules_are_terminal(self):
        correction = self.styles.split(
            "/* UI-R1 product integration correction: terminal layout and form authority. */",
            1,
        )[1]
        for marker in (
            "color-scheme: dark",
            "background-color: var(--acs-surface-deep)",
            "color: var(--acs-text-primary)",
            "border-color: var(--acs-primary)",
            "box-shadow: 0 0 0 3px var(--acs-primary-soft)",
            "body input:-webkit-autofill",
            "-webkit-text-fill-color: var(--acs-text-primary)",
            "-webkit-box-shadow: 0 0 0 1000px var(--acs-surface-deep) inset",
        ):
            self.assertIn(marker, correction)
        self.assertNotIn("background: white", correction.lower())
        self.assertNotIn("background-color: white", correction.lower())

    def test_ui_r1_correction_visible_shell_copy_is_chinese_first(self):
        static_shell = self.index.split('<script type="application/json"', 1)[0]
        context_renderer = self.script.split("function renderProjectContextBar(route)", 1)[1].split(
            "function renderEpisodeSelector", 1
        )[0]
        for marker in ("项目", "系列", "单集", "阶段", "当前对象", "版本", "尚未建立"):
            self.assertIn(marker, context_renderer)
        for forbidden in (
            "PROJECT NAVIGATOR",
            "PROJECT CONTEXT",
            "ENTERPRISE WORKSPACE",
            "CONTENT CANVAS",
            "FOUNDATION GATE",
            "Project Context = NULL",
            "No Project Context",
            "Internal Content Lab",
        ):
            self.assertNotIn(forbidden, f"{static_shell}\n{context_renderer}")
        self.assertNotIn("即将上线", f"{static_shell}\n{self.script}")

    def test_ui_r1_correction_project_shell_resolves_actual_episode_or_selector(self):
        route_block = self.script.split("function resolveRoute(path)", 1)[1].split(
            "function renderNotFound", 1
        )[0]
        for marker in (
            "resolveSelectedProductionContext()",
            'if (selected) return { redirect: `${productionContextBase(selected)}/${targetPage}` };',
            'type: "episode-selector"',
            "targetPage",
            "rememberProductionContext(persisted)",
        ):
            self.assertIn(marker, route_block)
        self.assertNotIn("fixture-project", route_block)
        self.assertNotIn('episodeRef: "current"', route_block)

    def test_ui_r1_correction_real_story_route_has_one_projection_authority(self):
        renderer_map = self.script.split("const renderers = {", 1)[1].split("};", 1)[0]
        projection = self.script.split("function buildStoryProjection(route)", 1)[1].split(
            "function renderStoryView(route)", 1
        )[0]
        self.assertEqual(renderer_map.count('"story-view": () => renderStoryView(resolved)'), 1)
        self.assertIn("episode.confirmedPlanBinding", self.script)
        self.assertIn("const sourcePlan = binding && binding.sourcePlan", projection)
        self.assertIn('schemaVersion: storyViewSchemaVersion', projection)
        for forbidden in ("StoryRepository", "fixture.", "fetch(", "DeepSeek"):
            self.assertNotIn(forbidden, projection)

    def test_ui_r1_correction_real_script_route_has_one_studio_authority(self):
        renderer_map = self.script.split("const renderers = {", 1)[1].split("};", 1)[0]
        route_block = self.script.split("function resolveRoute(path)", 1)[1].split(
            "function renderNotFound", 1
        )[0]
        self.assertEqual(renderer_map.count('"script-studio": () => renderScriptStudio(resolved)'), 1)
        self.assertIn('if (pageKey === "script") return { ...baseRoute, type: "script-studio" };', route_block)
        self.assertIn('requestApplicationJson(`${scriptWorkspaceEndpoint}?${scriptQuery(scope)}`)', self.script)
        self.assertNotIn("ScriptRepository", self.script)
        self.assertNotIn('type: "script-shell-placeholder"', self.script)

    def test_ui_r1_correction_context_bar_uses_real_lineage_and_versions(self):
        context_renderer = self.script.split("function renderProjectContextBar(route)", 1)[1].split(
            "function renderEpisodeSelector", 1
        )[0]
        for marker in (
            "const persisted = route.persisted",
            "persisted.series.title",
            "persisted.episode.episodeNumber",
            "来源方案 v${episode.sourcePlanVersion}",
            "selectedScriptVersion()",
            "scriptVersion.versionNumber",
        ):
            self.assertIn(marker, context_renderer)
        self.assertNotIn("fixture.project", context_renderer)
        self.assertNotIn("Project Context = NULL", context_renderer)
        self.assertNotIn("projectRef", context_renderer)

    def test_ui_r1_selected_cards_keep_dark_enterprise_surfaces(self):
        correction = self.styles.split(
            "/* Creator Enterprise selectable state correction */",
            1,
        )[1]
        for token in (
            "--acs-surface-deep: #11171d",
            "--acs-surface-hover: #252e37",
            "--acs-surface-selected: #193b39",
            "--acs-border: #2c353f",
            "--acs-border-strong: #3a4652",
            "--acs-primary: #22d1b6",
            "--acs-text-primary: #f4f7fa",
            "--acs-text-secondary: #cbd5e1",
            "--acs-primary-soft: rgba(34, 209, 182, 0.12)",
        ):
            self.assertIn(token, self.styles.lower())
        for selector in (
            ".director-output-card.is-selected",
            ".studio-flow-node.is-current",
            ".pipeline-stage.is-selected",
            ".v2-timeline-rail .timeline-segment.is-selected",
            ".v2-shot-grid .shot-card.is-selected",
            "body .script-scene-item.is-selected",
            "body .script-version-item.is-selected",
            ".tab.is-active",
            ".segment.is-active",
            ".segmented-control button.is-active",
            ".works-filter button.is-active",
            ".works-r1-filter button.is-active",
            ".asset-taxonomy button.is-active",
            ".nav-item.is-active",
            ".context-nav-item.is-active",
        ):
            self.assertIn(selector, correction)
        for declaration in (
            "background: var(--acs-surface-deep)",
            "background: var(--acs-surface-hover)",
            "background: var(--acs-surface-selected)",
            "border-color: var(--acs-primary)",
            "color: var(--acs-text-primary)",
            "color: var(--acs-text-secondary)",
            "rgba(34, 209, 182, 0.12)",
        ):
            self.assertIn(declaration, correction)
        for forbidden in ("background: white", "background: #fff", "#ffffff", "#edf7f5"):
            self.assertNotIn(forbidden, correction.lower())

    def test_ui_r1_ai_director_plan_status_has_three_clear_dark_states(self):
        block = self.script.split("function renderDirectorCanvas()", 1)[1].split(
            "function renderDirectorPlanning", 1
        )[0]
        for marker in (
            "director-plan-state-idle",
            "等待生成",
            "尚无候选方案",
            "director-plan-state-generating",
            "生成中",
            "director-plan-state-candidate",
            "待确认",
            "候选方案",
            "director-plan-state-confirmed",
            "已确认",
            "当前会话",
        ):
            self.assertIn(marker, block)
        self.assertNotIn("已确认（当前会话）", block)
        closeout_css = self.styles.split("/* UI-R1 closeout: confirmed plan status", 1)[1]
        self.assertIn("background: var(--acs-primary-soft)", closeout_css)
        self.assertIn("color: var(--acs-text-primary)", closeout_css)
        self.assertIn("color: var(--acs-text-secondary)", closeout_css)
        self.assertNotIn("background: white", closeout_css.lower())

    def test_ui_r1_projects_expose_confirmed_real_delete_controls(self):
        project_block = self.script.split("function renderProjects()", 1)[1].split(
            "function pipelineStatus", 1
        )[0]
        for marker in (
            'data-action="delete-series"',
            'data-action="delete-episode"',
            "删除系列",
            "删除单集",
            "episode-project-link",
        ):
            self.assertIn(marker, project_block)
        static_shell = self.index.split('<script type="application/json"', 1)[0]
        for marker in (
            'id="delete-dialog"',
            "确认删除？",
            "删除后不可恢复",
            'data-action="confirm-deletion"',
        ):
            self.assertIn(marker, static_shell)

    def test_ui_r1_delete_flow_calls_application_endpoint_then_reloads(self):
        block = self.script.split("async function confirmDeletion()", 1)[1].split(
            "function toggleSidebarCollapse", 1
        )[0]
        for marker in (
            'method: "DELETE"',
            "seriesEndpoint",
            "episodesEndpoint",
            "withWorkspace(endpoint)",
            "withEpisodeScope(endpoint, target.seriesRef)",
            "await loadSeriesData({ force: true })",
            "删除失败，请稍后重试。",
        ):
            self.assertIn(marker, block)
        self.assertNotIn("state.seriesRecords.filter", block)


if __name__ == "__main__":
    unittest.main()
