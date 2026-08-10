(function () {
  "use strict";

  const fixtureElement = document.getElementById("creator-fixture");
  const content = document.getElementById("app-content");
  const pageTitle = document.getElementById("page-title");
  const pageBreadcrumb = document.getElementById("page-breadcrumb");
  const sidebar = document.getElementById("sidebar");
  const sidebarBackdrop = document.getElementById("sidebar-backdrop");
  const workbench = document.getElementById("workbench");
  const contextNavigation = document.getElementById("context-navigation");
  const inspector = document.getElementById("inspector");
  const inspectorTitle = document.getElementById("inspector-title");
  const inspectorContent = document.getElementById("inspector-content");
  const inspectorFab = document.querySelector(".inspector-fab");
  const stickyActionBar = document.getElementById("sticky-action-bar");
  const bottomDrawer = document.getElementById("bottom-drawer");
  const bottomDrawerTitle = document.getElementById("bottom-drawer-title");
  const bottomDrawerContent = document.getElementById("bottom-drawer-content");
  const projectDialog = document.getElementById("project-dialog");
  const projectForm = document.getElementById("project-form");
  const deleteDialog = document.getElementById("delete-dialog");
  const deleteDialogTitle = document.getElementById("delete-dialog-title");
  const deleteDialogSubject = document.getElementById("delete-dialog-subject");
  const deleteDialogDescription = document.getElementById("delete-dialog-description");
  const deleteDialogError = document.getElementById("delete-dialog-error");
  const deleteDialogConfirm = document.getElementById("delete-dialog-confirm");
  const toast = document.getElementById("toast");
  const fixtureBanner = document.querySelector(".fixture-banner");
  const defaultFixtureBannerMarkup = fixtureBanner ? fixtureBanner.innerHTML : "";

  if (!fixtureElement || !content || !workbench || !stickyActionBar) {
    throw new Error("Creator Workspace UI Skeleton containers are missing.");
  }

  const fixture = JSON.parse(fixtureElement.textContent);
  const aiDirectorEndpoint = "/creator/internal/ai-director/plan";
  const seriesEndpoint = "/creator/internal/series";
  const projectsEndpoint = "/creator/internal/projects";
  const projectContextEndpoint = "/creator/internal/project-context";
  const confirmCreativePlanEndpoint = "/creator/internal/creative-plans/confirm";
  const episodesEndpoint = "/creator/internal/episodes";
  const scriptWorkspaceEndpoint = "/creator/internal/script-studio";
  const scriptGenerateEndpoint = `${scriptWorkspaceEndpoint}/generate`;
  const scriptManualVersionEndpoint = `${scriptWorkspaceEndpoint}/manual-version`;
  const scriptRewriteEndpoint = `${scriptWorkspaceEndpoint}/rewrite-scene`;
  const scriptConfirmEndpoint = `${scriptWorkspaceEndpoint}/confirm`;
  const storyboardBootstrapEndpoint = `${scriptWorkspaceEndpoint}/storyboard-bootstrap`;
  const seriesPlanningEndpoint = "/creator/internal/series-planning";
  const seriesPlanningGenerateEndpoint = `${seriesPlanningEndpoint}/generate`;
  const seriesPlanningConfirmEndpoint = `${seriesPlanningEndpoint}/confirm`;
  const seriesPlanningManualVersionEndpoint = `${seriesPlanningEndpoint}/manual-version`;
  const seriesPlanningConfirmVersionEndpoint = `${seriesPlanningEndpoint}/confirm-version`;
  const seriesPlanningM6BootstrapEndpoint = `${seriesPlanningEndpoint}/m6-bootstrap`;
  const workspaceRef = fixture.workspace.workspaceRef;
  const contentProfileRef = fixture.workspace.contentProfileRef;
  const projectShellBase = "/creator/project-shell";
  const defaultRoute = "/creator";
  let toastTimer;
  let dialogReturnFocus = null;
  let deleteDialogReturnFocus = null;
  let inspectorReturnFocus = null;
  const mobileQuery = window.matchMedia("(max-width: 900px)");
  const compactInspectorQuery = window.matchMedia("(max-width: 1439px)");

  const featureStates = Object.freeze({
    available: { label: "Available", badge: "", tone: "available" },
    fixture: { label: "Available - Fixture Only", badge: "Fixture Only", tone: "fixture" },
    development: { label: "In Development", badge: "In Development", tone: "development" },
    planned: { label: "Planned", badge: "Planned", tone: "planned" },
    disabled: { label: "Disabled", badge: "Disabled", tone: "disabled" }
  });

  const primaryRoutes = Object.freeze([
    { key: "dashboard", path: "/creator", label: "首页", english: "Dashboard", status: "available" },
    { key: "ai-director", path: "/creator/ai-director", label: "AI导演", english: "AI Director", status: "available" },
    { key: "projects", path: "/creator/projects", label: "项目", english: "Projects", status: "available" },
    { key: "assets", path: "/creator/assets", label: "资产库", english: "Asset Library", status: "available" },
    { key: "creation", path: "/creator/create", label: "创作中心", english: "Creation Center", status: "planned" },
    { key: "works", path: "/creator/works", label: "作品", english: "Works", status: "planned" }
  ]);

  const creationModules = Object.freeze([
    { key: "generation", path: "/creator/create/generation", label: "图片与视频", english: "Generation", version: "后续阶段", description: "需要真实资产需求与生成能力后才能执行。" },
    { key: "templates", path: "/creator/create/templates", label: "模板", english: "Templates", version: "待规划", description: "尚未建立可执行的模板能力。" },
    { key: "prompt-lab", path: "/creator/create/prompt-lab", label: "提示词实验", english: "Prompt Lab", version: "待规划", description: "实验内容不会自动成为正式制作记录。" },
    { key: "audio", path: "/creator/create/audio", label: "声音实验", english: "Audio Lab", version: "后续阶段", description: "需要正式声音制作能力后才能执行。" },
    { key: "models", path: "/creator/create/models", label: "创意实验", english: "Model Lab", version: "待规划", description: "当前不开放底层能力配置。" },
    { key: "tools", path: "/creator/create/tools", label: "快捷工具", english: "Quick Tools", version: "待规划", description: "尚未建立可进入正式项目的工具能力。" }
  ]);

  const projectNavigationGroups = Object.freeze([
    { label: "概览", key: "overview", items: [
      { key: "overview", label: "项目概览", suffix: "overview", type: "project-overview", status: "planned" }
    ] },
    { label: "策划", key: "planning", items: [
      { key: "project-director", label: "AI导演", suffix: "planning/director", type: "project-director", status: "available" },
      { key: "series-planning", label: "系列规划", suffix: "planning/series", type: "series-planning", status: "available" },
      { key: "bible", label: "IP圣经", suffix: "planning/bible", type: "bible-shell", status: "planned" },
      { key: "characters", label: "角色", suffix: "planning/characters", type: "character-shell", status: "planned" },
      { key: "continuity", label: "世界与连续性", suffix: "planning/continuity", type: "continuity-shell", status: "planned" }
    ] },
    { label: "内容", key: "content", items: [
      { key: "episodes", label: "分集", suffix: "episodes", type: "episode-list", status: "planned" },
      { key: "episode-workspace", label: "分集工作台", suffix: "episodes/current", type: "episode-workspace", status: "planned" },
      { key: "story", label: "故事", suffix: "episodes/current/story", type: "story-shell", status: "planned" },
      { key: "script", label: "剧本", suffix: "episodes/current/script", type: "script-shell", status: "planned" },
      { key: "consistency", label: "一致性", suffix: "episodes/current/consistency", type: "consistency-shell", status: "planned" }
    ] },
    { label: "制作", key: "production", items: [
      { key: "storyboard", label: "分镜", suffix: "production/storyboard", type: "storyboard-shell", status: "planned" },
      { key: "shots", label: "镜头", suffix: "production/shots", type: "shot-shell", status: "planned" },
      { key: "scenes", label: "场景", suffix: "production/scenes", type: "scene-shell", status: "planned" },
      { key: "project-assets", label: "项目资产", suffix: "production/assets", type: "project-assets-shell", status: "planned" },
      { key: "jobs", label: "生成任务", suffix: "production/jobs", type: "jobs-shell", status: "planned" }
    ] },
    { label: "后期", key: "post", items: [
      { key: "timeline", label: "时间线", suffix: "post/timeline", type: "timeline-shell", status: "planned" },
      { key: "preview", label: "预览", suffix: "post/preview", type: "preview-shell", status: "planned" },
      { key: "qc", label: "质检", suffix: "post/qc", type: "qc-shell", status: "planned" },
      { key: "approvals", label: "审批", suffix: "post/approvals", type: "approval-shell", status: "disabled" }
    ] },
    { label: "交付", key: "delivery", items: [
      { key: "masters", label: "成片", suffix: "delivery/masters", type: "master-shell", status: "planned" },
      { key: "exports", label: "导出", suffix: "delivery/exports", type: "export-shell", status: "disabled" },
      { key: "series-delivery", label: "系列管理", suffix: "delivery/series", type: "series-delivery-shell", status: "planned" },
      { key: "release", label: "发布", suffix: "delivery/release", type: "release-shell", status: "planned" },
      { key: "analytics", label: "数据", suffix: "delivery/analytics", type: "analytics-shell", status: "planned" }
    ] }
  ]);
  const projectPages = Object.freeze(projectNavigationGroups.flatMap((group) => group.items).map((page) => ({
    ...page,
    group: projectNavigationGroups.find((candidate) => candidate.items.includes(page)).label,
    path: `${projectShellBase}/${page.suffix}`
  })));

  const canonicalRouteTemplates = Object.freeze([
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
    "/creator/projects/:projectRef/delivery/analytics"
  ]);

  if (canonicalRouteTemplates.length !== fixture.meta.canonicalRouteCount) {
    throw new Error("Creator Workspace canonical route contract is inconsistent.");
  }

  const state = {
    activePath: defaultRoute,
    assetTab: "basic",
    assetFilter: "all",
    selectedShotKey: fixture.shots[0].localKey,
    selectedPipelineKey: (fixture.pipeline.find((stage) => stage.label === "Preview") || fixture.pipeline[1]).localKey,
    wizardStep: 1,
    wizardValues: { projectType: "series", seriesRef: "", title: "", contentType: "", episodeCount: "", duration: "60", aspectRatio: "9:16", platform: "", contentProfile: contentProfileRef, language: "中文", visualDirection: "", productionPreset: "" },
    bottomDrawerOpen: false,
    aiDirectorPhase: "input",
    aiDirectorBrief: { ...fixture.aiDirector.briefDefaults },
    aiDirectorPlan: null,
    aiDirectorPlanVersion: 0,
    aiDirectorConfirmed: false,
    aiDirectorError: null,
    confirmedCreativePlan: null,
    seriesRecords: [],
    seriesDataStatus: "idle",
    projectRecords: [],
    projectDataStatus: "idle",
    projectError: null,
    projectPhase: "idle",
    selectedSeriesRef: null,
    selectedEpisodeRef: null,
    seriesEpisodePhase: "idle",
    seriesEpisodeError: null,
    createdEpisode: null,
    pendingDeletion: null,
    deletionPhase: "idle",
    scriptWorkspaceStatus: "idle",
    scriptWorkspaceScope: "",
    scriptWorkspace: null,
    selectedScriptVersionRef: null,
    selectedScriptSceneRef: null,
    scriptPhase: "idle",
    scriptError: null,
    storyboardBootstrap: null,
    seriesPlanningStatus: "idle",
    seriesPlanningScope: "",
    seriesPlanningWorkspace: null,
    seriesPlanningCandidate: null,
    seriesPlanningPhase: "idle",
    seriesPlanningError: null,
    seriesPlanningInput: "围绕系列核心主题，规划完整的叙事弧、角色成长、分集目标与连续性线索。",
    selectedSeriesPlanVersionRef: null,
    previewState: "paused",
    previewMuted: true,
    sidebarCollapsed: false,
    mobileSidebarOpen: false,
    inspectorOpen: false,
    activeRoute: null
  };

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function normalizePath(value) {
    const candidate = String(value || "").trim();
    const withSlash = candidate.startsWith("/") ? candidate : `/${candidate}`;
    return withSlash.length > 1 ? withSlash.replace(/\/+$/, "") : withSlash;
  }

  async function requestApplicationJson(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Accept": "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {})
      }
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      const error = new Error(payload && payload.error && payload.error.message ? payload.error.message : "暂时无法完成操作，请稍后重试。");
      error.code = payload && payload.error ? payload.error.code : "application_error";
      throw error;
    }
    return payload;
  }

  function withWorkspace(path) {
    const separator = path.includes("?") ? "&" : "?";
    return `${path}${separator}workspaceRef=${encodeURIComponent(workspaceRef)}`;
  }

  function withEpisodeScope(path, seriesRefValue) {
    return `${withWorkspace(path)}&seriesRef=${encodeURIComponent(seriesRefValue)}`;
  }

  async function loadSeriesData({ force = false } = {}) {
    if (state.seriesDataStatus === "loading" || (!force && state.seriesDataStatus === "ready")) return;
    state.seriesDataStatus = "loading";
    try {
      const seriesPayload = await requestApplicationJson(withWorkspace(seriesEndpoint));
      state.seriesRecords = await Promise.all((seriesPayload.series || []).map(async (series) => ({
        ...series,
        episodes: await Promise.all((series.episodes || []).map(async (episode) => {
          const detail = await requestApplicationJson(
            withEpisodeScope(
              `${episodesEndpoint}/${encodeURIComponent(episode.episodeRef)}`,
              series.seriesRef
            )
          );
          return detail.episode;
        }))
      })));
      state.seriesDataStatus = "ready";
      resolveSelectedProductionContext();
    } catch (error) {
      state.seriesDataStatus = "error";
      state.seriesEpisodeError = "暂时无法读取系列与集数，请稍后重试。";
    }
    if (["/creator", "/creator/projects", "/creator/ai-director"].includes(state.activePath) || state.activePath.startsWith("/creator/projects/") || state.activePath.startsWith(`${projectShellBase}/`)) {
      renderRoute(state.activePath);
    }
  }

  async function loadProjectData({ force = false } = {}) {
    if (state.projectDataStatus === "loading" || (!force && state.projectDataStatus === "ready")) return;
    state.projectDataStatus = "loading";
    state.projectError = null;
    try {
      const payload = await requestApplicationJson(withWorkspace(projectsEndpoint));
      state.projectRecords = payload.projects || [];
      state.projectDataStatus = "ready";
    } catch (error) {
      state.projectDataStatus = "error";
      state.projectError = error && error.message ? error.message : "暂时无法读取项目，请稍后重试。";
    }
    if (state.activePath === "/creator" || state.activePath.startsWith("/creator/projects")) {
      renderRoute(state.activePath);
    }
  }

  function seriesPlanningScopeFromRoute(route = state.activeRoute) {
    if (!route || !route.project || !(route.project.seriesRefs || []).length) return null;
    return {
      workspaceRef,
      projectRef: route.project.projectRef,
      seriesRef: route.project.seriesRefs[0]
    };
  }

  function seriesPlanningScopeKey(scope) {
    return scope ? `${scope.workspaceRef}/${scope.projectRef}/${scope.seriesRef}` : "";
  }

  function seriesPlanningQuery(scope) {
    return `workspaceRef=${encodeURIComponent(scope.workspaceRef)}&projectRef=${encodeURIComponent(scope.projectRef)}&seriesRef=${encodeURIComponent(scope.seriesRef)}`;
  }

  async function loadSeriesPlanningWorkspace(route = state.activeRoute, { force = false } = {}) {
    const scope = seriesPlanningScopeFromRoute(route);
    if (!scope) return;
    const scopeKey = seriesPlanningScopeKey(scope);
    if (state.seriesPlanningStatus === "loading") return;
    if (!force && state.seriesPlanningStatus === "ready" && state.seriesPlanningScope === scopeKey) return;
    state.seriesPlanningStatus = "loading";
    state.seriesPlanningError = null;
    if (state.activeRoute && ["project-director", "series-planning"].includes(state.activeRoute.type)) renderRoute(state.activePath);
    try {
      const payload = await requestApplicationJson(`${seriesPlanningEndpoint}?${seriesPlanningQuery(scope)}`);
      state.seriesPlanningScope = scopeKey;
      state.seriesPlanningWorkspace = payload.workspace;
      const plan = payload.workspace.plan;
      const versions = payload.workspace.versions || [];
      state.selectedSeriesPlanVersionRef = plan && plan.currentSeriesPlanVersionRef
        ? plan.currentSeriesPlanVersionRef
        : versions.length ? versions[versions.length - 1].seriesPlanVersionRef : null;
      state.seriesPlanningStatus = "ready";
    } catch (error) {
      state.seriesPlanningStatus = "error";
      state.seriesPlanningError = error && error.message ? error.message : "系列规划暂时无法读取。";
    }
    if (state.activeRoute && ["project-director", "series-planning"].includes(state.activeRoute.type)) renderRoute(state.activePath);
  }

  function scriptScopeFromRoute(route = state.activeRoute) {
    if (!route || !route.persisted) return null;
    return {
      workspaceRef,
      seriesRef: route.persisted.series.seriesRef,
      episodeRef: route.persisted.episode.episodeRef
    };
  }

  function scriptScopeKey(scope) {
    return scope ? `${scope.workspaceRef}/${scope.seriesRef}/${scope.episodeRef}` : "";
  }

  function scriptQuery(scope) {
    return `workspaceRef=${encodeURIComponent(scope.workspaceRef)}&seriesRef=${encodeURIComponent(scope.seriesRef)}&episodeRef=${encodeURIComponent(scope.episodeRef)}`;
  }

  async function loadScriptWorkspace(route = state.activeRoute, { force = false, preserveSelection = true } = {}) {
    const scope = scriptScopeFromRoute(route);
    if (!scope) return;
    const scopeKey = scriptScopeKey(scope);
    if (state.scriptWorkspaceStatus === "loading") return;
    if (!force && state.scriptWorkspaceStatus === "ready" && state.scriptWorkspaceScope === scopeKey) return;
    state.scriptWorkspaceStatus = "loading";
    state.scriptError = null;
    if (state.activeRoute && state.activeRoute.type === "script-studio") renderRoute(state.activePath);
    try {
      const payload = await requestApplicationJson(`${scriptWorkspaceEndpoint}?${scriptQuery(scope)}`);
      state.scriptWorkspaceScope = scopeKey;
      state.scriptWorkspace = payload.workspace;
      const versions = payload.workspace.versions || [];
      const preferred = preserveSelection && versions.some((item) => item.scriptVersionRef === state.selectedScriptVersionRef)
        ? state.selectedScriptVersionRef
        : payload.workspace.script && payload.workspace.script.currentScriptVersionRef;
      state.selectedScriptVersionRef = preferred || (versions.length ? versions[versions.length - 1].scriptVersionRef : null);
      const selected = versions.find((item) => item.scriptVersionRef === state.selectedScriptVersionRef);
      if (!selected || !(selected.scenes || []).some((scene) => scene.scriptSceneRef === state.selectedScriptSceneRef)) {
        state.selectedScriptSceneRef = selected && selected.scenes.length ? selected.scenes[0].scriptSceneRef : null;
      }
      state.storyboardBootstrap = null;
      if (payload.workspace.script && payload.workspace.script.confirmedScriptVersionRef) {
        const bridge = await requestApplicationJson(`${storyboardBootstrapEndpoint}?${scriptQuery(scope)}`);
        state.storyboardBootstrap = bridge.bootstrap;
      }
      state.scriptWorkspaceStatus = "ready";
    } catch (error) {
      state.scriptWorkspaceStatus = "error";
      state.scriptError = error && error.message ? error.message : "剧本工作区暂时无法读取，请稍后重试。";
    }
    if (state.activeRoute && state.activeRoute.type === "script-studio") renderRoute(state.activePath);
  }

  function pathFromHash() {
    const raw = window.location.hash.slice(1);
    return raw ? normalizePath(raw) : defaultRoute;
  }

  function navigate(path, replace) {
    const next = normalizePath(path);
    if (replace) {
      window.history.replaceState(null, "", `#${next}`);
      renderRoute(next);
      return;
    }
    if (pathFromHash() === next) {
      renderRoute(next);
    } else {
      window.location.hash = next;
    }
  }

  function statusBadge(statusKey, additionalClass = "") {
    const status = featureStates[statusKey] || featureStates.planned;
    if (!status.badge) return "";
    if (statusKey === "fixture") return '<span class="sr-only">演示版本</span>';
    const labels = { fixture: "演示版本", development: "开发中", planned: "尚未启用", disabled: "暂不可用" };
    return `<span class="badge badge-${status.tone} ${additionalClass}"><i aria-hidden="true"></i>${escapeHtml(labels[statusKey] || status.badge)}</span>`;
  }

  function pageStatus(statusKey) {
    const status = featureStates[statusKey] || featureStates.planned;
    if (statusKey === "fixture") return '<span class="sr-only">可用，演示版本</span>';
    const labels = { available: "可用", fixture: "演示版本", development: "开发中", planned: "尚未启用", disabled: "暂不可用" };
    return `<span class="page-status page-status-${status.tone}"><i aria-hidden="true"></i>${escapeHtml(labels[statusKey] || status.label)}</span>`;
  }

  function governanceBadge(label, tone) {
    const labels = {
      "Rights HOLD": "权利待确认",
      HOLD: "权利待确认",
      "LOCAL REVIEW CANDIDATE": "候选预览",
      "PUBLICATION BLOCKED": "尚未开放",
      "Technical PASS": "技术检查通过",
      BLOCKED: "尚未开放",
      DISABLED: "暂不可用",
      "HUMAN REVIEW NOT COMPLETE": "等待人工确认",
      "6 SHOTS · 45 SECONDS": "6 个镜头 · 45 秒",
      "EXPORT BLOCKED": "暂不可导出",
      "PIPELINE VIEW / NO ORCHESTRATION": "制作流程总览"
    };
    return `<span class="governance-badge governance-${escapeHtml(tone)}"><i aria-hidden="true"></i>${escapeHtml(labels[label] || label)}</span>`;
  }

  function localizedStatusBadge(label, tone) {
    return `<span class="badge badge-${escapeHtml(tone)}"><i aria-hidden="true"></i>${escapeHtml(label)}</span>`;
  }

  function localizedPageStatus(label, tone = "fixture") {
    return `<span class="page-status page-status-${escapeHtml(tone)}"><i aria-hidden="true"></i>${escapeHtml(label)}</span>`;
  }

  function fixtureNotice() {
    return '<span class="sr-only page-fixture-contract">演示数据，不代表正式业务记录，仅用于当前会话。</span>';
  }

  function seriesApplicationNotice() {
    return '<span class="sr-only series-application-contract">系列与单集来自正式应用边界；当前不是正式项目，也不会创建制作任务。</span>';
  }

  function candidatePlanNotice() {
    return '<span class="sr-only candidate-plan-contract">候选创意方案 · 人工确认前不会进入后续流程 · 仅当前会话有效</span>';
  }

  function demoNotice(copy) {
    return `<span class="sr-only director-demo-notice">${escapeHtml(copy)} · 演示数据，不代表正式业务记录。</span>`;
  }

  function renderPageHeader({ eyebrow, title, description, status = "fixture", pageStatusLabel = "", meta = "" }) {
    return `
      <header class="view-header">
        <div class="view-heading-copy">
          <div class="eyebrow-row"><span class="eyebrow">${escapeHtml(eyebrow)}</span>${pageStatusLabel ? localizedPageStatus(pageStatusLabel, status) : pageStatus(status)}</div>
          <h2>${escapeHtml(title)}</h2>
          <p>${escapeHtml(description)}</p>
        </div>
        ${meta ? `<div class="view-header-meta">${meta}</div>` : ""}
      </header>
    `;
  }

  function updateShellBoundaryCopy(route) {
    if (!fixtureBanner) return;
    fixtureBanner.dataset.context = route && route.type === "ai-director" ? "ai-director" : "workspace";
    fixtureBanner.title = "演示媒体不是业务事实；系列与集数由本地开发服务管理。";
  }

  function renderLoadingState(label) {
    return `
      <div class="loading-state" role="status" aria-live="polite">
        <span class="loading-block" aria-hidden="true"></span>
        <span class="sr-only">${escapeHtml(label)}</span>
      </div>
    `;
  }

  function renderErrorState(title, description) {
    return `
      <div class="error-state" role="alert">
        <span class="error-state-icon" aria-hidden="true">!</span>
        <div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(description)}</p></div>
      </div>
    `;
  }

  function renderButtonLoading(label) {
    return `<button class="button button-primary is-loading" type="button" aria-busy="true" disabled><span class="button-spinner" aria-hidden="true"></span><span class="button-label">${escapeHtml(label)}</span></button>`;
  }

  function renderEmptyState({ icon = "○", title, description, action = "" }) {
    return `
      <div class="empty-state">
        <span class="empty-state-icon" aria-hidden="true">${escapeHtml(icon)}</span>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(description)}</p>
        ${action}
      </div>
    `;
  }

  function renderDashboard() {
    const seriesCount = state.seriesRecords.length;
    const episodes = state.seriesRecords.flatMap((series) => (series.episodes || []).map((episode) => ({ series, episode })));
    const confirmedEpisodes = episodes.filter(({ episode }) => Boolean(episode.confirmedPlanBinding));
    const scriptEpisodes = episodes.filter(({ episode }) => Boolean(episode.scriptRef || episode.confirmedScriptVersionRef));
    const recent = episodes.slice(0, 3);
    return `
      <section class="enterprise-hero" aria-labelledby="enterprise-hero-title">
        <div><span class="section-kicker">制作指挥中心</span><h2 id="enterprise-hero-title">把创意推进为可确认的制作成果</h2><p>从导演方案、系列与分集，到故事和剧本版本。这里只汇总当前工作区真实存在的制作记录。</p></div>
        <div class="enterprise-hero-actions"><a class="button button-primary" href="#/creator/ai-director">打开 AI导演</a><a class="button button-secondary" href="#/creator/projects">查看项目中心</a></div>
      </section>
      <section class="command-metrics" aria-label="工作区摘要">
        <article><span>系列</span><strong>${seriesCount}</strong><small>本地开发服务记录</small></article>
        <article><span>分集</span><strong>${episodes.length}</strong><small>已建立单集记录</small></article>
        <article><span>已确认方案</span><strong>${confirmedEpisodes.length}</strong><small>已绑定导演方案</small></article>
        <article><span>剧本工作区</span><strong>${scriptEpisodes.length}</strong><small>无数据时保持 0</small></article>
      </section>
      <section class="enterprise-grid enterprise-grid-wide">
        <article class="enterprise-panel">
          <header><div><span class="section-kicker">当前制作</span><h3>最近分集</h3></div><a class="text-link" href="#/creator/projects">全部项目</a></header>
          <div class="enterprise-list">${state.seriesDataStatus === "loading" || state.seriesDataStatus === "idle" ? renderLoadingState("正在读取真实系列与分集") : state.seriesDataStatus === "error" ? renderErrorState("暂时无法读取制作记录", "请确认本地应用服务正在运行。") : recent.length ? recent.map(({ series, episode }) => `<a class="enterprise-list-row" href="#/creator/projects/${encodeURIComponent(episode.episodeRef)}"><span class="row-index">第${String(episode.episodeNumber).padStart(2, "0")}集</span><span><strong>${escapeHtml(episode.title)}</strong><small>${escapeHtml(series.title)} · ${episode.confirmedPlanBinding ? `导演方案 v${escapeHtml(episode.sourcePlanVersion)}` : "等待确认导演方案"}</small></span><em>进入</em></a>`).join("") : renderEmptyState({ icon: "—", title: "还没有真实分集", description: "先在 AI导演确认方案，再创建系列与分集。", action: '<a class="button button-secondary" href="#/creator/ai-director">前往 AI导演</a>' })}</div>
        </article>
        <aside class="enterprise-panel enterprise-rail">
          <header><div><span class="section-kicker">能力进度</span><h3>制作能力</h3></div></header>
          ${[["01","AI导演","可用"],["02","系列与分集","可用"],["03","故事与剧本","可用"],["04","角色与 IP","暂停"],["05","制作与交付","规划中"]].map(([sequence,label,status]) => `<div class="capability-row"><span>${sequence}</span><strong>${label}</strong><em>${status}</em></div>`).join("")}
        </aside>
      </section>
      ${seriesApplicationNotice()}
    `;
  }

  function renderProjects() {
    const waiting = [state.seriesDataStatus, state.projectDataStatus].some((value) => value === "idle" || value === "loading");
    const failed = state.seriesDataStatus === "error" || state.projectDataStatus === "error";
    const renderEpisodeRows = (project, series) => (series.episodes || []).length
      ? series.episodes.map((episode) => `
          <article class="episode-project-row">
            <a class="episode-project-link" href="#/creator/projects/${encodeURIComponent(project.projectRef)}/episodes/${encodeURIComponent(episode.episodeRef)}">
              <span class="episode-number">E${String(episode.episodeNumber).padStart(2, "0")}</span>
              <span><strong>${escapeHtml(episode.title)}</strong><small>来源：已确认的 AI导演方案 v${escapeHtml(episode.sourcePlanVersion)}</small></span>
              <em>进入制作 →</em>
            </a>
            <button class="button button-danger-subtle episode-delete-action" type="button" data-action="delete-episode" data-series-ref="${escapeHtml(series.seriesRef)}" data-series-title="${escapeHtml(series.title)}" data-episode-ref="${escapeHtml(episode.episodeRef)}" data-episode-title="${escapeHtml(episode.title)}">删除单集</button>
          </article>
        `).join("")
      : '<div class="series-empty">项目已关联系列，尚未创建单集。</div>';
    const projectCards = state.projectRecords.map((project) => {
      const series = (project.seriesRefs || []).map(findSeries).find(Boolean);
      return `
        <article class="series-project-card project-record-card" data-project-ref="${escapeHtml(project.projectRef)}">
          <header>
            <div><span class="section-kicker">正式项目 · ${escapeHtml(project.projectType === "series" ? "系列制作" : project.projectType)}</span><h3>${escapeHtml(project.title)}</h3><p>${escapeHtml(project.description || "统一承载系列、单集与内容制作上下文")}</p></div>
            <div class="series-card-actions"><span class="badge badge-available"><i></i>${project.status === "active" ? "创作中" : "已归档"}</span><a class="button button-secondary" href="#/creator/projects/${encodeURIComponent(project.projectRef)}">打开项目</a></div>
          </header>
          <dl class="project-record-meta"><div><dt>项目类型</dt><dd>${escapeHtml(project.projectType)}</dd></div><div><dt>内容配置</dt><dd>${escapeHtml(project.contentProfileRef)}</dd></div><div><dt>目标平台</dt><dd>${escapeHtml(project.targetPlatform || "未设置")}</dd></div><div><dt>计划集数</dt><dd>${escapeHtml(project.plannedEpisodeCount)}</dd></div></dl>
          ${series ? `<div class="project-series-heading"><span>关联系列</span><strong>${escapeHtml(series.title)}</strong><small>${escapeHtml(series.seriesRef)}</small></div><div class="series-episode-list">${renderEpisodeRows(project, series)}</div>` : renderErrorState("关联系列暂时无法读取", "项目记录已保留，请刷新后重试。")}
        </article>
      `;
    }).join("");
    const assignedSeriesRefs = new Set(state.projectRecords.flatMap((project) => project.seriesRefs || []));
    const unassigned = state.seriesRecords.filter((series) => !assignedSeriesRefs.has(series.seriesRef));
    const unassignedCards = unassigned.map((series) => `
      <article class="series-project-card unassigned-series-card">
        <header><div><span class="section-kicker">既有系列 · 待关联</span><h3>${escapeHtml(series.title)}</h3><p>保留原有系列、单集与来源关系；可显式关联到一个新项目。</p></div><div class="series-card-actions"><button class="button button-secondary" type="button" data-action="associate-series-project" data-series-ref="${escapeHtml(series.seriesRef)}" data-series-title="${escapeHtml(series.title)}">建立项目上下文</button><button class="button button-danger-subtle" type="button" data-action="delete-series" data-series-ref="${escapeHtml(series.seriesRef)}" data-series-title="${escapeHtml(series.title)}" data-episode-count="${(series.episodes || []).length}">删除系列</button></div></header>
        <div class="series-episode-list">${(series.episodes || []).map((episode) => `<article class="episode-project-row"><a class="episode-project-link" href="#/creator/projects/${encodeURIComponent(episode.episodeRef)}"><span class="episode-number">E${String(episode.episodeNumber).padStart(2, "0")}</span><span><strong>${escapeHtml(episode.title)}</strong><small>兼容入口 · 尚未关联项目</small></span><em>打开 →</em></a></article>`).join("") || '<div class="series-empty">还没有集数。</div>'}</div>
      </article>
    `).join("");
    const records = waiting
      ? renderLoadingState("正在读取项目、系列与单集…")
      : failed
        ? renderErrorState("项目上下文暂时无法读取", state.projectError || "请确认本地 Creator Server 正在运行后重试。")
        : projectCards || renderEmptyState({ icon: "项", title: "还没有正式项目", description: "可以将一个现有系列显式关联为正式项目，保留全部既有身份与来源关系。", action: '<button class="button button-secondary" type="button" data-action="open-project-dialog">新建项目</button>' });
    return `
      ${renderPageHeader({ eyebrow: "项目中心", title: "项目", description: "以稳定项目身份组织系列、单集、故事与剧本制作上下文。", status: "available", meta: '<button class="button button-primary" type="button" data-action="open-project-dialog">新建项目</button>' })}
      <section class="project-center-toolbar" aria-label="项目筛选"><div class="segmented-control"><button class="is-active" type="button">全部</button><button type="button" disabled>进行中</button><button type="button" disabled>已归档</button></div><span>${state.projectRecords.length} 个项目 · ${state.seriesRecords.length} 个系列</span></section>
      <section class="enterprise-panel project-register" aria-labelledby="project-records-title"><header><div><span class="section-kicker">Project Context</span><h3 id="project-records-title">正式项目记录</h3></div><button class="button button-text" type="button" data-action="reload-projects">刷新</button></header><div class="series-project-list">${records}</div></section>
      ${unassignedCards ? `<section class="enterprise-panel project-register compatibility-register"><header><div><span class="section-kicker">兼容性队列</span><h3>尚未关联项目的既有系列</h3><p>不会自动迁移或按名称匹配；由用户显式建立关系。</p></div></header><div class="series-project-list">${unassignedCards}</div></section>` : ""}
    `;
  }

  function pipelineStatus(value) {
    const normalized = value.toLowerCase();
    let tone = "progress";
    if (normalized.startsWith("blocked")) tone = "blocked";
    if (normalized.startsWith("planned")) tone = "planned";
    if (normalized.startsWith("complete")) tone = "complete";
    if (normalized.startsWith("not started")) tone = "idle";
    const label = normalized.startsWith("blocked") ? "阻塞" : normalized.startsWith("planned") ? "尚未启用" : normalized.startsWith("complete") ? "完成" : normalized.startsWith("not started") ? "准备中" : "制作中";
    return `<span class="pipeline-status pipeline-${tone}"><i aria-hidden="true"></i>${label}</span>`;
  }

  function renderPipeline() {
    const studioStages = [
      ["Story", "故事", "梳理叙事方向"],
      ["Character", "角色", "确认角色视觉"],
      ["Storyboard", "分镜", "组织镜头语言"],
      ["Assets", "画面", "准备视觉资产"],
      ["Audio", "声音", "规划声音体验"],
      ["Timeline", "剪辑", "组织影片节奏"],
      ["Preview", "预览", "观看候选版本"],
      ["Export", "导出", "等待资格确认"]
    ].map(([source, label, description]) => ({ ...fixture.pipeline.find((stage) => stage.label === source), label, description }));
    const selected = fixture.pipeline.find((item) => item.localKey === state.selectedPipelineKey) || fixture.pipeline[0];
    const selectedView = studioStages.find((item) => item.localKey === selected.localKey) || studioStages[0];
    const evidenceLabels = {
      Idea: "创意简报 v0.1",
      Story: "45 秒故事结构",
      "IP Bible": "角色规则草稿",
      Character: "角色设定 v0.1",
      Storyboard: "6 个镜头 · 45 秒",
      Assets: "角色与关键画面",
      Audio: "静音候选版本",
      Timeline: "6 段镜头 · 45 秒",
      Preview: "候选版本 v1",
      Approval: "等待人工确认",
      Export: "候选版本 v1"
    };
    return `
      <section class="project-studio-hero">
        <div class="project-studio-cover"><img src="${escapeHtml(fixture.character.referenceImage)}" alt="晚灯第 1 集项目封面"></div>
        <div class="project-studio-title"><span>项目工作室</span><h2>${displayProjectTitle}</h2><p>情绪短片 · 45 秒 · 竖屏 9:16</p></div>
        <div class="project-studio-status"><small>当前阶段</small><strong>可预览</strong><a href="#${projectBase}/preview">观看候选版本 →</a></div>
      </section>
      <section class="studio-flow" aria-label="影视制作流程">
        ${studioStages.map((stage, index) => `<button type="button" class="studio-flow-node ${stage.localKey === state.selectedPipelineKey ? "is-current" : ""}" data-action="select-pipeline-stage" data-stage-key="${escapeHtml(stage.localKey)}" aria-pressed="${stage.localKey === state.selectedPipelineKey}" title="${escapeHtml(stage.description)}"><span>${String(index + 1).padStart(2, "0")}</span><strong>${stage.label}</strong>${stage.localKey === state.selectedPipelineKey ? '<em>当前位置</em>' : pipelineStatus(stage.status)}</button>`).join("")}
      </section>
      <section class="studio-workspace">
        <article class="studio-main-card">
          <div class="studio-main-visual"><img src="${escapeHtml(fixture.assets[2].src)}" alt="晚灯项目当前视觉"><span>当前创作画面</span></div>
          <div class="studio-main-copy"><span class="section-kicker">当前阶段</span><h3>${escapeHtml(selectedView.label)}</h3><p>围绕影片内容继续整理素材与创作判断，保持每一步都清楚可追溯。</p><div class="studio-evidence-row"><span><small>版本</small><strong>${escapeHtml(evidenceLabels[selected.label] || "当前版本")}</strong></span><span><small>状态</small><strong>${pipelineStatus(selected.status)}</strong></span><span><small>下一步</small><strong>由创作者确认</strong></span></div><a class="button button-secondary" href="#${escapeHtml(selected.route)}">进入当前阶段</a></div>
        </article>
        <aside class="studio-suggestion-card"><span>创作建议</span><h3>保持夜晚空间的留白</h3><p>延续晚灯的暖色视觉锚点，让情绪变化成为镜头之间的主要连接。</p><div><small>本阶段重点</small><strong>情绪与镜头节奏</strong></div></aside>
      </section>
      ${fixtureNotice()}
    `;
  }

  function renderAssetGrid(assets) {
    return `
      <div class="asset-grid">
        ${assets.map((asset) => `
          <article class="asset-card">
            <div class="asset-image-wrap"><img src="${escapeHtml(asset.src)}" alt="${escapeHtml(asset.label)}"></div>
            <div class="asset-card-copy">
              <div class="asset-card-top"><span class="asset-kind">${asset.kind === "reference" ? "角色设定" : "关键画面"}</span><span class="asset-user-state">${escapeHtml(asset.version)}</span></div>
              <h4>${escapeHtml(asset.label)}</h4>
              <p>来源：内部视觉参考 · 权利待确认</p>
            </div>
          </article>
        `).join("")}
      </div>
    `;
  }

  function assetTabContent() {
    const usageLabel = (asset) => asset.kind === "reference" ? "角色页 / 当前项目" : "分镜页 / 当前项目";
    if (state.assetTab === "versions") {
      return `
        <div class="table-wrap"><table class="data-table"><thead><tr><th>资产</th><th>版本</th><th>使用项目</th><th>状态</th></tr></thead><tbody>
          ${fixture.assets.map((asset) => `<tr><td>${escapeHtml(asset.label)}</td><td>${escapeHtml(asset.version)}</td><td>${displayProjectTitle}</td><td>内部体验</td></tr>`).join("")}
        </tbody></table></div>
      `;
    }
    if (state.assetTab === "usage") {
      return `
        <div class="usage-list">
          ${fixture.assets.map((asset) => `<article><span class="asset-kind">${asset.kind === "reference" ? "角色" : "画面"}</span><div><strong>${escapeHtml(asset.label)}</strong><p>${usageLabel(asset)}</p></div><span>当前项目使用</span></article>`).join("")}
        </div>
      `;
    }
    if (state.assetTab === "rights") {
      return `
        <div class="rights-panel">
          <div class="rights-summary"><span aria-hidden="true">!</span><div><strong>权利状态：待确认</strong><p>当前仅用于内部体验，正式使用前仍需完成人工权利确认。</p></div></div>
          <ul class="review-checklist"><li><span>来源记录</span><strong>已保留</strong></li><li><span>人工确认</span><strong>等待处理</strong></li><li><span>发布权限</span><strong>尚未确定</strong></li><li><span>当前用途</span><strong>内部演示</strong></li></ul>
        </div>
      `;
    }
    if (state.assetTab === "history") {
      return renderEmptyState({
        icon: "⏱",
        title: "生成记录 · 尚未启用",
        description: "未来将在这里查看资产的生成来源、时间和版本；当前没有可展示记录。"
      });
    }
    return `
      <div class="asset-overview-grid">
        <article class="info-block"><span>资产范围</span><strong>1 张角色设定 + 6 张关键画面</strong><p>用于${displayProjectTitle}。</p></article>
        <article class="info-block"><span>角色</span><strong>X2-C01 · 晚灯</strong><p>角色设定 v0.1 · 等待人工确认。</p></article>
        <article class="info-block"><span>使用项目</span><strong>${displayProjectTitle}</strong><p>情绪短片 · 45 秒。</p></article>
        <article class="info-block"><span>权利状态</span><strong class="text-hold">待确认</strong><p>正式使用前仍需完成人工确认。</p></article>
      </div>
    `;
  }

  function renderAssets() {
    const tabs = [
      ["basic", "基础信息"],
      ["versions", "版本"],
      ["usage", "使用记录"],
      ["rights", "权利"],
      ["history", "生成记录"]
    ];
    const filteredAssets = state.assetFilter === "all"
      ? fixture.assets
      : fixture.assets.filter((asset) => asset.kind === state.assetFilter);
    return `
      ${renderPageHeader({
        eyebrow: "创作资产中心",
        title: "资产库",
        description: "统一管理角色、场景、图片、视频和声音资产。",
        status: "fixture",
        meta: '<label class="asset-search"><span aria-hidden="true">⌕</span><input type="search" placeholder="搜索资产" aria-label="搜索资产" disabled></label>'
      })}
      <section class="asset-category-strip v2-asset-categories" aria-label="资产分类">
        ${[["角色","◉"],["场景","▱"],["图片","◇"],["视频","▶"],["音频","♪"],["模板","▦"]].map(([label, icon], index) => `<button type="button" class="asset-category ${index === 0 ? "is-fixture" : ""}" disabled><i aria-hidden="true">${icon}</i><strong>${label}</strong><small>${index === 0 ? "1 项" : index < 4 ? "浏览" : "尚未启用"}</small></button>`).join("")}
      </section>
      <section class="asset-feature-card">
        <div class="asset-feature-visual"><img src="${escapeHtml(fixture.character.referenceImage)}" alt="晚灯角色资产"><span>角色资产</span></div>
        <div class="asset-feature-copy"><span class="section-kicker">核心角色</span><h2>晚灯 <small>WANLIGHT</small></h2><p>陪伴型夜灯角色，以深蓝兜帽、琥珀灯面和月牙别针建立稳定视觉识别。</p><div class="asset-feature-meta"><span><small>角色</small><strong>晚灯</strong></span><span><small>版本</small><strong>v0.1</strong></span><span><small>使用项目</small><strong>${displayProjectTitle}</strong></span><span><small>权利状态</small><strong>待确认</strong></span></div><div class="button-row"><a class="button button-secondary" href="#${projectBase}/character">查看角色</a><button class="button button-text" type="button" data-action="select-asset-tab" data-tab="versions">查看版本</button></div></div>
      </section>
      <section class="card asset-detail-shell v2-asset-detail">
        <div class="tabs" role="tablist" aria-label="资产详情">
          ${tabs.map(([key, label]) => `<button class="tab ${state.assetTab === key ? "is-active" : ""}" id="asset-tab-${key}" type="button" role="tab" aria-selected="${state.assetTab === key}" aria-controls="asset-detail-panel" tabindex="${state.assetTab === key ? "0" : "-1"}" data-action="select-asset-tab" data-tab="${key}">${escapeHtml(label)}${key === "history" ? '<span class="badge badge-planned"><i></i>尚未启用</span>' : ""}</button>`).join("")}
        </div>
        <div class="tab-panel" id="asset-detail-panel" role="tabpanel" aria-labelledby="asset-tab-${escapeHtml(state.assetTab)}" tabindex="0">${assetTabContent()}</div>
      </section>
      <section class="asset-browser">
        <div class="card-heading">
          <div><span class="section-kicker">视觉资产</span><h3>关键帧与场景画面</h3></div>
          <div class="segmented-control" role="group" aria-label="资产筛选">
            ${[["all", "全部"], ["reference", "角色设定"], ["keyframe", "关键画面"]].map(([key, label]) => `<button type="button" class="segment ${state.assetFilter === key ? "is-active" : ""}" data-action="filter-assets" data-filter="${key}" aria-pressed="${state.assetFilter === key}">${label}</button>`).join("")}
          </div>
        </div>
        ${renderAssetGrid(filteredAssets)}
      </section>
      ${fixtureNotice()}
    `;
  }

  function renderCreationCenter() {
    const modules = [
      ["AI生成", "把文字与视觉意图转化为未来可用的创作素材", "✦"],
      ["模板中心", "从成熟的影片结构开始一段新的创作", "▦"],
      ["IP管理", "跨项目维护角色、世界观与创作资产", "◎"],
      ["AI记忆", "在未来延续已确认的创作偏好与作品语境", "◌"],
      ["工作流", "把重复的人工步骤整理为清晰创作路径", "⌁"],
      ["数据分析", "在未来查看作品表现与创作证据", "↗"]
    ];
    return `
      ${renderPageHeader({
        eyebrow: "智能创作工具",
        title: "创作中心",
        description: "让创意进入不同的 AI 创作能力。",
        status: "fixture"
      })}
      <section class="creation-center-hero"><div><span>创作能力中心</span><h2>让复杂创作变得更简单</h2><p>从图像、模板到工作流，按影片需要选择合适的创作能力。</p></div><div class="creation-orbit" aria-hidden="true"><i>✦</i><span></span><span></span><span></span></div></section>
      <section class="module-grid v2-module-grid">
        ${creationModules.map((module, index) => `
          <a class="module-card" href="#${escapeHtml(module.path)}">
            <span class="module-icon" aria-hidden="true">${modules[index][2]}</span>
            <div class="module-card-heading"><span class="module-status">尚未启用</span><span>${String(index + 1).padStart(2, "0")}</span></div>
            <h3>${modules[index][0]}</h3>
            <p>${modules[index][1]}</p>
            <span class="module-link">了解功能 <span aria-hidden="true">→</span></span>
          </a>
        `).join("")}
      </section>
      ${fixtureNotice()}
    `;
  }

  function renderCreationPreview(route) {
    const commonHeader = (title, description, eyebrow = "创作工具预览") => renderPageHeader({
      eyebrow,
      title,
      description,
      status: "planned"
    });

    if (route.key === "generation") {
      const modules = [
        ["✦", "图片生成", "从文字或参考图创建视觉资产"],
        ["▶", "视频生成", "将关键画面发展为连续镜头"],
        ["♪", "声音生成", "创建对白、环境声与音乐素材"]
      ];
      return `
        ${commonHeader("生成中心", "把文字、参考画面和创作意图转化为可使用的影视素材。", "未来创作工作台")}
        <section class="creation-preview-hero generation-preview-hero">
          <div><span class="section-kicker">创作入口</span><h2>从创作意图开始</h2><p>整理画面目标与参考方向，在功能开放后进入对应的创作模块。</p></div>
          <div class="generation-input-preview" aria-label="未来输入区域预览"><label for="generation-preview-input">描述你想创建的画面……</label><textarea id="generation-preview-input" disabled placeholder="描述画面、氛围与镜头意图"></textarea><button class="button button-primary" type="button" disabled>尚未启用</button></div>
        </section>
        <section class="creation-preview-grid creation-tool-grid" aria-label="生成能力预览">
          ${modules.map(([icon, title, description]) => `<article class="creation-preview-card"><span class="creation-preview-icon" aria-hidden="true">${icon}</span><span class="preview-status">尚未启用</span><h3>${title}</h3><p>${description}</p><button class="button button-text" type="button" disabled>暂不可用</button></article>`).join("")}
        </section>
        ${fixtureNotice()}
      `;
    }

    if (route.key === "templates") {
      const templates = [
        ["情绪短片", "用克制镜头完成情绪表达", "30–45 秒 · 竖屏", fixture.assets[2].src],
        ["角色独白", "围绕一个角色展开内心叙事", "45–60 秒 · 竖屏", fixture.assets[3].src],
        ["商品电影广告", "以电影化视觉组织产品表达", "15–30 秒 · 横屏", ""],
        ["奇幻叙事", "建立世界观、冲突与视觉奇观", "60–90 秒 · 横屏", fixture.assets[4].src],
        ["人物预告片", "用高密度镜头建立人物印象", "30–45 秒 · 横屏", ""],
        ["竖屏剧情片", "适配移动观看的紧凑剧情结构", "45–90 秒 · 竖屏", fixture.assets[5].src]
      ];
      return `
        ${commonHeader("模板库", "从成熟的影片结构出发，快速理解不同内容类型的创作方式。", "影片结构预览")}
        <section class="template-preview-grid" aria-label="模板预览">
          ${templates.map(([title, purpose, meta, image], index) => `<article class="template-preview-card"><div class="template-preview-cover template-cover-${index + 1}">${image ? `<img src="${escapeHtml(image)}" alt="${escapeHtml(title)}视觉示例">` : ""}<span>尚未启用</span></div><div><h3>${title}</h3><p>${purpose}</p><small>${meta}</small></div></article>`).join("")}
        </section>
        ${fixtureNotice()}
      `;
    }

    if (route.key === "ip-studio") {
      const modules = [
        ["角色", "晚灯", "陪伴型夜灯角色"],
        ["世界观", "夜晚书桌", "安静陪伴的深夜空间"],
        ["人物关系", "等待整理", "暂无已确认关系"],
        ["时间线", "第 1 集", "当前项目中的角色表达参考"]
      ];
      return `
        ${commonHeader("IP工作室", "整理跨项目可复用的角色、世界观与创作规则。", "IP 结构预览")}
        <section class="ip-preview-hero"><div class="ip-preview-visual"><img src="${escapeHtml(fixture.character.referenceImage)}" alt="晚灯角色设定"><span>晚灯 <small>WANLIGHT</small></span></div><div class="ip-preview-copy"><span class="section-kicker">演示 IP</span><h2>晚灯</h2><p>陪伴型夜灯角色，以深蓝兜帽、暖色灯面和月牙标识建立稳定识别。</p><dl><div><dt>世界观</dt><dd>夜晚书桌 / 安静陪伴</dd></div><div><dt>角色规则</dt><dd>深蓝兜帽 / 暖色灯面 / 月牙标识</dd></div></dl></div></section>
        <section class="ip-preview-modules" aria-label="IP 管理结构预览">${modules.map(([title, value, description]) => `<article><span>${title}</span><strong>${value}</strong><p>${description}</p><small>尚未启用</small></article>`).join("")}</section>
        ${fixtureNotice()}
      `;
    }

    if (route.key === "memory") {
      const memories = [
        ["角色记忆", "保持晚灯的造型与表达一致"],
        ["视觉风格", "延续低照度与暖色视觉锚点"],
        ["项目偏好", "整理项目内已确认的创作选择"],
        ["创作规则", "在不同镜头间提醒一致性要求"]
      ];
      return `
        ${commonHeader("创作记忆", "未来用于帮助不同镜头保持角色、视觉和创作规则的一致性。", "一致性工具预览")}
        <section class="memory-preview-shell"><div class="memory-preview-intro"><span aria-hidden="true">◌</span><div><h2>让作品记住已经确认的选择</h2><p>当前不会记录或学习用户行为；这里只展示未来的信息组织方式。</p></div></div><div class="memory-preview-grid">${memories.map(([title, description], index) => `<article><span>${String(index + 1).padStart(2, "0")}</span><h3>${title}</h3><p>${description}</p><small>尚未启用</small></article>`).join("")}</div></section>
        ${fixtureNotice()}
      `;
    }

    if (route.key === "workflow-presets") {
      const stages = ["创意", "角色", "分镜", "画面", "声音", "预览"];
      return `
        ${commonHeader("工作流预设", "预览不同影片类型的创作路径，不执行任务或自动推进阶段。", "电影生产路径预览")}
        <section class="workflow-preview-shell"><ol class="workflow-preview-flow">${stages.map((stage, index) => `<li><span>${String(index + 1).padStart(2, "0")}</span><strong>${stage}</strong>${index < stages.length - 1 ? '<i aria-hidden="true">→</i>' : ""}</li>`).join("")}</ol><div class="workflow-preset-grid"><article><span>情绪短片流程</span><h3>从情绪主题到候选预览</h3><p>适合角色陪伴、内心独白与短篇情绪表达。</p><button class="button button-secondary" type="button" disabled>尚未启用</button></article><article><span>角色故事流程</span><h3>围绕角色建立连续叙事</h3><p>适合角色设定、场景关系与分镜连续性规划。</p><button class="button button-secondary" type="button" disabled>尚未启用</button></article></div></section>
        ${fixtureNotice()}
      `;
    }

    const charts = ["作品表现趋势", "制作效率", "内容表现"];
    return `
      ${commonHeader("数据分析", "当作品产生真实运营数据后，可在这里查看表现趋势。", "数据产品预览")}
      <section class="analytics-empty-grid" aria-label="数据分析空状态">${charts.map((title, index) => `<article><div class="analytics-empty-heading"><h3>${title}</h3><span>尚未启用</span></div><div class="analytics-empty-chart chart-${index + 1}" aria-hidden="true"><i></i><i></i><i></i><i></i></div><strong>暂无真实数据</strong><p>当前没有可展示的真实运营数据。</p></article>`).join("")}</section>
      ${fixtureNotice()}
    `;
  }

  function renderDirectorBriefField(key, label, helper, required = true) {
    return `
      <label class="director-field" for="director-${escapeHtml(key)}">
        <span>${escapeHtml(label)}</span>
        <input
          id="director-${escapeHtml(key)}"
          name="${escapeHtml(key)}"
          type="text"
          value="${escapeHtml(state.aiDirectorBrief[key] || "")}"
          autocomplete="off"
          ${required ? "required" : ""}
        >
        <small>${escapeHtml(helper)}</small>
      </label>
    `;
  }

  function renderDirectorCanvas() {
    if (state.aiDirectorPhase === "input") {
      return `
        <div class="director-canvas-empty" data-ai-director-state="input">
          <div class="director-plan-state director-plan-state-idle" role="status"><i aria-hidden="true"></i><span><strong>等待生成</strong><small>尚无候选方案</small></span></div>
          <div class="director-empty-intro"><span class="director-empty-mark" aria-hidden="true">✦</span><h3>导演方案将在这里生成</h3><p>完成左侧创意输入后，可以查看故事方向、剧本草案、分镜规划和视觉风格。</p></div>
          <div class="director-preview-tiles" aria-label="导演方案内容预览">${["故事方向", "剧本草案", "分镜规划", "视觉风格"].map((label, index) => `<span><i>${String(index + 1).padStart(2, "0")}</i><strong>${label}</strong></span>`).join("")}</div>
        </div>
      `;
    }

    if (state.aiDirectorPhase === "generating") {
      return `
        <div class="director-loading-state" data-ai-director-state="generating" role="status" aria-live="polite">
          <span class="loading-spinner" aria-hidden="true"></span>
          <div><h3>正在整理导演方案…</h3><p>正在根据创意简报组织故事、镜头与视觉方向。</p></div>
          <div class="director-plan-state director-plan-state-generating"><i aria-hidden="true"></i><span><strong>生成中</strong><small>正在校验候选方案</small></span></div>
        </div>
      `;
    }

    if (state.aiDirectorPhase === "error" && !state.aiDirectorPlan) {
      return `
        <div class="director-error-state" data-ai-director-state="error" role="alert">
          <span aria-hidden="true">!</span>
          <div><h3>导演方案暂时无法生成</h3><p>请稍后重试。创意输入仍保留在当前页面。</p><button class="button button-secondary" type="button" data-action="regenerate-ai-director">重新生成</button></div>
        </div>
      `;
    }

    const plan = state.aiDirectorPlan;
    if (!plan) return "";
    const story = plan.storyDirection;
    const script = plan.scriptDraft;
    const storyboard = plan.storyboardPlan;
    const visual = plan.visualStyle;
    const planState = state.aiDirectorConfirmed
      ? '<div class="director-plan-state director-plan-state-confirmed"><i aria-hidden="true"></i><span><strong>已确认</strong><small>当前会话</small></span></div>'
      : '<div class="director-plan-state director-plan-state-candidate"><i aria-hidden="true"></i><span><strong>待确认</strong><small>候选方案</small></span></div>';
    const storyboardDuration = storyboard.reduce((sum, shot) => sum + Number(shot.durationSec || 0), 0);
    return `
      <div class="director-result" data-ai-director-state="${state.aiDirectorConfirmed ? "confirmed" : "result"}">
        <div class="director-result-banner" role="status">
          <span aria-hidden="true">✦</span>
          <div><strong>候选导演方案已准备</strong><p>版本 ${state.aiDirectorPlanVersion}</p></div>
          ${planState}
        </div>
        ${state.aiDirectorPhase === "error" ? '<p class="director-retained-plan" role="alert">重新生成暂时失败，已确认方案仍保留在当前会话。</p>' : ""}
        <div class="director-output-grid">
          <article class="director-output-card is-selected"><span>01</span><h3>故事方向</h3><strong>${escapeHtml(story.title)}</strong><p>${escapeHtml(story.synopsis)}</p><ul>${story.keyBeats.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></article>
          <article class="director-output-card"><span>02</span><h3>剧本草案</h3><p><b>开场</b>${escapeHtml(script.opening)}</p><p><b>发展</b>${escapeHtml(script.development)}</p><p><b>高潮</b>${escapeHtml(script.climax)}</p><p><b>结尾</b>${escapeHtml(script.ending)}</p></article>
          <article class="director-output-card"><span>03</span><h3>分镜规划</h3><strong>${storyboard.length} 个镜头 · ${storyboardDuration} 秒</strong><ul>${storyboard.map((shot) => `<li>镜头 ${escapeHtml(shot.shotNo)} · ${escapeHtml(shot.shotSize)} · ${escapeHtml(shot.visualDescription)}</li>`).join("")}</ul></article>
          <article class="director-output-card"><span>04</span><h3>视觉风格</h3><p><b>光线</b>${escapeHtml(visual.lighting)}</p><p><b>色彩</b>${escapeHtml(visual.palette)}</p><p><b>构图</b>${escapeHtml(visual.composition)}</p><p><b>氛围</b>${escapeHtml(visual.atmosphere)}</p></article>
        </div>
        <div class="director-result-actions">
          <button class="button button-secondary" type="button" data-action="confirm-ai-director-plan" ${state.aiDirectorConfirmed ? "disabled" : ""}>${state.aiDirectorConfirmed ? "当前会话已确认" : "确认导演方案"}</button>
          <button class="button button-text" type="button" data-action="regenerate-ai-director">重新生成</button>
        </div>
      </div>
    `;
  }

  function renderDirectorPlanning() {
    const production = state.aiDirectorPlan && state.aiDirectorPlan.productionPlan;
    const canCreateEpisode = Boolean(production && state.confirmedCreativePlan && state.aiDirectorConfirmed && state.seriesEpisodePhase !== "creating");
    const listValue = (items, fallback) => Array.isArray(items) && items.length ? items.map(escapeHtml).join("、") : fallback;
    const seriesOptions = state.seriesRecords.map((series) => `<option value="${escapeHtml(series.seriesRef)}">${escapeHtml(series.title)}</option>`).join("");
    const handoff = state.aiDirectorConfirmed ? `
      <form id="series-episode-form" class="series-episode-form">
        <div class="series-handoff-heading"><span class="section-kicker">项目交接</span><strong>创建系列与集数</strong><p>把已确认方案关联到一个稳定的系列与单集制作记录。</p></div>
        <label class="field-label">系列
          <select name="seriesRef" data-action="select-series-mode" ${canCreateEpisode ? "" : "disabled"}>
            <option value="__new__">新建系列</option>${seriesOptions}
          </select>
        </label>
        <div class="new-series-fields">
          <label class="field-label">系列名称<input name="seriesTitle" maxlength="80" value="晚灯" required></label>
          <label class="field-label">计划集数<input name="plannedEpisodeCount" type="number" min="1" max="10000" value="12" required></label>
        </div>
        <label class="field-label">本集标题<input name="episodeTitle" maxlength="120" value="${escapeHtml(state.aiDirectorPlan.storyDirection.title || "第1集")}" required></label>
        <label class="field-label">集数<input name="episodeNumber" type="number" min="1" max="100000" value="1" required></label>
        ${state.seriesEpisodeError ? `<p class="form-error" role="alert">${escapeHtml(state.seriesEpisodeError)}</p>` : ""}
        <div class="director-plan-action">${state.seriesEpisodePhase === "creating" ? renderButtonLoading("正在创建…") : `<button class="button button-secondary" type="submit" ${canCreateEpisode ? "" : "disabled"}>创建单集制作记录</button>`}<p>保存后可在当前工作区继续查看；不会建立正式项目或启动制作任务。</p></div>
      </form>
    ` : '<div class="director-plan-action"><button class="button button-primary" type="button" disabled>创建单集制作记录</button><p>人工确认并保存当前创意方案后，才可创建系列与集数。</p></div>';
    return `
      <section class="director-planning-panel" aria-labelledby="director-planning-title">
        <div class="card-heading"><div><span class="section-kicker">制作规划</span><h3 id="director-planning-title">把方案带入项目</h3></div></div>
        <div class="director-plan-cover"><img src="${escapeHtml(fixture.assets[2].src)}" alt="晚灯制作规划视觉"><span>晚灯 · 情绪短片</span></div>
        <dl class="director-plan-list">
          <div><dt>镜头数量</dt><dd>${production ? `${escapeHtml(production.shotCount)} 个镜头` : "待生成"}</dd></div>
          <div><dt>角色需求</dt><dd>${production ? listValue(production.characters, "无") : "待生成"}</dd></div>
          <div><dt>场景需求</dt><dd>${production ? listValue(production.scenes, "无") : "待生成"}</dd></div>
          <div><dt>资产需求</dt><dd>${production ? listValue(production.visualAssets, "无") : "待生成"}</dd></div>
          <div><dt>声音需求</dt><dd>${production ? listValue(production.audioNeeds, "无") : "待生成"}</dd></div>
        </dl>
        ${handoff}
      </section>
    `;
  }

  function renderAiDirector() {
    const fields = [
      ["topic", "主题", "示例：孤独与陪伴"],
      ["theme", "类型", "示例：情感短片"],
      ["audience", "目标用户", "示例：短视频用户"],
      ["duration", "视频时长", "示例：30秒"],
      ["platform", "发布平台", "示例：短视频平台"],
      ["style", "视觉风格", "示例：电影感"],
      ["character", "角色设定", "可选 · 示例：晚灯 WANLIGHT"]
    ];
    return `
      ${renderPageHeader({
        eyebrow: "创意入口",
        title: "AI导演",
        description: "从创意输入到导演方案与制作规划，在一个工作台里完成。",
        status: "development"
      })}
      <div class="director-workspace director-studio-grid">
        <section class="director-brief-panel">
          <div class="card-heading"><div><span class="section-kicker">你的创意</span><h3>创意输入</h3></div></div>
          <p class="director-panel-intro">描述你想创作的影片，让导演方案拥有清晰方向。</p>
          <form id="ai-director-form" class="director-brief-form">
            ${fields.map(([key, label, helper]) => renderDirectorBriefField(key, label, helper, key !== "character")).join("")}
            <div class="director-form-footer"><span>通过安全服务整理方案，结果需人工确认。</span><button class="button button-primary" type="submit" ${state.aiDirectorPhase === "generating" ? "disabled" : ""}>${state.aiDirectorPhase === "generating" ? "正在整理…" : "生成创意方案"}</button></div>
          </form>
        </section>
        <section class="director-canvas-panel" aria-labelledby="director-canvas-title">
          <div class="card-heading"><div><span class="section-kicker">创作方案</span><h3 id="director-canvas-title" tabindex="-1">导演方案</h3></div></div>
          ${renderDirectorCanvas()}
        </section>
        ${renderDirectorPlanning()}
      </div>
      ${candidatePlanNotice()}
    `;
  }

  function findPersistedEpisode(episodeRef) {
    for (const series of state.seriesRecords) {
      const episode = (series.episodes || []).find((item) => item.episodeRef === episodeRef);
      if (episode) return { series, episode };
    }
    return null;
  }

  function findProject(projectRef) {
    return state.projectRecords.find((project) => project.projectRef === projectRef) || null;
  }

  function findSeries(seriesRef) {
    return state.seriesRecords.find((series) => series.seriesRef === seriesRef) || null;
  }

  function projectProductionContext(project, episodeRef = null) {
    if (!project) return null;
    const series = (project.seriesRefs || []).map(findSeries).find(Boolean) || null;
    if (!series) return { project, series: null, episode: null };
    const episode = episodeRef
      ? (series.episodes || []).find((item) => item.episodeRef === episodeRef) || null
      : (series.episodes || [])[0] || null;
    return { project, series, episode };
  }

  function projectForSeries(seriesRef) {
    return state.projectRecords.find((project) => (project.seriesRefs || []).includes(seriesRef)) || null;
  }

  function productionContexts() {
    return state.seriesRecords.flatMap((series) => {
      const project = projectForSeries(series.seriesRef);
      return (series.episodes || []).map((episode) => ({ project, series, episode }));
    });
  }

  function rememberProductionContext(persisted) {
    if (!persisted || !persisted.series || !persisted.episode) return null;
    state.selectedSeriesRef = persisted.series.seriesRef;
    state.selectedEpisodeRef = persisted.episode.episodeRef;
    return persisted;
  }

  function resolveSelectedProductionContext() {
    if (state.selectedEpisodeRef) {
      const selected = findPersistedEpisode(state.selectedEpisodeRef);
      if (selected && (!state.selectedSeriesRef || selected.series.seriesRef === state.selectedSeriesRef)) return selected;
      state.selectedSeriesRef = null;
      state.selectedEpisodeRef = null;
    }
    const contexts = productionContexts();
    return contexts.length === 1 ? rememberProductionContext(contexts[0]) : null;
  }

  function productionContextBase(persisted) {
    if (!persisted) return "";
    if (persisted.project) return `/creator/projects/${encodeURIComponent(persisted.project.projectRef)}/episodes/${encodeURIComponent(persisted.episode.episodeRef)}`;
    const project = projectForSeries(persisted.series.seriesRef);
    if (project) return `/creator/projects/${encodeURIComponent(project.projectRef)}/episodes/${encodeURIComponent(persisted.episode.episodeRef)}`;
    return `/creator/projects/${encodeURIComponent(persisted.episode.episodeRef)}`;
  }

  const storyViewSchemaVersion = "creator.story-view.v1";

  function buildStoryProjection(route) {
    const persisted = route && route.persisted;
    const episode = persisted && persisted.episode;
    const series = persisted && persisted.series;
    const binding = episode && episode.confirmedPlanBinding;
    const sourcePlan = binding && binding.sourcePlan;
    if (
      !series
      || !episode
      || !binding
      || !sourcePlan
      || binding.sourcePlanSchemaVersion !== "creator.ai-director.plan.v1"
      || sourcePlan.schemaVersion !== binding.sourcePlanSchemaVersion
    ) {
      return null;
    }

    const interpretation = sourcePlan.creativeInterpretation || {};
    const direction = sourcePlan.storyDirection || {};
    const production = sourcePlan.productionPlan || {};
    const visualStyle = sourcePlan.visualStyle || {};
    const storyboard = Array.isArray(sourcePlan.storyboardPlan) ? sourcePlan.storyboardPlan : [];
    const targetDurationSec = storyboard.reduce((total, shot) => total + Number(shot.durationSec || 0), 0);
    return {
      schemaVersion: storyViewSchemaVersion,
      projectRef: route.project ? route.project.projectRef : null,
      seriesRef: series.seriesRef,
      episodeRef: episode.episodeRef,
      sourcePlanRef: binding.sourcePlanRef,
      sourcePlanSchemaVersion: binding.sourcePlanSchemaVersion,
      sourcePlanVersion: binding.sourcePlanVersion,
      episodeNumber: episode.episodeNumber,
      seriesTitle: series.title,
      title: direction.title || episode.title,
      logline: interpretation.logline || "",
      coreTheme: interpretation.coreTheme || "",
      targetEmotion: interpretation.targetEmotion || "",
      synopsis: direction.synopsis || "",
      keyBeats: Array.isArray(direction.keyBeats) ? direction.keyBeats : [],
      narrativeStructure: interpretation.narrativeArc || "",
      characters: Array.isArray(production.characters) ? production.characters : [],
      scenes: Array.isArray(production.scenes) ? production.scenes : [],
      targetDurationSec,
      visualTone: visualStyle.atmosphere || interpretation.targetEmotion || ""
    };
  }

  function renderStoryView(route) {
    const contextBar = renderProjectContextBar({ ...route, group: "内容" });
    const projection = buildStoryProjection(route);
    const persisted = route.persisted || {};
    const series = persisted.series;
    const episode = persisted.episode;
    if (!projection) {
      return `
        ${contextBar}
        ${renderPageHeader({
          eyebrow: series && episode ? `${escapeHtml(series.title)} · 第 ${escapeHtml(episode.episodeNumber)} 集` : "项目工作室 · 故事",
          title: "故事",
          description: "查看本集经人工确认的故事基线。",
          status: "available",
          meta: localizedStatusBadge("等待上游确认", "neutral")
        })}
        <section class="card story-empty-card" data-story-state="missing-confirmed-plan">
          ${renderEmptyState({
            icon: "·",
            title: "尚未确认故事方案",
            description: "本集还没有已确认的导演方案。请先前往 AI导演完成方案确认，再返回查看故事基线。",
            action: '<a class="button button-primary" href="#/creator/ai-director">前往 AI导演</a>'
          })}
        </section>
      `;
    }

    const list = (values, emptyLabel) => values.length
      ? values.map((value) => `<li>${escapeHtml(value)}</li>`).join("")
      : `<li class="story-muted-item">${escapeHtml(emptyLabel)}</li>`;
    return `
      ${contextBar}
      ${renderPageHeader({
        eyebrow: `${escapeHtml(projection.seriesTitle)} · 第 ${escapeHtml(projection.episodeNumber)} 集`,
        title: "故事",
        description: "查看已确认导演方案形成的本集故事基线；正式剧本生成、编辑、版本与确认由剧本工作台负责。",
        status: "available",
        meta: localizedStatusBadge(`已确认导演方案 v${projection.sourcePlanVersion}`, "available")
      })}
      <section
        class="story-view"
        data-story-schema="${escapeHtml(projection.schemaVersion)}"
        data-series-ref="${escapeHtml(projection.seriesRef)}"
        data-episode-ref="${escapeHtml(projection.episodeRef)}"
        data-source-plan-ref="${escapeHtml(projection.sourcePlanRef)}"
        data-source-plan-version="${escapeHtml(projection.sourcePlanVersion)}"
      >
        <article class="card story-overview-card">
          <div class="card-heading">
            <div><span class="section-kicker">故事概览</span><h3>${escapeHtml(projection.title)}</h3></div>
            ${localizedStatusBadge("只读基线", "available")}
          </div>
          <div class="story-overview-grid">
            <section><span>核心主题</span><strong>${escapeHtml(projection.coreTheme || "尚未填写")}</strong></section>
            <section><span>目标情绪</span><strong>${escapeHtml(projection.targetEmotion || "尚未填写")}</strong></section>
          </div>
          <div class="story-copy-block"><span>Logline</span><p>${escapeHtml(projection.logline || "尚未填写")}</p></div>
          <div class="story-copy-block"><span>故事梗概</span><p>${escapeHtml(projection.synopsis || "尚未填写")}</p></div>
        </article>

        <article class="card story-beats-card">
          <div class="card-heading"><div><span class="section-kicker">叙事推进</span><h3>关键剧情节点</h3></div></div>
          <ol class="story-beat-list">
            ${projection.keyBeats.length
              ? projection.keyBeats.map((beat, index) => `<li><span>节点 ${index + 1}</span><p>${escapeHtml(beat)}</p></li>`).join("")
              : '<li class="story-muted-item">当前方案未提供关键剧情节点。</li>'}
          </ol>
          <div class="story-structure"><span>叙事结构</span><strong>${escapeHtml(projection.narrativeStructure || "按关键剧情节点推进")}</strong></div>
        </article>

        <aside class="card story-context-card">
          <div class="card-heading"><div><span class="section-kicker">制作上下文</span><h3>方案需求</h3></div></div>
          <section><span>角色需求</span><ul>${list(projection.characters, "尚未列出角色需求")}</ul></section>
          <section><span>场景需求</span><ul>${list(projection.scenes, "尚未列出场景需求")}</ul></section>
          <dl class="story-context-meta">
            <div><dt>目标时长</dt><dd>${escapeHtml(projection.targetDurationSec || "—")} 秒</dd></div>
            <div><dt>视觉基调</dt><dd>${escapeHtml(projection.visualTone || "尚未填写")}</dd></div>
          </dl>
        </aside>

        <article class="card story-lineage-card">
          <div><span class="section-kicker">来源追溯</span><h3>已确认导演方案 v${escapeHtml(projection.sourcePlanVersion)}</h3></div>
          <dl class="story-product-lineage">
            <div><dt>系列</dt><dd>${escapeHtml(projection.seriesTitle)}</dd></div>
            <div><dt>单集</dt><dd>第 ${escapeHtml(projection.episodeNumber)} 集</dd></div>
            <div><dt>来源版本</dt><dd>导演方案 v${escapeHtml(projection.sourcePlanVersion)}</dd></div>
          </dl>
          <details class="advanced-lineage"><summary>高级溯源</summary><dl>
            ${projection.projectRef ? `<div><dt>项目引用</dt><dd><code>${escapeHtml(projection.projectRef)}</code></dd></div>` : ""}
            <div><dt>系列引用</dt><dd><code>${escapeHtml(projection.seriesRef)}</code></dd></div>
            <div><dt>单集引用</dt><dd><code>${escapeHtml(projection.episodeRef)}</code></dd></div>
            <div><dt>来源方案引用</dt><dd><code>${escapeHtml(projection.sourcePlanRef)}</code></dd></div>
            <div><dt>来源结构</dt><dd><code>${escapeHtml(projection.sourcePlanSchemaVersion)}</code></dd></div>
          </dl></details>
          <a class="button button-primary" href="#${escapeHtml(route.episodeBase || productionContextBase(route.persisted))}/script">进入剧本工作台</a>
          <p>继续使用同一单集；导航不会复制故事文本，也不会创建新的故事事实。</p>
        </article>
      </section>
    `;
  }

  function renderEpisodeProject(route) {
    const { series, episode } = route.persisted;
    const binding = episode.confirmedPlanBinding || {};
    const sourcePlan = binding.sourcePlan || {};
    const storyDirection = sourcePlan.storyDirection || {};
    return `
      ${renderProjectContextBar({ ...route, group: "内容" })}
      ${renderPageHeader({
        eyebrow: `${escapeHtml(series.title)} · 第 ${escapeHtml(episode.episodeNumber)} 集`,
        title: episode.title,
        description: "该单集已关联到一个经人工确认的 AI导演方案。",
        status: "available",
        meta: localizedStatusBadge("项目草稿", "neutral")
      })}
      <section class="episode-source-grid">
        <article class="card episode-source-card">
          <div class="card-heading"><div><span class="section-kicker">项目来源</span><h3>已确认的导演方案</h3></div>${localizedStatusBadge("已人工确认", "available")}</div>
          <dl class="episode-source-list">
            <div><dt>所属系列</dt><dd>${escapeHtml(series.title)}</dd></div>
            <div><dt>集数</dt><dd>第 ${escapeHtml(episode.episodeNumber)} 集</dd></div>
            <div><dt>方案版本</dt><dd>v${escapeHtml(episode.sourcePlanVersion)}</dd></div>
            <div><dt>来源能力</dt><dd>AI导演方案</dd></div>
            <div><dt>项目状态</dt><dd>${episode.status === "draft" ? "草稿" : escapeHtml(episode.status)}</dd></div>
          </dl>
        </article>
        <article class="card episode-boundary-card">
          <span class="section-kicker">单集状态</span>
          <h3>单集制作记录</h3>
          <p>当前单集可在刷新和本地服务重启后继续读取，并继续使用同一正式项目上下文。</p>
          <ul><li>导演方案来源关系已保留</li><li>系列与单集关系已保留</li><li>剧本工作台继续使用同一单集上下文</li></ul>
        </article>
        <article class="card episode-source-plan-card">
          <div class="card-heading"><div><span class="section-kicker">来源导演方案</span><h3>${escapeHtml(storyDirection.title || "已确认导演方案")}</h3></div>${localizedStatusBadge("不可变绑定", "available")}</div>
          <p>${escapeHtml(storyDirection.synopsis || "来源方案已保存，可供下一阶段读取。")}</p>
          <dl class="episode-source-list">
            <div><dt>来源方案</dt><dd>已确认导演方案 v${escapeHtml(String(binding.sourcePlanVersion || 1))}</dd></div>
            <div><dt>来源结构</dt><dd>导演方案 v1</dd></div>
            <div><dt>版本</dt><dd>v${escapeHtml(binding.sourcePlanVersion || episode.sourcePlanVersion)}</dd></div>
            <div><dt>正式项目</dt><dd>${route.project ? escapeHtml(route.project.title) : "兼容入口 · 待关联"}</dd></div>
          </dl>
        </article>
      </section>
    `;
  }

  function selectedScriptVersion() {
    const versions = state.scriptWorkspace && state.scriptWorkspace.versions ? state.scriptWorkspace.versions : [];
    return versions.find((item) => item.scriptVersionRef === state.selectedScriptVersionRef)
      || (versions.length ? versions[versions.length - 1] : null);
  }

  function selectedScriptScene() {
    const version = selectedScriptVersion();
    if (!version) return null;
    return (version.scenes || []).find((scene) => scene.scriptSceneRef === state.selectedScriptSceneRef)
      || version.scenes[0]
      || null;
  }

  function scriptChangeLabel(value) {
    return {
      "ai-generation": "初稿生成",
      "manual-edit": "人工编辑",
      "ai-scene-rewrite": "场景改写"
    }[value] || "剧本版本";
  }

  function scriptLines(values) {
    return (values || []).join("\n");
  }

  function dialogueLines(values) {
    return (values || []).map((item) => `${item.speaker} | ${item.emotion || ""} | ${item.text}`).join("\n");
  }

  function renderScriptSource(route, bootstrap) {
    const direction = bootstrap.storyDirection || {};
    const draft = bootstrap.scriptDraft || {};
    const generating = state.scriptPhase === "generating";
    return `
      ${renderPageHeader({
        eyebrow: `${route.persisted.series.title} · 第 ${route.persisted.episode.episodeNumber} 集 · 剧本`,
        title: "剧本工作室",
        description: "从本集已确认的导演方案生成、编辑并确认可追溯的正式剧本版本。",
        status: "available",
        meta: localizedStatusBadge("尚未生成剧本", "neutral")
      })}
      <section class="script-source-layout" data-script-state="${generating ? "generating" : state.scriptError ? "error" : "empty"}">
        <article class="card script-source-card">
          <div class="card-heading"><div><span class="section-kicker">上游来源</span><h3>已确认的本集创意上下文</h3></div>${localizedStatusBadge("已人工确认", "available")}</div>
          <h4>${escapeHtml(direction.title || route.persisted.episode.title)}</h4>
          <p>${escapeHtml(direction.synopsis || draft.summary || "本集导演方案已确认，可进入剧本生产。")}</p>
          <dl class="script-lineage-list">
            <div><dt>系列</dt><dd>${escapeHtml(route.persisted.series.title)}</dd></div>
            <div><dt>集数</dt><dd>第 ${escapeHtml(route.persisted.episode.episodeNumber)} 集</dd></div>
            <div><dt>目标时长</dt><dd>${escapeHtml(draft.targetDurationSec || bootstrap.productionPlan && bootstrap.productionPlan.targetDurationSec || 30)} 秒</dd></div>
            <div><dt>来源版本</dt><dd>导演方案 v${escapeHtml(bootstrap.sourcePlanVersion)}</dd></div>
          </dl>
        </article>
        <article class="card script-start-card">
          <span class="script-start-mark" aria-hidden="true">文</span>
          <span class="section-kicker">剧本工作台</span>
          <h3>生成第一个不可变剧本版本</h3>
          <p>生成结果会先经过本地结构与时长校验，并以待确认版本保存。生成成功不代表人工确认。</p>
          ${state.scriptError ? renderErrorState("剧本生成未完成", state.scriptError) : ""}
          <button class="button button-secondary" type="button" data-action="generate-script" ${generating ? "disabled" : ""}>${generating ? "正在生成剧本…" : "生成正式剧本"}</button>
        </article>
      </section>
    `;
  }

  function renderScriptStudio(route) {
    const contextBar = renderProjectContextBar({ ...route, group: "内容" });
    if (state.scriptWorkspaceStatus === "idle" || state.scriptWorkspaceStatus === "loading") {
      return `${contextBar}${renderPageHeader({ eyebrow: "项目工作室 · 剧本", title: "剧本工作室", description: "正在读取本集剧本与版本历史。", status: "available" })}${renderLoadingState("正在读取剧本工作区")}`;
    }
    if (state.scriptWorkspaceStatus === "error" || !state.scriptWorkspace) {
      return `${contextBar}${renderPageHeader({ eyebrow: "项目工作室 · 剧本", title: "剧本工作室", description: "本集剧本暂时无法读取。", status: "available" })}${renderErrorState("剧本工作区暂时不可用", state.scriptError || "请稍后重试。")}`;
    }
    const workspace = state.scriptWorkspace;
    if (!workspace.script) return `${contextBar}${renderScriptSource(route, workspace.bootstrap)}`;
    const version = selectedScriptVersion();
    const scene = selectedScriptScene();
    const confirmedRef = workspace.script.confirmedScriptVersionRef;
    const isSelectedConfirmed = Boolean(version && version.scriptVersionRef === confirmedRef);
    const totalDuration = (version.scenes || []).reduce((sum, item) => sum + Number(item.estimatedDurationSec || 0), 0);
    const phaseLabel = state.scriptPhase === "generating" ? "正在生成剧本…" : state.scriptPhase === "saving" ? "正在保存新版本…" : state.scriptPhase === "rewriting" ? "正在改写所选场景…" : state.scriptPhase === "confirming" ? "正在确认版本…" : "";
    const confirmed = Boolean(confirmedRef);
    return `
      ${contextBar}
      ${renderPageHeader({
        eyebrow: `${route.persisted.series.title} · 第 ${route.persisted.episode.episodeNumber} 集 · 剧本`,
        title: version.title,
        description: `${version.scenes.length} 场 · 预计 ${totalDuration} 秒 · 当前选择 v${version.versionNumber}`,
        status: "available",
        meta: isSelectedConfirmed ? localizedStatusBadge("已确认版本", "available") : localizedStatusBadge("待人工确认", "neutral")
      })}
      ${state.scriptError ? renderErrorState("剧本操作未完成", state.scriptError) : ""}
      ${phaseLabel ? `<div class="script-operation-state" role="status"><span class="button-spinner" aria-hidden="true"></span><strong>${escapeHtml(phaseLabel)}</strong></div>` : ""}
      <section class="script-studio-layout" data-script-state="${state.scriptError ? "error" : confirmed ? "confirmed" : state.scriptPhase === "idle" ? "ready" : escapeHtml(state.scriptPhase)}">
        <aside class="card script-scenes-panel" aria-label="剧本场景">
          <div class="card-heading"><div><span class="section-kicker">场景</span><h3>本集结构</h3></div><span>${version.scenes.length} 场</span></div>
          <div class="script-scene-list">${version.scenes.map((item) => `
            <button type="button" class="script-scene-item ${scene && scene.scriptSceneRef === item.scriptSceneRef ? "is-selected" : ""}" data-action="select-script-scene" data-scene-ref="${escapeHtml(item.scriptSceneRef)}" aria-pressed="${scene && scene.scriptSceneRef === item.scriptSceneRef}">
              <span>${String(item.sceneNumber).padStart(2, "0")}</span><strong>${escapeHtml(item.heading)}</strong><small>${escapeHtml(item.estimatedDurationSec)} 秒</small>
            </button>`).join("")}</div>
          <div class="script-source-mini"><span>来源</span><strong>已确认导演方案 v${escapeHtml(version.sourcePlanVersion)}</strong><small>与当前单集保持一致</small></div>
        </aside>
        <main class="card script-editor-panel">
          <form id="script-edit-form">
            <input type="hidden" name="scriptSceneRef" value="${escapeHtml(scene.scriptSceneRef)}">
            <div class="script-editor-heading"><div><span class="section-kicker">场景 ${escapeHtml(scene.sceneNumber)}</span><h3>${escapeHtml(scene.heading)}</h3></div><span>${escapeHtml(scene.estimatedDurationSec)} 秒</span></div>
            <div class="script-form-grid script-form-grid-meta">
              <label><span>剧本标题</span><input name="title" required maxlength="120" value="${escapeHtml(version.title)}"></label>
              <label><span>场景标题</span><input name="heading" required maxlength="120" value="${escapeHtml(scene.heading)}"></label>
              <label><span>地点</span><input name="location" required maxlength="120" value="${escapeHtml(scene.location)}"></label>
              <label><span>时间</span><input name="timeOfDay" required maxlength="80" value="${escapeHtml(scene.timeOfDay)}"></label>
            </div>
            <label class="script-field-wide"><span>剧情梗概</span><textarea name="synopsis" required rows="3">${escapeHtml(version.synopsis)}</textarea></label>
            <label class="script-field-wide"><span>场景动作</span><textarea name="action" required rows="5">${escapeHtml(scene.action)}</textarea></label>
            <label class="script-field-wide"><span>对白 <small>每行：说话人 | 情绪 | 台词</small></span><textarea name="dialogue" rows="5">${escapeHtml(dialogueLines(scene.dialogue))}</textarea></label>
            <div class="script-form-grid">
              <label><span>旁白 <small>每行一条</small></span><textarea name="narration" rows="4">${escapeHtml(scriptLines(scene.narration))}</textarea></label>
              <label><span>字幕意图 <small>每行一条，不含精确时间码</small></span><textarea name="subtitleText" rows="4">${escapeHtml(scriptLines(scene.subtitleText))}</textarea></label>
            </div>
            <div class="script-editor-actions"><span>保存会创建新的不可变剧本版本。</span><button class="button button-secondary" type="submit" ${state.scriptPhase !== "idle" ? "disabled" : ""}>保存为新版本</button></div>
          </form>
          <form id="script-rewrite-form" class="script-rewrite-form">
            <div><span class="section-kicker">局部改写</span><h4>只改写当前场景</h4><p>其他场景与本集已确认导演方案约束保持不变。</p></div>
            <label><span>改写要求</span><input name="instruction" required maxlength="500" placeholder="例如：缩短对白，让情绪转折更克制"></label>
            <button class="button button-secondary" type="submit" ${state.scriptPhase !== "idle" ? "disabled" : ""}>改写当前场景</button>
          </form>
        </main>
        <aside class="card script-versions-panel" aria-label="剧本版本历史">
          <div class="card-heading"><div><span class="section-kicker">版本历史</span><h3>${workspace.versions.length} 个版本</h3></div></div>
          <div class="script-version-list">${[...workspace.versions].reverse().map((item) => `
            <button type="button" class="script-version-item ${item.scriptVersionRef === version.scriptVersionRef ? "is-selected" : ""}" data-action="select-script-version" data-version-ref="${escapeHtml(item.scriptVersionRef)}" aria-pressed="${item.scriptVersionRef === version.scriptVersionRef}">
              <span>v${item.versionNumber}</span><strong>${escapeHtml(scriptChangeLabel(item.changeKind))}</strong><small>${item.scriptVersionRef === confirmedRef ? "已确认" : "待确认"}</small>
            </button>`).join("")}</div>
          <section class="script-confirmation-card">
            <span class="section-kicker">人工确认</span>
            <strong>${isSelectedConfirmed ? `v${version.versionNumber} 已确认` : `确认 v${version.versionNumber}`}</strong>
            <p>${isSelectedConfirmed ? "该不可变版本是当前确认版本。" : "确认只更新引用，不会改写任何历史版本。"}</p>
            <button class="button button-secondary" type="button" data-action="confirm-script-version" ${isSelectedConfirmed || state.scriptPhase !== "idle" ? "disabled" : ""}>${isSelectedConfirmed ? "当前已确认" : "确认此版本"}</button>
          </section>
          <section class="storyboard-bridge-card">
            <span class="section-kicker">下游桥接</span><strong>${state.storyboardBootstrap ? "分镜输入已就绪" : "等待剧本确认"}</strong>
            <p>${state.storyboardBootstrap ? "已生成可追溯输入；仍需角色与 IP 能力完成绑定，不会开始分镜生产。" : "草稿版本不会开放分镜输入。"}</p>
            ${state.storyboardBootstrap ? '<small>来源与版本关系已保留</small>' : ""}
          </section>
        </aside>
      </section>
    `;
  }

  function renderCharacter() {
    return `
      ${renderPageHeader({
        eyebrow: "项目工作室 · 角色",
        title: "晚灯 WANLIGHT",
        description: "管理角色身份、视觉设定、版本与项目使用情况。",
        status: "fixture",
        meta: governanceBadge("权利待确认", "hold")
      })}
      <section class="character-grid v2-character-grid">
        <article class="reference-card">
          <div class="reference-image"><img src="${escapeHtml(fixture.character.referenceImage)}" alt="晚灯角色设定表"></div>
          <div class="reference-copy">
            <span class="section-kicker">角色身份</span>
            <div class="status-cluster">${statusBadge("fixture")}${governanceBadge("权利待确认", "hold")}</div>
            <h3>${escapeHtml(fixture.character.name)} <small>${escapeHtml(fixture.character.romanizedName)}</small></h3>
            <p>陪伴型夜灯角色 · 角色设定 v0.1 · 使用项目 ${displayProjectTitle}</p>
          </div>
        </article>
        <article class="character-spec-card">
          <div class="card-heading"><div><span class="section-kicker">视觉设定</span><h3>角色识别锚点</h3></div><span>${fixture.character.anchors.length} 项</span></div>
          <ul class="anchor-list">${fixture.character.anchors.map((anchor, index) => `<li><span>${index + 1}</span><strong>${escapeHtml(anchor)}</strong></li>`).join("")}</ul>
          <div class="palette-row" aria-label="晚灯候选配色">${fixture.character.palette.map((color) => `<span class="palette-swatch" style="--swatch:${escapeHtml(color)}"><i>${escapeHtml(color)}</i></span>`).join("")}</div>
          <div class="rights-summary compact"><span aria-hidden="true">!</span><div><strong>权利待确认</strong><p>当前角色仅用于内部演示，正式使用前需要人工确认。</p></div></div>
        </article>
      </section>
      <section class="asset-browser compact-browser">
        <div class="card-heading"><div><span class="section-kicker">角色画面</span><h3>设定与关键帧</h3></div><a class="text-link" href="#/creator/assets">打开资产库 →</a></div>
        ${renderAssetGrid(fixture.assets.slice(0, 4))}
      </section>
      ${fixtureNotice()}
    `;
  }

  function selectedShot() {
    return fixture.shots.find((shot) => shot.localKey === state.selectedShotKey) || fixture.shots[0];
  }

  function renderStoryboard() {
    const shot = selectedShot();
    const selectedShotIndex = fixture.shots.findIndex((item) => item.localKey === shot.localKey);
    const shotScale = ["中景", "近景", "特写", "俯拍近景", "特写", "中近景"];
    const shotCamera = ["固定", "轻微推进", "固定", "固定", "轻微推进", "固定"];
    return `
      ${renderPageHeader({
        eyebrow: "项目工作室 · 分镜",
        title: "影视分镜墙",
        description: `用连续镜头组织${displayProjectTitle}的情绪与视觉节奏。`,
        status: "fixture",
        meta: governanceBadge("6 SHOTS · 45 SECONDS", "neutral")
      })}
      <section class="timeline-rail v2-timeline-rail" aria-label="45 秒镜头顺序">
        ${fixture.shots.map((item, index) => `<button type="button" class="timeline-segment ${item.localKey === state.selectedShotKey ? "is-selected" : ""}" style="--segment:${(item.duration / 45) * 100}%" data-action="select-shot" data-shot-key="${escapeHtml(item.localKey)}" aria-pressed="${item.localKey === state.selectedShotKey}"><strong>镜头 ${String(index + 1).padStart(2, "0")}</strong><small>${item.start}–${item.end}秒</small></button>`).join("")}
      </section>
      <section class="storyboard-layout v2-storyboard-layout">
        <div class="shot-grid v2-shot-grid">
          ${fixture.shots.map((item, index) => `
            <button type="button" class="shot-card ${item.localKey === state.selectedShotKey ? "is-selected" : ""}" data-action="select-shot" data-shot-key="${escapeHtml(item.localKey)}" aria-pressed="${item.localKey === state.selectedShotKey}">
              <span class="shot-image"><img src="${escapeHtml(item.image)}" alt="镜头 ${String(index + 1).padStart(2, "0")} ${escapeHtml(item.title)}"><i>镜头 ${String(index + 1).padStart(2, "0")}</i></span>
              <span class="shot-card-copy"><span class="shot-card-top"><strong>${escapeHtml(item.title)}</strong><em>${item.status === "Review required" ? "待确认" : "可用"}</em></span><span class="shot-spec"><small>时长 <b>${item.duration}秒</b></small><small>景别 <b>${shotScale[index]}</b></small><small>运镜 <b>${shotCamera[index]}</b></small></span></span>
            </button>
          `).join("")}
        </div>
        <aside class="shot-detail-panel" aria-label="选中镜头详情">
          <img src="${escapeHtml(shot.image)}" alt="${escapeHtml(shot.code)} 选中镜头">
          <div class="shot-detail-heading"><div><span class="section-kicker">选中镜头</span><h3>镜头 ${String(selectedShotIndex + 1).padStart(2, "0")} · ${escapeHtml(shot.title)}</h3></div><strong>${shot.start}.0–${shot.end}.0 秒</strong></div>
          <blockquote>${escapeHtml(shot.caption)}</blockquote>
          ${shot.secondaryCaption ? `<div class="secondary-caption"><small>${escapeHtml(shot.secondaryCaptionWindow)}</small><p>${escapeHtml(shot.secondaryCaption)}</p></div>` : ""}
          <p class="shot-note">镜头说明仅用于当前审看。</p>
        </aside>
      </section>
      ${fixtureNotice()}
    `;
  }

  function renderPreview() {
    const preview = fixture.preview;
    return `
      ${renderPageHeader({
        eyebrow: "项目工作室 · 预览",
        title: "影片预览",
        description: `${displayProjectTitle} · 当前版本 v1`,
        status: "fixture",
        meta: governanceBadge("LOCAL REVIEW CANDIDATE", "candidate")
      })}
      <section class="preview-layout v2-preview-layout">
        <article class="player-card v2-player-card">
          <div class="candidate-preview-ribbon"><strong>候选预览</strong><span>尚未正式导出</span></div>
          <div class="player-stage">
            <div class="phone-frame">
              <video id="candidate-video" preload="metadata" playsinline muted poster="${escapeHtml(preview.poster)}" aria-label="晚灯第 1 集候选版本预览">
                <source src="${escapeHtml(preview.src)}" type="video/mp4">
                当前浏览器无法播放此候选影片。
              </video>
            </div>
          </div>
          <div class="player-controls" aria-label="影片播放控制">
            <button class="button button-secondary compact" type="button" data-action="toggle-preview" aria-pressed="false"><span aria-hidden="true">▶</span><span id="preview-play-label">播放</span></button>
            <button class="button button-secondary compact" type="button" data-action="toggle-preview-mute" aria-pressed="true"><span aria-hidden="true">∅</span><span id="preview-mute-label">静音 · 无音轨</span></button>
            <span class="preview-time" id="preview-time">00:00 / 00:45</span>
            <span class="preview-state" id="preview-state">已暂停</span>
          </div>
          <div id="preview-error" hidden>${renderErrorState("候选影片无法播放", "请确认演示文件仍在当前工作区；页面不会自动上传或处理媒体。")}</div>
        </article>
        <details class="preview-info-card v2-preview-info">
          <summary><span><small>影片详情</small><strong>${displayProjectTitle}</strong></span><i aria-hidden="true">⌄</i></summary>
          <div class="preview-info-body"><p>45 秒情绪短片 · 当前为候选预览</p>
          <div class="preview-facts"><span><small>时长</small><strong>45 秒</strong></span><span><small>画幅</small><strong>9:16</strong></span><span><small>声音</small><strong>无音轨</strong></span><span><small>版本</small><strong>v1</strong></span></div>
          <section><span class="inspector-label">版本</span><strong>候选版本 v1</strong><p>可在当前工作区播放和审看。</p></section>
          <section><span class="inspector-label">权利状态</span>${governanceBadge("权利待确认", "hold")}<p>正式导出前需要完成人工确认。</p></section>
          <section><span class="inspector-label">反馈</span><p>评论功能尚未启用。当前不会保存反馈。</p></section>
          <details class="preview-technical-details"><summary>查看技术信息</summary><p>${escapeHtml(preview.dimensions)} · ${escapeHtml(preview.frameRate)} · ${escapeHtml(preview.codec)}</p><code>${escapeHtml(preview.sha256)}</code></details>
          </div>
        </details>
      </section>
      ${fixtureNotice()}
    `;
  }

  function renderWorks() {
    return `
      ${renderPageHeader({
        eyebrow: "展示与交付",
        title: "作品",
        description: "浏览制作中的项目、候选预览与未来完成作品。",
        status: "fixture"
      })}
      <nav class="works-filter" aria-label="作品分类"><button type="button">制作中</button><button class="is-active" type="button">可预览</button><button type="button">完成作品</button></nav>
      <section class="works-section works-gallery-section"><div class="v2-section-heading"><div><span>可预览</span><h2>候选影片</h2></div><span>1 个版本</span></div><article class="work-cinema-card work-preview"><img src="${escapeHtml(fixture.preview.poster)}" alt="晚灯候选影片海报"><div><span>候选预览</span><h3>${displayProjectTitle}</h3><p>情绪短片 · 45 秒 · 竖屏 9:16</p><div class="button-row"><a class="button button-primary" href="#${projectBase}/preview">查看预览</a><a class="button button-cinema" href="#${projectBase}/pipeline">继续制作</a></div></div></article></section>
      <section class="works-section works-empty"><div class="v2-section-heading"><div><span>完成作品</span><h2>准备好后会出现在这里</h2></div></div>${renderEmptyState({ icon: "◇", title: "还没有完成作品", description: "当前候选尚未正式导出；这里不会展示虚构作品。" })}</section>
      ${fixtureNotice()}
    `;
  }

  function renderExport() {
    return `
      ${renderPageHeader({
        eyebrow: "项目工作室 · 交付",
        title: "导出",
        description: "查看候选影片的交付准备情况，正式导出功能尚未开放。",
        status: "fixture",
        meta: governanceBadge("导出受限", "blocked")
      })}
      ${fixtureNotice()}
      <section class="card export-gate-card">
        <div class="export-lock" aria-hidden="true">↗</div>
        <span class="section-kicker">交付准备</span>
        <h3>当前候选版本尚不能正式导出</h3>
        <p>候选版本已完成本地技术检查，但创意确认、权利确认与发布准备仍未完成。</p>
        <div class="export-gates">
          <article><span>01</span><div><strong>创意确认</strong><p>等待人工确认</p></div>${governanceBadge("未完成", "blocked")}</article>
          <article><span>02</span><div><strong>权利确认</strong><p>需要人工复核</p></div>${governanceBadge("暂缓", "hold")}</article>
          <article><span>03</span><div><strong>导出能力</strong><p>当前阶段暂不提供</p></div>${governanceBadge("不可用", "blocked")}</article>
          <article><span>04</span><div><strong>发布准备</strong><p>尚未进入发布阶段</p></div>${governanceBadge("未开始", "blocked")}</article>
        </div>
        <button class="button button-secondary export-button" type="button" data-capability="export" disabled>导出不可用</button>
        <small>当前不会生成文件、下载内容或执行发布。</small>
        <span class="sr-only">导出能力尚未实现，渲染与下载均不可用。</span>
      </section>
    `;
  }

  function renderCreationCenterR1() {
    return `${renderPageHeader({ eyebrow: "创意实验区", title: "创作中心", description: "探索未来创意工具；实验内容不会自动进入正式项目。", status: "planned" })}<section class="creation-r1-hero"><div><span class="section-kicker">创意能力预览</span><h2>探索创意能力，不越过制作门禁</h2><p>所有模块都显示真实能力状态。未建立能力、输入合同或正式项目上下文时，不会执行生成。</p></div><span class="creation-r1-seal">R1<br><small>页面预览</small></span></section><section class="creation-r1-grid">${creationModules.map((module,index) => `<a href="#${escapeHtml(module.path)}"><span class="module-number">0${index+1}</span><div><small>创作工具</small><h3>${escapeHtml(module.label)}</h3><p>${escapeHtml(module.description)}</p></div><em>${escapeHtml(module.version)}</em></a>`).join("")}</section>`;
  }

  function renderCreationPreviewR1(route) {
    const copy = {
      generation: ["图片与视频", "未来从已确认资产需求发起受控生成。", ["输入合同","候选输出","人工接纳"]],
      templates: ["模板", "未来浏览经过版本化和适用范围确认的模板。", ["类型筛选","结构预览","应用门禁"]],
      "prompt-lab": ["提示词实验", "隔离实验创意表达，不自动写入正式制作记录。", ["实验输入","参数比较","结果审查"]],
      audio: ["声音实验", "未来探索对白、环境声与音乐候选。", ["声音意图","候选试听","权利确认"]],
      models: ["创意实验", "未来在受控环境比较创意能力；当前不开放底层配置。", ["能力目录","安全配置","评估证据"]],
      tools: ["快捷工具", "未来承载不改变权威数据的小型创作工具。", ["输入","本地处理","人工确认"]]
    }[route.key];
    return `${renderPageHeader({ eyebrow: "创作中心 · 功能预览", title: copy[0], description: copy[1], status: "planned" })}<section class="creation-tool-shell"><div class="tool-shell-canvas"><span class="section-kicker">工作区预览</span><h3>${escapeHtml(copy[0])}工作台</h3><p>能力尚未授权。此页面没有实际生成、后台任务或生成结果。</p><div class="tool-shell-input"><label>未来输入区域<textarea disabled placeholder="等待能力合同与正式输入"></textarea></label><button class="button button-primary" type="button" disabled>能力未启用</button></div></div><aside>${copy[2].map((item,index) => `<article><span>0${index+1}</span><strong>${escapeHtml(item)}</strong><small>尚未建立</small></article>`).join("")}</aside></section>`;
  }

  function selectedSeriesPlanVersion() {
    const workspace = state.seriesPlanningWorkspace;
    const versions = workspace && Array.isArray(workspace.versions) ? workspace.versions : [];
    return versions.find((item) => item.seriesPlanVersionRef === state.selectedSeriesPlanVersionRef)
      || (versions.length ? versions[versions.length - 1] : null);
  }

  function seriesPlanningLoading(route, title) {
    return `${renderProjectContextBar(route)}${renderPageHeader({ eyebrow: "策划 · 系列规划", title, description: "正在读取项目与系列规划上下文。", status: "available" })}${renderLoadingState("正在读取系列规划")}`;
  }

  function renderSeriesDirectorCandidate(candidate) {
    const arcs = candidate.mainArcs || [];
    const items = candidate.episodePlanItems || [];
    return `
      <section class="series-director-candidate" data-series-plan-candidate="true">
        <header><div><span class="section-kicker">候选系列方案</span><h3>${escapeHtml(candidate.seriesConcept)}</h3></div>${localizedStatusBadge("等待人工确认", "development")}</header>
        <div class="series-candidate-summary">
          <article><span>故事前提</span><p>${escapeHtml(candidate.premise)}</p></article>
          <article><span>系列 Logline</span><p>${escapeHtml(candidate.logline)}</p></article>
          <article><span>主叙事方向</span><p>${escapeHtml(candidate.mainNarrativeDirection)}</p></article>
        </div>
        <div class="series-candidate-metrics"><span><strong>${arcs.length}</strong> 条主弧线</span><span><strong>${items.length}</strong> 个计划分集</span><span><strong>${(candidate.characterArcIntents || []).length}</strong> 条角色成长意图</span></div>
        <div class="series-candidate-arcs">${arcs.map((arc) => `<article><small>ARC ${escapeHtml(arc.arcNumber)} · EP${String(arc.episodeStart).padStart(2, "0")}–EP${String(arc.episodeEnd).padStart(2, "0")}</small><strong>${escapeHtml(arc.title)}</strong><p>${escapeHtml(arc.objective)}</p></article>`).join("")}</div>
        <div class="series-candidate-actions"><button class="button button-primary" type="button" data-action="confirm-series-plan">确认并建立系列规划 v1</button><button class="button button-text" type="button" data-action="regenerate-series-plan">重新生成候选</button><p>人工确认后才会由 V5 建立不可变规划版本；不会批量创建单集。</p></div>
      </section>`;
  }

  function renderProjectSeriesDirector(route) {
    if (state.seriesPlanningStatus === "idle" || state.seriesPlanningStatus === "loading") return seriesPlanningLoading(route, "项目 AI导演");
    if (state.seriesPlanningStatus === "error" || !state.seriesPlanningWorkspace) {
      return `${renderProjectContextBar(route)}${renderPageHeader({ eyebrow: "策划 · AI导演", title: "项目 AI导演", description: "基于真实项目与系列上下文组织系列规划候选。", status: "available" })}${renderErrorState("系列导演暂时不可用", state.seriesPlanningError || "请稍后重试。")}`;
    }
    const workspace = state.seriesPlanningWorkspace;
    const context = workspace.context;
    const plan = workspace.plan;
    const series = context.series;
    const project = context.project;
    const generating = state.seriesPlanningPhase === "generating";
    const existing = plan ? selectedSeriesPlanVersion() : null;
    return `
      ${renderProjectContextBar(route)}
      ${renderPageHeader({ eyebrow: `${escapeHtml(project.title)} · 系列策划`, title: "项目 AI导演", description: "使用真实项目上下文生成系列规划候选，并在人工确认后交给 V5 保存。", status: "available", meta: localizedStatusBadge(plan ? "已有确认规划" : "等待规划", plan ? "available" : "neutral") })}
      <section class="series-director-layout" data-series-director="true">
        <article class="enterprise-panel series-director-context">
          <header><div><span class="section-kicker">项目上下文</span><h3>${escapeHtml(project.title)}</h3></div>${localizedStatusBadge("正式项目", "available")}</header>
          <dl><div><dt>系列</dt><dd>${escapeHtml(series.title)}</dd></div><div><dt>计划集数</dt><dd>${escapeHtml(project.plannedEpisodeCount)}</dd></div><div><dt>已创建单集</dt><dd>${escapeHtml((series.episodes || []).length)}</dd></div><div><dt>目标平台</dt><dd>${escapeHtml(project.targetPlatform || "尚未设置")}</dd></div></dl>
          <p>计划分集是规划事实，不是生产单集；系统不会按计划集数批量创建 Episode。</p>
        </article>
        <article class="enterprise-panel series-director-input">
          <header><div><span class="section-kicker">Series Director</span><h3>系列创意输入</h3></div></header>
          ${plan ? `<div class="series-existing-plan"><strong>系列规划已经建立</strong><p>当前确认版本为 v${escapeHtml(existing ? existing.versionNumber : "—")}。如需查看弧线、计划分集与版本历史，请进入系列规划。</p><a class="button button-secondary" href="#${escapeHtml(route.projectBase)}/planning/series">查看系列规划</a></div>` : `
            <form id="series-director-form">
              <label>规划目标<textarea name="creativeInput" required maxlength="4000">${escapeHtml(state.seriesPlanningInput)}</textarea><small>输入与项目上下文会发送到既有 V4 文本生成端口；Provider 只返回候选内容。</small></label>
              ${state.seriesPlanningError ? `<p class="form-error" role="alert">${escapeHtml(state.seriesPlanningError)}</p>` : ""}
              <button class="button button-primary" type="submit" ${generating ? "disabled" : ""}>${generating ? "正在生成系列方案…" : "生成系列规划候选"}</button>
            </form>`}
        </article>
      </section>
      ${state.seriesPlanningCandidate ? renderSeriesDirectorCandidate(state.seriesPlanningCandidate) : ""}`;
  }

  function seriesPlanVersionContent(version) {
    const keys = ["seriesConcept", "premise", "logline", "mainNarrativeDirection", "mainArcs", "subArcs", "characterArcIntents", "episodePlanItems", "narrativeRhythm", "worldIntent", "continuityIntent", "foreshadowingContext", "productionAssumptions"];
    return Object.fromEntries(keys.map((key) => [key, JSON.parse(JSON.stringify(version[key]))]));
  }

  function renderSeriesPlanning(route) {
    if (state.seriesPlanningStatus === "idle" || state.seriesPlanningStatus === "loading") return seriesPlanningLoading(route, "系列规划");
    if (state.seriesPlanningStatus === "error" || !state.seriesPlanningWorkspace) {
      return `${renderProjectContextBar(route)}${renderPageHeader({ eyebrow: "策划 · 系列规划", title: "系列规划", description: "查看系列弧线、计划分集与版本历史。", status: "available" })}${renderErrorState("系列规划暂时无法读取", state.seriesPlanningError || "请稍后重试。")}`;
    }
    const workspace = state.seriesPlanningWorkspace;
    const context = workspace.context;
    const plan = workspace.plan;
    if (!plan) {
      return `${renderProjectContextBar(route)}${renderPageHeader({ eyebrow: `${escapeHtml(context.project.title)} · 系列策划`, title: "系列规划", description: "规划尚未建立；请先在项目 AI导演生成候选并完成人工确认。", status: "available" })}<section class="enterprise-panel series-plan-empty">${renderEmptyState({ icon: "策", title: "尚未建立系列规划", description: "系列规划必须来自真实项目上下文，经候选校验与人工确认后才会成为权威版本。", action: `<a class="button button-primary" href="#${escapeHtml(route.projectBase)}/planning/director">前往项目 AI导演</a>` })}</section>`;
    }
    const version = selectedSeriesPlanVersion();
    const confirmed = plan.confirmedSeriesPlanVersionRef === version.seriesPlanVersionRef;
    const createdEpisodes = (context.series.episodes || []).length;
    return `
      ${renderProjectContextBar(route)}
      ${renderPageHeader({ eyebrow: `${escapeHtml(context.project.title)} · 系列策划`, title: "系列规划", description: "在同一项目与系列身份上查看弧线、计划分集、来源与不可变版本。", status: "available", meta: localizedStatusBadge(confirmed ? `已确认 v${version.versionNumber}` : `当前 v${version.versionNumber} · 待确认`, confirmed ? "available" : "development") })}
      <section class="series-plan-overview" data-series-plan-schema="${escapeHtml(plan.schemaVersion)}" data-series-plan-ref="${escapeHtml(plan.seriesPlanRef)}" data-series-plan-version-ref="${escapeHtml(version.seriesPlanVersionRef)}">
        <article class="enterprise-panel series-plan-hero"><span class="section-kicker">系列生产规划</span><h2>${escapeHtml(version.seriesConcept)}</h2><p>${escapeHtml(version.logline)}</p><div class="series-plan-kpis"><span><strong>${escapeHtml(version.mainArcs.length)}</strong>主弧线</span><span><strong>${escapeHtml(version.episodePlanItems.length)}</strong>计划分集</span><span><strong>${escapeHtml(createdEpisodes)}</strong>已创建单集</span><span><strong>v${escapeHtml(version.versionNumber)}</strong>当前版本</span></div><small>计划分集不会自动创建生产单集。</small></article>
        <article class="enterprise-panel series-plan-source"><header><div><span class="section-kicker">来源与身份</span><h3>Project → Series → Series Plan</h3></div></header><dl><div><dt>项目</dt><dd>${escapeHtml(context.project.title)}</dd></div><div><dt>系列</dt><dd>${escapeHtml(context.series.title)}</dd></div><div><dt>规划状态</dt><dd>${confirmed ? "已人工确认" : "等待人工确认"}</dd></div><div><dt>当前版本</dt><dd>v${escapeHtml(version.versionNumber)}</dd></div></dl><details><summary>高级溯源</summary><code>${escapeHtml(context.projectRef)}</code><code>${escapeHtml(context.seriesRef)}</code><code>${escapeHtml(plan.seriesPlanRef)}</code><code>${escapeHtml(version.seriesPlanVersionRef)}</code></details></article>
      </section>
      <section class="enterprise-panel series-arc-navigator"><header><div><span class="section-kicker">Arc Navigator</span><h3>主叙事弧线</h3></div><span>${escapeHtml(version.mainNarrativeDirection)}</span></header><div>${version.mainArcs.map((arc) => `<article><small>ARC ${escapeHtml(arc.arcNumber)}</small><strong>${escapeHtml(arc.title)}</strong><span>EP${String(arc.episodeStart).padStart(2, "0")}–EP${String(arc.episodeEnd).padStart(2, "0")}</span><p>${escapeHtml(arc.objective)}</p><em>${escapeHtml(arc.turningPoint)}</em></article>`).join("")}</div></section>
      <section class="series-plan-board">
        <article class="enterprise-panel series-episode-plan"><header><div><span class="section-kicker">Episode Plan</span><h3>计划分集</h3></div><span>${escapeHtml(version.episodePlanItems.length)} 项规划事实</span></header><div class="series-plan-table" role="table" aria-label="计划分集"><div class="series-plan-table-head" role="row"><span>集次</span><span>标题与 Logline</span><span>叙事弧</span><span>连续性 / 伏笔</span></div>${version.episodePlanItems.map((item) => `<div class="series-plan-table-row" role="row" data-episode-plan-item-ref="${escapeHtml(item.episodePlanItemRef)}"><span>E${String(item.episodeNumber).padStart(2, "0")}</span><span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.logline)}</small></span><span>ARC ${escapeHtml(item.arcNumber)}<small>${escapeHtml(item.narrativePurpose)}</small></span><span><small>${escapeHtml((item.continuityNotes || []).join(" · ") || "—")}</small><small>${escapeHtml((item.foreshadowing || []).join(" · ") || "—")}</small></span></div>`).join("")}</div></article>
        <aside class="series-plan-aside"><article class="enterprise-panel"><span class="section-kicker">角色成长意图</span>${version.characterArcIntents.map((item) => `<section><strong>${escapeHtml(item.roleLabel)}</strong><p>${escapeHtml(item.startingState)} → ${escapeHtml(item.destination)}</p><small>${escapeHtml(item.developmentIntent)}</small></section>`).join("")}</article><article class="enterprise-panel"><span class="section-kicker">世界与连续性</span><p>${escapeHtml(version.worldIntent)}</p><ul>${(version.continuityIntent || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><ul>${(version.foreshadowingContext || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></article></aside>
      </section>
      <section class="series-version-layout">
        <article class="enterprise-panel series-version-history"><header><div><span class="section-kicker">Version History</span><h3>不可变版本</h3></div></header>${workspace.versions.map((item) => `<button type="button" data-action="select-series-plan-version" data-version-ref="${escapeHtml(item.seriesPlanVersionRef)}" class="${item.seriesPlanVersionRef === version.seriesPlanVersionRef ? "is-selected" : ""}"><span>v${escapeHtml(item.versionNumber)}</span><strong>${item.changeKind === "ai-candidate-confirmed" ? "AI 候选确认" : "人工修订"}</strong><small>${item.seriesPlanVersionRef === plan.confirmedSeriesPlanVersionRef ? "已确认" : "历史版本"}</small></button>`).join("")}</article>
        <article class="enterprise-panel series-revision-panel"><header><div><span class="section-kicker">版本操作</span><h3>${confirmed ? "建立人工修订" : "确认当前版本"}</h3></div></header>${confirmed ? `<form id="series-plan-revision-form"><label>故事前提<textarea name="premise" required maxlength="1200">${escapeHtml(version.premise)}</textarea></label><button class="button button-secondary" type="submit" ${state.seriesPlanningPhase !== "idle" ? "disabled" : ""}>保存为新版本</button><p>新版本不会覆盖历史版本，保存后仍需人工确认。</p></form>` : `<p>${escapeHtml(version.premise)}</p><button class="button button-primary" type="button" data-action="confirm-series-plan-version" ${state.seriesPlanningPhase !== "idle" ? "disabled" : ""}>确认当前规划版本</button>`}${state.seriesPlanningError ? `<p class="form-error" role="alert">${escapeHtml(state.seriesPlanningError)}</p>` : ""}</article>
      </section>`;
  }

  const enterprisePageCopy = Object.freeze({
    "project-overview": ["项目概览", "项目级创意、内容、制作与交付状态的总览。", "项目", "summary"],
    "project-director": ["项目 AI导演", "在正式项目上下文内查看导演方案与人工确认关系。", "策划", "detail"],
    "series-planning": ["系列规划", "组织系列方向、分集结构与内容目标。", "策划", "table"],
    "bible-shell": ["IP圣经", "集中查看已确认的世界观、角色规则与来源版本。", "策划", "detail"],
    "character-shell": ["角色工作台", "查看角色身份、版本、关系与绑定状态。", "策划", "board"],
    "continuity-shell": ["世界与连续性", "检查跨集角色、世界设定与连续性约束。", "策划", "table"],
    "episode-list": ["分集中心", "按系列与单集的来源关系组织内容制作。", "内容", "table"],
    "episode-workspace": ["分集工作台", "进入单一单集上下文，承接已确认导演方案、故事与剧本来源关系。", "内容", "summary"],
    "story-shell": ["故事", "查看同一单集上已确认的故事投影。", "内容", "editor"],
    "script-shell": ["剧本工作台", "管理不可变剧本版本、人工确认与下游衔接。", "内容", "editor"],
    "consistency-shell": ["一致性检查", "汇总故事、角色、场景与剧本之间的差异。", "内容", "table"],
    "storyboard-shell": ["分镜工作台", "等待角色与设定输入就绪后，再组织场景与镜头规划。", "制作", "board"],
    "shot-shell": ["镜头工作台", "查看镜头身份、版本、状态与素材需求。", "制作", "board"],
    "scene-shell": ["场景工作台", "组织正式场景对象与跨镜头复用关系。", "制作", "detail"],
    "project-assets-shell": ["项目资产", "查看项目范围内已绑定资产及其版本来源。", "制作", "board"],
    "jobs-shell": ["生成任务", "未来展示真实任务状态；当前不创建任务或队列。", "制作", "table"],
    "timeline-shell": ["时间线", "未来组织已确认镜头、音频与版本的编辑时间线。", "后期", "timeline"],
    "preview-shell": ["预览", "未来查看来自正式制作链的候选预览。", "后期", "player"],
    "qc-shell": ["质量检查", "未来汇总技术、内容与交付质量门禁。", "后期", "table"],
    "approval-shell": ["审批", "未来记录可识别人类的审批决定与责任边界。", "后期", "detail"],
    "master-shell": ["成片", "未来管理通过全部门禁的正式成片版本。", "交付", "player"],
    "export-shell": ["导出", "未来从已接受成片建立交付产物。", "交付", "detail"],
    "series-delivery-shell": ["系列管理", "未来汇总系列级交付与版本关系。", "交付", "table"],
    "release-shell": ["发布", "未来管理已授权发布目的地与人工确认。", "交付", "detail"],
    "analytics-shell": ["数据", "未来显示可追溯的真实运营与交付证据。", "交付", "table"]
  });

  function renderProjectOverview(route) {
    const project = route.project;
    const context = projectProductionContext(project);
    const series = context && context.series;
    const episodes = series ? series.episodes || [] : [];
    return `
      ${renderProjectContextBar(route)}
      ${renderPageHeader({ eyebrow: "项目工作室", title: project.title, description: project.description || "统一承载系列、单集与制作来源关系。", status: "available", meta: localizedStatusBadge(project.status === "active" ? "创作中" : "已归档", project.status === "active" ? "available" : "neutral") })}
      <section class="project-overview-grid">
        <article class="enterprise-panel project-overview-hero"><span class="section-kicker">项目概览</span><h2>${escapeHtml(project.title)}</h2><p>${escapeHtml(project.description || "正式项目生产上下文")}</p><dl class="project-record-meta"><div><dt>项目类型</dt><dd>${escapeHtml(project.projectType)}</dd></div><div><dt>画幅</dt><dd>${escapeHtml(project.aspectRatio)}</dd></div><div><dt>单集目标</dt><dd>${escapeHtml(project.defaultDurationSec)} 秒</dd></div><div><dt>计划集数</dt><dd>${escapeHtml(project.plannedEpisodeCount)}</dd></div></dl></article>
        <article class="enterprise-panel"><header><div><span class="section-kicker">生产关系</span><h3>系列与单集</h3></div><a class="text-link" href="#${route.projectBase}/episodes">查看分集</a></header>${series ? `<div class="project-lineage-summary"><div><span>系列</span><strong>${escapeHtml(series.title)}</strong><small>${escapeHtml(series.seriesRef)}</small></div><div><span>已创建单集</span><strong>${episodes.length}</strong><small>不会按计划集数批量创建</small></div></div>` : renderErrorState("关联系列暂时无法读取", "项目身份已保留，请刷新后重试。")}</article>
      </section>
      <section class="enterprise-panel project-production-spine"><header><div><span class="section-kicker">Production Spine</span><h3>真实制作链</h3></div></header><div class="project-spine-steps">${["项目","系列","单集","故事","剧本"].map((label, index) => `<span class="${index < 3 || episodes.length ? "is-ready" : ""}"><i>${index + 1}</i><strong>${label}</strong></span>`).join("")}</div></section>
    `;
  }

  function renderProjectEpisodeList(route) {
    const context = projectProductionContext(route.project);
    const series = context && context.series;
    const episodes = series ? series.episodes || [] : [];
    return `
      ${renderProjectContextBar(route)}
      ${renderPageHeader({ eyebrow: "项目工作室 · 内容", title: "分集", description: "查看当前项目关联系列中的真实单集记录。", status: "available" })}
      <section class="enterprise-panel"><header><div><span class="section-kicker">${series ? escapeHtml(series.title) : "关联系列"}</span><h3>已创建单集</h3></div><span>${episodes.length} 集</span></header>${episodes.length ? `<div class="enterprise-list">${episodes.map((episode) => `<a class="enterprise-list-row" href="#${route.projectBase}/episodes/${encodeURIComponent(episode.episodeRef)}"><span class="row-index">E${String(episode.episodeNumber).padStart(2, "0")}</span><span><strong>${escapeHtml(episode.title)}</strong><small>来源方案 v${escapeHtml(episode.sourcePlanVersion)} · ${escapeHtml(episode.status)}</small></span><em>进入制作</em></a>`).join("")}</div>` : renderEmptyState({ icon: "—", title: "尚未创建单集", description: "计划集数只是制作意图，不会自动创建单集记录。" })}</section>
    `;
  }

  function renderProjectContextBar(route) {
    const persisted = route.persisted;
    const episode = persisted && persisted.episode;
    let version = "—";
    if (route.type === "story-view" && episode && episode.sourcePlanVersion) version = `来源方案 v${episode.sourcePlanVersion}`;
    if (route.type === "script-studio") {
      const scriptVersion = selectedScriptVersion();
      version = scriptVersion ? `v${scriptVersion.versionNumber}` : "待生成";
    } else if (["project-director", "series-planning"].includes(route.type)) {
      const planVersion = selectedSeriesPlanVersion();
      version = planVersion ? `规划 v${planVersion.versionNumber}` : "待规划";
    } else if (route.type === "episode-project" && episode && episode.sourcePlanVersion) {
      version = `来源方案 v${episode.sourcePlanVersion}`;
    }
    const project = route.project || (persisted && persisted.project) || (persisted && projectForSeries(persisted.series.seriesRef));
    const fields = [
      ["项目", project ? project.title : "尚未建立"], ["系列", persisted ? persisted.series.title : project && project.seriesRefs.length ? (findSeries(project.seriesRefs[0]) || {}).title || "读取中" : "尚未选择"],
      ["单集", persisted ? `第 ${persisted.episode.episodeNumber} 集` : "尚未选择"],
      ["阶段", route.group || "—"], ["当前对象", route.label || "—"], ["版本", version]
    ];
    return `<section class="project-context-bar" aria-label="制作上下文"><div class="context-gate"><span></span><strong>制作上下文</strong><small>${project ? "正式项目" : persisted ? "兼容单集" : "尚未选择项目"}</small></div>${fields.map(([label,value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</section>`;
  }

  function renderEpisodeSelector(route) {
    const target = route.targetPage === "script" ? "script" : route.targetPage === "pipeline" ? "pipeline" : "story";
    const targetLabel = target === "script" ? "剧本" : target === "pipeline" ? "分集概览" : "故事";
    const contexts = productionContexts();
    return `
      ${renderProjectContextBar(route)}
      ${renderPageHeader({ eyebrow: "制作上下文", title: `选择单集后查看${targetLabel}`, description: "请选择一个真实存在的系列与单集；当前选择只用于页面导航，不会创建项目记录。", status: "available" })}
      <section class="enterprise-panel episode-selector" data-episode-selector="true">
        ${contexts.length ? `<div class="enterprise-list">${contexts.map(({ series, episode }) => `<a class="enterprise-list-row" href="#${productionContextBase({ series, episode })}/${target}" data-series-ref="${escapeHtml(series.seriesRef)}" data-episode-ref="${escapeHtml(episode.episodeRef)}"><span class="row-index">E${String(episode.episodeNumber).padStart(2, "0")}</span><span><strong>${escapeHtml(episode.title)}</strong><small>${escapeHtml(series.title)} · ${episode.confirmedPlanBinding ? "已有确认方案" : "等待确认方案"}</small></span><em>选择</em></a>`).join("")}</div>` : renderEmptyState({ icon: "—", title: "还没有可选择的单集", description: "请先在 AI导演确认创意方案并建立系列与单集。", action: '<a class="button button-secondary" href="#/creator/ai-director">前往 AI导演</a>' })}
      </section>
    `;
  }

  function renderShellCanvas(kind, title) {
    const emptyCopy = "当前没有可用于此页面的正式数据。页面结构已就绪，但不会用演示内容替代生产事实。";
    if (kind === "board") return `<div class="shell-board-empty"><span class="section-kicker">内容画板</span><strong>暂无正式内容</strong><p>${emptyCopy}</p><small>取得正式项目上下文与已接受上游对象后，此处才会显示真实卡片。</small></div>`;
    if (kind === "timeline") return `<div class="shell-timeline"><div class="timeline-ruler">${["00:00","00:15","00:30","00:45","01:00"].map((item) => `<span>${item}</span>`).join("")}</div>${["画面","声音","字幕","标记"].map((item) => `<div class="timeline-lane"><strong>${item}</strong><span></span></div>`).join("")}</div>`;
    if (kind === "player") return `<div class="shell-player"><div class="shell-player-screen"><span>尚无正式媒体</span><strong>${escapeHtml(title)}</strong><small>等待正式上游输出</small></div><div class="shell-player-controls"><button type="button" disabled>播放</button><span>00:00 / 00:00</span><i></i></div></div>`;
    if (kind === "editor") return `<div class="shell-editor"><aside><span>结构</span>${["概览","第一部分","第二部分","第三部分"].map((item) => `<button type="button" disabled>${item}</button>`).join("")}</aside><article><span class="section-kicker">内容工作区</span><h3>${escapeHtml(title)}</h3><p>${emptyCopy}</p><div class="editor-lines">${[1,2,3,4,5].map(() => "<span></span>").join("")}</div></article><aside><span>版本</span><strong>暂无版本</strong><small>等待正式来源</small></aside></div>`;
    if (kind === "table") return `<div class="shell-table"><header><span>对象</span><span>状态</span><span>来源</span><span>版本</span></header><div class="shell-table-empty"><strong>暂无正式记录</strong><p>${emptyCopy}</p></div></div>`;
    if (kind === "detail") return `<div class="shell-detail-grid"><article><span class="section-kicker">当前内容</span><h3>等待正式项目上下文</h3><p>${emptyCopy}</p></article><aside>${["身份","来源","状态","版本"].map((item) => `<div><span>${item}</span><strong>未建立</strong></div>`).join("")}</aside></div>`;
    if (kind === "summary") return `<div class="shell-summary-grid">${["创意","内容","制作","交付"].map((item,index) => `<article><span>0${index+1}</span><strong>${item}</strong><p>等待正式数据</p></article>`).join("")}</div>`;
    return `<div class="shell-empty"><strong>${escapeHtml(title)}</strong><p>${emptyCopy}</p></div>`;
  }

  function renderEnterpriseShellPage(route) {
    const [title, description, stage, kind] = enterprisePageCopy[route.type] || [route.label, "页面结构已就绪。", route.group || "项目", "summary"];
    const disabled = route.status === "disabled";
    return `${renderProjectContextBar(route)}${renderPageHeader({ eyebrow: `${stage} · 制作工作区`, title, description, status: route.status, meta: localizedStatusBadge(disabled ? "受门禁限制" : "结构已就绪", disabled ? "neutral" : "planned") })}<section class="enterprise-shell-page" data-shell-kind="${escapeHtml(kind)}">${renderShellCanvas(kind, title)}</section><section class="workflow-action-bar"><div><span>当前页面</span><strong>${escapeHtml(title)}</strong><small>${route.persisted ? "使用当前单集的真实来源关系" : "尚未建立项目上下文"}</small></div><div><button class="button button-secondary" type="button" data-action="toggle-bottom-drawer">版本与活动</button><button class="button button-primary" type="button" disabled>${disabled ? "当前不可操作" : "等待上游能力"}</button></div></section>`;
  }

  function renderAssetsR1() {
    return `${renderPageHeader({ eyebrow: "工作区资产", title: "资产库", description: "浏览当前工作区明确标记的内部参考媒体；不存在时保持空态。", status: "available", meta: localizedStatusBadge("内部参考", "neutral") })}<section class="asset-r1-layout"><aside class="asset-taxonomy"><span class="section-kicker">资产分类</span>${["全部","角色","场景","图片","视频","音频","模板"].map((item,index) => `<button type="button" ${index ? "disabled" : 'class="is-active"'}>${item}<span>${index ? "0" : fixture.assets.length}</span></button>`).join("")}</aside><div class="asset-r1-main"><header><div><h3>内部视觉参考</h3><p>这些媒体不是正式项目资产，也没有获得发布权利。</p></div>${governanceBadge("权利待确认", "hold")}</header>${renderAssetGrid(fixture.assets)}</div></section>${fixtureNotice()}`;
  }

  function renderWorksR1() {
    return `${renderPageHeader({ eyebrow: "成片与交付", title: "作品", description: "只展示通过正式成片与交付门禁的作品。", status: "planned" })}<section class="works-r1-stage"><div class="works-r1-filter"><button class="is-active" type="button">全部</button><button type="button" disabled>制作中</button><button type="button" disabled>待交付</button><button type="button" disabled>已发布</button></div>${renderEmptyState({ icon: "—", title: "还没有正式作品", description: "内部参考候选片不会出现在作品库。需要成片、权利、审批与交付能力就绪后才会显示。" })}</section>`;
  }

  function renderPlaceholder(route) {
    const isDisabled = route.status === "disabled";
    const parentRoute = route.context === "creation" ? "/creator/creation" : route.context === "project" ? `${route.projectBase || projectBase}/pipeline` : "/creator/dashboard";
    const statusText = isDisabled ? "暂不可用" : "尚未启用";
    const title = route.label;
    const description = route.description || "当前只建立页面位置、状态与责任边界，不实现未来能力。";
    if (route.key === "approval") {
      return `
        ${renderPageHeader({
          eyebrow: "项目工作室 · 审批",
          title: "人工确认",
          description: "该页面用于展示人工确认要求。界面和技术检查不会自动完成批准。",
          status: "disabled",
          meta: localizedStatusBadge("需要人工确认", "neutral")
        })}
        ${fixtureNotice()}
        <section class="approval-preview-card">
          <span class="approval-preview-mark" aria-hidden="true">待</span>
          <div><span class="section-kicker">流程状态</span><h2>等待人工确认</h2><p>创意、权利与发布准备仍需由对应责任人确认，当前页面不会自动改变任何批准状态。</p></div>
          <button class="button button-secondary" type="button" disabled>暂不可用</button>
        </section>
      `;
    }
    return `
      ${renderPageHeader({
        eyebrow: route.eyebrow || "功能预览",
        title,
        description,
        status: route.status,
        meta: route.status === "disabled" ? localizedStatusBadge("需要人工确认", "neutral") : ""
      })}
      ${route.context === "project" ? fixtureNotice("项目占位页不会创建、保存或推进正式项目、制作、IP、声音或时间线记录。") : ""}
      <section class="card placeholder-card">
        ${renderEmptyState({
          icon: isDisabled ? "×" : "·",
          title: `${title} · ${statusText}`,
          description,
          action: `<a class="button button-secondary" href="#${parentRoute}">${route.context === "creation" ? "返回创作中心" : route.context === "project" ? "返回生产流程" : "返回总览"}</a>`
        })}
        <div class="placeholder-boundaries">
          <span><small>当前状态</small><strong>${isDisabled ? "暂不可用" : "尚未启用"}</strong></span>
          <span><small>功能内容</small><strong>暂无内容</strong></span>
          <span><small>下一步</small><strong>完成页面所列前置条件</strong></span>
          <span class="sr-only">当前功能尚未实现，仅显示页面位置与状态。</span>
        </div>
      </section>
    `;
  }

  function resolveRoute(path) {
    const normalized = normalizePath(path);
    if (normalized === "/creator/dashboard") return { redirect: "/creator" };
    if (normalized === "/creator/creation") return { redirect: "/creator/create" };
    const canonicalProjectMatch = normalized.match(/^\/creator\/projects\/([^/]+)(?:\/(.*))?$/);
    if (canonicalProjectMatch && canonicalProjectMatch[1] !== "new") {
      const project = findProject(decodeURIComponent(canonicalProjectMatch[1]));
      if (project) {
        const projectBase = `/creator/projects/${encodeURIComponent(project.projectRef)}`;
        const suffix = canonicalProjectMatch[2] || "";
        const defaultContext = projectProductionContext(project);
        if (!suffix) return { redirect: `${projectBase}/overview` };
        if (suffix === "overview") {
          return {
            type: "project-overview-real",
            key: "overview",
            label: "项目概览",
            status: "available",
            path: normalized,
            projectBase,
            project,
            persisted: defaultContext && defaultContext.episode ? defaultContext : null,
            context: "project-shell",
            group: "概览",
            breadcrumb: `${project.title} / 项目概览`
          };
        }
        if (suffix === "episodes") {
          return {
            type: "project-episode-list-real",
            key: "episodes",
            label: "分集",
            status: "available",
            path: normalized,
            projectBase,
            project,
            persisted: defaultContext && defaultContext.episode ? defaultContext : null,
            context: "project-shell",
            group: "内容",
            breadcrumb: `${project.title} / 分集`
          };
        }
        const episodeMatch = suffix.match(/^episodes\/([^/]+)(?:\/(story|script))?$/);
        if (episodeMatch) {
          const persisted = projectProductionContext(project, decodeURIComponent(episodeMatch[1]));
          if (!persisted || !persisted.series || !persisted.episode) return null;
          rememberProductionContext(persisted);
          const target = episodeMatch[2] || "pipeline";
          const episodeBase = `${projectBase}/episodes/${encodeURIComponent(persisted.episode.episodeRef)}`;
          const route = {
            key: target,
            label: target === "pipeline" ? "分集工作台" : target === "story" ? "故事" : "剧本",
            status: "available",
            path: normalized,
            projectBase,
            episodeBase,
            project,
            persisted,
            context: "episode",
            group: "内容",
            breadcrumb: `${project.title} / 第 ${persisted.episode.episodeNumber} 集 / ${target === "pipeline" ? "概览" : target === "story" ? "故事" : "剧本"}`
          };
          if (target === "pipeline") return { ...route, type: "episode-project" };
          if (target === "story") return { ...route, type: "story-view" };
          return { ...route, type: "script-studio" };
        }
        const projectPage = projectPages.find((page) => page.suffix === suffix);
        if (projectPage) {
          return {
            ...projectPage,
            path: normalized,
            projectBase,
            project,
            persisted: defaultContext && defaultContext.episode ? defaultContext : null,
            context: "project-shell",
            breadcrumb: `${project.title} / ${projectPage.group} / ${projectPage.label}`
          };
        }
        return null;
      }
    }
    const persistedProjectMatch = normalized.match(/^\/creator\/projects\/([^/]+)(?:\/([^/]+))?$/);
    if (persistedProjectMatch && !["new"].includes(persistedProjectMatch[1])) {
      const persisted = findPersistedEpisode(decodeURIComponent(persistedProjectMatch[1]));
      if (persisted) {
        const linkedProject = projectForSeries(persisted.series.seriesRef);
        if (linkedProject) {
          const target = persistedProjectMatch[2] || "story";
          const canonicalTarget = target === "pipeline" ? "" : `/${target}`;
          return { redirect: `/creator/projects/${encodeURIComponent(linkedProject.projectRef)}/episodes/${encodeURIComponent(persisted.episode.episodeRef)}${canonicalTarget}` };
        }
        rememberProductionContext(persisted);
        const dynamicBase = `/creator/projects/${encodeURIComponent(persisted.episode.episodeRef)}`;
        const pageKey = persistedProjectMatch[2];
        if (!pageKey) return { redirect: `${dynamicBase}/story` };
        if (!["pipeline", "story", "script"].includes(pageKey)) return null;
        const baseRoute = {
          key: pageKey,
          label: pageKey === "pipeline" ? "分集概览" : pageKey === "story" ? "故事" : "剧本",
          status: "available",
          path: normalized,
          projectBase: dynamicBase,
          episodeRef: persisted.episode.episodeRef,
          persisted,
          context: "episode",
          breadcrumb: `${persisted.series.title} / 第 ${persisted.episode.episodeNumber} 集 / ${pageKey === "pipeline" ? "概览" : pageKey === "story" ? "故事" : "剧本"}`
        };
        if (pageKey === "pipeline") return { ...baseRoute, type: "episode-project" };
        if (pageKey === "story") return { ...baseRoute, type: "story-view" };
        if (pageKey === "script") return { ...baseRoute, type: "script-studio" };
      }
    }

    const primary = primaryRoutes.find((route) => route.path === normalized);
    if (primary) {
      if (primary.key === "dashboard") return { ...primary, type: "dashboard", breadcrumb: "创作空间 / 首页" };
      if (primary.key === "ai-director") return { ...primary, type: "ai-director", breadcrumb: "创作空间 / AI导演" };
      if (primary.key === "projects") return { ...primary, type: "projects", breadcrumb: "创作空间 / 项目" };
      if (primary.key === "assets") return { ...primary, type: "assets", breadcrumb: "创作空间 / 资产库" };
      if (primary.key === "creation") return { ...primary, type: "creation", breadcrumb: "创作空间 / 创作中心", context: "creation" };
      if (primary.key === "works") return { ...primary, type: "works", breadcrumb: "创作空间 / 作品" };
      return {
        ...primary,
        type: "placeholder",
        breadcrumb: `创作空间 / ${primary.label}`,
        eyebrow: primary.english.toUpperCase(),
        description: "未来候选版本与正式输出的分层浏览入口；当前不展示虚构作品或发布结果。"
      };
    }

    if (normalized === "/creator/projects/new") {
      return { type: "project-wizard-page", key: "project-new", path: normalized, label: "新建项目", status: "planned", breadcrumb: "项目 / 新建项目" };
    }

    if (normalized === "/creator/account") {
      return { type: "placeholder", key: "account", path: normalized, label: "账户", english: "Account", status: "planned", breadcrumb: "创作空间 / 账户", eyebrow: "个人空间", description: "创作者账户功能尚未启用。" };
    }

    const creation = creationModules.find((module) => module.path === normalized);
    if (creation) {
      return { ...creation, type: "creation-preview", status: "planned", breadcrumb: `创作中心 / ${creation.label}`, eyebrow: "创作工具 · 尚未启用", context: "creation" };
    }

    if (normalized.startsWith(`${projectShellBase}/`)) {
      const projectPage = projectPages.find((page) => page.path === normalized);
      if (!projectPage) return null;
      const selected = resolveSelectedProductionContext();
      const targetPage = projectPage.key === "episode-workspace" ? "pipeline" : projectPage.key;
      if (["pipeline", "story", "script"].includes(targetPage)) {
        if (selected) return { redirect: `${productionContextBase(selected)}/${targetPage}` };
        return {
          ...projectPage,
          type: "episode-selector",
          targetPage,
          breadcrumb: `制作上下文 / ${projectPage.label}`,
          context: "project-shell"
        };
      }
      return {
        ...projectPage,
        persisted: selected,
        projectBase: productionContextBase(selected),
        breadcrumb: `制作工作区 / ${projectPage.group} / ${projectPage.label}`,
        context: "project-shell"
      };
    }

    return null;
  }

  function renderNotFound(path) {
    return `
      ${renderPageHeader({ eyebrow: "页面未找到", title: "找不到这个页面", description: "该页面地址不存在或尚未开放。", status: "disabled" })}
      <section class="card placeholder-card">
        ${renderEmptyState({ icon: "?", title: "页面不可用", description: `当前地址 ${path} 暂时无法访问。`, action: '<a class="button button-secondary" href="#/creator/dashboard">返回首页</a>' })}
        <span class="sr-only">页面地址不存在，不代表正式业务状态。</span>
      </section>
    `;
  }

  function renderContextNav(route) {
    const episodeContext = route.context === "episode";
    const productionContext = route.persisted || resolveSelectedProductionContext();
    const groups = route.context === "project-shell" || episodeContext ? projectNavigationGroups : null;
    const items = route.context === "creation" ? creationModules.map((module) => ({ ...module, status: "planned" })) : [];
    if (groups) {
      const itemPath = (item) => {
        const project = route.project || (productionContext && productionContext.project);
        if (project) {
          const base = route.projectBase || `/creator/projects/${encodeURIComponent(project.projectRef)}`;
          if (item.key === "overview") return `${base}/overview`;
          if (item.key === "episodes") return `${base}/episodes`;
          if (item.key === "episode-workspace") return productionContext && productionContext.episode ? `${base}/episodes/${encodeURIComponent(productionContext.episode.episodeRef)}` : `${base}/episodes`;
          if (item.key === "story" || item.key === "script") return productionContext && productionContext.episode ? `${base}/episodes/${encodeURIComponent(productionContext.episode.episodeRef)}/${item.key}` : `${base}/episodes`;
          return `${base}/${item.suffix}`;
        }
        if (!productionContext) return `${projectShellBase}/${item.suffix}`;
        const base = route.projectBase || productionContextBase(productionContext);
        if (item.key === "episode-workspace") return `${base}/pipeline`;
        if (item.key === "story" || item.key === "script") return `${base}/${item.key}`;
        return `${projectShellBase}/${item.suffix}`;
      };
      const isCurrent = (item) => route.key === item.key || (episodeContext && route.key === "pipeline" && item.key === "episode-workspace");
      const contextLabel = route.project
        ? `${route.project.title}${productionContext && productionContext.episode ? ` · 第 ${productionContext.episode.episodeNumber} 集` : ""}`
        : productionContext
          ? `${productionContext.series.title} · 第 ${productionContext.episode.episodeNumber} 集 · 兼容入口`
          : "尚未选择项目";
      const capabilityBadge = (item) => {
        if (!productionContext || !["story", "script"].includes(item.key)) return statusBadge(item.status);
        if (item.key === "story") return productionContext.episode.confirmedPlanBinding ? localizedStatusBadge("已就绪", "available") : localizedStatusBadge("待确认方案", "neutral");
        if (productionContext.episode.confirmedScriptVersionRef) return localizedStatusBadge("已确认", "available");
        if (productionContext.episode.scriptRef) return localizedStatusBadge("编辑中", "development");
        return localizedStatusBadge("待生成", "neutral");
      };
      contextNavigation.hidden = false;
      workbench.classList.add("has-context-nav");
      contextNavigation.innerHTML = `<div class="context-nav-heading"><span>项目导航</span><strong>${escapeHtml(contextLabel)}</strong></div>${groups.map((group) => `<section class="context-nav-group"><span>${escapeHtml(group.label)}</span>${group.items.map((item) => `<a href="#${escapeHtml(itemPath(item))}" class="context-nav-item ${isCurrent(item) ? "is-active" : ""}" aria-current="${isCurrent(item) ? "page" : "false"}"><span>${escapeHtml(item.label)}</span>${capabilityBadge(item)}</a>`).join("")}</section>`).join("")}`;
      return;
    }
    if (!items.length) {
      contextNavigation.hidden = true;
      contextNavigation.innerHTML = "";
      workbench.classList.remove("has-context-nav");
      return;
    }

    const title = "创作工具";
    const subtitle = "实验区 · 不写入项目";
    contextNavigation.hidden = false;
    workbench.classList.add("has-context-nav");
    contextNavigation.innerHTML = `
      <div class="context-nav-heading"><span>${escapeHtml(title)}</span><strong>${escapeHtml(subtitle)}</strong></div>
      <div class="context-nav-list">
        ${items.map((item) => `<a href="#${escapeHtml(item.path)}" class="context-nav-item ${item.path === route.path ? "is-active" : ""}" aria-current="${item.path === route.path ? "page" : "false"}"><span>${escapeHtml(item.label)}</span>${statusBadge(item.status)}</a>`).join("")}
      </div>
    `;
  }

  function routeSupportsInspector(route) {
    return Boolean(route && (route.context === "project-shell" || route.context === "episode" || ["assets", "ai-director"].includes(route.type)));
  }

  function renderInspector(route) {
    inspectorTitle.textContent = route ? route.label || route.english || "当前页面" : "未知路由";
    const shot = selectedShot();
    const base = '<span class="sr-only">演示数据，不代表正式业务记录，仅用于当前会话。</span>';
    let detail = "";
    if (route && route.type === "storyboard") {
      const shotStatusLabel = shot.status === "Review required" ? "待确认" : "可用";
      const index = fixture.shots.findIndex((item) => item.localKey === shot.localKey);
      detail = `<section class="inspector-section"><span class="inspector-label">选中镜头</span><strong>镜头 ${String(index + 1).padStart(2, "0")} · ${escapeHtml(shot.title)}</strong><p>${shot.start}.0–${shot.end}.0 秒 · ${shot.duration} 秒</p><p>${shotStatusLabel}</p></section>`;
    } else if (route && route.type === "preview") {
      detail = `<section class="inspector-section"><span class="inspector-label">候选版本</span><strong>v1 · 可预览</strong><p>45 秒 · 9:16 · 无音轨</p><p>权利状态仍待人工确认。</p></section>`;
    } else if (route && route.type === "pipeline") {
      const stage = fixture.pipeline.find((item) => item.localKey === state.selectedPipelineKey) || fixture.pipeline[0];
      const stageLabels = { Idea: "创意", Story: "故事", "IP Bible": "IP设定", Character: "角色", Storyboard: "分镜", Assets: "画面", Audio: "声音", Timeline: "剪辑", Preview: "预览", Approval: "确认", Export: "导出" };
      detail = `<section class="inspector-section"><span class="inspector-label">当前阶段</span><strong>${escapeHtml(stageLabels[stage.label] || stage.label)}</strong><p>${pipelineStatus(stage.status)}</p><p>创作状态由用户确认，页面不会自动推进。</p></section>`;
    } else if (route && route.type === "ai-director") {
      detail = `<section class="inspector-section"><span class="inspector-label">能力状态</span>${localizedStatusBadge("开发中", "development")}<p>当前可体验创意规划流程。</p></section>`;
    } else if (route && route.type === "episode-project") {
      detail = `<section class="inspector-section"><span class="inspector-label">单集制作</span><strong>${escapeHtml(route.persisted.episode.title)}</strong><p>${escapeHtml(route.persisted.series.title)} · 第 ${escapeHtml(route.persisted.episode.episodeNumber)} 集</p><p>来源：已确认导演方案 v${escapeHtml(route.persisted.episode.sourcePlanVersion)}</p></section>`;
    } else if (route && route.type === "story-view") {
      const projection = buildStoryProjection(route);
      detail = projection
        ? `<section class="inspector-section"><span class="inspector-label">故事来源</span><strong>已确认导演方案 v${escapeHtml(projection.sourcePlanVersion)}</strong><p>${escapeHtml(projection.seriesTitle)} · 第 ${escapeHtml(projection.episodeNumber)} 集</p><p>高级溯源可在故事页按需查看。</p></section>`
        : `<section class="inspector-section"><span class="inspector-label">故事来源</span><strong>尚未确认故事方案</strong><p>请先前往 AI导演确认本集方案。</p></section>`;
    } else if (route && route.type === "script-studio") {
      const version = selectedScriptVersion();
      const script = state.scriptWorkspace && state.scriptWorkspace.script;
      const confirmed = Boolean(script && version && script.confirmedScriptVersionRef === version.scriptVersionRef);
      detail = version
        ? `<section class="inspector-section"><span class="inspector-label">剧本版本</span><strong>v${escapeHtml(version.versionNumber)} · ${escapeHtml(scriptChangeLabel(version.changeKind))}</strong><p>${escapeHtml(version.scenes.length)} 场 · ${escapeHtml(version.targetDurationSec)} 秒</p><p>${confirmed ? "已人工确认" : "等待人工确认"}</p></section>`
        : `<section class="inspector-section"><span class="inspector-label">剧本工作室</span><strong>尚未生成剧本</strong><p>输入来自本集已确认导演方案。</p></section>`;
    } else if (route && ["project-director", "series-planning"].includes(route.type)) {
      const workspace = state.seriesPlanningWorkspace;
      const plan = workspace && workspace.plan;
      const version = selectedSeriesPlanVersion();
      detail = plan && version
        ? `<section class="inspector-section"><span class="inspector-label">系列规划</span><strong>v${escapeHtml(version.versionNumber)} · ${plan.confirmedSeriesPlanVersionRef === version.seriesPlanVersionRef ? "已确认" : "等待确认"}</strong><p>${escapeHtml(version.episodePlanItems.length)} 个计划分集 · ${(workspace.context.series.episodes || []).length} 个已创建单集</p><p>计划身份由 V5 管理，页面不会批量创建 Episode。</p></section>`
        : `<section class="inspector-section"><span class="inspector-label">系列规划</span><strong>尚未建立权威规划</strong><p>请在真实项目上下文中生成候选并完成人工确认。</p></section>`;
    } else if (route && route.type === "assets") {
      detail = `<section class="inspector-section"><span class="inspector-label">权利状态</span>${governanceBadge("HOLD", "hold")}<p>正式使用前需要完成人工确认。</p></section>`;
    } else if (route && route.context === "project-shell") {
      detail = route.project
        ? `<section class="inspector-section"><span class="inspector-label">项目上下文</span><strong>${escapeHtml(route.project.title)}</strong><p>${escapeHtml(route.project.projectType)} · ${escapeHtml(route.project.status === "active" ? "创作中" : "已归档")}</p><p>v${escapeHtml(route.project.version)} · ${escapeHtml(route.project.seriesRefs.length)} 个关联系列</p></section><section class="inspector-section"><span class="inspector-label">页面状态</span><strong>${escapeHtml(route.label)}</strong><p>${route.status === "disabled" ? "受人工或能力门禁限制" : "使用正式项目身份"}</p></section>`
        : `<section class="inspector-section"><span class="inspector-label">项目上下文</span><strong>尚未建立</strong><p>当前为既有单集兼容入口，可从项目中心显式建立关系。</p></section>`;
    } else {
      detail = `<section class="inspector-section"><span class="inspector-label">工作区</span><strong>创作者工作区</strong><p>当前页面没有独立业务对象。</p></section>`;
    }
    inspectorContent.innerHTML = `${base}${detail}`;
  }

  function aiDirectorStickyConfig() {
    if (state.aiDirectorPhase === "generating") {
      return { label: "正在整理导演方案…", disabled: true, note: "不会显示虚假进度" };
    }
    if (state.seriesEpisodePhase === "creating") {
      return { label: "正在创建系列与集数…", disabled: true, note: "本地开发服务正在保存关联" };
    }
    if (state.aiDirectorConfirmed) {
      return { label: "创建单集制作记录", action: "submit-series-episode", note: "关联到稳定系列 · 不建立正式项目" };
    }
    if (state.aiDirectorPlan) {
      return { label: "确认导演方案", action: "confirm-ai-director-plan", note: "人工确认后才能创建系列与集数" };
    }
    if (state.aiDirectorPhase === "error") {
      return { label: "重新生成", action: "regenerate-ai-director", note: "创意输入仍保留在当前页面" };
    }
    return { label: "生成创意方案", action: "run-ai-director", note: "整理故事、镜头与视觉方向" };
  }

  function scriptStudioStickyConfig() {
    if (state.scriptPhase !== "idle") {
      const label = state.scriptPhase === "generating" ? "正在生成剧本…" : state.scriptPhase === "rewriting" ? "正在改写场景…" : state.scriptPhase === "saving" ? "正在保存版本…" : "正在确认版本…";
      return { label, disabled: true, note: "当前操作完成前不会创建重复版本" };
    }
    if (!state.scriptWorkspace || !state.scriptWorkspace.script) {
      return { label: "生成正式剧本", action: "generate-script", note: "读取本集已确认导演方案 · 生成后仍需人工确认" };
    }
    const selected = selectedScriptVersion();
    const alreadyConfirmed = Boolean(selected && state.scriptWorkspace.script.confirmedScriptVersionRef === selected.scriptVersionRef);
    return {
      label: alreadyConfirmed ? "当前版本已确认" : "确认当前剧本版本",
      action: "confirm-script-version",
      disabled: alreadyConfirmed,
      note: "只更新确认引用 · 历史版本保持不可变"
    };
  }

  function stickyConfig(route) {
    if (!route) return { label: "返回总览", target: defaultRoute, note: "未知路由 · 未创建任何事实" };
    const map = {
      dashboard: { label: "开始创作", target: "/creator/ai-director", note: "从一个想法开始新的影片方案" },
      projects: { label: "查看新建流程", action: "open-project-dialog", note: "最终提交保持禁用 · 不建立正式项目" },
      assets: { label: "返回首页", target: defaultRoute, note: "内部参考媒体 · 不形成正式项目资产" },
      creation: { label: "返回首页", target: defaultRoute, note: "六项智能工具正在准备中" },
      "ai-director": aiDirectorStickyConfig(),
      "episode-project": { label: "查看全部项目", target: "/creator/projects", note: "系列 → 单集 → 已确认导演方案" },
      "script-studio": scriptStudioStickyConfig()
    };
    if (map[route.type]) return map[route.type];
    if (route.context === "creation") return { label: "返回创作中心", target: "/creator/create", note: "实验能力不会写入正式项目" };
    if (route.context === "project-shell") return { label: "返回项目中心", target: "/creator/projects", note: "尚未建立正式项目 · 页面不会推进制作状态" };
    return { label: "返回首页", target: defaultRoute, note: "功能尚未启用" };
  }

  function shouldRenderStickyBar(route) {
    if (!route) return false;
    return ["dashboard", "ai-director", "episode-project", "script-studio"].includes(route.type);
  }

  function renderStickyBar(route) {
    const visible = shouldRenderStickyBar(route);
    stickyActionBar.hidden = !visible;
    document.querySelector(".app-frame").classList.toggle("no-sticky-bar", !visible);
    if (!visible) {
      stickyActionBar.innerHTML = "";
      return;
    }
    const config = stickyConfig(route);
    const primary = config.disabled
      ? `<button class="button button-primary" type="button" disabled data-capability="${escapeHtml(config.capability || "disabled-action")}">${escapeHtml(config.label)}</button>`
      : config.action
        ? `<button class="button button-primary" type="button" data-action="${escapeHtml(config.action)}">${escapeHtml(config.label)}</button>`
        : `<a class="button button-primary" href="#${escapeHtml(config.target)}">${escapeHtml(config.label)}</a>`;
    const showInspectorControl = routeSupportsInspector(route);
    stickyActionBar.innerHTML = `
      <div class="sticky-status"><div><strong>${escapeHtml(route && route.label ? route.label : "当前页面")}</strong><p>${escapeHtml(config.note)}</p><span class="sr-only">演示内容，不会自动保存为正式记录。</span></div></div>
      <div class="sticky-actions">${showInspectorControl ? '<button class="button button-secondary inspector-toggle-label" type="button" data-action="toggle-inspector">展开详情</button>' : ""}${primary}</div>
    `;
  }

  function updatePrimaryNav(path) {
    document.querySelectorAll(".primary-nav [data-route]").forEach((link) => {
      const route = link.getAttribute("data-route");
      const active = route === "/creator/projects"
        ? path === route || path.startsWith("/creator/projects/")
        : route === "/creator/create"
          ? path === route || path.startsWith("/creator/create/")
          : path === route;
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function applyInspectorState() {
    const supported = routeSupportsInspector(state.activeRoute);
    if (!supported) state.inspectorOpen = false;
    const open = supported && state.inspectorOpen;
    workbench.classList.toggle("inspector-closed", !open);
    inspector.classList.toggle("is-open", open);
    inspector.inert = !open;
    inspector.setAttribute("aria-hidden", String(!open));
    inspectorFab.hidden = open || !supported;
    document.querySelectorAll('[data-action="toggle-inspector"]').forEach((button) => {
      button.setAttribute("aria-expanded", String(open));
      const label = open ? "收起详情" : "展开详情";
      button.setAttribute("aria-label", label);
      if (button.classList.contains("inspector-toggle-label")) button.textContent = label;
    });
  }

  function applySidebarAccessibility() {
    const mobile = mobileQuery.matches;
    const open = mobile && state.mobileSidebarOpen;
    sidebar.classList.toggle("is-open", open);
    sidebarBackdrop.classList.toggle("is-visible", open);
    sidebar.inert = mobile && !open;
    sidebar.setAttribute("aria-hidden", String(mobile && !open));
    const trigger = document.querySelector('[data-action="open-mobile-sidebar"]');
    if (trigger) trigger.setAttribute("aria-expanded", String(open));
    const collapseButton = document.querySelector('[data-action="toggle-sidebar-collapse"]');
    if (collapseButton) {
      collapseButton.setAttribute("aria-label", mobile ? "关闭导航" : state.sidebarCollapsed ? "展开一级导航" : "折叠一级导航");
    }
  }

  function stopPreview() {
    const video = document.getElementById("candidate-video");
    if (video && !video.paused) video.pause();
    state.previewState = "paused";
  }

  function bindPreviewEvents() {
    const video = document.getElementById("candidate-video");
    if (!video) return;
    video.muted = state.previewMuted;
    const refresh = () => updatePreviewUi(video);
    video.addEventListener("play", () => { state.previewState = "playing"; refresh(); });
    video.addEventListener("pause", () => { if (!video.ended) state.previewState = "paused"; refresh(); });
    video.addEventListener("ended", () => { state.previewState = "ended"; refresh(); });
    video.addEventListener("timeupdate", refresh);
    video.addEventListener("loadedmetadata", refresh);
    video.addEventListener("error", () => { state.previewState = "error"; refresh(); });
    refresh();
  }

  function formatTime(value) {
    if (!Number.isFinite(value)) return "00:00";
    const seconds = Math.max(0, Math.floor(value));
    return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function updatePreviewUi(video) {
    const playLabel = document.getElementById("preview-play-label");
    const muteLabel = document.getElementById("preview-mute-label");
    const time = document.getElementById("preview-time");
    const status = document.getElementById("preview-state");
    const playButton = document.querySelector('[data-action="toggle-preview"]');
    const muteButton = document.querySelector('[data-action="toggle-preview-mute"]');
    const errorState = document.getElementById("preview-error");
    if (!playLabel || !time || !status) return;
    const playing = state.previewState === "playing";
    playLabel.textContent = playing ? "暂停" : state.previewState === "ended" ? "重新播放" : "播放";
    time.textContent = `${formatTime(video.currentTime)} / ${formatTime(video.duration || 45)}`;
    status.textContent = state.previewState === "error" ? "本地媒体加载失败" : state.previewState === "ended" ? "播放结束" : playing ? "播放中" : "已暂停";
    if (playButton) playButton.setAttribute("aria-pressed", String(playing));
    if (muteLabel) muteLabel.textContent = state.previewMuted ? "静音 · 无音轨" : "取消静音 · 仍无音轨";
    if (muteButton) muteButton.setAttribute("aria-pressed", String(state.previewMuted));
    if (errorState) errorState.hidden = state.previewState !== "error";
  }

  function renderRoute(path) {
    const normalized = normalizePath(path);
    if ((normalized === "/creator" || normalized === "/creator/projects" || normalized === "/creator/ai-director" || normalized.startsWith("/creator/projects/") || normalized.startsWith(`${projectShellBase}/`)) && state.seriesDataStatus === "idle") {
      loadSeriesData();
    }
    if ((normalized === "/creator" || normalized.startsWith("/creator/projects")) && state.projectDataStatus === "idle") {
      loadProjectData();
    }
    const route = resolveRoute(normalized);
    if (route && route.redirect) {
      navigate(route.redirect, true);
      return;
    }

    const previousPath = state.activePath;
    stopPreview();
    state.activePath = normalized;
    const resolved = route || { type: "not-found", path: normalized, label: "未知路由", status: "disabled", breadcrumb: "创作空间 / 页面未找到" };
    state.activeRoute = resolved;
    if (normalized !== previousPath) {
      state.inspectorOpen = !compactInspectorQuery.matches && ["project-shell", "episode"].includes(resolved.context);
    }
    updateShellBoundaryCopy(resolved);
    pageTitle.textContent = resolved.label || resolved.english || "创作空间";
    pageBreadcrumb.textContent = resolved.breadcrumb || "创作空间";
    document.title = `${resolved.label || "创作空间"} · AI Cinematic Studio`;
    updatePrimaryNav(normalized);
    renderContextNav(resolved);

    const renderers = {
      dashboard: renderDashboard,
      projects: renderProjects,
      assets: renderAssetsR1,
      creation: renderCreationCenterR1,
      "creation-preview": () => renderCreationPreviewR1(resolved),
      works: renderWorksR1,
      "ai-director": renderAiDirector,
      "project-wizard-page": () => `${renderPageHeader({ eyebrow: "项目生产上下文", title: "新建项目", description: "将现有系列显式关联到稳定的项目身份，并保留全部既有来源关系。", status: "available" })}<section class="enterprise-panel project-context-gate"><span class="gate-index">新建</span><div><h3>建立正式项目上下文</h3><p>创建操作由 Creator Application 调用 V5 Project 公共边界；不会批量创建单集、剧本或任务。</p></div><button class="button button-primary" type="button" data-action="open-project-dialog">打开配置向导</button></section>`,
      "project-overview-real": () => renderProjectOverview(resolved),
      "project-episode-list-real": () => renderProjectEpisodeList(resolved),
      "episode-project": () => renderEpisodeProject(resolved),
      "episode-selector": () => renderEpisodeSelector(resolved),
      "story-view": () => renderStoryView(resolved),
      "script-studio": () => renderScriptStudio(resolved),
      "project-overview": () => renderEnterpriseShellPage(resolved),
      "project-director": () => renderProjectSeriesDirector(resolved),
      "series-planning": () => renderSeriesPlanning(resolved),
      "bible-shell": () => renderEnterpriseShellPage(resolved),
      "character-shell": () => renderEnterpriseShellPage(resolved),
      "continuity-shell": () => renderEnterpriseShellPage(resolved),
      "episode-list": () => renderEnterpriseShellPage(resolved),
      "episode-workspace": () => renderEnterpriseShellPage(resolved),
      "story-shell": () => renderEnterpriseShellPage(resolved),
      "script-shell": () => renderEnterpriseShellPage(resolved),
      "consistency-shell": () => renderEnterpriseShellPage(resolved),
      "storyboard-shell": () => renderEnterpriseShellPage(resolved),
      "shot-shell": () => renderEnterpriseShellPage(resolved),
      "scene-shell": () => renderEnterpriseShellPage(resolved),
      "project-assets-shell": () => renderEnterpriseShellPage(resolved),
      "jobs-shell": () => renderEnterpriseShellPage(resolved),
      "timeline-shell": () => renderEnterpriseShellPage(resolved),
      "preview-shell": () => renderEnterpriseShellPage(resolved),
      "qc-shell": () => renderEnterpriseShellPage(resolved),
      "approval-shell": () => renderEnterpriseShellPage(resolved),
      "master-shell": () => renderEnterpriseShellPage(resolved),
      "export-shell": () => renderEnterpriseShellPage(resolved),
      "series-delivery-shell": () => renderEnterpriseShellPage(resolved),
      "release-shell": () => renderEnterpriseShellPage(resolved),
      "analytics-shell": () => renderEnterpriseShellPage(resolved),
      placeholder: () => renderPlaceholder(resolved),
      "not-found": () => renderNotFound(normalized)
    };
    content.innerHTML = (renderers[resolved.type] || renderers["not-found"])();
    renderInspector(resolved);
    renderStickyBar(resolved);
    applyInspectorState();
    closeMobileSidebar();
    if (resolved.type === "preview") bindPreviewEvents();
    content.focus({ preventScroll: true });
    if (resolved.type === "script-studio") {
      const nextScope = scriptScopeKey(scriptScopeFromRoute(resolved));
      if (state.scriptWorkspaceStatus === "idle" || state.scriptWorkspaceScope !== nextScope) {
        loadScriptWorkspace(resolved);
      }
    }
    if (["project-director", "series-planning"].includes(resolved.type)) {
      const nextScope = seriesPlanningScopeKey(seriesPlanningScopeFromRoute(resolved));
      if (state.seriesPlanningStatus === "idle" || state.seriesPlanningScope !== nextScope) {
        loadSeriesPlanningWorkspace(resolved);
      }
    }
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 3200);
  }

  function captureWizardValues() {
    const formData = new FormData(projectForm);
    Object.keys(state.wizardValues).forEach((key) => {
      if (formData.has(key)) state.wizardValues[key] = String(formData.get(key) || "");
    });
  }

  function wizardField(label, name, value, options = []) {
    if (options.length) return `<label><span>${escapeHtml(label)}</span><select name="${escapeHtml(name)}">${options.map((option) => `<option value="${escapeHtml(option)}" ${option === value ? "selected" : ""}>${escapeHtml(option || "请选择")}</option>`).join("")}</select></label>`;
    return `<label><span>${escapeHtml(label)}</span><input name="${escapeHtml(name)}" value="${escapeHtml(value)}" autocomplete="off"></label>`;
  }

  function wizardSeriesField(value) {
    const options = state.seriesRecords.map((series) => {
      const linked = Boolean(projectForSeries(series.seriesRef));
      return `<option value="${escapeHtml(series.seriesRef)}" ${series.seriesRef === value ? "selected" : ""} ${linked ? "disabled" : ""}>${escapeHtml(series.title)}${linked ? " · 已关联项目" : ""}</option>`;
    }).join("");
    return `<label><span>关联系列</span><select name="seriesRef" required><option value="">请选择既有系列</option>${options}</select><small>显式保留 seriesRef、episodeRef 与现有来源关系。</small></label>`;
  }

  function renderProjectWizard() {
    const values = state.wizardValues;
    const panels = {
      1: `<section class="wizard-step"><div><span class="section-kicker">STEP 01</span><h3>选择项目类型</h3><p>当前启用系列项目，用于承载既有系列与单集的生产上下文。</p></div><div class="wizard-choice-grid"><label><input type="radio" name="projectType" value="series" checked><span><strong>系列项目</strong><small>关联一个现有系列，保留全部生产来源</small></span></label><label class="is-disabled"><input type="radio" name="projectType" value="standalone" disabled><span><strong>独立影片</strong><small>后续阶段开放</small></span></label><label class="is-disabled"><input type="radio" name="projectType" value="brand-film" disabled><span><strong>品牌影片</strong><small>后续阶段开放</small></span></label></div></section>`,
      2: `<section class="wizard-step"><div><span class="section-kicker">STEP 02</span><h3>基本信息</h3><p>项目将通过 Creator Application 写入 V5 Project 公共边界。</p></div><div class="wizard-form-grid">${wizardSeriesField(values.seriesRef)}${wizardField("项目名称","title",values.title)}${wizardField("内容类型","contentType",values.contentType,["","剧情短片","系列内容","品牌内容"])}${wizardField("计划集数","episodeCount",values.episodeCount)}${wizardField("单集时长（秒）","duration",values.duration)}${wizardField("画幅","aspectRatio",values.aspectRatio,["9:16","16:9","1:1"])}${wizardField("目标平台","platform",values.platform,["","短视频平台","流媒体","内部审看"])}</div></section>`,
      3: `<section class="wizard-step"><div><span class="section-kicker">第 03 步</span><h3>制作默认值</h3><p>正式默认值需要由项目管理能力承担。</p></div><div class="wizard-form-grid">${wizardField("内容配置","contentProfile",values.contentProfile)}${wizardField("语言","language",values.language,["中文","英文","多语言"])}${wizardField("视觉方向","visualDirection",values.visualDirection)}${wizardField("制作预设","productionPreset",values.productionPreset,["","标准短片","高保真电影","快速审看"])}</div></section>`,
      4: `<section class="wizard-step"><div><span class="section-kicker">STEP 04</span><h3>检查并创建</h3><p>创建项目不会复制或改写系列、单集、故事与剧本身份。</p></div><dl class="wizard-review">${[["项目类型","系列项目"],["关联系列",(findSeries(values.seriesRef) || {}).title || "未选择"],["项目名称",values.title || "未填写"],["内容类型",values.contentType || "未选择"],["计划集数",values.episodeCount || "未填写"],["单集时长",`${values.duration || "—"} 秒`],["画幅",values.aspectRatio],["平台",values.platform || "未选择"],["语言",values.language],["视觉方向",values.visualDirection || "未填写"]].map(([label,value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl>${state.projectError ? `<p class="form-error" role="alert">${escapeHtml(state.projectError)}</p>` : ""}</section>`
    };
    document.getElementById("project-wizard-content").innerHTML = panels[state.wizardStep];
    projectDialog.querySelectorAll("[data-wizard-step-indicator]").forEach((item) => item.classList.toggle("is-current", Number(item.dataset.wizardStepIndicator) === state.wizardStep));
    const previous = projectDialog.querySelector('[data-action="wizard-previous"]');
    const next = projectDialog.querySelector('[data-action="wizard-next"]');
    const submit = projectDialog.querySelector('[data-action="wizard-submit"]');
    previous.hidden = state.wizardStep === 1;
    next.hidden = state.wizardStep === 4;
    submit.hidden = state.wizardStep !== 4;
    submit.disabled = state.projectPhase === "creating" || !values.seriesRef || !values.title.trim() || !Number(values.episodeCount || 0);
    submit.textContent = state.projectPhase === "creating" ? "正在创建…" : "创建项目";
  }

  function openProjectDialog(trigger) {
    dialogReturnFocus = trigger || document.activeElement;
    state.wizardStep = 1;
    if (!state.wizardValues.seriesRef) {
      const available = state.seriesRecords.find((series) => !projectForSeries(series.seriesRef));
      if (available) {
        state.wizardValues.seriesRef = available.seriesRef;
        if (!state.wizardValues.title) state.wizardValues.title = available.title;
        if (!state.wizardValues.episodeCount) state.wizardValues.episodeCount = String(available.plannedEpisodeCount || 1);
      }
    }
    renderProjectWizard();
    projectDialog.showModal();
    window.requestAnimationFrame(() => {
      const first = projectDialog.querySelector("input, select, button");
      if (first) first.focus();
    });
  }

  function closeProjectDialog() {
    if (projectDialog.open) projectDialog.close();
  }

  async function createProjectFromWizard() {
    if (state.projectPhase === "creating") return;
    const values = state.wizardValues;
    state.projectError = null;
    if (!values.seriesRef || !values.title.trim() || !Number(values.episodeCount || 0)) {
      state.projectError = "请选择既有系列，并填写项目名称与计划集数。";
      renderProjectWizard();
      return;
    }
    state.projectPhase = "creating";
    renderProjectWizard();
    try {
      const payload = await requestApplicationJson(projectsEndpoint, {
        method: "POST",
        body: JSON.stringify({
          workspaceRef,
          contentProfileRef,
          projectType: "series",
          seriesRef: values.seriesRef,
          title: values.title.trim(),
          description: values.contentType || "Creator 项目生产上下文",
          targetPlatform: values.platform,
          aspectRatio: values.aspectRatio,
          defaultDurationSec: Number(values.duration || 60),
          plannedEpisodeCount: Number(values.episodeCount)
        })
      });
      state.projectPhase = "idle";
      await loadProjectData({ force: true });
      closeProjectDialog();
      state.wizardValues = { projectType: "series", seriesRef: "", title: "", contentType: "", episodeCount: "", duration: "60", aspectRatio: "9:16", platform: "", contentProfile: contentProfileRef, language: "中文", visualDirection: "", productionPreset: "" };
      showToast("项目上下文已建立");
      navigate(`/creator/projects/${encodeURIComponent(payload.project.projectRef)}`);
    } catch (error) {
      state.projectPhase = "idle";
      state.projectError = error && error.message ? error.message : "项目创建失败，请稍后重试。";
      renderProjectWizard();
    }
  }

  function openDeleteDialog(trigger, kind) {
    const isSeries = kind === "series";
    const episodeCount = Number(trigger.dataset.episodeCount || 0);
    state.pendingDeletion = {
      kind,
      seriesRef: trigger.dataset.seriesRef || "",
      seriesTitle: trigger.dataset.seriesTitle || "",
      episodeRef: trigger.dataset.episodeRef || "",
      episodeTitle: trigger.dataset.episodeTitle || "",
      episodeCount
    };
    state.deletionPhase = "confirming";
    deleteDialogReturnFocus = trigger;
    deleteDialogTitle.textContent = isSeries ? "确认删除系列？" : "确认删除单集？";
    deleteDialogSubject.textContent = isSeries
      ? `删除系列「${state.pendingDeletion.seriesTitle}」`
      : `删除单集「${state.pendingDeletion.episodeTitle}」`;
    deleteDialogDescription.textContent = isSeries && episodeCount
      ? `删除后不可恢复，并将同时删除该系列下 ${episodeCount} 条单集记录。已有剧本版本时系统会阻止删除。`
      : "删除后不可恢复。已有剧本版本时系统会阻止删除，以保护现有制作链路。";
    deleteDialogError.hidden = true;
    deleteDialogError.textContent = "";
    deleteDialogConfirm.disabled = false;
    deleteDialogConfirm.removeAttribute("aria-busy");
    deleteDialogConfirm.textContent = isSeries ? "删除系列" : "删除单集";
    deleteDialog.showModal();
    window.requestAnimationFrame(() => {
      const cancel = deleteDialog.querySelector('[data-action="close-delete-dialog"]');
      if (cancel) cancel.focus();
    });
  }

  function closeDeleteDialog() {
    if (state.deletionPhase === "deleting") return;
    if (deleteDialog.open) deleteDialog.close();
  }

  async function confirmDeletion() {
    const target = state.pendingDeletion;
    if (!target || state.deletionPhase === "deleting") return;
    state.deletionPhase = "deleting";
    deleteDialogError.hidden = true;
    deleteDialogConfirm.disabled = true;
    deleteDialogConfirm.setAttribute("aria-busy", "true");
    deleteDialogConfirm.innerHTML = '<span class="button-spinner" aria-hidden="true"></span><span>正在删除…</span>';
    const isSeries = target.kind === "series";
    const endpoint = isSeries
      ? `${seriesEndpoint}/${encodeURIComponent(target.seriesRef)}`
      : `${episodesEndpoint}/${encodeURIComponent(target.episodeRef)}`;
    const requestPath = isSeries
      ? withWorkspace(endpoint)
      : withEpisodeScope(endpoint, target.seriesRef);
    try {
      await requestApplicationJson(requestPath, { method: "DELETE" });
      if (isSeries && state.selectedSeriesRef === target.seriesRef) {
        state.selectedSeriesRef = null;
        state.selectedEpisodeRef = null;
      } else if (!isSeries && state.selectedEpisodeRef === target.episodeRef) {
        state.selectedEpisodeRef = null;
      }
      state.pendingDeletion = null;
      state.deletionPhase = "idle";
      deleteDialog.close();
      await loadSeriesData({ force: true });
      renderRoute("/creator/projects");
      showToast(isSeries ? "系列及其单集已删除" : "单集已删除");
    } catch (error) {
      state.deletionPhase = "error";
      deleteDialogError.textContent = error && error.message ? error.message : "删除失败，请稍后重试。";
      deleteDialogError.hidden = false;
      deleteDialogConfirm.disabled = false;
      deleteDialogConfirm.removeAttribute("aria-busy");
      deleteDialogConfirm.textContent = isSeries ? "重试删除系列" : "重试删除单集";
    }
  }

  function toggleSidebarCollapse() {
    state.sidebarCollapsed = !state.sidebarCollapsed;
    document.getElementById("app-shell").classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
    const button = document.querySelector('[data-action="toggle-sidebar-collapse"]');
    button.setAttribute("aria-expanded", String(!state.sidebarCollapsed));
    button.setAttribute("aria-label", state.sidebarCollapsed ? "展开一级导航" : "折叠一级导航");
    showToast(state.sidebarCollapsed ? "一级导航已折叠" : "一级导航已展开");
  }

  function openMobileSidebar() {
    state.mobileSidebarOpen = true;
    applySidebarAccessibility();
    window.requestAnimationFrame(() => {
      const closeButton = sidebar.querySelector('[data-action="toggle-sidebar-collapse"]');
      if (closeButton) closeButton.focus();
    });
  }

  function closeMobileSidebar(restoreFocus = false) {
    state.mobileSidebarOpen = false;
    applySidebarAccessibility();
    if (restoreFocus) {
      const trigger = document.querySelector('[data-action="open-mobile-sidebar"]');
      if (trigger) trigger.focus();
    }
  }

  function isCandidatePlan(plan) {
    return Boolean(
      plan &&
      plan.schemaVersion === "creator.ai-director.plan.v1" &&
      plan.creativeInterpretation &&
      plan.storyDirection &&
      plan.scriptDraft &&
      Array.isArray(plan.storyboardPlan) &&
      plan.visualStyle &&
      plan.productionPlan &&
      plan.productionPlan.shotCount === plan.storyboardPlan.length
    );
  }

  function readAiDirectorBrief() {
    const form = document.getElementById("ai-director-form");
    if (!form) return null;
    const durationInput = form.elements.duration;
    if (durationInput) {
      const durationMatch = String(durationInput.value || "").trim().match(/^(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?|秒)?$/i);
      const durationSeconds = durationMatch ? Number(durationMatch[1]) : 0;
      durationInput.setCustomValidity(durationSeconds > 0 && durationSeconds <= 3600 ? "" : "请输入 1–3600 秒的合理时长");
    }
    if (!form.reportValidity()) return null;
    const formData = new FormData(form);
    return Object.fromEntries(
      Object.keys(fixture.aiDirector.briefDefaults).map((key) => [key, String(formData.get(key) || "").trim()])
    );
  }

  async function runAiDirector() {
    if (state.aiDirectorPhase === "generating") return;
    const brief = readAiDirectorBrief();
    if (!brief) return;
    const previousPlan = state.aiDirectorPlan;
    const previousConfirmed = state.aiDirectorConfirmed;
    state.aiDirectorBrief = brief;
    state.aiDirectorPhase = "generating";
    state.aiDirectorError = null;
    renderRoute("/creator/ai-director");
    const abortController = new AbortController();
    const timeout = window.setTimeout(() => abortController.abort(), 45_000);
    try {
      const payload = await requestApplicationJson(aiDirectorEndpoint, {
        method: "POST",
        body: JSON.stringify({ brief }),
        signal: abortController.signal
      });
      if (!isCandidatePlan(payload.plan)) throw new Error("candidate-plan-unavailable");
      state.aiDirectorPlan = payload.plan;
      state.aiDirectorPlanVersion += 1;
      state.aiDirectorConfirmed = false;
      state.confirmedCreativePlan = null;
      state.seriesEpisodePhase = "idle";
      state.seriesEpisodeError = null;
      state.aiDirectorPhase = "result";
      showToast("候选导演方案已生成 · 请完成人工确认");
    } catch (error) {
      state.aiDirectorPlan = previousPlan;
      state.aiDirectorConfirmed = previousConfirmed;
      state.aiDirectorPhase = "error";
      state.aiDirectorError = "导演方案暂时无法生成，请稍后重试。";
      showToast("导演方案暂时无法生成，请稍后重试。");
    } finally {
      window.clearTimeout(timeout);
      renderRoute("/creator/ai-director");
      window.requestAnimationFrame(() => {
        const canvas = document.getElementById("director-canvas-title");
        if (canvas) canvas.focus({ preventScroll: true });
      });
    }
  }

  async function confirmAiDirectorPlan() {
    if (!state.aiDirectorPlan || state.aiDirectorPhase === "generating") return;
    state.aiDirectorPhase = "confirming";
    state.aiDirectorError = null;
    renderRoute("/creator/ai-director");
    try {
      const payload = await requestApplicationJson(confirmCreativePlanEndpoint, {
        method: "POST",
        body: JSON.stringify({
          workspaceRef,
          humanConfirmed: true,
          brief: state.aiDirectorBrief,
          plan: state.aiDirectorPlan,
          sourcePlanRef: `local-ai-director-plan-${state.aiDirectorPlanVersion}`,
          sourcePlanVersion: state.aiDirectorPlanVersion
        })
      });
      state.confirmedCreativePlan = payload.confirmedPlan;
      state.aiDirectorConfirmed = true;
      state.aiDirectorPhase = "confirmed";
      await loadSeriesData({ force: true });
      showToast("导演方案已完成人工确认");
    } catch (error) {
      state.aiDirectorConfirmed = false;
      state.confirmedCreativePlan = null;
      state.aiDirectorPhase = "result";
      state.aiDirectorError = error.message || "暂时无法确认导演方案。";
      showToast(state.aiDirectorError);
    }
    renderRoute("/creator/ai-director");
  }

  async function createSeriesEpisode(form) {
    if (!state.confirmedCreativePlan || state.seriesEpisodePhase === "creating") return;
    const formData = new FormData(form);
    state.seriesEpisodePhase = "creating";
    state.seriesEpisodeError = null;
    renderRoute("/creator/ai-director");
    try {
      let seriesRefValue = String(formData.get("seriesRef") || "");
      if (seriesRefValue === "__new__") {
        const seriesPayload = await requestApplicationJson(seriesEndpoint, {
          method: "POST",
          body: JSON.stringify({
            workspaceRef,
            contentProfileRef,
            title: String(formData.get("seriesTitle") || "晚灯").trim(),
            description: "由已确认的 AI导演方案开始的创作系列",
            plannedEpisodeCount: Number(formData.get("plannedEpisodeCount") || 1)
          })
        });
        seriesRefValue = seriesPayload.series.seriesRef;
      }
      const episodePayload = await requestApplicationJson(episodesEndpoint, {
        method: "POST",
        body: JSON.stringify({
          workspaceRef,
          seriesRef: seriesRefValue,
          creativePlanRef: state.confirmedCreativePlan.creativePlanRef,
          episodeNumber: Number(formData.get("episodeNumber") || 1),
          seasonNumber: 1,
          volumeNumber: 1,
          title: String(formData.get("episodeTitle") || "第1集").trim()
        })
      });
      state.createdEpisode = episodePayload.episode;
      state.seriesEpisodePhase = "created";
      await loadSeriesData({ force: true });
      navigate(`/creator/projects/${encodeURIComponent(episodePayload.episode.episodeRef)}`);
      showToast("系列与集数已创建");
    } catch (error) {
      state.seriesEpisodePhase = "error";
      state.seriesEpisodeError = error.message || "暂时无法创建系列与集数。";
      renderRoute("/creator/ai-director");
      showToast(state.seriesEpisodeError);
    }
  }

  function scriptContentFromVersion(version) {
    return {
      title: version.title,
      logline: version.logline,
      synopsis: version.synopsis,
      targetDurationSec: version.targetDurationSec,
      scenes: JSON.parse(JSON.stringify(version.scenes))
    };
  }

  function parseScriptLines(value) {
    return String(value || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  }

  function parseDialogueLines(value) {
    return parseScriptLines(value).map((line) => {
      const parts = line.split("|").map((item) => item.trim());
      if (parts.length < 3 || !parts[0] || !parts[1] || !parts.slice(2).join("|").trim()) {
        throw new Error("对白请使用“说话人 | 情绪 | 台词”格式，每行一条。");
      }
      return { speaker: parts[0], emotion: parts[1], text: parts.slice(2).join("|").trim() };
    });
  }

  async function refreshScriptAfterMutation(route, versionRef, message) {
    state.selectedScriptVersionRef = versionRef || state.selectedScriptVersionRef;
    state.scriptPhase = "idle";
    state.scriptError = null;
    await loadScriptWorkspace(route, { force: true, preserveSelection: true });
    if (message) showToast(message);
  }

  async function generateScript() {
    const route = state.activeRoute;
    const scope = scriptScopeFromRoute(route);
    if (!scope || state.scriptPhase !== "idle") return;
    state.scriptPhase = "generating";
    state.scriptError = null;
    renderRoute(state.activePath);
    try {
      const payload = await requestApplicationJson(scriptGenerateEndpoint, {
        method: "POST",
        body: JSON.stringify(scope)
      });
      await refreshScriptAfterMutation(route, payload.scriptVersion.scriptVersionRef, "剧本 v1 已创建，等待人工确认");
    } catch (error) {
      state.scriptPhase = "idle";
      state.scriptError = error && error.message ? error.message : "剧本生成暂时未完成，请稍后重试。";
      renderRoute(state.activePath);
    }
  }

  async function saveManualScriptVersion(form) {
    const route = state.activeRoute;
    const scope = scriptScopeFromRoute(route);
    const workspace = state.scriptWorkspace;
    const version = selectedScriptVersion();
    const scene = selectedScriptScene();
    if (!scope || !workspace || !workspace.script || !version || !scene || state.scriptPhase !== "idle") return;
    const formData = new FormData(form);
    try {
      const contentValue = scriptContentFromVersion(version);
      contentValue.title = String(formData.get("title") || "").trim();
      contentValue.synopsis = String(formData.get("synopsis") || "").trim();
      const editedScene = contentValue.scenes.find((item) => item.scriptSceneRef === scene.scriptSceneRef);
      editedScene.heading = String(formData.get("heading") || "").trim();
      editedScene.location = String(formData.get("location") || "").trim();
      editedScene.timeOfDay = String(formData.get("timeOfDay") || "").trim();
      editedScene.action = String(formData.get("action") || "").trim();
      editedScene.dialogue = parseDialogueLines(formData.get("dialogue"));
      editedScene.narration = parseScriptLines(formData.get("narration"));
      editedScene.subtitleText = parseScriptLines(formData.get("subtitleText"));
      if (!contentValue.title || !contentValue.synopsis || !editedScene.heading || !editedScene.location || !editedScene.timeOfDay || !editedScene.action) {
        throw new Error("请完整填写剧本标题、梗概与当前场景的必填内容。");
      }
      state.scriptPhase = "saving";
      state.scriptError = null;
      renderRoute(state.activePath);
      const payload = await requestApplicationJson(scriptManualVersionEndpoint, {
        method: "POST",
        body: JSON.stringify({
          ...scope,
          scriptRef: workspace.script.scriptRef,
          baseScriptVersionRef: version.scriptVersionRef,
          content: contentValue
        })
      });
      await refreshScriptAfterMutation(route, payload.scriptVersion.scriptVersionRef, `剧本 v${payload.scriptVersion.versionNumber} 已保存`);
    } catch (error) {
      state.scriptPhase = "idle";
      state.scriptError = error && error.message ? error.message : "新版本暂时无法保存。";
      renderRoute(state.activePath);
    }
  }

  async function rewriteScriptScene(form) {
    const route = state.activeRoute;
    const scope = scriptScopeFromRoute(route);
    const workspace = state.scriptWorkspace;
    const version = selectedScriptVersion();
    const scene = selectedScriptScene();
    if (!scope || !workspace || !workspace.script || !version || !scene || state.scriptPhase !== "idle") return;
    const instruction = String(new FormData(form).get("instruction") || "").trim();
    if (!instruction) return;
    state.scriptPhase = "rewriting";
    state.scriptError = null;
    renderRoute(state.activePath);
    try {
      const payload = await requestApplicationJson(scriptRewriteEndpoint, {
        method: "POST",
        body: JSON.stringify({
          ...scope,
          scriptRef: workspace.script.scriptRef,
          baseScriptVersionRef: version.scriptVersionRef,
          scriptSceneRef: scene.scriptSceneRef,
          instruction
        })
      });
      await refreshScriptAfterMutation(route, payload.scriptVersion.scriptVersionRef, `场景改写已保存为 v${payload.scriptVersion.versionNumber}`);
    } catch (error) {
      state.scriptPhase = "idle";
      state.scriptError = error && error.message ? error.message : "场景改写暂时未完成。";
      renderRoute(state.activePath);
    }
  }

  async function confirmScriptVersion() {
    const route = state.activeRoute;
    const scope = scriptScopeFromRoute(route);
    const workspace = state.scriptWorkspace;
    const version = selectedScriptVersion();
    if (!scope || !workspace || !workspace.script || !version || state.scriptPhase !== "idle") return;
    state.scriptPhase = "confirming";
    state.scriptError = null;
    renderRoute(state.activePath);
    try {
      await requestApplicationJson(scriptConfirmEndpoint, {
        method: "POST",
        body: JSON.stringify({
          ...scope,
          scriptRef: workspace.script.scriptRef,
          scriptVersionRef: version.scriptVersionRef,
          humanConfirmed: true
        })
      });
      await refreshScriptAfterMutation(route, version.scriptVersionRef, `剧本 v${version.versionNumber} 已人工确认`);
    } catch (error) {
      state.scriptPhase = "idle";
      state.scriptError = error && error.message ? error.message : "版本确认暂时未完成。";
      renderRoute(state.activePath);
    }
  }

  async function generateSeriesPlanCandidate() {
    const route = state.activeRoute;
    const scope = seriesPlanningScopeFromRoute(route);
    if (!scope || state.seriesPlanningPhase === "generating") return;
    const form = document.getElementById("series-director-form");
    const value = form ? String(new FormData(form).get("creativeInput") || "").trim() : state.seriesPlanningInput;
    if (!value) return;
    state.seriesPlanningInput = value;
    state.seriesPlanningPhase = "generating";
    state.seriesPlanningError = null;
    renderRoute(state.activePath);
    try {
      const payload = await requestApplicationJson(seriesPlanningGenerateEndpoint, {
        method: "POST",
        body: JSON.stringify({ ...scope, creativeInput: value })
      });
      state.seriesPlanningCandidate = payload.candidate;
      state.seriesPlanningPhase = "candidate";
      showToast("系列规划候选已生成 · 请完成人工确认");
    } catch (error) {
      state.seriesPlanningPhase = "idle";
      state.seriesPlanningError = error && error.message ? error.message : "系列规划候选暂时无法生成。";
      showToast(state.seriesPlanningError);
    }
    renderRoute(state.activePath);
  }

  async function confirmSeriesPlanCandidate() {
    const scope = seriesPlanningScopeFromRoute(state.activeRoute);
    if (!scope || !state.seriesPlanningCandidate || state.seriesPlanningPhase === "confirming") return;
    state.seriesPlanningPhase = "confirming";
    state.seriesPlanningError = null;
    renderRoute(state.activePath);
    try {
      await requestApplicationJson(seriesPlanningConfirmEndpoint, {
        method: "POST",
        body: JSON.stringify({ ...scope, humanConfirmed: true, candidate: state.seriesPlanningCandidate })
      });
      state.seriesPlanningCandidate = null;
      state.seriesPlanningPhase = "idle";
      await loadSeriesPlanningWorkspace(state.activeRoute, { force: true });
      showToast("系列规划 v1 已人工确认");
      navigate(`${state.activeRoute.projectBase}/planning/series`);
    } catch (error) {
      state.seriesPlanningPhase = "candidate";
      state.seriesPlanningError = error && error.message ? error.message : "系列规划暂时无法确认。";
      renderRoute(state.activePath);
    }
  }

  async function createManualSeriesPlanVersion(form) {
    const scope = seriesPlanningScopeFromRoute(state.activeRoute);
    const workspace = state.seriesPlanningWorkspace;
    const version = selectedSeriesPlanVersion();
    if (!scope || !workspace || !workspace.plan || !version || state.seriesPlanningPhase !== "idle") return;
    const premise = String(new FormData(form).get("premise") || "").trim();
    if (!premise) return;
    const contentValue = seriesPlanVersionContent(version);
    contentValue.premise = premise;
    state.seriesPlanningPhase = "saving";
    state.seriesPlanningError = null;
    renderRoute(state.activePath);
    try {
      const payload = await requestApplicationJson(seriesPlanningManualVersionEndpoint, {
        method: "POST",
        body: JSON.stringify({
          ...scope,
          seriesPlanRef: workspace.plan.seriesPlanRef,
          expectedPlanVersion: workspace.plan.version,
          content: contentValue
        })
      });
      state.seriesPlanningPhase = "idle";
      state.selectedSeriesPlanVersionRef = payload.version.seriesPlanVersionRef;
      await loadSeriesPlanningWorkspace(state.activeRoute, { force: true });
      showToast(`系列规划 v${payload.version.versionNumber} 已保存 · 等待人工确认`);
    } catch (error) {
      state.seriesPlanningPhase = "idle";
      state.seriesPlanningError = error && error.message ? error.message : "系列规划版本暂时无法保存。";
      renderRoute(state.activePath);
    }
  }

  async function confirmCurrentSeriesPlanVersion() {
    const workspace = state.seriesPlanningWorkspace;
    const version = selectedSeriesPlanVersion();
    if (!workspace || !workspace.plan || !version || state.seriesPlanningPhase !== "idle") return;
    state.seriesPlanningPhase = "confirming";
    state.seriesPlanningError = null;
    renderRoute(state.activePath);
    try {
      await requestApplicationJson(seriesPlanningConfirmVersionEndpoint, {
        method: "POST",
        body: JSON.stringify({
          workspaceRef,
          seriesPlanRef: workspace.plan.seriesPlanRef,
          seriesPlanVersionRef: version.seriesPlanVersionRef,
          expectedPlanVersion: workspace.plan.version,
          humanConfirmed: true
        })
      });
      state.seriesPlanningPhase = "idle";
      await loadSeriesPlanningWorkspace(state.activeRoute, { force: true });
      showToast(`系列规划 v${version.versionNumber} 已人工确认`);
    } catch (error) {
      state.seriesPlanningPhase = "idle";
      state.seriesPlanningError = error && error.message ? error.message : "当前规划版本暂时无法确认。";
      renderRoute(state.activePath);
    }
  }

  function resetFixture() {
    state.assetTab = "basic";
    state.assetFilter = "all";
    state.selectedShotKey = fixture.shots[0].localKey;
    state.selectedPipelineKey = (fixture.pipeline.find((stage) => stage.label === "Preview") || fixture.pipeline[1]).localKey;
    state.wizardStep = 1;
    state.wizardValues = { projectType: "series", seriesRef: "", title: "", contentType: "", episodeCount: "", duration: "60", aspectRatio: "9:16", platform: "", contentProfile: contentProfileRef, language: "中文", visualDirection: "", productionPreset: "" };
    state.aiDirectorPhase = "input";
    state.aiDirectorBrief = { ...fixture.aiDirector.briefDefaults };
    state.aiDirectorPlan = null;
    state.aiDirectorPlanVersion = 0;
    state.aiDirectorConfirmed = false;
    state.aiDirectorError = null;
    state.confirmedCreativePlan = null;
    state.seriesEpisodePhase = "idle";
    state.seriesEpisodeError = null;
    state.createdEpisode = null;
    state.previewState = "paused";
    state.previewMuted = true;
    renderRoute(state.activePath);
    showToast("当前体验已重置 · 没有保存或修改业务数据");
  }

  function rerenderAndRestoreFocus(selector) {
    renderRoute(state.activePath);
    window.requestAnimationFrame(() => {
      const target = document.querySelector(selector);
      if (target) target.focus();
    });
  }

  function handleAction(button) {
    const action = button.dataset.action;
    if (!action) return;
    if (action === "open-project-dialog") openProjectDialog(button);
    if (action === "associate-series-project") {
      state.wizardValues.seriesRef = button.dataset.seriesRef || "";
      state.wizardValues.title = button.dataset.seriesTitle || "";
      const series = findSeries(state.wizardValues.seriesRef);
      state.wizardValues.episodeCount = String(series ? series.plannedEpisodeCount : 1);
      openProjectDialog(button);
    }
    if (action === "close-project-dialog") closeProjectDialog();
    if (action === "delete-episode") openDeleteDialog(button, "episode");
    if (action === "delete-series") openDeleteDialog(button, "series");
    if (action === "close-delete-dialog") closeDeleteDialog();
    if (action === "confirm-deletion") confirmDeletion();
    if (action === "wizard-next") {
      captureWizardValues();
      state.wizardStep = Math.min(4, state.wizardStep + 1);
      renderProjectWizard();
    }
    if (action === "wizard-previous") {
      captureWizardValues();
      state.wizardStep = Math.max(1, state.wizardStep - 1);
      renderProjectWizard();
    }
    if (action === "toggle-bottom-drawer") {
      state.bottomDrawerOpen = !state.bottomDrawerOpen;
      bottomDrawer.hidden = !state.bottomDrawerOpen;
      bottomDrawerTitle.textContent = "版本、任务与活动";
      bottomDrawerContent.innerHTML = '<div class="drawer-empty"><strong>暂无正式活动</strong><p>这里不会显示虚构的后台任务、版本或制作日志。</p></div>';
    }
    if (action === "toggle-sidebar-collapse") {
      if (mobileQuery.matches) closeMobileSidebar(true);
      else toggleSidebarCollapse();
    }
    if (action === "open-mobile-sidebar") openMobileSidebar();
    if (action === "close-mobile-sidebar") closeMobileSidebar();
    if (action === "toggle-inspector") {
      if (!state.inspectorOpen) inspectorReturnFocus = button;
      state.inspectorOpen = !state.inspectorOpen;
      applyInspectorState();
      window.requestAnimationFrame(() => {
        if (state.inspectorOpen) {
          const closeButton = inspector.querySelector('[data-action="toggle-inspector"]');
          if (closeButton) closeButton.focus();
        } else {
          const returnTarget = inspectorReturnFocus && document.contains(inspectorReturnFocus) ? inspectorReturnFocus : inspectorFab;
          if (returnTarget && !returnTarget.hidden) returnTarget.focus();
          inspectorReturnFocus = null;
        }
      });
    }
    if (action === "reset-fixture") resetFixture();
    if (action === "run-ai-director") runAiDirector();
    if (action === "regenerate-ai-director") runAiDirector();
    if (action === "confirm-ai-director-plan") confirmAiDirectorPlan();
    if (action === "submit-series-episode") {
      const form = document.getElementById("series-episode-form");
      if (form) form.requestSubmit();
    }
    if (action === "reload-series") loadSeriesData({ force: true });
    if (action === "reload-projects") {
      loadSeriesData({ force: true });
      loadProjectData({ force: true });
    }
    if (action === "generate-script") generateScript();
    if (action === "confirm-script-version") confirmScriptVersion();
    if (action === "regenerate-series-plan") generateSeriesPlanCandidate();
    if (action === "confirm-series-plan") confirmSeriesPlanCandidate();
    if (action === "confirm-series-plan-version") confirmCurrentSeriesPlanVersion();
    if (action === "select-series-plan-version") {
      state.selectedSeriesPlanVersionRef = button.dataset.versionRef;
      state.seriesPlanningError = null;
      rerenderAndRestoreFocus(`[data-action="select-series-plan-version"][data-version-ref="${state.selectedSeriesPlanVersionRef}"]`);
    }
    if (action === "select-script-version") {
      state.selectedScriptVersionRef = button.dataset.versionRef;
      const version = selectedScriptVersion();
      state.selectedScriptSceneRef = version && version.scenes.length ? version.scenes[0].scriptSceneRef : null;
      state.scriptError = null;
      rerenderAndRestoreFocus(`[data-action="select-script-version"][data-version-ref="${state.selectedScriptVersionRef}"]`);
    }
    if (action === "select-script-scene") {
      state.selectedScriptSceneRef = button.dataset.sceneRef;
      state.scriptError = null;
      rerenderAndRestoreFocus(`[data-action="select-script-scene"][data-scene-ref="${state.selectedScriptSceneRef}"]`);
    }
    if (action === "select-asset-tab") {
      state.assetTab = button.dataset.tab;
      rerenderAndRestoreFocus(`[data-action="select-asset-tab"][data-tab="${state.assetTab}"]`);
    }
    if (action === "filter-assets") {
      state.assetFilter = button.dataset.filter;
      rerenderAndRestoreFocus(`[data-action="filter-assets"][data-filter="${state.assetFilter}"]`);
    }
    if (action === "select-shot") {
      state.selectedShotKey = button.dataset.shotKey;
      rerenderAndRestoreFocus(`[data-action="select-shot"][data-shot-key="${state.selectedShotKey}"]`);
    }
    if (action === "select-pipeline-stage") {
      state.selectedPipelineKey = button.dataset.stageKey;
      rerenderAndRestoreFocus(`[data-action="select-pipeline-stage"][data-stage-key="${state.selectedPipelineKey}"]`);
    }
    if (action === "toggle-preview") {
      const video = document.getElementById("candidate-video");
      if (!video) return;
      if (video.ended) video.currentTime = 0;
      if (video.paused) {
        video.play().catch(() => {
          state.previewState = "error";
          updatePreviewUi(video);
        });
      } else {
        video.pause();
      }
    }
    if (action === "toggle-preview-mute") {
      const video = document.getElementById("candidate-video");
      if (!video) return;
      state.previewMuted = !state.previewMuted;
      video.muted = state.previewMuted;
      updatePreviewUi(video);
    }
  }

  document.addEventListener("click", (event) => {
    const actionButton = event.target.closest("[data-action]");
    if (actionButton && !actionButton.disabled) handleAction(actionButton);
    const routeLink = event.target.closest('a[href^="#/creator/"]');
    if (routeLink) closeMobileSidebar();
  });

  document.addEventListener("submit", (event) => {
    if (event.target.id === "ai-director-form") {
      event.preventDefault();
      runAiDirector();
    }
    if (event.target.id === "series-episode-form") {
      event.preventDefault();
      createSeriesEpisode(event.target);
    }
    if (event.target.id === "script-edit-form") {
      event.preventDefault();
      saveManualScriptVersion(event.target);
    }
    if (event.target.id === "script-rewrite-form") {
      event.preventDefault();
      rewriteScriptScene(event.target);
    }
    if (event.target.id === "series-director-form") {
      event.preventDefault();
      generateSeriesPlanCandidate();
    }
    if (event.target.id === "series-plan-revision-form") {
      event.preventDefault();
      createManualSeriesPlanVersion(event.target);
    }
  });

  document.addEventListener("keydown", (event) => {
    const activeTab = event.target.closest('[role="tab"][data-action="select-asset-tab"]');
    if (activeTab && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      const tabs = Array.from(document.querySelectorAll('[role="tab"][data-action="select-asset-tab"]'));
      const currentIndex = tabs.indexOf(activeTab);
      let nextIndex = currentIndex;
      if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
      if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      event.preventDefault();
      state.assetTab = tabs[nextIndex].dataset.tab;
      rerenderAndRestoreFocus(`[data-action="select-asset-tab"][data-tab="${state.assetTab}"]`);
      return;
    }

    if (state.mobileSidebarOpen && event.key === "Tab") {
      const focusable = Array.from(sidebar.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  projectForm.addEventListener("submit", (event) => {
    event.preventDefault();
    createProjectFromWizard();
  });

  projectDialog.addEventListener("close", () => {
    if (dialogReturnFocus && typeof dialogReturnFocus.focus === "function") dialogReturnFocus.focus();
    dialogReturnFocus = null;
  });

  projectDialog.addEventListener("cancel", () => {
    window.requestAnimationFrame(() => {
      if (dialogReturnFocus && typeof dialogReturnFocus.focus === "function") dialogReturnFocus.focus();
    });
  });

  deleteDialog.addEventListener("close", () => {
    state.pendingDeletion = null;
    state.deletionPhase = "idle";
    if (deleteDialogReturnFocus && document.contains(deleteDialogReturnFocus)) deleteDialogReturnFocus.focus();
    deleteDialogReturnFocus = null;
  });

  deleteDialog.addEventListener("cancel", (event) => {
    if (state.deletionPhase === "deleting") {
      event.preventDefault();
      return;
    }
    window.requestAnimationFrame(() => {
      if (deleteDialogReturnFocus && document.contains(deleteDialogReturnFocus)) deleteDialogReturnFocus.focus();
    });
  });

  window.addEventListener("hashchange", () => renderRoute(pathFromHash()));
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.mobileSidebarOpen) {
      closeMobileSidebar(true);
    } else if (event.key === "Escape" && compactInspectorQuery.matches && state.inspectorOpen) {
      state.inspectorOpen = false;
      applyInspectorState();
      if (inspectorReturnFocus && document.contains(inspectorReturnFocus)) inspectorReturnFocus.focus();
      else if (!inspectorFab.hidden) inspectorFab.focus();
      inspectorReturnFocus = null;
    }
  });

  mobileQuery.addEventListener("change", (event) => {
    state.mobileSidebarOpen = false;
    if (event.matches) {
      state.sidebarCollapsed = false;
      document.getElementById("app-shell").classList.remove("sidebar-collapsed");
      state.inspectorOpen = false;
    }
    else state.inspectorOpen = !compactInspectorQuery.matches;
    applySidebarAccessibility();
    applyInspectorState();
  });

  compactInspectorQuery.addEventListener("change", (event) => {
    if (!mobileQuery.matches) {
      state.inspectorOpen = !event.matches;
      applyInspectorState();
    }
  });

  window.CreatorWorkspaceSkeleton = Object.freeze({
    taskId: fixture.meta.taskId,
    featureStates,
    primaryRoutes,
    creationModules,
    projectPages,
    canonicalRouteTemplates,
    storyViewSchemaVersion,
    buildStoryProjection,
    renderLoadingState,
    renderErrorState,
    renderButtonLoading
  });

  if (!window.location.hash) {
    window.history.replaceState(null, "", `#${defaultRoute}`);
  }
  applySidebarAccessibility();
  renderRoute(pathFromHash());
})();
