/* ═══════════════════════════════════════════════════════════════════
   AI Enterprise Tool — Application Logic
   ═══════════════════════════════════════════════════════════════════ */

const API_BASE = '';

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

async function submitQuery() {
    const input = document.getElementById('queryInput');
    const query = input.value.trim();
    if (!query) return;

    const streamEnabled = document.getElementById('streamToggle').checked;

    // Hide empty state, show messages
    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.style.display = 'none';

    // Add user message
    addMessage('user', query);
    input.value = '';
    input.style.height = 'auto';

    // Disable send button
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
        msg.innerHTML = `
            <div class="message-avatar">🧠</div>
            <div class="message-body">
                <div class="message-content">${formatContent(content)}</div>
                ${metaHtml}
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
            refreshStatus();
        } else {
            resultEl.className = 'ingest-result error';
            resultEl.textContent = `✗ ${data.detail || 'Ingestion failed'}`;
        }
    } catch (err) {
        resultEl.className = 'ingest-result error';
        resultEl.textContent = `✗ Connection error: ${err.message}`;
    }

    btn.disabled = false;
    btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        Start Ingestion
    `;
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

// ── System Status ───────────────────────────────────────────────

async function refreshStatus() {
    try {
        const resp = await fetch(`${API_BASE}/health`);
        const data = await resp.json();

        setStatusPill('statusApi', 'Online', 'online');
        document.getElementById('statusApiDetail').textContent = `Version ${data.version}`;

        setStatusPill('statusKb', data.chunks_indexed > 0 ? 'Active' : 'Empty', data.chunks_indexed > 0 ? 'online' : 'warning');
        document.getElementById('statusKbDetail').textContent = `${data.chunks_indexed} chunks indexed`;

        // Update sidebar badge
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
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatContent(text) {
    // Basic markdown-like formatting
    let html = escapeHtml(text);
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Line breaks
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
    refreshStatus();
    // Refresh status every 30 seconds
    setInterval(refreshStatus, 30000);
});
