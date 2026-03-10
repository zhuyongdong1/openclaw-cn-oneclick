function $(id) { return document.getElementById(id); }

function setToken(token) {
  if (!token) {
    localStorage.removeItem("token");
    return;
  }
  localStorage.setItem("token", token);
}
function getToken() { return localStorage.getItem("token") || ""; }

async function api(path, opts) {
  const o = opts || {};
  const headers = Object.assign({ "Content-Type": "application/json" }, o.headers || {});
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(path, Object.assign({}, o, { headers }));
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch {}
  if (!res.ok) throw new Error((json && (json.detail || json.message)) || text || `HTTP ${res.status}`);
  return json;
}

function msg(text, danger = false) {
  const el = $("config-msg");
  el.textContent = text;
  el.className = danger ? "danger" : "hint";
}

function fillConfig(c) {
  $("deepseek_base_url").value = c.deepseek_base_url || "";
  $("feishu_app_id").value = c.feishu_app_id || "";
  $("openclaw_gateway_port").value = c.openclaw_gateway_port || "18789";
  $("openclaw_bridge_port").value = c.openclaw_bridge_port || "18790";
  msg(`已读取（密钥不会明文回显）: DeepSeek ${c.deepseek_api_key_masked || "(空)"} / 飞书Secret ${c.feishu_app_secret_masked || "(空)"}`);
}

async function checkHealth() {
  $("health-out").textContent = "checking...";
  try {
    const out = await api("/healthz", { method: "GET" });
    $("health-out").textContent = JSON.stringify(out);
  } catch (e) {
    $("health-out").textContent = String(e.message || e);
  }
}

async function doLogin() {
  const email = $("email").value.trim();
  const password = $("password").value;
  if (!email || !password) return alert("请先输入邮箱和密码");
  try {
    const out = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    setToken(out.access_token);
    msg("登录成功");
    await loadConfig();
  } catch (e) {
    alert(String(e.message || e));
  }
}

function getConfigPayload() {
  return {
    deepseek_api_key: $("deepseek_api_key").value.trim(),
    deepseek_base_url: $("deepseek_base_url").value.trim(),
    feishu_app_id: $("feishu_app_id").value.trim(),
    feishu_app_secret: $("feishu_app_secret").value.trim(),
    feishu_webhook: $("feishu_webhook").value.trim(),
    openclaw_gateway_token: $("openclaw_gateway_token").value.trim(),
    openclaw_gateway_port: $("openclaw_gateway_port").value.trim() || "18789",
    openclaw_bridge_port: $("openclaw_bridge_port").value.trim() || "18790",
  };
}

async function loadConfig() {
  try {
    const out = await api("/admin/config", { method: "GET" });
    fillConfig(out);
  } catch (e) {
    msg(String(e.message || e), true);
  }
}

async function saveConfig(apply = false) {
  try {
    const payload = getConfigPayload();
    const out = await api("/admin/config", { method: "POST", body: JSON.stringify(payload) });
    msg(`保存成功：${(out.saved || []).join(", ") || "(无)"}`);
    if (apply) {
      msg("正在应用配置并重启 Gateway...");
      const a = await api("/admin/config/apply", { method: "POST" });
      msg(a.ok ? "已生效：Gateway 重启成功" : `应用失败：${a.message}`, !a.ok);
    }
  } catch (e) {
    msg(String(e.message || e), true);
  }
}

function renderAudit(items) {
  const root = $("audit");
  root.innerHTML = "";
  if (!items || items.length === 0) {
    root.textContent = "(暂无日志)";
    return;
  }
  for (const it of items) {
    const div = document.createElement("div");
    div.className = "audit-item";
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.innerHTML = `<span>${it.created_at}</span><span>${it.actor_email} · ${it.action}</span>`;
    const detail = document.createElement("div");
    detail.className = "detail";
    detail.textContent = it.detail;
    div.appendChild(meta);
    div.appendChild(detail);
    root.appendChild(div);
  }
}

async function refreshAudit() {
  const root = $("audit");
  root.textContent = "loading...";
  try {
    const items = await api("/admin/audit?limit=50", { method: "GET" });
    renderAudit(items);
  } catch (e) {
    root.textContent = String(e.message || e);
  }
}

$("btn-login").addEventListener("click", doLogin);
$("btn-logout").addEventListener("click", () => { setToken(""); msg("已退出"); });
$("btn-health").addEventListener("click", checkHealth);
$("btn-load").addEventListener("click", loadConfig);
$("btn-save").addEventListener("click", () => saveConfig(false));
$("btn-apply").addEventListener("click", () => saveConfig(true));
$("btn-audit").addEventListener("click", refreshAudit);

checkHealth();
