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
  const projectDialog = document.getElementById("project-dialog");
  const projectForm = document.getElementById("project-form");
  const toast = document.getElementById("toast");
  const fixtureBanner = document.querySelector(".fixture-banner");
  const defaultFixtureBannerMarkup = fixtureBanner ? fixtureBanner.innerHTML : "";

  if (!fixtureElement || !content || !workbench || !stickyActionBar) {
    throw new Error("Creator Workspace UI Skeleton containers are missing.");
  }

  const fixture = JSON.parse(fixtureElement.textContent);
  const aiDirectorEndpoint = "/creator/internal/ai-director/plan";
  const projectRef = fixture.project.projectRef;
  const projectBase = `/creator/projects/${projectRef}`;
  const displayProjectTitle = "晚灯 · 第 1 集";
  const defaultRoute = "/creator/dashboard";
  let toastTimer;
  let dialogReturnFocus = null;
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
    { key: "dashboard", path: "/creator/dashboard", label: "首页", english: "Dashboard", status: "fixture" },
    { key: "ai-director", path: "/creator/ai-director", label: "AI导演", english: "AI Director", status: "fixture", featureStatus: "development" },
    { key: "projects", path: "/creator/projects", label: "项目", english: "Projects", status: "fixture" },
    { key: "assets", path: "/creator/assets", label: "资产库", english: "Asset Library", status: "fixture" },
    { key: "creation", path: "/creator/creation", label: "创作中心", english: "Creation Center", status: "fixture" },
    { key: "works", path: "/creator/works", label: "作品", english: "Works", status: "fixture" }
  ]);

  const creationModules = Object.freeze([
    { key: "generation", path: "/creator/creation/generation", label: "生成中心", english: "Generation Center", version: "v0.2", description: "未来用于把文字与视觉意图整理为创作素材；当前功能即将上线。" },
    { key: "templates", path: "/creator/creation/templates", label: "模板库", english: "Template Library", version: "TBD", description: "未来模板浏览入口；当前没有模板执行能力。" },
    { key: "ip-studio", path: "/creator/creation/ip-studio", label: "IP 工作室", english: "IP Studio", version: "v0.3", description: "未来用于跨项目管理角色与世界观；当前功能即将上线。" },
    { key: "memory", path: "/creator/creation/memory", label: "AI 记忆", english: "AI Memory", version: "v0.3", description: "未来用于延续已确认的创作偏好；当前不会保存或检索记忆。" },
    { key: "workflow-presets", path: "/creator/creation/workflow-presets", label: "工作流预设", english: "Workflow Preset", version: "TBD", description: "未来用于整理重复的人工创作步骤；当前功能即将上线。" },
    { key: "analytics", path: "/creator/creation/analytics", label: "数据分析", english: "Analytics", version: "v1.0", description: "未来证据只读视图；当前没有真实统计或商业结论。" }
  ]);

  const projectPages = Object.freeze([
    { key: "pipeline", label: "生产流程", english: "Production Pipeline", status: "fixture" },
    { key: "story", label: "故事", english: "Story", status: "planned" },
    { key: "ip-bible", label: "IP 圣经", english: "IP Bible", status: "planned" },
    { key: "character", label: "角色", english: "Character", status: "fixture" },
    { key: "scene", label: "场景", english: "Scene", status: "planned" },
    { key: "storyboard", label: "分镜", english: "Storyboard", status: "fixture" },
    { key: "audio", label: "音频", english: "Audio", status: "planned" },
    { key: "timeline", label: "时间线", english: "Timeline", status: "planned" },
    { key: "preview", label: "预览", english: "Preview", status: "fixture" },
    { key: "approval", label: "审批", english: "Approval", status: "disabled" },
    { key: "export", label: "导出", english: "Export", status: "fixture" },
    { key: "settings", label: "设置", english: "Settings", status: "planned" }
  ].map((page) => ({ ...page, path: `${projectBase}/${page.key}` })));

  const canonicalRouteTemplates = Object.freeze([
    "/creator/dashboard",
    "/creator/projects",
    "/creator/assets",
    "/creator/creation",
    "/creator/works",
    "/creator/account",
    "/creator/ai-director",
    "/creator/projects/:projectRef",
    "/creator/projects/:projectRef/pipeline",
    "/creator/projects/:projectRef/story",
    "/creator/projects/:projectRef/ip-bible",
    "/creator/projects/:projectRef/character",
    "/creator/projects/:projectRef/scene",
    "/creator/projects/:projectRef/storyboard",
    "/creator/projects/:projectRef/audio",
    "/creator/projects/:projectRef/timeline",
    "/creator/projects/:projectRef/preview",
    "/creator/projects/:projectRef/approval",
    "/creator/projects/:projectRef/export",
    "/creator/projects/:projectRef/settings",
    "/creator/creation/generation",
    "/creator/creation/templates",
    "/creator/creation/ip-studio",
    "/creator/creation/memory",
    "/creator/creation/workflow-presets",
    "/creator/creation/analytics"
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
    localProjectDrafts: [],
    localDraftCounter: 0,
    aiDirectorPhase: "input",
    aiDirectorBrief: { ...fixture.aiDirector.briefDefaults },
    aiDirectorPlan: null,
    aiDirectorPlanVersion: 0,
    aiDirectorConfirmed: false,
    aiDirectorError: null,
    aiDirectorProjectDraft: null,
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
    if (statusKey === "fixture") return '<span class="sr-only">FIXTURE ONLY</span>';
    const labels = { fixture: "演示版本", development: "开发中", planned: "即将上线", disabled: "暂不可用" };
    return `<span class="badge badge-${status.tone} ${additionalClass}"><i aria-hidden="true"></i>${escapeHtml(labels[statusKey] || status.badge)}</span>`;
  }

  function pageStatus(statusKey) {
    const status = featureStates[statusKey] || featureStates.planned;
    if (statusKey === "fixture") return '<span class="sr-only">AVAILABLE - FIXTURE ONLY</span>';
    const labels = { available: "可用", fixture: "演示版本", development: "开发中", planned: "即将上线", disabled: "暂不可用" };
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
    return '<span class="sr-only page-fixture-contract">FIXTURE ONLY · NOT A DOMAIN FACT · SESSION ONLY</span>';
  }

  function candidatePlanNotice() {
    return '<span class="sr-only candidate-plan-contract">候选创意方案 · 人工确认前不会进入后续流程 · 仅当前会话有效</span>';
  }

  function demoNotice(copy) {
    return `<span class="sr-only director-demo-notice">${escapeHtml(copy)} · FIXTURE ONLY · NOT A DOMAIN FACT</span>`;
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
    fixtureBanner.title = "当前为内部体验数据，不会保存、生成或发布。";
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
    const project = fixture.project;
    return `
      <section class="v2-hero" aria-labelledby="v2-hero-title">
        <div class="v2-hero-copy">
          <span class="v2-overline">AI Cinematic Studio</span>
          <h2 id="v2-hero-title">从一个想法，创造完整影片</h2>
          <p>AI 导演、角色、镜头、画面、声音和剪辑，在一个工作台里完成。</p>
          <div class="v2-hero-actions">
            <a class="button button-primary" href="#/creator/ai-director">开始创作</a>
            <a class="button button-cinema" href="#/creator/ai-director">AI导演 <span aria-hidden="true">↗</span></a>
          </div>
          <div class="v2-journey-line" aria-label="完整创作流程"><span>创意</span><i></i><span>故事</span><i></i><span>角色</span><i></i><span>镜头</span><i></i><span>影片</span></div>
        </div>
        <div class="v2-hero-visual">
          <img src="${escapeHtml(fixture.character.referenceImage)}" alt="晚灯角色视觉">
          <div class="v2-hero-visual-caption"><span>正在创作</span><strong>${displayProjectTitle}</strong><small>${project.durationSeconds} 秒 · 情绪短片 · 竖屏</small></div>
        </div>
      </section>

      <section class="v2-section" aria-labelledby="capability-title">
        <div class="v2-section-heading"><div><span>创作能力</span><h2 id="capability-title">一站式影视创作工作台</h2></div><p>从灵感到候选影片，始终围绕作品推进。</p></div>
        <div class="capability-showcase">
          <a class="capability-card capability-card-featured" href="#/creator/ai-director"><span class="capability-icon">✦</span><div><small>创意入口</small><h3>AI导演</h3><p>把创意整理为故事与制作方案</p></div><b>进入</b></a>
          <a class="capability-card" href="#${projectBase}/pipeline"><span class="capability-icon">◫</span><div><small>核心空间</small><h3>项目工作室</h3><p>管理完整影视生产流程</p></div><b>进入</b></a>
          <a class="capability-card" href="#/creator/assets"><span class="capability-icon">◇</span><div><small>视觉资产</small><h3>资产中心</h3><p>统一管理角色、场景、画面和声音</p></div><b>进入</b></a>
          <a class="capability-card is-upcoming" href="#/creator/creation"><span class="capability-icon">⌁</span><div><small>即将上线</small><h3>智能生成</h3><p>未来接入图像、视频和声音生成能力</p></div><b>了解</b></a>
        </div>
      </section>

      <section class="v2-section recent-project-section" aria-labelledby="recent-title">
        <div class="v2-section-heading"><div><span>最近项目</span><h2 id="recent-title">继续你的创作</h2></div><a class="text-link" href="#/creator/projects">查看全部项目 →</a></div>
        <article class="project-cinema-card">
          <div class="project-cinema-poster"><img src="${escapeHtml(fixture.character.referenceImage)}" alt="晚灯第 1 集项目封面"><span>可预览</span></div>
          <div class="project-cinema-copy"><span>情绪短片 · 竖屏 9:16</span><h3>${displayProjectTitle}</h3><p>${escapeHtml(project.description)}</p><div class="project-cinema-meta"><span><small>时长</small><strong>45 秒</strong></span><span><small>当前阶段</small><strong>可预览</strong></span><span><small>版本</small><strong>候选 v1</strong></span></div><a class="button button-secondary" href="#${projectBase}/pipeline">继续制作</a></div>
          <div class="project-cinema-frames">${fixture.assets.slice(1, 4).map((asset) => `<img src="${escapeHtml(asset.src)}" alt="${escapeHtml(asset.label)}">`).join("")}</div>
        </article>
      </section>

      <section class="v2-section creation-journey-section" aria-labelledby="journey-title">
        <div class="v2-section-heading"><div><span>创作流程</span><h2 id="journey-title">让每一步都看得见</h2></div><p>沿着影片生产脉络，自然进入下一阶段。</p></div>
        <ol class="creation-journey">${["故事", "角色", "分镜", "画面", "声音", "剪辑", "作品"].map((label, index) => `<li><span>${String(index + 1).padStart(2, "0")}</span><strong>${label}</strong>${index < 6 ? '<i aria-hidden="true">→</i>' : ""}</li>`).join("")}</ol>
      </section>
      ${fixtureNotice()}
    `;
  }

  function renderProjects() {
    const localDrafts = state.localProjectDrafts.length
      ? state.localProjectDrafts.map((draft) => `
          <article class="project-row local-draft-row">
            <span class="project-thumbnail local-thumbnail" aria-hidden="true">草</span>
            <div class="project-row-copy"><span class="badge badge-fixture"><i></i>临时草稿</span><h3>${escapeHtml(draft.title)}</h3><p>${escapeHtml(draft.format)} · 仅当前会话有效</p></div>
            <button class="button button-secondary" type="button" disabled>不会保存</button>
          </article>
        `).join("")
      : renderEmptyState({
          icon: "+",
          title: "还没有新的项目草稿",
          description: "你可以创建一个仅在当前会话有效的临时项目草稿，它不会保存到系统。",
          action: '<button class="button button-secondary" type="button" data-action="open-project-dialog">创建项目草稿</button>'
        });

    return `
      ${renderPageHeader({
        eyebrow: "项目中心",
        title: "项目",
        description: "管理影片项目，并从最近的创作阶段继续工作。",
        status: "fixture",
        meta: '<button class="button button-secondary" type="button" data-action="open-project-dialog">＋ 创建项目草稿</button>'
      })}
      <section class="card project-list-panel v2-project-list">
        <div class="list-section-heading"><div><span class="section-kicker">最近项目</span><h3>继续制作</h3></div><span>1 个项目</span></div>
        <article class="project-row fixture-project-row">
          <img class="project-thumbnail" src="${escapeHtml(fixture.character.referenceImage)}" alt="晚灯项目封面">
          <div class="project-row-copy">
            <div class="status-cluster">${statusBadge("fixture")}${governanceBadge("LOCAL REVIEW CANDIDATE", "candidate")}</div>
            <h3>${displayProjectTitle}</h3>
            <p>45 秒情绪短片 · ${fixture.shots.length} 个镜头 · 当前阶段：可预览</p>
          </div>
          <a class="button button-secondary" href="#${projectBase}/pipeline">继续制作</a>
        </article>
        <div class="list-section-heading local-heading"><div><span class="section-kicker">临时草稿</span><h3>当前会话</h3></div><span>${state.localProjectDrafts.length} 项</span></div>
        <div class="local-drafts">${localDrafts}</div>
      </section>
      ${fixtureNotice()}
    `;
  }

  function pipelineStatus(value) {
    const normalized = value.toLowerCase();
    let tone = "progress";
    if (normalized.startsWith("blocked")) tone = "blocked";
    if (normalized.startsWith("planned")) tone = "planned";
    if (normalized.startsWith("complete")) tone = "complete";
    if (normalized.startsWith("not started")) tone = "idle";
    const label = normalized.startsWith("blocked") ? "阻塞" : normalized.startsWith("planned") ? "即将上线" : normalized.startsWith("complete") ? "完成" : normalized.startsWith("not started") ? "准备中" : "制作中";
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
              <p>使用项目：${displayProjectTitle}</p>
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
        title: "生成记录 · 即将上线",
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
        ${[["角色","◉"],["场景","▱"],["图片","◇"],["视频","▶"],["音频","♪"],["模板","▦"]].map(([label, icon], index) => `<button type="button" class="asset-category ${index === 0 ? "is-fixture" : ""}" disabled><i aria-hidden="true">${icon}</i><strong>${label}</strong><small>${index === 0 ? "1 项" : index < 4 ? "浏览" : "即将上线"}</small></button>`).join("")}
      </section>
      <section class="asset-feature-card">
        <div class="asset-feature-visual"><img src="${escapeHtml(fixture.character.referenceImage)}" alt="晚灯角色资产"><span>角色资产</span></div>
        <div class="asset-feature-copy"><span class="section-kicker">核心角色</span><h2>晚灯 <small>WANLIGHT</small></h2><p>陪伴型夜灯角色，以深蓝兜帽、琥珀灯面和月牙别针建立稳定视觉识别。</p><div class="asset-feature-meta"><span><small>角色</small><strong>晚灯</strong></span><span><small>版本</small><strong>v0.1</strong></span><span><small>使用项目</small><strong>${displayProjectTitle}</strong></span><span><small>权利状态</small><strong>待确认</strong></span></div><div class="button-row"><a class="button button-secondary" href="#${projectBase}/character">查看角色</a><button class="button button-text" type="button" data-action="select-asset-tab" data-tab="versions">查看版本</button></div></div>
      </section>
      <section class="card asset-detail-shell v2-asset-detail">
        <div class="tabs" role="tablist" aria-label="资产详情">
          ${tabs.map(([key, label]) => `<button class="tab ${state.assetTab === key ? "is-active" : ""}" id="asset-tab-${key}" type="button" role="tab" aria-selected="${state.assetTab === key}" aria-controls="asset-detail-panel" tabindex="${state.assetTab === key ? "0" : "-1"}" data-action="select-asset-tab" data-tab="${key}">${escapeHtml(label)}${key === "history" ? '<span class="badge badge-planned"><i></i>即将上线</span>' : ""}</button>`).join("")}
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
            <div class="module-card-heading"><span class="module-status">即将上线</span><span>${String(index + 1).padStart(2, "0")}</span></div>
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
          <div class="generation-input-preview" aria-label="未来输入区域预览"><label for="generation-preview-input">描述你想创建的画面……</label><textarea id="generation-preview-input" disabled placeholder="描述画面、氛围与镜头意图"></textarea><button class="button button-primary" type="button" disabled>即将上线</button></div>
        </section>
        <section class="creation-preview-grid creation-tool-grid" aria-label="生成能力预览">
          ${modules.map(([icon, title, description]) => `<article class="creation-preview-card"><span class="creation-preview-icon" aria-hidden="true">${icon}</span><span class="preview-status">即将上线</span><h3>${title}</h3><p>${description}</p><button class="button button-text" type="button" disabled>暂不可用</button></article>`).join("")}
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
          ${templates.map(([title, purpose, meta, image], index) => `<article class="template-preview-card"><div class="template-preview-cover template-cover-${index + 1}">${image ? `<img src="${escapeHtml(image)}" alt="${escapeHtml(title)}视觉示例">` : ""}<span>即将上线</span></div><div><h3>${title}</h3><p>${purpose}</p><small>${meta}</small></div></article>`).join("")}
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
        <section class="ip-preview-modules" aria-label="IP 管理结构预览">${modules.map(([title, value, description]) => `<article><span>${title}</span><strong>${value}</strong><p>${description}</p><small>即将上线</small></article>`).join("")}</section>
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
        <section class="memory-preview-shell"><div class="memory-preview-intro"><span aria-hidden="true">◌</span><div><h2>让作品记住已经确认的选择</h2><p>当前不会记录或学习用户行为；这里只展示未来的信息组织方式。</p></div></div><div class="memory-preview-grid">${memories.map(([title, description], index) => `<article><span>${String(index + 1).padStart(2, "0")}</span><h3>${title}</h3><p>${description}</p><small>即将上线</small></article>`).join("")}</div></section>
        ${fixtureNotice()}
      `;
    }

    if (route.key === "workflow-presets") {
      const stages = ["创意", "角色", "分镜", "画面", "声音", "预览"];
      return `
        ${commonHeader("工作流预设", "预览不同影片类型的创作路径，不执行任务或自动推进阶段。", "电影生产路径预览")}
        <section class="workflow-preview-shell"><ol class="workflow-preview-flow">${stages.map((stage, index) => `<li><span>${String(index + 1).padStart(2, "0")}</span><strong>${stage}</strong>${index < stages.length - 1 ? '<i aria-hidden="true">→</i>' : ""}</li>`).join("")}</ol><div class="workflow-preset-grid"><article><span>情绪短片流程</span><h3>从情绪主题到候选预览</h3><p>适合角色陪伴、内心独白与短篇情绪表达。</p><button class="button button-secondary" type="button" disabled>即将上线</button></article><article><span>角色故事流程</span><h3>围绕角色建立连续叙事</h3><p>适合角色设定、场景关系与分镜连续性规划。</p><button class="button button-secondary" type="button" disabled>即将上线</button></article></div></section>
        ${fixtureNotice()}
      `;
    }

    const charts = ["作品表现趋势", "制作效率", "内容表现"];
    return `
      ${commonHeader("数据分析", "当作品产生真实运营数据后，可在这里查看表现趋势。", "数据产品预览")}
      <section class="analytics-empty-grid" aria-label="数据分析空状态">${charts.map((title, index) => `<article><div class="analytics-empty-heading"><h3>${title}</h3><span>即将上线</span></div><div class="analytics-empty-chart chart-${index + 1}" aria-hidden="true"><i></i><i></i><i></i><i></i></div><strong>暂无真实数据</strong><p>当前没有可展示的真实运营数据。</p></article>`).join("")}</section>
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
    const statusLabel = state.aiDirectorConfirmed ? "已确认（当前会话）" : "待确认";
    const statusTone = state.aiDirectorConfirmed ? "success" : "warning";
    const storyboardDuration = storyboard.reduce((sum, shot) => sum + Number(shot.durationSec || 0), 0);
    return `
      <div class="director-result" data-ai-director-state="${state.aiDirectorConfirmed ? "confirmed" : "result"}">
        <div class="director-result-banner" role="status">
          <span aria-hidden="true">✦</span>
          <div><strong>候选导演方案已准备</strong><p>版本 ${state.aiDirectorPlanVersion} · ${statusLabel}</p></div>
          ${localizedStatusBadge(statusLabel, statusTone)}
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
    const canCreateDraft = Boolean(production && state.aiDirectorConfirmed && state.aiDirectorPhase !== "generating");
    const listValue = (items, fallback) => Array.isArray(items) && items.length ? items.map(escapeHtml).join("、") : fallback;
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
        <div class="director-plan-action"><button class="button button-primary" type="button" data-action="create-ai-director-project-draft" ${canCreateDraft ? "" : "disabled"}>创建项目草稿</button><p>${state.aiDirectorConfirmed ? "仅当前会话有效，不会保存到系统。" : "确认导演方案后才可创建当前会话草稿。"}</p></div>
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

  function renderProjectDraftHandoff(route) {
    const draft = route.draft;
    return `
      ${renderPageHeader({
        eyebrow: "项目草稿交接",
        title: draft.title,
        description: "AI导演已创建一个仅在当前会话中有效的临时项目草稿。",
        status: "fixture",
        meta: localizedStatusBadge("仅当前会话", "neutral")
      })}
      ${demoNotice("该 local-* 引用仅用于当前页面导航；刷新页面或重置会话后失效，不会保存到系统。")}
      <section class="card draft-handoff-card" data-ai-director-state="handoff">
        <div class="draft-handoff-mark" aria-hidden="true">↗</div>
        <div class="draft-handoff-copy">
          <span class="section-kicker">项目草稿</span>
          <h3>项目草稿交接已建立</h3>
        <p>已在当前会话建立临时草稿。它不会保存到系统，也不会创建真实项目、故事、角色或制作数据。</p>
        </div>
        <dl class="draft-handoff-meta">
          <div><dt>本地草稿编号</dt><dd><code>${escapeHtml(draft.projectRef)}</code></dd></div>
          <div><dt>来源</dt><dd>AI导演</dd></div>
          <div><dt>保存状态</dt><dd>仅当前会话 · 不会保存</dd></div>
          <div><dt>数据性质</dt><dd>非真实业务数据</dd></div>
        </dl>
        <div class="draft-handoff-actions"><a class="button button-secondary" href="#/creator/ai-director">返回AI导演</a><a class="button button-text" href="#${projectBase}/pipeline">打开晚灯项目</a></div>
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
        meta: governanceBadge("Rights HOLD", "hold")
      })}
      <section class="character-grid v2-character-grid">
        <article class="reference-card">
          <div class="reference-image"><img src="${escapeHtml(fixture.character.referenceImage)}" alt="晚灯角色设定表"></div>
          <div class="reference-copy">
            <span class="section-kicker">角色身份</span>
            <div class="status-cluster">${statusBadge("fixture")}${governanceBadge("Rights HOLD", "hold")}</div>
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
          <section><span class="inspector-label">权利状态</span>${governanceBadge("Rights HOLD", "hold")}<p>正式导出前需要完成人工确认。</p></section>
          <section><span class="inspector-label">反馈</span><p>评论功能即将上线。当前不会保存反馈。</p></section>
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
        <span class="sr-only">EXPORT ENGINE NOT IMPLEMENTED · RENDER NOT AUTHORIZED · DOWNLOAD DISABLED</span>
      </section>
    `;
  }

  function renderPlaceholder(route) {
    const isDisabled = route.status === "disabled";
    const parentRoute = route.context === "creation" ? "/creator/creation" : route.context === "project" ? `${projectBase}/pipeline` : "/creator/dashboard";
    const statusText = isDisabled ? "暂不可用" : "即将上线";
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
      ${route.context === "project" ? fixtureNotice("项目占位页不创建、保存或推进 Project / Production / IP / Audio / Timeline 事实。") : ""}
      <section class="card placeholder-card">
        ${renderEmptyState({
          icon: isDisabled ? "×" : "·",
          title: `${title} · ${statusText}`,
          description,
          action: `<a class="button button-secondary" href="#${parentRoute}">${route.context === "creation" ? "返回创作中心" : route.context === "project" ? "返回生产流程" : "返回总览"}</a>`
        })}
        <div class="placeholder-boundaries">
          <span><small>当前状态</small><strong>${isDisabled ? "暂不可用" : "即将上线"}</strong></span>
          <span><small>功能内容</small><strong>暂无内容</strong></span>
          <span><small>开放时间</small><strong>敬请期待</strong></span>
          <span class="sr-only">${featureStates[route.status].label} · NONE / FIXTURE LABEL ONLY · NOT IMPLEMENTED</span>
        </div>
      </section>
    `;
  }

  function resolveRoute(path) {
    const normalized = normalizePath(path);
    if (normalized === `/creator/projects/${projectRef}`) {
      return { redirect: `${projectBase}/pipeline` };
    }

    const localProjectMatch = normalized.match(/^\/creator\/projects\/(local-[a-z0-9-]+)$/);
    if (localProjectMatch) {
      const draft = state.localProjectDrafts.find((item) => item.projectRef === localProjectMatch[1]);
      if (draft) {
        return {
          type: "project-draft-handoff",
          key: "project-draft-handoff",
          path: normalized,
          label: "项目草稿交接",
          english: "Project Draft Mock Handoff",
          status: "fixture",
          breadcrumb: "AI导演 / 本地项目草稿",
          draft
        };
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

    if (normalized === "/creator/account") {
      return { type: "placeholder", key: "account", path: normalized, label: "账户", english: "Account", status: "planned", breadcrumb: "创作空间 / 账户", eyebrow: "个人空间", description: "创作者账户功能即将上线。" };
    }

    const creation = creationModules.find((module) => module.path === normalized);
    if (creation) {
      return { ...creation, type: "creation-preview", status: "planned", breadcrumb: `创作中心 / ${creation.label}`, eyebrow: "创作工具 · 即将上线", context: "creation" };
    }

    if (normalized.startsWith(`${projectBase}/`)) {
      const projectPage = projectPages.find((page) => page.path === normalized);
      if (!projectPage) return null;
      const route = { ...projectPage, breadcrumb: `${displayProjectTitle} / ${projectPage.label}`, context: "project" };
      if (projectPage.key === "pipeline") return { ...route, type: "pipeline" };
      if (projectPage.key === "character") return { ...route, type: "character" };
      if (projectPage.key === "storyboard") return { ...route, type: "storyboard" };
      if (projectPage.key === "preview") return { ...route, type: "preview" };
      if (projectPage.key === "export") return { ...route, type: "export" };

      const descriptions = {
        story: "故事意图与版本参考的未来页面；当前不生成、改写或保存故事。",
        "ip-bible": "单项目世界观、角色规则与时间线的未来参考页面；当前功能即将上线。",
        scene: "项目场景规划的未来入口；当前不会创建场景或生成画面。",
        audio: "声音意图、来源与权利确认的未来入口；当前候选影片为静音版本。",
        timeline: "影片节奏与镜头组织的未来入口；当前功能即将上线。",
        approval: "该页面只展示人工确认要求；界面或技术检查不会自动完成批准。",
        settings: "未来成员、权限、工作流配置与归档的占位；当前不实现任何设置或持久化。"
      };
      return { ...route, type: "placeholder", eyebrow: `项目工作室 · ${projectPage.label}`, description: descriptions[projectPage.key] };
    }

    return null;
  }

  function renderNotFound(path) {
    return `
      ${renderPageHeader({ eyebrow: "页面未找到", title: "找不到这个页面", description: "该页面地址不存在或尚未开放。", status: "disabled" })}
      <section class="card placeholder-card">
        ${renderEmptyState({ icon: "?", title: "页面不可用", description: `当前地址 ${path} 暂时无法访问。`, action: '<a class="button button-secondary" href="#/creator/dashboard">返回首页</a>' })}
        <span class="sr-only">ROUTE NOT FOUND · NOT A DOMAIN FACT</span>
      </section>
    `;
  }

  function renderContextNav(route) {
    const items = route.context === "project" ? projectPages : route.context === "creation" ? creationModules.map((module) => ({ ...module, status: "planned" })) : [];
    if (!items.length) {
      contextNavigation.hidden = true;
      contextNavigation.innerHTML = "";
      workbench.classList.remove("has-context-nav");
      return;
    }

    const title = route.context === "project" ? "项目工作室" : "创作工具";
    const subtitle = route.context === "project" ? displayProjectTitle : "即将上线";
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
    return Boolean(route && (route.context === "project" || ["assets", "character", "storyboard", "preview"].includes(route.type)));
  }

  function renderInspector(route) {
    inspectorTitle.textContent = route ? route.label || route.english || "当前页面" : "未知路由";
    const shot = selectedShot();
    const base = '<span class="sr-only">FIXTURE ONLY · NOT A DOMAIN FACT · V5 NOT CONNECTED · SESSION ONLY</span>';
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
    } else if (route && route.type === "project-draft-handoff") {
      detail = `<section class="inspector-section"><span class="inspector-label">项目草稿</span><strong>${escapeHtml(route.draft.title)}</strong><p>仅当前会话有效 · 不会保存</p></section>`;
    } else if (route && (route.type === "character" || route.type === "assets")) {
      detail = `<section class="inspector-section"><span class="inspector-label">权利状态</span>${governanceBadge("HOLD", "hold")}<p>正式使用前需要完成人工确认。</p></section>`;
    } else {
      detail = `<section class="inspector-section"><span class="inspector-label">当前项目</span><strong>${displayProjectTitle}</strong><p>情绪短片 · 45 秒 · 竖屏 9:16</p></section>`;
    }
    inspectorContent.innerHTML = `${base}${detail}`;
  }

  function aiDirectorStickyConfig() {
    if (state.aiDirectorPhase === "generating") {
      return { label: "正在整理导演方案…", disabled: true, note: "不会显示虚假进度" };
    }
    if (state.aiDirectorConfirmed) {
      return { label: "创建项目草稿", action: "create-ai-director-project-draft", note: "仅当前会话有效，不会保存到系统" };
    }
    if (state.aiDirectorPlan) {
      return { label: "确认导演方案", action: "confirm-ai-director-plan", note: "人工确认后才能创建项目草稿" };
    }
    if (state.aiDirectorPhase === "error") {
      return { label: "重新生成", action: "regenerate-ai-director", note: "创意输入仍保留在当前页面" };
    }
    return { label: "生成创意方案", action: "run-ai-director", note: "整理故事、镜头与视觉方向" };
  }

  function stickyConfig(route) {
    if (!route) return { label: "返回总览", target: defaultRoute, note: "未知路由 · 未创建任何事实" };
    const map = {
      dashboard: { label: "开始创作", target: "/creator/ai-director", note: "从一个想法开始新的影片方案" },
      projects: { label: "创建项目草稿", action: "open-project-dialog", note: "仅当前会话有效 · 不会保存到系统" },
      assets: { label: "查看晚灯角色", target: `${projectBase}/character`, note: "角色、场景与关键画面统一管理" },
      creation: { label: "返回首页", target: defaultRoute, note: "六项智能工具正在准备中" },
      "ai-director": aiDirectorStickyConfig(),
      "project-draft-handoff": { label: "打开晚灯项目", target: `${projectBase}/pipeline`, note: "项目草稿已建立 · 仅当前会话有效" },
      pipeline: { label: "进入角色", target: `${projectBase}/character`, note: "项目制作流程总览 · 状态由创作者确认" },
      character: { label: "查看分镜", target: `${projectBase}/storyboard`, note: "晚灯角色 · 权利状态待确认" },
      storyboard: { label: "查看影片预览", target: `${projectBase}/preview`, note: "六镜头分镜墙 · 继续审看影片节奏" },
      preview: { label: "返回项目工作室", target: `${projectBase}/pipeline`, note: "候选预览 · 尚未正式导出" },
      export: { label: "暂不可导出", disabled: true, note: "权利确认与导出能力尚未完成" }
    };
    if (map[route.type]) return map[route.type];
    if (route.context === "creation") return { label: "返回创作中心", target: "/creator/creation", note: "功能即将上线" };
    if (route.context === "project") return { label: "返回项目工作室", target: `${projectBase}/pipeline`, note: "页面状态不会自动改变项目进度" };
    return { label: "返回首页", target: defaultRoute, note: "功能即将上线" };
  }

  function shouldRenderStickyBar(route) {
    if (!route) return false;
    if (["dashboard", "ai-director", "pipeline", "storyboard", "preview", "export"].includes(route.type)) return true;
    return route.type === "placeholder" && route.key === "approval";
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
      ? `<button class="button button-primary" type="button" disabled data-capability="export">${escapeHtml(config.label)}</button>`
      : config.action
        ? `<button class="button button-primary" type="button" data-action="${escapeHtml(config.action)}">${escapeHtml(config.label)}</button>`
        : `<a class="button button-primary" href="#${escapeHtml(config.target)}">${escapeHtml(config.label)}</a>`;
    const showInspectorControl = routeSupportsInspector(route);
    stickyActionBar.innerHTML = `
      <div class="sticky-status"><div><strong>${escapeHtml(route && route.label ? route.label : "当前页面")}</strong><p>${escapeHtml(config.note)}</p><span class="sr-only">FIXTURE ONLY · NOT SAVED</span></div></div>
      <div class="sticky-actions">${showInspectorControl ? '<button class="button button-secondary inspector-toggle-label" type="button" data-action="toggle-inspector">展开详情</button>' : ""}${primary}</div>
    `;
  }

  function updatePrimaryNav(path) {
    document.querySelectorAll(".primary-nav [data-route]").forEach((link) => {
      const route = link.getAttribute("data-route");
      const active = route === "/creator/projects"
        ? path === route || path.startsWith("/creator/projects/")
        : route === "/creator/creation"
          ? path === route || path.startsWith("/creator/creation/")
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
      state.inspectorOpen = !compactInspectorQuery.matches && resolved.context === "project";
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
      pipeline: renderPipeline,
      assets: renderAssets,
      creation: renderCreationCenter,
      "creation-preview": () => renderCreationPreview(resolved),
      works: renderWorks,
      "ai-director": renderAiDirector,
      "project-draft-handoff": () => renderProjectDraftHandoff(resolved),
      character: renderCharacter,
      storyboard: renderStoryboard,
      preview: renderPreview,
      export: renderExport,
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
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 3200);
  }

  function openProjectDialog(trigger) {
    dialogReturnFocus = trigger || document.activeElement;
    projectDialog.showModal();
    window.requestAnimationFrame(() => projectForm.elements.title.focus());
  }

  function closeProjectDialog() {
    if (projectDialog.open) projectDialog.close();
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
      const response = await fetch(aiDirectorEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ brief }),
        signal: abortController.signal
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok || !isCandidatePlan(payload.plan)) throw new Error("candidate-plan-unavailable");
      state.aiDirectorPlan = payload.plan;
      state.aiDirectorPlanVersion += 1;
      state.aiDirectorConfirmed = false;
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

  function confirmAiDirectorPlan() {
    if (!state.aiDirectorPlan || state.aiDirectorPhase === "generating") return;
    state.aiDirectorConfirmed = true;
    state.aiDirectorPhase = "confirmed";
    state.aiDirectorError = null;
    renderRoute("/creator/ai-director");
    showToast("导演方案已确认 · 仅当前会话有效");
  }

  function buildAiDirectorProjectDraftInput(projectRefValue) {
    if (!state.aiDirectorPlan || !state.aiDirectorConfirmed) return null;
    const plan = state.aiDirectorPlan;
    return {
      schemaVersion: "creator.project-draft-input.v1",
      localKey: projectRefValue,
      projectRef: projectRefValue,
      sourcePlanRef: `local-ai-director-plan-${state.aiDirectorPlanVersion}`,
      sourcePlanSchemaVersion: plan.schemaVersion,
      sourcePlanVersion: state.aiDirectorPlanVersion,
      sourcePlan: plan,
      persistence: "session-only",
      domainFact: false,
      story: {
        creativeInterpretation: plan.creativeInterpretation,
        direction: plan.storyDirection,
        script: plan.scriptDraft
      },
      characters: plan.productionPlan.characters,
      scenes: plan.productionPlan.scenes,
      storyboard: plan.storyboardPlan,
      visualStyle: plan.visualStyle,
      productionPlan: plan.productionPlan
    };
  }

  function createAiDirectorProjectDraft() {
    const projectRefValue = "local-project-wanlight-001";
    const draftInput = buildAiDirectorProjectDraftInput(projectRefValue);
    if (!draftInput) return;
    const draft = {
      ...draftInput,
      title: `${state.aiDirectorBrief.topic} · 项目草稿`,
      format: `${state.aiDirectorBrief.duration} · ${state.aiDirectorBrief.platform}`,
      source: "AI Director candidate creative plan"
    };
    const existingIndex = state.localProjectDrafts.findIndex((item) => item.projectRef === projectRefValue);
    if (existingIndex >= 0) state.localProjectDrafts.splice(existingIndex, 1, draft);
    else state.localProjectDrafts.unshift(draft);
    state.aiDirectorProjectDraft = draft;
    state.aiDirectorPhase = "handoff";
    navigate(`/creator/projects/${draft.projectRef}`);
    showToast("项目草稿已建立 · 仅当前会话有效");
  }

  function resetFixture() {
    state.assetTab = "basic";
    state.assetFilter = "all";
    state.selectedShotKey = fixture.shots[0].localKey;
    state.selectedPipelineKey = (fixture.pipeline.find((stage) => stage.label === "Preview") || fixture.pipeline[1]).localKey;
    state.localProjectDrafts = [];
    state.localDraftCounter = 0;
    state.aiDirectorPhase = "input";
    state.aiDirectorBrief = { ...fixture.aiDirector.briefDefaults };
    state.aiDirectorPlan = null;
    state.aiDirectorPlanVersion = 0;
    state.aiDirectorConfirmed = false;
    state.aiDirectorError = null;
    state.aiDirectorProjectDraft = null;
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
    if (action === "close-project-dialog") closeProjectDialog();
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
    if (action === "create-ai-director-project-draft") createAiDirectorProjectDraft();
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
    if (event.target.id !== "ai-director-form") return;
    event.preventDefault();
    runAiDirector();
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
    const formData = new FormData(projectForm);
    const title = String(formData.get("title") || "").trim();
    if (!title) return;
    state.localDraftCounter += 1;
    state.localProjectDrafts.unshift({
      localKey: `local-project-${state.localDraftCounter}`,
      title,
      format: String(formData.get("format") || "竖屏短视频 · 9:16")
    });
    projectForm.reset();
    projectDialog.close();
    if (state.activePath !== "/creator/projects") navigate("/creator/projects");
    else renderRoute(state.activePath);
    showToast("临时草稿已加入当前会话 · 不会保存到系统");
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
