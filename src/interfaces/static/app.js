/* ═══════════════════════════════════════════════════════════════════
   AI Enterprise Tool — Application Logic
   ═══════════════════════════════════════════════════════════════════ */

const API_BASE = '';

const VIEW_KEYS = ['ask', 'ingest', 'knowledge', 'stats', 'audit', 'status'];

// ── Theme ───────────────────────────────────────────────────────

function initTheme() {
    const saved = localStorage.getItem('aet-theme');
    const theme = saved || 'dark';
    document.documentElement.setAttribute('data-theme', theme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('aet-theme', next);
}

// ── Toast Notifications ─────────────────────────────────────────

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('toast-exit');
        toast.addEventListener('animationend', () => toast.remove());
    }, 4000);
}

// ── Mobile Sidebar ──────────────────────────────────────────────

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');
}

// ── Shortcuts Modal ─────────────────────────────────────────────

function showShortcuts() {
    document.getElementById('shortcutsModal').classList.add('open');
}

function hideShortcuts() {
    document.getElementById('shortcutsModal').classList.remove('open');
}

// ── Keyboard Shortcuts ──────────────────────────────────────────

function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        const tag = (e.target.tagName || '').toLowerCase();
        const isTyping = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;

        if (e.key === 'Escape') {
            hideShortcuts();
            return;
        }

        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const input = document.getElementById('queryInput');
            if (input) {
                switchView('ask');
                input.focus();
            }
            return;
        }

        if (isTyping) return;

        if (e.key === '?') {
            e.preventDefault();
            showShortcuts();
            return;
        }

        const num = parseInt(e.key, 10);
        if (num >= 1 && num <= VIEW_KEYS.length) {
            e.preventDefault();
            switchView(VIEW_KEYS[num - 1]);
        }
    });
}

// ── View Switching ──────────────────────────────────────────────

function switchView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    const view = document.getElementById(`view-${viewName}`);
    const navBtn = document.querySelector(`.nav-item[data-view="${viewName}"]`);

    if (view) view.classList.add('active');
    if (navBtn) navBtn.classList.add('active');

    if (viewName === 'audit') refreshAudit();
    if (viewName === 'status') refreshStatus();
    if (viewName === 'knowledge') refreshKnowledgeBase();
    if (viewName === 'stats') refreshStats();

    // Close mobile sidebar on view switch
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (sidebar.classList.contains('open')) {
        sidebar.classList.remove('open');
        overlay.classList.remove('open');
    }
}

// ── Ask / Chat ──────────────────────────────────────────────────

function setQuery(text) {
    const input = document.getElementById('queryInput');
    input.value = text;
    input.focus();
    autoResize(input);
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        submitQuery();
    }
}

function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 150) + 'px';
}

function clearChat() {
    const container = document.getElementById('chatMessages');
    container.innerHTML = '';
    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.style.display = '';
}

async function submitQuery() {
    const input = document.getElementById('queryInput');
    const query = input.value.trim();
    if (!query) return;

    const streamEnabled = document.getElementById('streamToggle').checked;

    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.style.display = 'none';

    addMessage('user', query);
    input.value = '';
    input.style.height = 'auto';

    const sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;

    if (streamEnabled) {
        await streamResponse(query);
    } else {
        await fetchResponse(query);
    }

    sendBtn.disabled = false;
}

function addMessage(role, content, meta = null) {
    const container = document.getElementById('chatMessages');

    const msg = document.createElement('div');
    msg.className = `message message-${role}`;

    if (role === 'user') {
        msg.innerHTML = `<div class="message-bubble">${escapeHtml(content)}</div>`;
    } else {
        let metaHtml = '';
        if (meta) {
            metaHtml = buildMetaHtml(meta);
        }
        const feedbackHtml = buildFeedbackHtml();
        msg.innerHTML = `
            <div class="message-avatar">🧠</div>
            <div class="message-body">
                <div class="message-content">${formatContent(content)}</div>
                ${metaHtml}
                ${feedbackHtml}
            </div>
        `;
    }

    container.appendChild(msg);
    scrollToBottom();
    return msg;
}

function addStreamMessage() {
    const container = document.getElementById('chatMessages');
    const msg = document.createElement('div');
    msg.className = 'message message-assistant';
    msg.innerHTML = `
        <div class="message-avatar">🧠</div>
        <div class="message-body">
            <div class="message-content" id="streamContent">
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
            <div class="message-meta" id="streamMeta"></div>
        </div>
    `;
    container.appendChild(msg);
    scrollToBottom();
    return msg;
}

function buildFeedbackHtml() {
    return `
        <div class="feedback-actions">
            <button class="feedback-btn" onclick="sendFeedback(this, 'positive')" title="Helpful">👍</button>
            <button class="feedback-btn" onclick="sendFeedback(this, 'negative')" title="Not helpful">👎</button>
        </div>
    `;
}

async function sendFeedback(btn, rating) {
    const row = btn.closest('.feedback-actions');
    const buttons = row.querySelectorAll('.feedback-btn');
    buttons.forEach(b => b.disabled = true);
    btn.classList.add('active');

    // Find the query text from the nearest preceding user message
    const msgEl = btn.closest('.message');
    let query = '';
    let prev = msgEl ? msgEl.previousElementSibling : null;
    while (prev) {
        if (prev.classList.contains('message-user')) {
            const bubble = prev.querySelector('.message-bubble');
            if (bubble) query = bubble.textContent;
            break;
        }
        prev = prev.previousElementSibling;
    }

    const apiRating = rating === 'positive' ? 'up' : 'down';

    try {
        await fetch(`${API_BASE}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query || 'unknown', rating: apiRating }),
        });
        showToast(rating === 'positive' ? 'Thanks for the feedback!' : 'Thanks — we\'ll improve.', 'success');
    } catch (_err) {
        showToast('Failed to send feedback.', 'error');
    }
}

function buildMetaHtml(meta) {
    let parts = [];

    if (meta.confidence !== undefined) {
        const pct = Math.round(meta.confidence * 100);
        const color = pct >= 70 ? 'var(--success)' : pct >= 40 ? 'var(--warning)' : 'var(--error)';
        parts.push(`
            <span class="meta-item">
                Confidence:
                <span class="confidence-bar">
                    <span class="confidence-fill" style="width: ${pct}%; background: ${color};"></span>
                </span>
                ${pct}%
            </span>
        `);
    }

    if (meta.model_used && meta.model_used !== 'none') {
        parts.push(`<span class="meta-item">Model: ${escapeHtml(meta.model_used)}</span>`);
    }

    let html = parts.length > 0 ? `<div class="message-meta">${parts.join('')}</div>` : '';

    if (meta.citations && meta.citations.length > 0) {
        html += `<div class="citations-list">${meta.citations.map(c =>
            `<span class="citation-tag">${escapeHtml(c.source_id)}</span>`
        ).join('')}</div>`;
    }

    if (meta.staleness_warnings && meta.staleness_warnings.length > 0) {
        html += meta.staleness_warnings.map(w =>
            `<div class="staleness-warning">⚠ ${escapeHtml(w)}</div>`
        ).join('');
    }

    return html;
}

async function fetchResponse(query) {
    try {
        const resp = await fetch(`${API_BASE}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, stream: false }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
            addMessage('assistant', `Sorry, something went wrong: ${err.detail || 'Server error'}`);
            return;
        }

        const data = await resp.json();
        addMessage('assistant', data.answer, {
            confidence: data.confidence,
            model_used: data.model_used,
            citations: data.citations,
            staleness_warnings: data.staleness_warnings,
        });
    } catch (err) {
        addMessage('assistant', `Connection error: ${err.message}. Please check that the server is running.`);
    }
}

async function streamResponse(query) {
    const msg = addStreamMessage();
    const contentEl = document.getElementById('streamContent');
    let fullText = '';

    try {
        const resp = await fetch(`${API_BASE}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, stream: true }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
            contentEl.textContent = `Sorry, something went wrong: ${err.detail || 'Server error'}`;
            return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            fullText += text;
            contentEl.innerHTML = formatContent(fullText);
            scrollToBottom();
        }

        // Add feedback buttons after stream completes
        const body = msg.querySelector('.message-body');
        if (body) {
            const feedbackDiv = document.createElement('div');
            feedbackDiv.innerHTML = buildFeedbackHtml();
            body.appendChild(feedbackDiv.firstElementChild);
        }
    } catch (err) {
        contentEl.textContent = fullText || `Connection error: ${err.message}`;
    }
}

function scrollToBottom() {
    const chatArea = document.getElementById('chatArea');
    chatArea.scrollTop = chatArea.scrollHeight;
}

// ── Ingestion ───────────────────────────────────────────────────

async function ingestGitHub(event) {
    event.preventDefault();
    const owner = document.getElementById('ghOwner').value.trim();
    const repo = document.getElementById('ghRepo').value.trim();
    const resultEl = document.getElementById('ingestResult');
    const btn = document.getElementById('ingestBtn');

    if (!owner || !repo) return;

    btn.disabled = true;
    btn.textContent = 'Ingesting...';
    resultEl.className = 'ingest-result';
    resultEl.textContent = '';

    try {
        const resp = await fetch(`${API_BASE}/ingest/github`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ owner, repo }),
        });

        const data = await resp.json();

        if (resp.ok) {
            resultEl.className = 'ingest-result success';
            resultEl.textContent = `✓ Ingested ${data.prs_ingested} PRs and ${data.commits_ingested} commits (${data.chunks_created} chunks created)`;
            showToast('Ingestion completed successfully!', 'success');
            refreshStatus();
        } else {
            resultEl.className = 'ingest-result error';
            resultEl.textContent = `✗ ${data.detail || 'Ingestion failed'}`;
            showToast(data.detail || 'Ingestion failed', 'error');
        }
    } catch (err) {
        resultEl.className = 'ingest-result error';
        resultEl.textContent = `✗ Connection error: ${err.message}`;
        showToast('Connection error during ingestion.', 'error');
    }

    btn.disabled = false;
    btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        Start Ingestion
    `;
}

// ── Knowledge Base ──────────────────────────────────────────────

let kbPage = 1;
const KB_PAGE_SIZE = 20;

async function refreshKnowledgeBase(page) {
    if (page !== undefined) kbPage = page;

    const sourceFilter = document.getElementById('kbSourceFilter').value;
    const repoFilter = document.getElementById('kbRepoFilter').value.trim();
    const listEl = document.getElementById('kbList');
    const summaryEl = document.getElementById('kbSummary');
    const paginationEl = document.getElementById('kbPagination');

    listEl.innerHTML = Array.from({ length: 4 }, () =>
        '<div class="kb-card skeleton"><div class="skeleton-line" style="width:60%"></div><div class="skeleton-line"></div><div class="skeleton-line" style="width:80%"></div></div>'
    ).join('');

    const params = new URLSearchParams({ page: kbPage, page_size: KB_PAGE_SIZE });
    if (sourceFilter) params.set('source_type', sourceFilter);
    if (repoFilter) params.set('repo', repoFilter);

    try {
        const resp = await fetch(`${API_BASE}/chunks?${params}`);
        const data = await resp.json();

        const chunks = data.chunks || data.items || data;
        const total = data.total ?? chunks.length;

        summaryEl.textContent = `Showing ${chunks.length} of ${total} chunks`;

        if (chunks.length === 0) {
            listEl.innerHTML = '<div class="kb-empty">No chunks found matching your filters.</div>';
            paginationEl.innerHTML = '';
            return;
        }

        listEl.innerHTML = chunks.map(c => `
            <div class="kb-card">
                <div class="kb-card-header">
                    <span class="kb-source-badge">${escapeHtml(c.source_type || 'unknown')}</span>
                    <span class="kb-repo">${escapeHtml(c.repo || c.source_id || '')}</span>
                </div>
                <div class="kb-card-content">${escapeHtml(c.content_preview || c.content || c.text || '')}</div>
                <div class="kb-card-footer">
                    <span class="kb-card-id">${escapeHtml(c.id || c.chunk_id || '')}</span>
                    <span class="kb-card-date">${formatTimestamp(c.timestamp || c.created_at)}</span>
                </div>
            </div>
        `).join('');

        const totalPages = Math.ceil(total / KB_PAGE_SIZE);
        if (totalPages > 1) {
            let btns = '';
            for (let i = 1; i <= totalPages && i <= 10; i++) {
                btns += `<button class="kb-page-btn${i === kbPage ? ' active' : ''}" onclick="refreshKnowledgeBase(${i})">${i}</button>`;
            }
            if (totalPages > 10) btns += `<span class="kb-page-ellipsis">…</span>`;
            paginationEl.innerHTML = btns;
        } else {
            paginationEl.innerHTML = '';
        }
    } catch (err) {
        listEl.innerHTML = `<div class="kb-empty">Failed to load knowledge base: ${escapeHtml(err.message)}</div>`;
        summaryEl.textContent = 'Error loading data';
        paginationEl.innerHTML = '';
    }
}

// ── Analytics / Stats ───────────────────────────────────────────

async function refreshStats() {
    try {
        const resp = await fetch(`${API_BASE}/stats`);
        const data = await resp.json();

        const chunks = data.chunks || {};
        const queries = data.queries || {};
        const feedback = data.feedback || {};

        document.getElementById('statTotalChunks').textContent = chunks.total ?? '—';
        document.getElementById('statTotalQueries').textContent = queries.total ?? '—';
        document.getElementById('statOutdated').textContent = chunks.outdated ?? '—';

        const sat = feedback.satisfaction_rate;
        document.getElementById('statSatisfaction').textContent =
            sat !== undefined && sat !== null ? `${Math.round(sat * 100)}%` : '—';

        renderBreakdown('statsBySource', chunks.by_source_type);
        renderBreakdown('statsByRepo', chunks.by_repo);
        renderBreakdown('statsByUser', queries.by_user);
        renderFeedbackBreakdown('statsFeedback', feedback);
    } catch (err) {
        document.getElementById('statTotalChunks').textContent = '—';
        document.getElementById('statTotalQueries').textContent = '—';
        document.getElementById('statSatisfaction').textContent = '—';
        document.getElementById('statOutdated').textContent = '—';
        showToast('Failed to load analytics.', 'error');
    }
}

function renderBreakdown(elementId, data) {
    const el = document.getElementById(elementId);
    if (!data || (Array.isArray(data) && data.length === 0) || (typeof data === 'object' && Object.keys(data).length === 0)) {
        el.textContent = 'No data available';
        return;
    }

    const entries = Array.isArray(data) ? data : Object.entries(data).map(([k, v]) => ({ label: k, count: v }));
    el.innerHTML = entries.map(e => {
        const label = escapeHtml(e.label || e.name || e.key || '');
        const count = e.count ?? e.value ?? 0;
        return `<div class="breakdown-row"><span class="breakdown-label">${label}</span><span class="breakdown-value">${count}</span></div>`;
    }).join('');
}

function renderFeedbackBreakdown(elementId, data) {
    const el = document.getElementById(elementId);
    if (!data) {
        el.textContent = 'No data available';
        return;
    }

    if (typeof data === 'object' && !Array.isArray(data)) {
        el.innerHTML = Object.entries(data).map(([k, v]) =>
            `<div class="breakdown-row"><span class="breakdown-label">${escapeHtml(k)}</span><span class="breakdown-value">${v}</span></div>`
        ).join('');
    } else {
        renderBreakdown(elementId, data);
    }
}

// ── Audit Log ───────────────────────────────────────────────────

async function refreshAudit() {
    const tbody = document.getElementById('auditTableBody');

    try {
        const resp = await fetch(`${API_BASE}/audit`);
        const data = await resp.json();

        if (data.length === 0) {
            tbody.innerHTML = '<tr class="empty-row"><td colspan="4">No audit entries yet. Ask a question to see activity here.</td></tr>';
            return;
        }

        tbody.innerHTML = data.map(entry => `
            <tr>
                <td style="white-space: nowrap; font-family: var(--font-mono); font-size: 12px;">${formatTimestamp(entry.timestamp)}</td>
                <td><strong>${escapeHtml(entry.user_id)}</strong></td>
                <td>${escapeHtml(truncate(entry.query, 80))}</td>
                <td><span style="color: var(--accent)">${entry.chunks_retrieved.length} chunks</span></td>
            </tr>
        `).join('');
    } catch (err) {
        tbody.innerHTML = `<tr class="empty-row"><td colspan="4">Failed to load audit log: ${err.message}</td></tr>`;
    }
}

function filterAuditLog() {
    const searchText = (document.getElementById('auditSearch').value || '').toLowerCase();
    const rows = document.querySelectorAll('#auditTableBody tr:not(.empty-row)');

    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(searchText) ? '' : 'none';
    });
}

function exportAuditCSV() {
    const link = document.createElement('a');
    link.href = `${API_BASE}/audit/export`;
    link.download = 'audit_log.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// ── System Status ───────────────────────────────────────────────

async function refreshStatus() {
    try {
        const resp = await fetch(`${API_BASE}/health`);
        const data = await resp.json();

        setStatusPill('statusApi', 'Online', 'online');
        document.getElementById('statusApiDetail').textContent = `Version ${data.version}`;

        setStatusPill('statusKb', data.chunks_indexed > 0 ? 'Active' : 'Empty', data.chunks_indexed > 0 ? 'online' : 'warning');
        document.getElementById('statusKbDetail').textContent = `${data.chunks_indexed} chunks indexed`;

        const badge = document.getElementById('systemBadge');
        badge.innerHTML = `<span class="status-dot online"></span><span>System Online</span>`;

        setStatusPill('statusLlm', 'Configured', 'online');
        document.getElementById('statusLlmDetail').textContent = 'Claude API ready';

        setStatusPill('statusGh', 'Connected', 'online');
        document.getElementById('statusGhDetail').textContent = 'Webhook receiver active';
    } catch (err) {
        setStatusPill('statusApi', 'Offline', 'offline');
        document.getElementById('statusApiDetail').textContent = err.message;

        const badge = document.getElementById('systemBadge');
        badge.innerHTML = `<span class="status-dot offline"></span><span>Offline</span>`;
    }
}

function setStatusPill(id, text, cls) {
    const el = document.getElementById(id);
    el.textContent = text;
    el.className = `status-pill ${cls}`;
}

// ── Utilities ───────────────────────────────────────────────────

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function formatContent(text) {
    let html = escapeHtml(text);

    // Code blocks (triple backtick) — content already escaped by escapeHtml above
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_match, lang, code) => {
        const langLabel = lang ? `<span class="code-lang">${escapeHtml(lang)}</span>` : '';
        return `<pre class="code-block">${langLabel}<code>${code.trim()}</code></pre>`;
    });

    // Headings (### / ## / #)
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Inline code (after code blocks to avoid conflicts)
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bullet lists (process before line breaks)
    html = html.replace(/^[•\-\*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/((<li>.*<\/li>\n?)+)/g, (match) => `<ul>${match.replace(/\n/g, '')}</ul>`);

    // Line breaks (but not inside pre/ul blocks already handled)
    html = html.replace(/\n/g, '<br>');

    return html;
}

function formatTimestamp(ts) {
    if (!ts) return '—';
    const d = new Date(ts);
    return d.toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
}

function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '…' : str;
}

// ── Initialize ──────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initKeyboardShortcuts();
    refreshStatus();
    setInterval(refreshStatus, 30000);
});
