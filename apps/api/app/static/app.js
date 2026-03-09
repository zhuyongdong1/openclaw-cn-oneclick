function $(id) {
  return document.getElementById(id);
}

function setToken(token) {
  if (!token) {
    localStorage.removeItem("token");
    $("token").textContent = "(none)";
    return;
  }
  localStorage.setItem("token", token);
  $("token").textContent = token;
}

function getToken() {
  return localStorage.getItem("token") || "";
}

async function api(path, opts) {
  const o = opts || {};
  const headers = Object.assign({ "Content-Type": "application/json" }, o.headers || {});
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(path, Object.assign({}, o, { headers }));
  const text = await res.text();
  let json;
  try { json = text ? JSON.parse(text) : null; } catch { json = null; }
  if (!res.ok) {
    const msg = (json && (json.detail || json.message)) || text || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return json;
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
  if (!email || !password) {
    alert("Email and password required");
    return;
  }
  try {
    const out = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(out.access_token);
  } catch (e) {
    alert(String(e.message || e));
  }
}

function renderAudit(items) {
  const root = $("audit");
  root.innerHTML = "";
  if (!items || items.length === 0) {
    root.textContent = "(no audit logs)";
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

$("btn-health").addEventListener("click", checkHealth);
$("btn-login").addEventListener("click", doLogin);
$("btn-logout").addEventListener("click", () => setToken(""));
$("btn-audit").addEventListener("click", refreshAudit);

setToken(getToken());
checkHealth();
