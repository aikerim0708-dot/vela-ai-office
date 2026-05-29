// VELA AI Office — frontend JS

// ---------- Telegram WebApp SDK интеграция ----------
(function initTelegram() {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (!tg) return; // открыто в обычном браузере — без Telegram

  try {
    tg.ready();
    tg.expand();
    const tp = tg.themeParams || {};
    const root = document.documentElement.style;
    if (tp.bg_color) root.setProperty("--bg", tp.bg_color);
    if (tp.secondary_bg_color) root.setProperty("--card", tp.secondary_bg_color);
    if (tp.text_color) root.setProperty("--text", tp.text_color);
    if (tp.hint_color) root.setProperty("--text-muted", tp.hint_color);
    if (tp.button_color) root.setProperty("--primary", tp.button_color);
    if (tp.section_separator_color) root.setProperty("--border", tp.section_separator_color);
    window.VELA_INIT_DATA = tg.initData || "";
    window.VELA_USER = tg.initDataUnsafe && tg.initDataUnsafe.user;
    console.info("Telegram WebApp init:", { user: window.VELA_USER });
  } catch (e) {
    console.warn("Telegram init failed:", e);
  }
})();

const AGENT_AVATARS = {
  "max": "👨‍💼",
  "leo": "🦁",
  "anna": "📦",
  "zara": "💰",
  "eva": "🎨",
  "aikerim": "🌙",
};

const AGENT_COLORS = {
  "max": "#4f46e5",
  "leo": "#f59e0b",
  "anna": "#10b981",
  "zara": "#8b5cf6",
  "eva": "#ec4899",
};

async function api(path, options) {
  options = options || {};
  options.headers = options.headers || {};
  if (window.VELA_INIT_DATA) {
    options.headers["X-Telegram-Init-Data"] = window.VELA_INIT_DATA;
  }
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

// ---------- Goal box (главное поле — цель команде через Макса) ----------
function setGoal(text) {
  document.getElementById("goal-input").value = text;
  document.getElementById("goal-input").focus();
}

async function postGoal() {
  const goal = document.getElementById("goal-input").value.trim();
  if (!goal) return;

  const btn = document.getElementById("goal-btn");
  const resultBox = document.getElementById("goal-result");
  btn.disabled = true;
  btn.textContent = "Макс делегирует команде…";
  resultBox.classList.remove("show");
  resultBox.innerHTML = "";

  try {
    const res = await api("/goal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal }),
    });

    const delegationsHtml = (res.delegations || [])
      .map((d) => {
        const a = window._agentsCache.find((x) => x.slug === d.agent);
        const name = a ? a.name : d.agent;
        const avatar = a ? a.avatar_emoji : "🤖";
        return `<span class="delegation-badge">${avatar} ${name}</span>`;
      })
      .join("");

    const needsHtml = (res.needs_data_from_aikerim || []).length
      ? `<div class="plan"><strong>⚠️ Нужно от тебя:</strong> ${res.needs_data_from_aikerim.join(", ")}</div>`
      : "";

    resultBox.innerHTML = `
      <h3>🎯 Цель: ${escapeHtml(res.goal || goal)}</h3>
      ${res.plan ? `<div class="plan"><strong>План Макса:</strong> ${escapeHtml(res.plan)}</div>` : ""}
      ${needsHtml}
      ${delegationsHtml ? `<div class="delegations">Делегировал: ${delegationsHtml}</div>` : ""}
      <div class="final">${escapeHtml(res.final_summary)}</div>
    `;
    resultBox.classList.add("show");
    resultBox.scrollIntoView({ behavior: "smooth", block: "start" });

    // Обновим ленту активности и команду
    const tasks = await api("/tasks?limit=50");
    renderActivity(tasks.tasks);
  } catch (err) {
    resultBox.innerHTML = `<div class="final">Ошибка: ${escapeHtml(err.message)}</div>`;
    resultBox.classList.add("show");
  } finally {
    btn.disabled = false;
    btn.textContent = "Поставить задачу команде";
  }
}

// ---------- Home page ----------
const KZT_RATE = 6.60; // курс ₽→₸ (из юнит-экономики VELA)

async function renderHome() {
  // 1. Дайджест Макса (KPI вверху)
  loadVelaKpi();

  // 2. Команда (заполняем кэш агентов — нужен для решений и goal-result)
  const { agents } = await api("/agents");
  window._agentsCache = agents;

  // 3. Решения, ждущие Айкерим (открытые гипотезы) — после кэша агентов
  loadDecisions();

  const grid = document.getElementById("team-grid");
  grid.innerHTML = agents
    .map((a) => {
      const color = a.color || AGENT_COLORS[a.slug] || "#4f46e5";
      const avatar = a.avatar_emoji || AGENT_AVATARS[a.slug] || a.name[0];
      return `
      <a class="team-card" href="/agent/${a.slug}">
        <div class="team-avatar status-online" style="background: ${color}">${avatar}</div>
        <div class="name">${a.name}</div>
        <div class="role">${a.title || a.role}</div>
      </a>`;
    })
    .join("");

  // 4. Свёрнутые блоки — активность, inbox, файлы
  const tasks = await api("/tasks?limit=50");
  renderActivity(tasks.tasks);
  loadUploads();
  loadInboxList();

  // WB-токен — НЕ дёргаем автоматом (WB лимитит 429). Только кэш.
  const lastOk = parseInt(localStorage.getItem("wb_last_ok") || "0", 10);
  const wbStatus = document.getElementById("wb-status");
  if (wbStatus) {
    if (Date.now() - lastOk < 5 * 60 * 1000) {
      wbStatus.textContent = "🟢 живой";
      wbStatus.className = "wb-status ok";
    } else {
      wbStatus.textContent = "—";
      wbStatus.className = "wb-status";
    }
  }
}

// ---------- Дайджест Макса (KPI + сводка) ----------
async function loadVelaKpi() {
  try {
    const r = await api("/digest/morning");
    const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("ru-RU"));

    const revKzt = r.revenue_rub == null ? null : Math.round(r.revenue_rub * KZT_RATE);
    setText("kpi-revenue-kzt", revKzt == null ? "—" : fmt(revKzt));
    setText("kpi-orders", fmt(r.orders_count));
    setDrr("kpi-drr-razors", r.razors?.drr_pct);
    setDrr("kpi-drr-lashes", r.lashes?.drr_pct);
    setText("digest-date", `за ${formatDateShort(r.yesterday)}`);

    // Сводка-текст под KPI: флаги или базовая строка
    const summary = document.getElementById("digest-summary");
    if (summary) {
      if (r.flags && r.flags.length) {
        summary.innerHTML = r.flags
          .map((f) => `<span class="flag-${f.level}">${flagEmoji(f.level)} ${escapeHtml(f.text)}</span>`)
          .join("<br>");
      } else {
        summary.textContent =
          `🟢 Всё под контролем. ${fmt(r.orders_count)} заказов, ` +
          `${fmt(Math.round((r.revenue_rub || 0) * KZT_RATE))} ₸ выручки, ` +
          `${r.open_hypotheses} гипотез в работе.`;
      }
    }
  } catch (e) {
    console.error("Digest load error", e);
    const summary = document.getElementById("digest-summary");
    if (summary) summary.textContent = "⚠️ Не удалось загрузить данные WB.";
  }
}

function formatDateShort(iso) {
  if (!iso) return "вчера";
  const d = new Date(iso);
  if (isNaN(d)) return "вчера";
  const months = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"];
  return `${d.getDate()} ${months[d.getMonth()]}`;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setDrr(id, drr) {
  const el = document.getElementById(id);
  if (!el) return;
  if (drr == null) { el.textContent = "—"; el.className = "dkpi-val"; return; }
  el.textContent = drr + "%";
  // Норма ДРР ≤ 25% (язык ВБ): зелёный/жёлтый/красный
  el.className = "dkpi-val " + (drr <= 25 ? "drr-ok" : drr <= 50 ? "drr-warn" : "drr-bad");
}

function flagEmoji(level) {
  return { red: "🚨", yellow: "🟡", blue: "🔵", green: "🟢" }[level] || "•";
}

// ---------- Ждут твоего решения (открытые гипотезы) ----------
async function loadDecisions() {
  const section = document.getElementById("decisions-section");
  const list = document.getElementById("decisions-list");
  if (!section || !list) return;
  try {
    const r = await api("/brain/hypotheses?status=open");
    const hyps = r.hypotheses || [];
    if (!hyps.length) { section.style.display = "none"; return; }

    setText("decisions-count", hyps.length);
    section.style.display = "";
    list.innerHTML = hyps
      .slice(0, 6)
      .map((h) => {
        const who = (window._agentsCache || []).find((a) => a.slug === h.author_slug);
        const avatar = who ? (who.avatar_emoji || who.name[0]) : "🤖";
        const meta = [h.metric, h.target, h.deadline].filter(Boolean).join(" · ");
        return `<div class="decision-row" data-id="${h.id}">
          <div class="decision-head">${avatar} <strong>${escapeHtml(h.title)}</strong></div>
          ${h.action ? `<div class="decision-action">${escapeHtml(h.action)}</div>` : ""}
          ${meta ? `<div class="decision-meta">${escapeHtml(meta)}</div>` : ""}
          <div class="decision-btns">
            <button class="btn-yes" onclick="decideHypothesis(${h.id}, 'accepted')">✅ Запускаем</button>
            <button class="btn-no" onclick="decideHypothesis(${h.id}, 'rejected')">✕ Не сейчас</button>
          </div>
        </div>`;
      })
      .join("");
  } catch (e) {
    console.error("Decisions load error", e);
    section.style.display = "none";
  }
}

async function decideHypothesis(id, decision) {
  const row = document.querySelector(`.decision-row[data-id="${id}"]`);
  if (row) row.style.opacity = "0.5";
  try {
    await api(`/brain/hypotheses/${id}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    await loadDecisions();
  } catch (e) {
    if (row) row.style.opacity = "1";
    alert("Не удалось сохранить решение: " + e.message);
  }
}

// ---------- Knowledge Inbox ----------
async function loadInboxList() {
  try {
    const r = await api("/inbox");
    const items = r.items || [];
    const pending = items.filter((i) => i.status === "pending");
    const pendingBadge = document.getElementById("inbox-pending");
    if (pendingBadge) pendingBadge.textContent = pending.length;

    const list = document.getElementById("inbox-list");
    if (!list) return;
    if (items.length === 0) {
      list.innerHTML = `<div class="hint" style="opacity:.7">Inbox пуст. Кидай сюда новости WB, скрины конкурентов, заметки.</div>`;
      return;
    }
    list.innerHTML = items
      .slice(0, 12)
      .map((i) => {
        const kindMap = {
          wb_news: "📢 WB", competitor: "🎯 конкурент", price_change: "💰 цена",
          supply: "📦 поставка", review: "⭐ отзыв", other: "📝 другое", unknown: "❓",
        };
        const tag = kindMap[i.kind] || i.kind;
        const statusEmoji = i.status === "pending" ? "⏳" : "✅";
        const fileBit = i.filename ? ` 📎` : "";
        return `<div class="inbox-row ${i.status}">
          <div class="inbox-head">${statusEmoji} <span class="inbox-tag">${tag}</span> ${escapeHtml(i.note.slice(0, 80))}${fileBit}</div>
          ${i.processed_summary ? `<div class="inbox-summary">${escapeHtml(i.processed_summary)}</div>` : ""}
          <div class="inbox-meta">${formatTime(i.created_at)}${i.triggers_chain ? ` · 🔗 цепочка: ${i.triggers_chain}` : ""}</div>
        </div>`;
      })
      .join("");
  } catch (e) {
    console.error("Inbox load error", e);
  }
}

async function addInbox() {
  const t = document.getElementById("inbox-note");
  const note = t.value.trim();
  if (!note) return;
  try {
    await api("/inbox", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    });
    t.value = "";
    await loadInboxList();
  } catch (e) {
    alert("Не сохранилось: " + e.message);
  }
}

async function uploadInboxFile(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  const note = document.getElementById("inbox-note").value.trim();
  const fd = new FormData();
  fd.append("file", file);
  if (note) fd.append("note", note);
  try {
    const res = await fetch("/api/inbox/upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    document.getElementById("inbox-note").value = "";
    ev.target.value = "";
    await loadInboxList();
  } catch (e) {
    alert("Не загрузилось: " + e.message);
  }
}

async function processInbox() {
  const btn = document.getElementById("inbox-process-btn");
  btn.disabled = true;
  btn.textContent = "Макс читает…";
  try {
    const r = await fetch("/api/inbox/process", { method: "POST" });
    const j = await r.json();
    if (!r.ok) {
      alert("Ошибка: " + (j.detail || JSON.stringify(j)));
      return;
    }
    await loadInboxList();
    await loadVelaKpi();
    const chains = j.chains?.length ? `\n\nЗапущено цепочек: ${j.chains.length}` : "";
    alert(`Обработано: ${j.processed}${chains}`);
  } catch (e) {
    alert("Ошибка: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "🧠 Макс, обработай";
  }
}

async function checkWBHealth() {
  const el = document.getElementById("wb-status");
  if (!el) return;
  el.textContent = "проверка…";
  el.className = "wb-status";
  try {
    const r = await api("/wb/health");
    if (r.ok) {
      el.textContent = r.cached ? "🟢 токен живой (кэш)" : "🟢 токен живой";
      el.className = "wb-status ok";
      localStorage.setItem("wb_last_ok", Date.now().toString());
    } else if (r.status === 429) {
      el.textContent = "🟡 WB rate-limit, подожди 1–2 мин";
      el.className = "wb-status";
      el.title = r.error || "";
    } else {
      el.textContent = `🔴 ${r.status || "ошибка"}`;
      el.title = r.error || "";
      el.className = "wb-status fail";
    }
  } catch (e) {
    el.textContent = "🔴 нет связи";
    el.className = "wb-status fail";
  }
}

async function loadUploads() {
  const box = document.getElementById("uploads-list");
  if (!box) return;
  try {
    const r = await api("/uploads");
    if (!r.files.length) {
      box.innerHTML = `<div class="hint" style="opacity:.7">Файлов пока нет. Прикрепи Excel — Лео/Зара прочитают.</div>`;
      return;
    }
    box.innerHTML = r.files
      .map(
        (f) => `
        <div class="upload-row">
          <span class="upload-name">📄 ${f.name}</span>
          <span class="upload-meta">${f.size_kb} KB</span>
          <button class="btn-link" onclick="deleteUpload('${f.name.replace(/'/g, "\\'")}')">×</button>
        </div>`
      )
      .join("");
  } catch (e) {
    box.innerHTML = `<div class="hint" style="color:#dc2626">Ошибка загрузки списка: ${e.message}</div>`;
  }
}

async function uploadFile(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const box = document.getElementById("uploads-list");
  if (box) box.innerHTML = `<div class="hint">Загружаю ${file.name}…</div>`;
  try {
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    await loadUploads();
    ev.target.value = "";
  } catch (e) {
    alert("Не загрузилось: " + e.message);
  }
}

async function deleteUpload(name) {
  if (!confirm(`Удалить ${name}?`)) return;
  await fetch(`/api/uploads/${encodeURIComponent(name)}`, { method: "DELETE" });
  loadUploads();
}

function endingFor(n) {
  const last = n % 10;
  const lastTwo = n % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return "";
  if (last === 1) return "а";
  if (last >= 2 && last <= 4) return "и";
  return "";
}

function renderActivity(tasks) {
  const list = document.getElementById("activity-list");
  if (!tasks || tasks.length === 0) {
    list.innerHTML = `<div class="activity-item">
      <div class="status-icon">∅</div>
      <div class="content">
        <div class="title">Пока пусто</div>
        <div class="meta">Запусти агента — здесь появится история</div>
      </div>
    </div>`;
    return;
  }

  list.innerHTML = tasks
    .slice(0, 8)
    .map((t) => {
      const time = formatTime(t.created_at);
      const mockBadge = t.is_mock
        ? '<span class="mock-badge">mock</span>'
        : "";
      return `<a class="activity-item" href="/agent/${t.agent_slug}">
        <div class="status-icon">✓</div>
        <div class="content">
          <div class="title">${escapeHtml(t.prompt)} ${mockBadge}</div>
          <div class="meta">${t.agent_slug} · ${time}</div>
        </div>
      </a>`;
    })
    .join("");
}

function formatTime(iso) {
  const d = new Date(iso);
  const now = new Date();
  const diffMin = Math.floor((now - d) / 60000);
  if (diffMin < 1) return "только что";
  if (diffMin < 60) return `${diffMin}м назад`;
  if (diffMin < 60 * 24) return `${Math.floor(diffMin / 60)}ч назад`;
  return d.toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ---------- Agent page ----------
async function renderAgentPage() {
  const slug = window.location.pathname.split("/").pop();
  const agent = await api(`/agents/${slug}`);

  document.title = `${agent.name} — VELA AI Office`;
  document.getElementById("agent-name").textContent = agent.name;
  document.getElementById("agent-role").textContent = agent.role;
  document.getElementById("agent-hero-name").textContent = agent.name;
  document.getElementById("agent-hero-role").textContent = agent.role;
  document.getElementById("agent-metric").textContent = "🎯 " + agent.primary_metric;
  document.getElementById("agent-avatar").textContent = AGENT_AVATARS[slug] || agent.name[0];

  // Шаблоны
  const templateList = document.getElementById("template-list");
  templateList.innerHTML = (agent.templates || [])
    .map(
      (t, i) => `<div class="template-item" data-prompt="${escapeAttr(t.prompt)}">
        <div class="title">${t.title}</div>
        <div class="preview">${t.prompt}</div>
      </div>`
    )
    .join("");

  // Клик по шаблону → вставить в textarea
  templateList.querySelectorAll(".template-item").forEach((el) => {
    el.addEventListener("click", () => {
      document.getElementById("task-prompt").value = el.dataset.prompt;
      document.getElementById("task-prompt").focus();
    });
  });

  // Submit
  document.getElementById("task-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = document.getElementById("task-prompt").value.trim();
    if (!prompt) return;

    const btn = e.target.querySelector(".btn");
    const resultBox = document.getElementById("result-box");
    btn.disabled = true;
    btn.textContent = "Агент работает…";
    resultBox.style.display = "none";

    try {
      const result = await api("/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_slug: slug, prompt }),
      });
      resultBox.textContent = result.output;
      resultBox.style.display = "block";
      resultBox.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      resultBox.textContent = "Ошибка: " + err.message;
      resultBox.style.display = "block";
    } finally {
      btn.disabled = false;
      btn.textContent = "Запустить агента";
    }
  });
}

function escapeAttr(s) {
  return s.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ---------- Tasks page ----------
async function renderTasksPage() {
  const { tasks } = await api("/tasks?limit=100");
  document.getElementById("tasks-summary").textContent =
    tasks.length === 0
      ? "Пока пусто — запусти первого агента"
      : `Всего записей: ${tasks.length}`;

  const list = document.getElementById("tasks-list");
  if (tasks.length === 0) {
    list.innerHTML = `<div class="activity-item">
      <div class="status-icon">∅</div>
      <div class="content">
        <div class="title">История пуста</div>
        <div class="meta">Перейди в Агенты и запусти задачу</div>
      </div>
    </div>`;
    return;
  }

  // Получим имена агентов для маппинга slug → name
  const { agents } = await api("/agents");
  const agentNames = Object.fromEntries(agents.map((a) => [a.slug, a.name]));

  list.innerHTML = tasks
    .map((t) => {
      const time = formatTime(t.created_at);
      const mockBadge = t.is_mock ? '<span class="mock-badge">mock</span>' : "";
      const name = agentNames[t.agent_slug] || t.agent_slug;
      return `<a class="activity-item" href="/agent/${t.agent_slug}">
        <div class="status-icon">✓</div>
        <div class="content">
          <div class="title">${escapeHtml(t.prompt)} ${mockBadge}</div>
          <div class="meta">${name} · ${time}</div>
        </div>
      </a>`;
    })
    .join("");
}

// ---------- Chat page (AI Office / Чат) ----------
let _chatPollInterval = null;

let _chatChannel = "group";
let _chatSending = false;

async function renderChatPage() {
  // авто-рост textarea
  const ta = document.getElementById("chat-input");
  if (ta) {
    ta.addEventListener("input", () => {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
    });
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
  }
  await loadChatThread(true);
  if (_chatPollInterval) clearInterval(_chatPollInterval);
  _chatPollInterval = setInterval(() => loadChatThread(false), 15000);
}

function switchChannel(channel) {
  if (_chatChannel === channel) return;
  _chatChannel = channel;
  document.querySelectorAll(".chat-tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.channel === channel)
  );
  document.getElementById("chat-title").textContent =
    channel === "max_dm" ? "Макс — твой COO" : "Чат команды";
  document.getElementById("chat-hint").textContent =
    channel === "max_dm"
      ? "Личный чат с Максом. Он помнит контекст переписки."
      : "Без @ — Макс созывает команду. С @Лео / @Зара — ответит один агент.";
  const ta = document.getElementById("chat-input");
  if (ta) ta.placeholder = channel === "max_dm" ? "Написать Максу…" : "Сообщение команде…";
  loadChatThread(true);
}

async function loadChatThread(scroll) {
  const { posts } = await api(`/chat?limit=80&channel=${_chatChannel}`);
  const thread = document.getElementById("chat-thread");
  // posts приходят desc — разворачиваем в хронологию
  const ordered = posts.slice().reverse();

  if (!ordered.length) {
    thread.innerHTML = `<div class="chat-empty">${
      _chatChannel === "max_dm"
        ? "👨‍💼 Напиши Максу — он твоя правая рука. Поставь цель, спроси что с цифрами, обсуди идею."
        : "👥 Чат команды пуст. Напиши сообщение — Макс соберёт команду, или позови одного: @Лео, @Анна, @Зара, @Ева."
    }</div>`;
    return;
  }

  thread.innerHTML = ordered.map((p) => renderBubble(p)).join("");
  if (scroll !== false) scrollChatToBottom();
}

function scrollChatToBottom() {
  // .chat-thread не отдельный скролл-контейнер — скроллим окно вниз
  requestAnimationFrame(() => window.scrollTo(0, document.body.scrollHeight));
}

function renderBubble(p) {
  const time = formatTime(p.created_at);
  if (p.is_me) {
    return `<div class="bubble-row me">
      <div class="bubble bubble-me">
        <div class="bubble-text">${escapeHtml(p.body)}</div>
        <div class="bubble-time">${time}</div>
      </div>
    </div>`;
  }
  const color = AGENT_COLORS[p.author_slug] || "#4f46e5";
  return `<div class="bubble-row them">
    <div class="bubble-avatar" style="background:${color}">${p.author_avatar}</div>
    <div class="bubble bubble-them">
      <div class="bubble-author">${escapeHtml(p.author_name)}</div>
      <div class="bubble-text">${escapeHtml(p.body)}</div>
      <div class="bubble-time">${time}</div>
    </div>
  </div>`;
}

async function sendChat() {
  if (_chatSending) return;
  const ta = document.getElementById("chat-input");
  const text = ta.value.trim();
  if (!text) return;

  _chatSending = true;
  const btn = document.getElementById("chat-send");
  btn.disabled = true;
  ta.value = "";
  ta.style.height = "auto";

  // оптимистично показываем своё сообщение + индикатор печати
  const thread = document.getElementById("chat-thread");
  const isDM = _chatChannel === "max_dm";
  const emptyEl = thread.querySelector(".chat-empty");
  if (emptyEl) emptyEl.remove();
  thread.insertAdjacentHTML("beforeend", `<div class="bubble-row me">
    <div class="bubble bubble-me"><div class="bubble-text">${escapeHtml(text)}</div></div>
  </div>`);
  const typingWho = isDM ? "Макс печатает…" : "Команда думает…";
  thread.insertAdjacentHTML("beforeend",
    `<div class="bubble-row them" id="typing-row">
      <div class="bubble bubble-them typing">${typingWho}</div>
    </div>`);
  scrollChatToBottom();

  try {
    const endpoint = isDM ? "/chat/max" : "/chat/send";
    await api(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    await loadChatThread(true);
  } catch (e) {
    const t = document.getElementById("typing-row");
    if (t) t.querySelector(".bubble").textContent = "⚠️ Ошибка: " + e.message;
  } finally {
    _chatSending = false;
    btn.disabled = false;
  }
}

// ---------- Brain VELA ----------
async function renderBrainPage() {
  await renderBrainTab("hypotheses");
}

async function renderBrainTab(tab) {
  document.querySelectorAll(".brain-tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === tab);
  });

  const container = document.getElementById("brain-content");
  container.innerHTML = "Загрузка…";

  if (tab === "hypotheses") {
    const { hypotheses } = await api("/brain/hypotheses");
    if (!hypotheses.length) {
      container.innerHTML = `<div class="brain-card">
        <div class="head"><div class="title">Гипотез пока нет</div></div>
        <div style="font-size:13px;color:var(--text-muted)">Каждая гипотеза = метрика + срок + критерий + что делаем если не зашло. Агенты записывают сюда автоматически.</div>
      </div>`;
      return;
    }
    container.innerHTML = hypotheses
      .map((h) => `<div class="brain-card">
        <div class="head">
          <div class="title">${escapeHtml(h.title)}</div>
          <span class="status status-${h.status}">${h.status}</span>
        </div>
        <div class="row"><span class="label">Действие</span><span class="val">${escapeHtml(h.action)}</span></div>
        <div class="row"><span class="label">Метрика</span><span class="val">${escapeHtml(h.metric)}</span></div>
        <div class="row"><span class="label">Критерий</span><span class="val">${escapeHtml(h.target)}</span></div>
        <div class="row"><span class="label">Срок</span><span class="val">${h.deadline || "—"}</span></div>
        <div class="row"><span class="label">Если не зашло</span><span class="val">${escapeHtml(h.fallback)}</span></div>
        ${h.result ? `<div class="row"><span class="label">Результат</span><span class="val">${escapeHtml(h.result)}</span></div>` : ""}
        <div class="author">Автор: ${h.author_slug} · ${formatTime(h.created_at)}</div>
      </div>`)
      .join("");
  } else if (tab === "events") {
    const { events } = await api("/brain/events");
    if (!events.length) {
      container.innerHTML = `<div class="brain-card">
        <div class="head"><div class="title">Событий нет</div></div>
        <div style="font-size:13px;color:var(--text-muted)">Просадки, рост, праздники, баги WB — всё пишется сюда чтобы команда помнила контекст.</div>
      </div>`;
      return;
    }
    container.innerHTML = events
      .map((e) => `<div class="brain-card">
        <div class="head">
          <div class="title">${escapeHtml(e.title)}</div>
          <span class="status status-open">${e.kind}</span>
        </div>
        <div class="row"><span class="label">Дата</span><span class="val">${e.date}</span></div>
        <div class="row"><span class="label">Описание</span><span class="val">${escapeHtml(e.description)}</span></div>
        ${e.impact_on_orders ? `<div class="row"><span class="label">Эффект</span><span class="val">${escapeHtml(e.impact_on_orders)}</span></div>` : ""}
        <div class="author">${e.created_by} · ${formatTime(e.created_at)}</div>
      </div>`)
      .join("");
  } else if (tab === "summary") {
    const { summary } = await api("/brain/summary");
    container.innerHTML = `<div class="brain-card">
      <div class="head"><div class="title">Сводка Brain VELA</div></div>
      <pre style="white-space:pre-wrap;font-family:inherit;font-size:13px;line-height:1.6;margin:0">${escapeHtml(summary)}</pre>
    </div>`;
  }
}

// ---------- More page ----------
async function renderMorePage() {
  try {
    const h = await api("/health");
    document.getElementById("provider").textContent =
      h.provider === "mock" ? "MockAgentProvider (заглушки)" : h.provider;
    document.getElementById("agents-count").textContent = h.agents_count;
    document.getElementById("server-time").textContent = new Date(h.time).toLocaleString("ru-RU");
  } catch (e) {
    document.getElementById("provider").textContent = "ошибка";
  }
}
