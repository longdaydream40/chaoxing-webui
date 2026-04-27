const API_BASE =
  (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) ||
  window.location.origin;
const TOKEN_KEY = "lycoris_app_token";
const USER_KEY = "lycoris_app_user";
const COVER_KEY = "lycoris_cover_burn_entered";

const nodes = {
  coverGate: document.getElementById("coverGate"),
  coverPortrait: document.getElementById("coverPortrait"),
  burnCanvas: document.getElementById("burnCanvas"),
  appShell: document.querySelector("main.shell"),
  authStateText: document.getElementById("authStateText"),
  logoutBtn: document.getElementById("logoutBtn"),
  announcementList: document.getElementById("announcementList"),
  taskInviteCode: document.getElementById("taskInviteCode"),
  checkInviteBtn: document.getElementById("checkInviteBtn"),
  inviteStateText: document.getElementById("inviteStateText"),
  username: document.getElementById("username"),
  password: document.getElementById("password"),
  speed: document.getElementById("speed"),
  jobs: document.getElementById("jobs"),
  notopenAction: document.getElementById("notopen_action"),
  loadCoursesBtn: document.getElementById("loadCoursesBtn"),
  startBtn: document.getElementById("startBtn"),
  courseList: document.getElementById("courseList"),
  taskId: document.getElementById("taskId"),
  taskStatus: document.getElementById("taskStatus"),
  courseProgress: document.getElementById("courseProgress"),
  moduleProgress: document.getElementById("moduleProgress"),
  currentTask: document.getElementById("currentTask"),
  playbackProgress: document.getElementById("playbackProgress"),
  pauseTaskBtn: document.getElementById("pauseTaskBtn"),
  resumeTaskBtn: document.getElementById("resumeTaskBtn"),
  cancelTaskBtn: document.getElementById("cancelTaskBtn"),
  activePlaybackList: document.getElementById("activePlaybackList"),
  logArea: document.getElementById("logArea"),
  adminPanel: document.getElementById("adminPanel"),
  adminRefreshBtn: document.getElementById("adminRefreshBtn"),
  adminStateText: document.getElementById("adminStateText"),
  noticeTitle: document.getElementById("noticeTitle"),
  noticeContent: document.getElementById("noticeContent"),
  publishNoticeBtn: document.getElementById("publishNoticeBtn"),
  aiConfigEnabled: document.getElementById("aiConfigEnabled"),
  aiEndpoint: document.getElementById("aiEndpoint"),
  aiModel: document.getElementById("aiModel"),
  aiApiKey: document.getElementById("aiApiKey"),
  aiSubmitAnswers: document.getElementById("aiSubmitAnswers"),
  aiHttpProxy: document.getElementById("aiHttpProxy"),
  aiMinIntervalSeconds: document.getElementById("aiMinIntervalSeconds"),
  aiDelay: document.getElementById("aiDelay"),
  aiCoverRate: document.getElementById("aiCoverRate"),
  aiTrueList: document.getElementById("aiTrueList"),
  aiFalseList: document.getElementById("aiFalseList"),
  saveAiConfigBtn: document.getElementById("saveAiConfigBtn"),
  testAiConfigBtn: document.getElementById("testAiConfigBtn"),
  aiConfigStateText: document.getElementById("aiConfigStateText"),
  inviteNote: document.getElementById("inviteNote"),
  inviteMaxUses: document.getElementById("inviteMaxUses"),
  inviteExpireHours: document.getElementById("inviteExpireHours"),
  generateInviteBtn: document.getElementById("generateInviteBtn"),
  inviteList: document.getElementById("inviteList"),
  taskList: document.getElementById("taskList"),
  inspectTaskId: document.getElementById("inspectTaskId"),
  inspectTaskBtn: document.getElementById("inspectTaskBtn"),
  adminLogArea: document.getElementById("adminLogArea"),
};

let currentUser = null;
let pollingTimer = null;
let currentTaskId = "";
const COVER_IMAGES = ["./assets/cover-chisato.png", "./assets/cover-chisato-alt.png"];

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function getStoredUser() {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function setStoredUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  currentUser = user;
}

function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  sessionStorage.removeItem(COVER_KEY);
}

function appendLog(line) {
  const previous = nodes.logArea.textContent ? `${nodes.logArea.textContent}\n` : "";
  nodes.logArea.textContent = `${previous}${line}`;
  nodes.logArea.scrollTop = nodes.logArea.scrollHeight;
}

function setEmpty(container, message) {
  container.replaceChildren();
  const p = document.createElement("p");
  p.textContent = message;
  container.appendChild(p);
}

function safeText(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function makeCourseItem(children) {
  const item = document.createElement("div");
  item.className = "course-item";
  const wrap = document.createElement("span");
  children.forEach((child) => wrap.appendChild(child));
  item.appendChild(wrap);
  return item;
}

function makeLine(text) {
  const line = document.createElement("span");
  line.textContent = text;
  return line;
}

function makeBreak() {
  return document.createElement("br");
}

function makeSmall(text) {
  const small = document.createElement("small");
  small.textContent = text;
  return small;
}

function makeStrong(text) {
  const strong = document.createElement("strong");
  strong.textContent = text;
  return strong;
}

function chooseCoverImage() {
  if (!nodes.coverPortrait) return;
  const index = Math.floor(Math.random() * COVER_IMAGES.length);
  nodes.coverPortrait.src = COVER_IMAGES[index];
}

function ensureEntryGate() {
  const entered = sessionStorage.getItem(COVER_KEY) === "1";
  if (!entered) {
    chooseCoverImage();
    if (nodes.coverGate) nodes.coverGate.hidden = false;
    if (nodes.appShell) nodes.appShell.hidden = true;
    return false;
  }
  if (!getToken()) {
    window.location.href = "/login/";
    return false;
  }
  if (nodes.coverGate) nodes.coverGate.hidden = true;
  if (nodes.appShell) nodes.appShell.hidden = false;
  return true;
}

async function requestJson(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(data.error || "request failed");
  return data;
}

async function postJson(path, body) {
  return requestJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function loadCurrentUser() {
  const data = await requestJson("/api/auth/me", { method: "GET" });
  setStoredUser(data.user);
  return data.user;
}

function renderCourses(courses) {
  nodes.courseList.replaceChildren();
  if (!courses.length) {
    setEmpty(nodes.courseList, "暂无课程，请先获取课程列表。");
    return;
  }

  courses.forEach((course) => {
    const item = document.createElement("label");
    item.className = "course-item";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = safeText(course.courseId, "");

    const span = document.createElement("span");
    span.appendChild(document.createTextNode(safeText(course.title, "未命名课程")));
    span.appendChild(document.createTextNode(" "));
    span.appendChild(makeSmall(`ID: ${safeText(course.courseId)}`));

    item.append(input, span);
    nodes.courseList.appendChild(item);
  });
}

function selectedCourseIds() {
  return [...nodes.courseList.querySelectorAll("input[type='checkbox']:checked")].map((el) => el.value);
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hrs = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hrs > 0) return `${hrs}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function playbackItems(taskData) {
  const runtime = taskData.runtime || null;
  const fromRuntime = runtime && runtime.current_playbacks;
  if (fromRuntime && typeof fromRuntime === "object") return Object.values(fromRuntime);
  const single = taskData.current_playback || (runtime && runtime.current_playback);
  return single ? [single] : [];
}

function renderPlaybackList(items) {
  nodes.activePlaybackList.replaceChildren();
  const visibleItems = items.filter((item) => !["completed", "failed", "cancelled"].includes(item.status));
  if (!visibleItems.length) {
    const p = document.createElement("p");
    p.className = "hint-text";
    p.textContent = "暂无并行任务。";
    nodes.activePlaybackList.appendChild(p);
    return;
  }

  visibleItems.forEach((item) => {
    const current = Number(item.play_time || 0);
    const duration = Number(item.duration || 0);
    const percent = Number.isFinite(Number(item.percent))
      ? Math.max(0, Math.min(100, Math.round(Number(item.percent))))
      : duration > 0
        ? Math.min(100, Math.round((current / duration) * 100))
        : item.status === "completed"
          ? 100
          : 0;

    const row = document.createElement("div");
    row.className = "playback-item";

    const header = document.createElement("div");
    header.className = "playback-item-header";
    const title = document.createElement("strong");
    title.textContent = safeText(item.task_name || item.module_title || item.course_title, "任务");
    const badge = document.createElement("span");
    badge.textContent = `${safeText(item.type, "task")} · ${safeText(item.status, "running")}`;
    header.append(title, badge);

    const meta = document.createElement("div");
    meta.className = "playback-item-meta";
    meta.textContent = `${safeText(item.course_title)} / ${safeText(item.module_title)} · ${percent}% · ${formatDuration(current)} / ${formatDuration(duration)}`;

    const bar = document.createElement("div");
    bar.className = "playback-bar";
    const fill = document.createElement("span");
    fill.style.width = `${percent}%`;
    bar.appendChild(fill);

    row.append(header, meta, bar);
    nodes.activePlaybackList.appendChild(row);
  });
}

function updateTaskControls(status) {
  const hasTask = Boolean(currentTaskId);
  const isActive = ["queued", "running", "paused", "cancelling"].includes(status);
  nodes.pauseTaskBtn.disabled = !hasTask || status !== "running";
  nodes.resumeTaskBtn.disabled = !hasTask || status !== "paused";
  nodes.cancelTaskBtn.disabled = !hasTask || !isActive || status === "cancelling";
}

function updateTaskView(taskData) {
  const task = taskData.task || taskData;
  const runtime = taskData.runtime || null;
  const items = playbackItems(taskData);
  const visibleItems = items.filter((item) => !["completed", "failed", "cancelled"].includes(item.status));
  const playback = visibleItems[0] || items[items.length - 1] || null;
  currentTaskId = safeText(task.task_id, "");
  nodes.taskId.textContent = safeText(task.task_id);
  nodes.taskStatus.textContent = safeText(task.status);
  nodes.courseProgress.textContent = `${task.done_courses || 0} / ${task.total_courses || 0}`;
  nodes.moduleProgress.textContent = `${task.done_modules || 0} / ${task.total_modules || 0}`;
  renderPlaybackList(items);
  updateTaskControls(task.status || "");

  if (playback) {
    const title = playback.task_name || playback.module_title || playback.course_title || "-";
    const current = Number(playback.play_time || 0);
    const duration = Number(playback.duration || 0);
    const percent = duration > 0 ? Math.min(100, Math.round((current / duration) * 100)) : 0;
    nodes.currentTask.textContent = safeText(title);
    nodes.playbackProgress.textContent = `${percent}% · ${formatDuration(current)} / ${formatDuration(duration)}`;
  } else {
    nodes.currentTask.textContent = "-";
    nodes.playbackProgress.textContent = "0% · 00:00 / 00:00";
  }

  if (Array.isArray(taskData.events)) {
    nodes.logArea.textContent = taskData.events.map((e) => `[${e.created_at}] ${e.message}`).join("\n");
  }
  if (runtime && Array.isArray(runtime.logs) && runtime.logs.length) {
    nodes.logArea.textContent = `${nodes.logArea.textContent}\n${runtime.logs
      .map((x) => `[live] ${x}`)
      .join("\n")}`.trim();
  }
}

function pollTask(taskId) {
  if (pollingTimer) clearInterval(pollingTimer);
  pollingTimer = setInterval(async () => {
    try {
      const data = await requestJson(`/api/tasks/${encodeURIComponent(taskId)}`, { method: "GET" });
      updateTaskView(data);
      if (["completed", "failed", "cancelled"].includes(data.task.status)) clearInterval(pollingTimer);
    } catch (error) {
      appendLog(`状态轮询失败: ${error.message}`);
      clearInterval(pollingTimer);
    }
  }, 1000);
}

async function controlTask(action) {
  if (!currentTaskId) {
    appendLog("没有可控制的任务。");
    return;
  }
  try {
    const data = await postJson(`/api/tasks/${encodeURIComponent(currentTaskId)}/${action}`, {});
    updateTaskView(data);
    appendLog(`任务已${action === "pause" ? "暂停" : action === "resume" ? "继续" : "取消"}。`);
    if (action === "resume") pollTask(currentTaskId);
  } catch (error) {
    appendLog(`任务控制失败: ${error.message}`);
  }
}

async function loadAnnouncements() {
  try {
    const data = await requestJson("/api/announcements", { method: "GET" });
    const items = data.announcements || [];
    nodes.announcementList.replaceChildren();
    if (!items.length) {
      setEmpty(nodes.announcementList, "暂无公告。");
      return;
    }
    items.forEach((notice) => {
      nodes.announcementList.appendChild(
        makeCourseItem([
          makeStrong(safeText(notice.title, "公告")),
          makeBreak(),
          makeLine(safeText(notice.content, "")),
          makeBreak(),
          makeSmall(safeText(notice.created_at)),
        ])
      );
    });
  } catch {
    setEmpty(nodes.announcementList, "公告加载失败。");
  }
}

async function loadCourses() {
  const inviteCode = nodes.taskInviteCode.value.trim();
  if (!inviteCode) {
    appendLog("请先填写任务邀请码。");
    return;
  }
  try {
    nodes.loadCoursesBtn.disabled = true;
    appendLog("正在拉取课程列表...");
    const data = await postJson("/api/courses", {
      invite_code: inviteCode,
      username: nodes.username.value.trim(),
      password: nodes.password.value.trim(),
    });
    renderCourses(data.courses || []);
    appendLog(`课程列表加载完成，共 ${(data.courses || []).length} 门课程。`);
  } catch (error) {
    appendLog(`课程列表加载失败: ${error.message}`);
  } finally {
    nodes.loadCoursesBtn.disabled = false;
  }
}

async function startTask() {
  const inviteCode = nodes.taskInviteCode.value.trim();
  if (!inviteCode) {
    appendLog("请填写任务邀请码。");
    return;
  }
  const courseIds = selectedCourseIds();
  if (!courseIds.length) {
    appendLog("请至少选择一门课程。");
    return;
  }
  try {
    nodes.startBtn.disabled = true;
    appendLog("正在提交任务...");
    const data = await postJson("/api/tasks", {
      invite_code: inviteCode,
      username: nodes.username.value.trim(),
      password: nodes.password.value.trim(),
      course_ids: courseIds,
      speed: Number(nodes.speed.value || 1.0),
      jobs: Number(nodes.jobs.value || 4),
      notopen_action: nodes.notopenAction.value,
    });
    currentTaskId = data.task_id;
    nodes.taskId.textContent = data.task_id;
    nodes.taskStatus.textContent = data.status;
    appendLog(`任务已创建: ${data.task_id}`);
    checkInvite().catch(() => {});
    pollTask(data.task_id);
  } catch (error) {
    appendLog(`任务提交失败: ${error.message}`);
  } finally {
    nodes.startBtn.disabled = false;
  }
}

function ensureAdmin() {
  if (!currentUser || currentUser.role !== "admin") {
    if (nodes.adminLogArea) nodes.adminLogArea.textContent = "需要管理员账号登录。";
    return false;
  }
  return true;
}

function setAdminMessage(message) {
  if (nodes.adminLogArea) nodes.adminLogArea.textContent = message;
}

async function publishNotice() {
  if (!ensureAdmin()) return;
  try {
    const data = await postJson("/api/admin/announcements", {
      title: nodes.noticeTitle.value.trim(),
      content: nodes.noticeContent.value.trim(),
    });
    setAdminMessage(`公告发布成功: ${data.announcement.id}`);
    nodes.noticeTitle.value = "";
    nodes.noticeContent.value = "";
    await loadAnnouncements();
  } catch (error) {
    setAdminMessage(`发布失败: ${error.message}`);
  }
}

async function generateInvite() {
  if (!ensureAdmin()) return;
  try {
    const maxUsesRaw = nodes.inviteMaxUses.value.trim();
    const expireRaw = nodes.inviteExpireHours.value.trim();
    const data = await postJson("/api/admin/invites/generate", {
      note: nodes.inviteNote.value.trim(),
      max_uses: maxUsesRaw ? Number(maxUsesRaw) : null,
      expires_hours: expireRaw ? Number(expireRaw) : null,
    });
    setAdminMessage(`邀请码创建成功: ${data.invite.code}`);
    nodes.inviteNote.value = "";
    nodes.inviteMaxUses.value = "";
    nodes.inviteExpireHours.value = "";
    await refreshInvites();
  } catch (error) {
    setAdminMessage(`邀请码创建失败: ${error.message}`);
  }
}

function setAiConfigMessage(message) {
  if (nodes.aiConfigStateText) nodes.aiConfigStateText.textContent = message;
}

function renderAiConfig(config) {
  if (!nodes.aiConfigEnabled) return;
  nodes.aiConfigEnabled.value = config.enabled ? "true" : "false";
  nodes.aiEndpoint.value = safeText(config.endpoint, "");
  nodes.aiModel.value = safeText(config.model, "");
  nodes.aiApiKey.value = "";
  nodes.aiApiKey.placeholder = config.has_api_key
    ? `已保存密钥 ${safeText(config.api_key_preview, "")}，留空则保留`
    : "留空则不设置密钥";
  nodes.aiSubmitAnswers.value = config.submit ? "true" : "false";
  nodes.aiHttpProxy.value = safeText(config.http_proxy, "");
  nodes.aiMinIntervalSeconds.value = safeText(config.min_interval_seconds, "1");
  nodes.aiDelay.value = safeText(config.delay, "1");
  nodes.aiCoverRate.value = safeText(config.cover_rate, "0.75");
  nodes.aiTrueList.value = safeText(config.true_list, "正确,对,√,是");
  nodes.aiFalseList.value = safeText(config.false_list, "错误,错,×,否,不对,不正确");
  setAiConfigMessage(config.has_api_key ? "模型配置已加载，密钥不会回显。" : "模型配置已加载，尚未保存 API Key。");
}

function readAiConfigForm() {
  return {
    enabled: nodes.aiConfigEnabled.value === "true",
    endpoint: nodes.aiEndpoint.value.trim(),
    model: nodes.aiModel.value.trim(),
    api_key: nodes.aiApiKey.value.trim(),
    submit: nodes.aiSubmitAnswers.value === "true",
    http_proxy: nodes.aiHttpProxy.value.trim(),
    min_interval_seconds: Number(nodes.aiMinIntervalSeconds.value || 1),
    delay: Number(nodes.aiDelay.value || 1),
    cover_rate: Number(nodes.aiCoverRate.value || 0.75),
    true_list: nodes.aiTrueList.value.trim(),
    false_list: nodes.aiFalseList.value.trim(),
  };
}

async function refreshAiConfig() {
  if (!ensureAdmin() || !nodes.aiConfigEnabled) return;
  try {
    const data = await requestJson("/api/admin/ai-config");
    renderAiConfig(data.config || {});
  } catch (error) {
    setAiConfigMessage(`模型配置加载失败: ${error.message}`);
    setAdminMessage(`模型配置加载失败: ${error.message}`);
  }
}

async function saveAiConfig() {
  if (!ensureAdmin()) return;
  try {
    nodes.saveAiConfigBtn.disabled = true;
    const data = await postJson("/api/admin/ai-config", readAiConfigForm());
    renderAiConfig(data.config || {});
    setAiConfigMessage("模型配置已保存。");
  } catch (error) {
    setAiConfigMessage(`模型配置保存失败: ${error.message}`);
  } finally {
    nodes.saveAiConfigBtn.disabled = false;
  }
}

async function testAiConfig() {
  if (!ensureAdmin()) return;
  try {
    nodes.testAiConfigBtn.disabled = true;
    setAiConfigMessage("正在测试模型连接...");
    const data = await postJson("/api/admin/ai-config/test", readAiConfigForm());
    setAiConfigMessage(data.ok ? `连接成功: ${safeText(data.response, "OK")}` : "连接失败：没有收到有效响应。");
  } catch (error) {
    setAiConfigMessage(`连接测试失败: ${error.message}`);
  } finally {
    nodes.testAiConfigBtn.disabled = false;
  }
}

async function toggleInvite(code, enabled) {
  if (!ensureAdmin()) return;
  try {
    await postJson(enabled ? "/api/admin/invites/enable" : "/api/admin/invites/disable", { code });
    await refreshInvites();
  } catch (error) {
    setAdminMessage(`操作失败: ${error.message}`);
  }
}

function formatUseLimit(value) {
  if (value === null || value === undefined) return "不限";
  return String(value);
}

function formatInviteCheck(invite) {
  const usedCount = Number(invite.used_count || 0);
  const maxUses = formatUseLimit(invite.max_uses);
  if (invite.remaining_uses === null || invite.remaining_uses === undefined) {
    return `邀请码可用，剩余不限（已用 ${usedCount}/${maxUses}）。`;
  }
  return `邀请码可用，剩余 ${invite.remaining_uses} 次（已用 ${usedCount}/${maxUses}）。`;
}

async function checkInvite() {
  if (!nodes.inviteStateText) return;
  const code = nodes.taskInviteCode.value.trim();
  if (!code) {
    nodes.inviteStateText.textContent = "请先输入邀请码。";
    return;
  }
  try {
    if (nodes.checkInviteBtn) nodes.checkInviteBtn.disabled = true;
    nodes.inviteStateText.textContent = "正在查询邀请码...";
    const data = await postJson("/api/invites/check", { code });
    const invite = data.invite || {};
    if (!invite.valid) {
      nodes.inviteStateText.textContent = `邀请码不可用: ${invite.message || "未知原因"}`;
      return;
    }
    nodes.inviteStateText.textContent = formatInviteCheck(invite);
  } catch (error) {
    nodes.inviteStateText.textContent = `邀请码查询失败: ${error.message}`;
  } finally {
    if (nodes.checkInviteBtn) nodes.checkInviteBtn.disabled = false;
  }
}

async function refreshInvites() {
  if (!ensureAdmin()) return;
  try {
    const data = await requestJson("/api/admin/invites");
    const invites = data.invites || [];
    nodes.inviteList.replaceChildren();
    if (!invites.length) {
      setEmpty(nodes.inviteList, "暂无邀请码。");
      return;
    }

    invites.forEach((invite) => {
      const status = invite.enabled ? "启用" : "停用";
      const maxUses = formatUseLimit(invite.max_uses);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn";
      button.textContent = invite.enabled ? "停用" : "启用";
      button.addEventListener("click", () => toggleInvite(invite.code, !invite.enabled));

      nodes.inviteList.appendChild(
        makeCourseItem([
          makeStrong(safeText(invite.code)),
          makeLine(` [${status}] 使用 ${invite.used_count}/${maxUses}`),
          makeBreak(),
          makeSmall(`${safeText(invite.note)} · ${safeText(invite.created_at)}`),
          makeBreak(),
          button,
        ])
      );
    });
  } catch (error) {
    setEmpty(nodes.inviteList, `邀请码加载失败: ${error.message}`);
    setAdminMessage(`邀请码加载失败: ${error.message}`);
  }
}

async function refreshTasks() {
  if (!ensureAdmin()) return;
  try {
    const data = await requestJson("/api/admin/tasks");
    const tasks = data.tasks || [];
    nodes.taskList.replaceChildren();
    if (!tasks.length) {
      setEmpty(nodes.taskList, "暂无任务。");
      return;
    }

    tasks.forEach((task) => {
      const closeButton = document.createElement("button");
      const status = safeText(task.status, "");
      const canClose = !["completed", "failed", "cancelled", "cancelling"].includes(status);
      closeButton.type = "button";
      closeButton.className = "btn";
      closeButton.textContent = "关闭任务";
      closeButton.disabled = !canClose;
      closeButton.addEventListener("click", () => adminCloseTask(task.task_id));

      nodes.taskList.appendChild(
        makeCourseItem([
          makeStrong(safeText(task.task_id)),
          makeLine(` [${status}] 用户: ${safeText(task.username)}`),
          makeBreak(),
          makeLine(`课程 ${task.done_courses || 0}/${task.total_courses || 0} · 模块 ${task.done_modules || 0}/${task.total_modules || 0}`),
          makeBreak(),
          makeSmall(safeText(task.created_at)),
          makeBreak(),
          closeButton,
        ])
      );
    });
  } catch (error) {
    setEmpty(nodes.taskList, `任务总览加载失败: ${error.message}`);
    setAdminMessage(`任务总览加载失败: ${error.message}`);
  }
}

async function adminCloseTask(taskId) {
  if (!ensureAdmin() || !taskId) return;
  try {
    await postJson(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, {});
    setAdminMessage(`任务已关闭: ${taskId}`);
    await refreshTasks();
  } catch (error) {
    setAdminMessage(`关闭任务失败: ${error.message}`);
  }
}

async function inspectTask() {
  if (!ensureAdmin()) return;
  const taskId = nodes.inspectTaskId.value.trim();
  if (!taskId) return;
  try {
    const data = await requestJson(`/api/admin/tasks/${encodeURIComponent(taskId)}`);
    const events = data.events || [];
    nodes.adminLogArea.textContent = events.map((e) => `[${e.created_at}] ${e.message}`).join("\n");
  } catch (error) {
    setAdminMessage(`查询失败: ${error.message}`);
  }
}

async function refreshAllAdmin() {
  if (!ensureAdmin()) return;
  await Promise.allSettled([refreshAiConfig(), refreshInvites(), refreshTasks()]);
}

function bindAdminControls() {
  nodes.adminRefreshBtn?.addEventListener("click", () => refreshAllAdmin().catch((error) => setAdminMessage(error.message)));
  nodes.publishNoticeBtn?.addEventListener("click", publishNotice);
  nodes.saveAiConfigBtn?.addEventListener("click", saveAiConfig);
  nodes.testAiConfigBtn?.addEventListener("click", testAiConfig);
  nodes.generateInviteBtn?.addEventListener("click", generateInvite);
  nodes.inspectTaskBtn?.addEventListener("click", inspectTask);
}

async function renderAdminPanel() {
  if (!nodes.adminPanel) return;
  if (!currentUser || currentUser.role !== "admin") {
    nodes.adminPanel.hidden = true;
    return;
  }

  nodes.adminPanel.hidden = false;
  nodes.adminStateText.textContent = `已启用管理员控制区: ${currentUser.username}`;
  await refreshAllAdmin();
}

async function init() {
  if (!ensureEntryGate()) return;
  try {
    currentUser = await loadCurrentUser();
  } catch {
    clearAuth();
    window.location.href = "/login/";
    return;
  }

  nodes.authStateText.textContent = `已登录: ${currentUser.username} (${currentUser.role})`;
  nodes.logoutBtn.addEventListener("click", () => {
    clearAuth();
    window.location.href = "/login/";
  });
  nodes.checkInviteBtn?.addEventListener("click", checkInvite);
  nodes.taskInviteCode?.addEventListener("change", () => {
    if (nodes.taskInviteCode.value.trim()) checkInvite();
  });
  nodes.taskInviteCode?.addEventListener("input", () => {
    if (nodes.inviteStateText) nodes.inviteStateText.textContent = "";
  });
  nodes.loadCoursesBtn.addEventListener("click", loadCourses);
  nodes.startBtn.addEventListener("click", startTask);
  nodes.pauseTaskBtn.addEventListener("click", () => controlTask("pause"));
  nodes.resumeTaskBtn.addEventListener("click", () => controlTask("resume"));
  nodes.cancelTaskBtn.addEventListener("click", () => controlTask("cancel"));
  bindAdminControls();
  renderCourses([]);
  await loadAnnouncements();
  await renderAdminPanel();
}

let coverBurning = false;

function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

function startBurnCanvas(originX, originY) {
  const canvas = nodes.burnCanvas;
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = window.innerWidth;
  const height = window.innerHeight;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const maxRadius = Math.hypot(Math.max(originX, width - originX), Math.max(originY, height - originY)) * 1.12;
  const particles = Array.from({ length: 420 }, (_, index) => {
    const angle = Math.random() * Math.PI * 2;
    const speed = 50 + Math.random() * 620;
    return {
      angle,
      speed,
      delay: 0.08 + Math.random() * 0.62,
      size: 0.8 + Math.random() * 2.6,
      lift: 80 + Math.random() * 280,
      wobble: Math.random() * 54,
      warm: index % 5 === 0,
    };
  });
  const smoke = Array.from({ length: 26 }, () => ({
    angle: Math.random() * Math.PI * 2,
    distance: 80 + Math.random() * maxRadius * 0.72,
    width: 80 + Math.random() * 190,
    delay: 0.24 + Math.random() * 0.36,
  }));

  const started = performance.now();
  const duration = 3000;

  function draw(now) {
    const t = Math.min(1, (now - started) / duration);
    const eased = easeOutCubic(t);
    const radius = Math.max(12, maxRadius * eased);

    ctx.clearRect(0, 0, width, height);
    ctx.globalCompositeOperation = "source-over";

    const dim = ctx.createRadialGradient(originX, originY, Math.max(1, radius * 0.18), originX, originY, maxRadius * 1.04);
    dim.addColorStop(0, `rgba(0, 0, 0, ${0.02 + t * 0.1})`);
    dim.addColorStop(0.44, `rgba(20, 4, 4, ${0.16 + t * 0.3})`);
    dim.addColorStop(1, `rgba(0, 0, 0, ${0.46 + t * 0.44})`);
    ctx.fillStyle = dim;
    ctx.fillRect(0, 0, width, height);

    ctx.globalCompositeOperation = "lighter";
    if (t < 0.22) {
      const sparkT = Math.sin((t / 0.22) * Math.PI);
      const spark = ctx.createRadialGradient(originX, originY, 0, originX, originY, 34 + sparkT * 54);
      spark.addColorStop(0, `rgba(255, 244, 185, ${0.68 * sparkT})`);
      spark.addColorStop(0.34, `rgba(255, 128, 36, ${0.36 * sparkT})`);
      spark.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = spark;
      ctx.fillRect(0, 0, width, height);
    }

    particles.forEach((p) => {
      const pt = Math.max(0, Math.min(1, (t - p.delay) / (1 - p.delay)));
      if (pt <= 0) return;
      const drift = p.speed * easeOutCubic(pt);
      const x = originX + Math.cos(p.angle) * drift + Math.sin(pt * 12 + p.angle) * p.wobble;
      const y = originY + Math.sin(p.angle) * drift - p.lift * pt + Math.cos(pt * 9 + p.angle) * 18;
      const alpha = Math.sin(Math.PI * pt) * (p.warm ? 0.9 : 0.68);
      const size = p.size * (1.2 - pt * 0.68);
      ctx.fillStyle = p.warm
        ? `rgba(255, 236, 156, ${alpha})`
        : `rgba(255, ${88 + Math.floor(90 * (1 - pt))}, 42, ${alpha})`;
      ctx.fillRect(x, y, size, size);
    });

    ctx.globalCompositeOperation = "source-over";
    smoke.forEach((wisp) => {
      const st = Math.max(0, Math.min(1, (t - wisp.delay) / (1 - wisp.delay)));
      if (st <= 0) return;
      const spread = wisp.distance * easeOutCubic(st);
      const x = originX + Math.cos(wisp.angle) * spread + Math.sin(st * 9 + wisp.angle) * 38;
      const y = originY + Math.sin(wisp.angle) * spread - 130 * st;
      const smokeGrad = ctx.createRadialGradient(x, y, 0, x, y, wisp.width * (0.55 + st));
      smokeGrad.addColorStop(0, `rgba(18, 8, 7, ${0.2 * Math.sin(Math.PI * st)})`);
      smokeGrad.addColorStop(0.45, `rgba(63, 19, 15, ${0.1 * Math.sin(Math.PI * st)})`);
      smokeGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = smokeGrad;
      ctx.fillRect(0, 0, width, height);
    });

    if (t > 0.66) {
      const finalAlpha = Math.min(1, (t - 0.66) / 0.34);
      ctx.fillStyle = `rgba(2, 0, 0, ${finalAlpha * 0.82})`;
      ctx.fillRect(0, 0, width, height);
    }

    if (t < 1) requestAnimationFrame(draw);
  }

  requestAnimationFrame(draw);
}

function enterFromCover(event) {
  if (!nodes.coverGate || coverBurning) return;
  coverBurning = true;
  const point = event.touches ? event.touches[0] : event;
  const x = point && Number.isFinite(point.clientX) ? point.clientX : window.innerWidth / 2;
  const y = point && Number.isFinite(point.clientY) ? point.clientY : window.innerHeight / 2;
  nodes.coverGate.style.setProperty("--burn-x", `${x}px`);
  nodes.coverGate.style.setProperty("--burn-y", `${y}px`);
  nodes.coverGate.classList.add("is-burning");
  startBurnCanvas(x, y);
  window.setTimeout(() => {
    sessionStorage.setItem(COVER_KEY, "1");
    window.location.href = "/login/";
  }, 3000);
}

if (nodes.coverGate) {
  nodes.coverGate.addEventListener("click", enterFromCover);
  nodes.coverGate.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      enterFromCover(event);
    }
  });
}

init();
