const state = {
  profiles: [],
  authLinks: [],
  selectedAuthLinkId: "",
  createLinkKind: "official",
  authPickerProfile: "",
  officialLoginProfile: "",
  officialLoginCode: "",
  officialLoginMode: "web",
  officialLoginUrl: "",
  authJsonProfile: "",
  authJsonText: "",
  search: "",
  status: "",
  pollingProfile: "",
};

const els = {
  body: document.querySelector("#profileBody"),
  search: document.querySelector("#searchInput"),
  status: document.querySelector("#statusFilter"),
  authLinkSelect: document.querySelector("#authLinkSelect"),
  url: document.querySelector("#urlInput"),
  authLinkForm: document.querySelector("#authLinkForm"),
  authLinkName: document.querySelector("#authLinkNameInput"),
  authLinkUrl: document.querySelector("#authLinkUrlInput"),
  deleteAuthLink: document.querySelector("#deleteAuthLinkBtn"),
  refresh: document.querySelector("#refreshBtn"),
  createForm: document.querySelector("#createForm"),
  guidedCreate: document.querySelector("#guidedCreateBtn"),
  batchForm: document.querySelector("#batchForm"),
  suggestName: document.querySelector("#suggestNameBtn"),
  name: document.querySelector("#nameInput"),
  note: document.querySelector("#noteInput"),
  prefix: document.querySelector("#prefixInput"),
  start: document.querySelector("#startInput"),
  count: document.querySelector("#countInput"),
  totalCount: document.querySelector("#totalCount"),
  readyCount: document.querySelector("#readyCount"),
  openedCount: document.querySelector("#openedCount"),
  emptyCount: document.querySelector("#emptyCount"),
  visibleCount: document.querySelector("#visibleCount"),
  quickLinkButtons: document.querySelector("#quickLinkButtons"),
  officialLoginLinkText: document.querySelector("#officialLoginLinkText"),
  authLoginLinkText: document.querySelector("#authLoginLinkText"),
  registerLinkText: document.querySelector("#registerLinkText"),
  authPicker: document.querySelector("#authPicker"),
  authPickerProfile: document.querySelector("#authPickerProfile"),
  authPickerList: document.querySelector("#authPickerList"),
  authPickerClose: document.querySelector("#authPickerClose"),
  officialLoginModal: document.querySelector("#officialLoginModal"),
  officialLoginProfile: document.querySelector("#officialLoginProfile"),
  officialLoginCode: document.querySelector("#officialLoginCode"),
  officialLoginUrl: document.querySelector("#officialLoginUrl"),
  officialLoginClose: document.querySelector("#officialLoginClose"),
  copyOfficialCode: document.querySelector("#copyOfficialCodeBtn"),
  openChatGptLogin: document.querySelector("#openChatGptLoginBtn"),
  openOfficialLogin: document.querySelector("#openOfficialLoginBtn"),
  copyOfficialUrl: document.querySelector("#copyOfficialUrlBtn"),
  checkOfficialLogin: document.querySelector("#checkOfficialLoginBtn"),
  authJsonModal: document.querySelector("#authJsonModal"),
  authJsonProfile: document.querySelector("#authJsonProfile"),
  authJsonContent: document.querySelector("#authJsonContent"),
  authJsonClose: document.querySelector("#authJsonClose"),
  copyAuthJson: document.querySelector("#copyAuthJsonBtn"),
  downloadAuthJson: document.querySelector("#downloadAuthJsonBtn"),
  toast: document.querySelector("#toast"),
};

const DEFAULT_LINKS = {
  official: { label: "官方登录网站", url: "https://chatgpt.com" },
  auth: { label: "Auth 授权网站", url: "https://auth.openai.com" },
  register: { label: "注册账号网站", url: "https://invite.kyl23333.xyz/" },
};

let pollTimer = null;
const autoSaveTimers = new Map();

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => els.toast.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function loadProfiles() {
  const payload = await api("/api/profiles");
  state.profiles = payload.profiles || [];
  render();
}

async function loadAuthLinks() {
  const payload = await api("/api/auth-links");
  state.authLinks = payload.links || [];
  if (!state.selectedAuthLinkId && state.authLinks.length > 0) {
    state.selectedAuthLinkId = state.authLinks[0].id;
  }
  renderAuthLinks();
  renderQuickLinks();
}

function selectedAuthLink() {
  return state.authLinks.find((link) => link.id === state.selectedAuthLinkId);
}

function linkForKind(kind) {
  const links = state.authLinks;
  if (kind === "official") {
    return (
      links.find((link) => link.id === "chatgpt") ||
      links.find((link) => /chatgpt/i.test(link.label) || /chatgpt\.com/i.test(link.url)) ||
      DEFAULT_LINKS.official
    );
  }
  if (kind === "auth") {
    return (
      links.find((link) => link.id === "openai-auth") ||
      links.find((link) => normalizeUrl(link.url) === "https://auth.openai.com") ||
      DEFAULT_LINKS.auth
    );
  }
  if (kind === "register") {
    return (
      links.find((link) => /羊毛|注册|invite|register/i.test(link.label) || /invite|signup|register/i.test(link.url)) ||
      DEFAULT_LINKS.register
    );
  }
  return DEFAULT_LINKS.official;
}

function createOpenUrl() {
  return linkForKind(state.createLinkKind).url;
}

function currentOpenUrl() {
  return els.url.value || selectedAuthLink()?.url || DEFAULT_LINKS.official.url;
}

function normalizeUrl(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.host}${parsed.pathname === "/" ? "" : parsed.pathname}`;
  } catch {
    return String(url || "").trim();
  }
}

function openAuthPicker(profileName) {
  state.authPickerProfile = profileName;
  els.authPickerProfile.textContent = profileName;
  renderAuthPicker();
  els.authPicker.classList.remove("hidden");
}

function closeAuthPicker() {
  state.authPickerProfile = "";
  els.authPicker.classList.add("hidden");
}

function renderAuthPicker() {
  if (state.authLinks.length === 0) {
    els.authPickerList.innerHTML = `<div class="empty-row">暂无链接，先在链接库添加一个。</div>`;
    return;
  }
  els.authPickerList.innerHTML = state.authLinks
    .map(
      (link) => `
        <button type="button" class="link-choice" data-link-id="${escapeAttr(link.id)}">
          <span>${escapeHtml(link.label)}</span>
          <small>${escapeHtml(link.url)}</small>
        </button>
      `,
    )
    .join("");
}

function renderAuthLinks() {
  const links = state.authLinks;
  if (links.length === 0) {
    els.authLinkSelect.innerHTML = `<option value="">暂无链接</option>`;
    els.url.value = DEFAULT_LINKS.official.url;
    return;
  }

  if (!links.some((link) => link.id === state.selectedAuthLinkId)) {
    state.selectedAuthLinkId = links[0].id;
  }

  els.authLinkSelect.innerHTML = links
    .map((link) => {
      const selected = link.id === state.selectedAuthLinkId ? "selected" : "";
      return `<option value="${escapeAttr(link.id)}" ${selected}>${escapeHtml(link.label)}</option>`;
    })
    .join("");

  const link = selectedAuthLink();
  if (link) els.url.value = link.url;
}

function renderQuickLinks() {
  const official = linkForKind("official");
  const auth = linkForKind("auth");
  const register = linkForKind("register");
  els.officialLoginLinkText.textContent = official.url;
  els.authLoginLinkText.textContent = auth.url;
  els.registerLinkText.textContent = register.url;

  els.quickLinkButtons.querySelectorAll("[data-create-link]").forEach((button) => {
    button.classList.toggle("active", button.dataset.createLink === state.createLinkKind);
  });
}

function filteredProfiles() {
  const query = state.search.trim().toLowerCase();
  return state.profiles
    .filter((profile) => {
      if (state.status && profile.status !== state.status) return false;
      if (!query) return true;
      return [profile.name, profile.email, profile.note, profile.dir, profile.officialAuth?.email]
        .join(" ")
        .toLowerCase()
        .includes(query);
    })
    .sort((a, b) => {
      const createdDiff = Number(b.createdAt || 0) - Number(a.createdAt || 0);
      if (createdDiff !== 0) return createdDiff;
      return String(b.name).localeCompare(String(a.name), "zh-CN", { numeric: true });
    });
}

function render() {
  const profiles = filteredProfiles();
  const counts = countProfiles(state.profiles);
  els.totalCount.textContent = state.profiles.length;
  els.readyCount.textContent = counts.jsonReady;
  els.openedCount.textContent = counts.opened;
  els.emptyCount.textContent = counts.empty;
  els.visibleCount.textContent = `${profiles.length} 条`;

  if (profiles.length === 0) {
    els.body.innerHTML = `<tr><td colspan="7" class="empty-row">没有匹配的账号环境</td></tr>`;
    return;
  }

  els.body.innerHTML = profiles.map(profileRow).join("");
}

function countProfiles(profiles) {
  return profiles.reduce(
    (acc, profile) => {
      if (profile.officialAuth?.ready) acc.jsonReady += 1;
      if (profile.status === "opened") acc.opened += 1;
      if (profile.status === "empty") acc.empty += 1;
      return acc;
    },
    { jsonReady: 0, opened: 0, empty: 0 },
  );
}

function profileRow(profile) {
  const lastOpened = profile.lastOpenedAt ? formatTime(profile.lastOpenedAt) : "-";
  const officialAuth = profile.officialAuth || {};
  const savedEmail = officialAuth.email || "";
  const emailValue = profile.email || savedEmail || "";
  const authClass = officialAuth.ready ? "ok" : state.pollingProfile === profile.name ? "busy" : "warn";
  const authTitle = officialAuth.ready ? "JSON已保存" : state.pollingProfile === profile.name ? "获取中" : "JSON未获取";
  const authMeta = officialAuth.ready
    ? [savedEmail, officialAuth.planType, officialAuth.lastRefresh ? formatTime(officialAuth.updatedAt) : ""].filter(Boolean).join(" · ")
    : profile.status === "registering"
      ? "注册页已打开；完成验证后保存邮箱，再点继续授权"
      : profile.status === "auth_pending"
        ? "已准备授权；点继续授权获取官方 JSON"
        : "点击获取JSON后完成官方授权";

  return `
    <tr data-name="${escapeAttr(profile.name)}">
      <td>
        <input class="inline-input profile-name-input js-profile-name" value="${escapeAttr(profile.name)}" />
        <div class="path" title="${escapeAttr(profile.dir)}">${escapeHtml(profile.dir)}</div>
      </td>
      <td>
        <div class="input-with-action">
          <input class="inline-input js-email" value="${escapeAttr(emailValue)}" placeholder="可后面再补" />
          <button class="small-action js-copy-email" type="button">复制</button>
        </div>
      </td>
      <td>
        <div class="auth-state ${authClass}">
          <strong>${escapeHtml(authTitle)}</strong>
          <small title="${escapeAttr(officialAuth.path || "")}">${escapeHtml(authMeta || "-")}</small>
          <div class="json-inline-actions">
            <button class="small-action js-view-json" type="button" ${officialAuth.ready ? "" : "disabled"}>查看JSON</button>
            <button class="small-action js-download-json" type="button" ${officialAuth.ready ? "" : "disabled"}>下载JSON</button>
          </div>
        </div>
      </td>
      <td>
        <select class="inline-input js-status">
          ${statusOption("empty", "空环境", profile.status)}
          ${statusOption("opened", "已打开", profile.status)}
          ${statusOption("registering", "注册中", profile.status)}
          ${statusOption("auth_pending", "待授权", profile.status)}
          ${statusOption("ready", "可用", profile.status)}
          ${statusOption("disabled", "停用", profile.status)}
        </select>
      </td>
      <td>
        <input class="inline-input js-note" value="${escapeAttr(profile.note || "")}" placeholder="备注" />
      </td>
      <td>${escapeHtml(lastOpened)}</td>
      <td>
        <div class="actions">
          <button class="primary js-open-chatgpt">打开ChatGPT官网</button>
          <button class="js-open-register" title="打开注册入口，人工完成验证码/邮箱/头像等验证">注册入口</button>
          <button class="step-two js-start-official-login" title="继续官方 OAuth 授权并保存 auth.json">继续授权</button>
          <button class="js-save">保存现有信息</button>
          <button class="danger js-delete">删除账号</button>
        </div>
      </td>
    </tr>
  `;
}

function statusOption(value, label, current) {
  const selected = value === current ? "selected" : "";
  return `<option value="${value}" ${selected}>${label}</option>`;
}

function formatTime(ms) {
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}

function normalizeEmailInput(value) {
  return String(value || "").replace(/\s+/g, "").trim();
}

function cleanEmailField(row) {
  const input = row.querySelector(".js-email");
  const cleaned = normalizeEmailInput(input.value);
  if (input.value !== cleaned) input.value = cleaned;
  return cleaned;
}

async function openProfile(name, url = currentOpenUrl()) {
  const payload = await api("/api/profiles/open", {
    method: "POST",
    body: JSON.stringify({ name, url }),
  });
  upsertProfile(payload.profile);
  render();
  toast(`已打开 ${name}`);
}

async function openRegisterStep(row) {
  const name = row.dataset.name;
  const email = cleanEmailField(row);
  const note = row.querySelector(".js-note").value || "等待人工注册/验证";
  const profile = await patchProfile(
    row,
    {
      email,
      note,
      status: "registering",
    },
    { quiet: true },
  );
  await openProfile(profile.name, linkForKind("register").url);
  toast(`已在 ${profile.name} 的独立 Chrome 打开注册入口；验证步骤你手动处理`);
}

async function createGuidedProfile() {
  const payload = await api("/api/profiles", {
    method: "POST",
    body: JSON.stringify({
      name: els.name.value,
      note: els.note.value || "注册向导：等待人工注册/验证",
      status: "registering",
    }),
  });
  upsertProfile(payload.profile);
  render();
  await openProfile(payload.profile.name, linkForKind("register").url);
  els.note.value = "";
  await suggestName();
  toast("注册向导已启动：先完成页面注册/验证，再填邮箱并点继续授权");
}

async function patchProfile(row, updates, options = {}) {
  const name = row.dataset.name;
  const payload = await api(`/api/profiles/${encodeURIComponent(name)}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
  removeProfile(name);
  upsertProfile(payload.profile);
  if (options.render !== false) render();
  if (options.message) toast(options.message);
  else if (!options.quiet) toast(`已保存 ${payload.profile.name}`);
  return payload.profile;
}

async function saveProfile(row, options = {}) {
  const updates = {
    name: row.querySelector(".js-profile-name").value,
    email: cleanEmailField(row),
    status: row.querySelector(".js-status").value,
    note: row.querySelector(".js-note").value,
  };
  return patchProfile(row, updates, options);
}

function autoSaveKey(row, field) {
  return `${row.dataset.name}:${field}`;
}

async function autoSaveProfile(row, field) {
  if (!row.isConnected) return;
  try {
    const updates = {};
    if (field === "name") {
      const nextName = row.querySelector(".js-profile-name").value;
      if (nextName === row.dataset.name) return;
      updates.name = nextName;
    } else if (field === "email") {
      updates.email = cleanEmailField(row);
    }
    const profile = await patchProfile(row, updates, {
      render: field !== "email",
      message: field === "name" ? "账号名已自动保存" : "邮箱已自动保存",
    });
    if (field === "email") {
      row.dataset.name = profile.name;
    }
  } catch (error) {
    toast(error.message);
  }
}

function scheduleAutoSave(row, field, delay = 800) {
  const key = autoSaveKey(row, field);
  clearTimeout(autoSaveTimers.get(key));
  autoSaveTimers.set(
    key,
    setTimeout(() => {
      autoSaveTimers.delete(key);
      autoSaveProfile(row, field);
    }, delay),
  );
}

function flushAutoSave(row, field) {
  const key = autoSaveKey(row, field);
  const timer = autoSaveTimers.get(key);
  if (timer) {
    clearTimeout(timer);
    autoSaveTimers.delete(key);
  }
  return autoSaveProfile(row, field);
}

async function copyText(value, successMessage = "已复制") {
  const text = String(value || "").trim();
  if (!text) {
    toast("没有可复制内容");
    return false;
  }
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  toast(successMessage);
  return true;
}

async function startOfficialLogin(name) {
  state.pollingProfile = name;
  render();
  let targetName = name;
  const row = document.querySelector(`tr[data-name="${CSS.escape(name)}"]`);
  if (row) {
    const profile = await saveProfile(row, { quiet: true, render: false });
    targetName = profile.name;
  }
  await api(`/api/profiles/${encodeURIComponent(targetName)}/official-login`, {
    method: "POST",
    body: JSON.stringify({ mode: "web" }),
  });
  closeOfficialLoginModal();
  toast(`已在 ${targetName} 的独立 Chrome 窗口打开授权页`);
  await loadProfiles();
  startPollingLogin(targetName);
}

async function checkOfficialLogin(name, quiet = false) {
  const payload = await api(`/api/profiles/${encodeURIComponent(name)}/official-login`);
  if (payload.officialAuth?.ready) {
    if (!quiet) toast(`auth.json 已保存：${payload.officialAuth.email || payload.profile}`);
    closeOfficialLoginModal();
  } else if (!quiet) {
    toast(payload.running ? "授权还在等待完成" : "授权流程未运行，请重新点第二步");
  }
  await loadProfiles();
  return payload;
}

function startPollingLogin(name) {
  stopPollingLogin(false);
  state.pollingProfile = name;
  render();
  pollTimer = setInterval(async () => {
    try {
      const payload = await checkOfficialLogin(name, true);
      if (payload.officialAuth?.ready || !payload.running) {
        stopPollingLogin(payload.officialAuth?.ready);
      }
    } catch {
      stopPollingLogin(false);
    }
  }, 3500);
}

function stopPollingLogin(done) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
  if (done) toast("auth.json 已保存到这个账号里");
  if (!pollTimer) state.pollingProfile = "";
  render();
}

function showOfficialLogin(payload, quiet = false) {
  if (payload.officialAuth?.ready) {
    if (!quiet) toast(`auth.json 已保存：${payload.officialAuth.email || payload.profile}`);
    closeOfficialLoginModal();
    return;
  }

  state.officialLoginProfile = payload.profile;
  state.officialLoginCode = payload.code || "";
  state.officialLoginMode = payload.mode || "web";
  state.officialLoginUrl = payload.loginUrl || payload.deviceUrl || "";
  renderOfficialLoginModal(payload);
  els.officialLoginModal.classList.remove("hidden");
}

function renderOfficialLoginModal(payload = {}) {
  els.officialLoginProfile.textContent = state.officialLoginProfile || "-";
  els.officialLoginCode.textContent = state.officialLoginCode || "网页授权";
  els.officialLoginUrl.textContent = state.officialLoginUrl || payload.message || "授权页会自动打开，完成后点查状态。";
  els.copyOfficialCode.disabled = !state.officialLoginCode;
  els.openOfficialLogin.disabled = !state.officialLoginUrl;
  els.copyOfficialUrl.disabled = !state.officialLoginUrl;
}

function closeOfficialLoginModal() {
  els.officialLoginModal.classList.add("hidden");
}

async function showAuthJson(name) {
  const payload = await api(`/api/profiles/${encodeURIComponent(name)}/auth.json`);
  state.authJsonProfile = name;
  state.authJsonText = JSON.stringify(payload, null, 2);
  renderAuthJsonModal();
  els.authJsonModal.classList.remove("hidden");
}

function renderAuthJsonModal() {
  els.authJsonProfile.textContent = state.authJsonProfile || "-";
  els.authJsonContent.value = state.authJsonText || "";
}

function closeAuthJsonModal() {
  els.authJsonModal.classList.add("hidden");
}

function downloadAuthJson(name) {
  if (!name) {
    toast("没有可下载的账号");
    return;
  }
  window.location.href = `/api/profiles/${encodeURIComponent(name)}/auth.json`;
  toast(`正在下载 ${name} 的 auth.json`);
}

function upsertProfile(profile) {
  const index = state.profiles.findIndex((item) => item.name === profile.name);
  if (index >= 0) state.profiles[index] = profile;
  else state.profiles.push(profile);
  state.profiles.sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0));
}

function removeProfile(name) {
  state.profiles = state.profiles.filter((item) => item.name !== name);
}

function confirmDeleteProfile(profile) {
  const name = profile?.name || "";
  if (profile?.officialAuth?.ready) {
    const email = profile.officialAuth.email ? `\n账号邮箱：${profile.officialAuth.email}` : "";
    return confirm(`该账号已经生成好 JSON。${email}\n\n是否确认删除账号“${name}”？\n\n删除后会移动到 deleted-profiles 备份区。`);
  }
  return confirm(`该账号还没有生成 JSON。\n\n是否仍然确认删除账号“${name}”？\n\n删除后会移动到 deleted-profiles 备份区。`);
}

async function suggestName() {
  const prefix = els.prefix.value || "team";
  const payload = await api(`/api/next-name?prefix=${encodeURIComponent(prefix)}&padding=2`);
  els.name.value = payload.name;
}

els.search.addEventListener("input", () => {
  state.search = els.search.value;
  render();
});

els.status.addEventListener("change", () => {
  state.status = els.status.value;
  render();
});

els.authLinkSelect.addEventListener("change", () => {
  state.selectedAuthLinkId = els.authLinkSelect.value;
  renderAuthLinks();
});

els.quickLinkButtons.addEventListener("click", (event) => {
  const button = event.target.closest("[data-create-link]");
  if (!button) return;
  state.createLinkKind = button.dataset.createLink;
  renderQuickLinks();
});

els.refresh.addEventListener("click", () => {
  Promise.all([loadProfiles(), loadAuthLinks()])
    .then(() => toast("已刷新"))
    .catch((error) => toast(error.message));
});

els.authLinkForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = await api("/api/auth-links", {
      method: "POST",
      body: JSON.stringify({
        label: els.authLinkName.value,
        url: els.authLinkUrl.value,
      }),
    });
    state.authLinks = payload.links || [];
    state.selectedAuthLinkId = payload.link?.id || state.selectedAuthLinkId;
    renderAuthLinks();
    renderAuthPicker();
    renderQuickLinks();
    els.authLinkName.value = "";
    els.authLinkUrl.value = "";
    toast("已添加链接");
  } catch (error) {
    toast(error.message);
  }
});

els.deleteAuthLink.addEventListener("click", async () => {
  const link = selectedAuthLink();
  if (!link) return;
  if (!confirm(`删除链接“${link.label}”？\n\n只删除链接记录，不会删除账号环境。`)) return;
  try {
    const payload = await api(`/api/auth-links/${encodeURIComponent(link.id)}`, { method: "DELETE" });
    state.authLinks = payload.links || [];
    state.selectedAuthLinkId = state.authLinks[0]?.id || "";
    renderAuthLinks();
    renderAuthPicker();
    renderQuickLinks();
    toast("已删除链接");
  } catch (error) {
    toast(error.message);
  }
});

els.authPickerClose.addEventListener("click", closeAuthPicker);

els.authPicker.addEventListener("click", (event) => {
  if (event.target === els.authPicker) closeAuthPicker();
});

els.authPickerList.addEventListener("click", async (event) => {
  const button = event.target.closest(".link-choice");
  if (!button || !state.authPickerProfile) return;
  const link = state.authLinks.find((item) => item.id === button.dataset.linkId);
  if (!link) return;
  try {
    const profileName = state.authPickerProfile;
    state.selectedAuthLinkId = link.id;
    renderAuthLinks();
    closeAuthPicker();
    await openProfile(profileName, link.url);
    toast(`已用 ${profileName} 打开：${link.label}`);
  } catch (error) {
    toast(error.message);
  }
});

els.officialLoginClose.addEventListener("click", closeOfficialLoginModal);

els.officialLoginModal.addEventListener("click", (event) => {
  if (event.target === els.officialLoginModal) closeOfficialLoginModal();
});

els.authJsonClose.addEventListener("click", closeAuthJsonModal);

els.authJsonModal.addEventListener("click", (event) => {
  if (event.target === els.authJsonModal) closeAuthJsonModal();
});

els.copyAuthJson.addEventListener("click", async () => {
  await copyText(els.authJsonContent.value, "auth.json 已复制");
});

els.downloadAuthJson.addEventListener("click", () => {
  downloadAuthJson(state.authJsonProfile);
});

els.copyOfficialCode.addEventListener("click", async () => {
  if (!state.officialLoginCode) return;
  await copyText(state.officialLoginCode, "代码已复制");
});

els.openChatGptLogin.addEventListener("click", async () => {
  if (!state.officialLoginProfile) return;
  try {
    await openProfile(state.officialLoginProfile, DEFAULT_LINKS.official.url);
    toast("已在该账号的独立 Chrome 打开登录页");
  } catch (error) {
    toast(error.message);
  }
});

els.openOfficialLogin.addEventListener("click", async () => {
  if (!state.officialLoginProfile) return;
  try {
    await openProfile(state.officialLoginProfile, state.officialLoginUrl || DEFAULT_LINKS.auth.url);
  } catch (error) {
    toast(error.message);
  }
});

els.copyOfficialUrl.addEventListener("click", async () => {
  await copyText(state.officialLoginUrl, "授权 URL 已复制");
});

els.checkOfficialLogin.addEventListener("click", async () => {
  if (!state.officialLoginProfile) return;
  try {
    const payload = await checkOfficialLogin(state.officialLoginProfile);
    if (!payload.officialAuth?.ready) toast("还没保存成功，授权完成后再查一次");
  } catch (error) {
    toast(error.message);
  }
});

els.suggestName.addEventListener("click", () => {
  suggestName().catch((error) => toast(error.message));
});

els.guidedCreate.addEventListener("click", async () => {
  try {
    await createGuidedProfile();
  } catch (error) {
    toast(error.message);
  }
});

els.createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = await api("/api/profiles", {
      method: "POST",
      body: JSON.stringify({
        name: els.name.value,
        note: els.note.value,
        status: "opened",
      }),
    });
    upsertProfile(payload.profile);
    await openProfile(payload.profile.name, createOpenUrl());
    els.note.value = "";
    await suggestName();
  } catch (error) {
    toast(error.message);
  }
});

els.batchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = await api("/api/profiles/batch", {
      method: "POST",
      body: JSON.stringify({
        prefix: els.prefix.value || "team",
        start: Number(els.start.value || 1),
        count: Number(els.count.value || 1),
        padding: 2,
      }),
    });
    for (const profile of payload.profiles || []) upsertProfile(profile);
    render();
    toast(`已预创建 ${(payload.profiles || []).length} 个账号环境`);
  } catch (error) {
    toast(error.message);
  }
});

els.body.addEventListener("click", async (event) => {
  const row = event.target.closest("tr[data-name]");
  if (!row) return;
  const name = row.dataset.name;
  try {
    if (event.target.closest(".js-open-chatgpt")) {
      await openProfile(name, linkForKind("official").url);
    } else if (event.target.closest(".js-open-register")) {
      await openRegisterStep(row);
    } else if (event.target.closest(".js-start-official-login")) {
      await startOfficialLogin(name);
    } else if (event.target.closest(".js-view-json")) {
      await showAuthJson(name);
    } else if (event.target.closest(".js-download-json")) {
      downloadAuthJson(name);
    } else if (event.target.closest(".js-copy-email")) {
      await copyText(cleanEmailField(row), "邮箱已复制");
    } else if (event.target.closest(".js-save")) {
      await saveProfile(row);
    } else if (event.target.closest(".js-delete")) {
      const profile = state.profiles.find((item) => item.name === name);
      if (!confirmDeleteProfile(profile)) return;
      await api(`/api/profiles/${encodeURIComponent(name)}`, { method: "DELETE" });
      removeProfile(name);
      render();
      toast(`已删除 ${name}`);
    }
  } catch (error) {
    toast(error.message);
  }
});

els.body.addEventListener("input", (event) => {
  const row = event.target.closest("tr[data-name]");
  if (!row) return;
  if (event.target.closest(".js-email")) {
    scheduleAutoSave(row, "email");
  }
});

els.body.addEventListener("focusout", (event) => {
  const row = event.target.closest("tr[data-name]");
  if (!row) return;
  if (event.target.closest(".js-profile-name")) {
    flushAutoSave(row, "name");
  }
});

els.body.addEventListener("keydown", (event) => {
  const row = event.target.closest("tr[data-name]");
  if (!row || event.key !== "Enter") return;
  if (event.target.closest(".js-profile-name")) {
    event.preventDefault();
    event.target.blur();
  }
});

Promise.all([loadProfiles(), loadAuthLinks()])
  .then(suggestName)
  .catch((error) => toast(error.message));
