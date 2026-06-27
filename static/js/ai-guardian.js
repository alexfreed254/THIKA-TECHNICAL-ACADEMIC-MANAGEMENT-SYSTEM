/**
 * TTTI Guardian — AI Academic Assistant
 * Shared widget for all portal base templates.
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'ttti_ai_chat';
  const MAX_HISTORY = 40;

  let aiTyping = false;
  let lastFailedQuery = null;
  let meta = null;

  const fab    = document.getElementById('ai-fab');
  const panel  = document.getElementById('ai-panel');
  const msgs   = document.getElementById('ai-messages');
  const input  = document.getElementById('ai-input');
  const sendBtn = document.getElementById('ai-send-btn');
  const chips  = document.getElementById('ai-chips');
  const hdrSub = document.getElementById('ai-hdr-sub');

  if (!fab || !panel || !msgs || !input) return;

  /* ── Utilities ─────────────────────────────────────────────── */
  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function nowTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function formatReply(text) {
    if (!text) return '';
    const lines = String(text).split('\n');
    let html = '';
    let inList = false;

    lines.forEach(function (line) {
      const trimmed = line.trim();
      if (trimmed.startsWith('• ') || trimmed.startsWith('- ')) {
        if (!inList) { html += '<ul>'; inList = true; }
        const item = esc(trimmed.slice(2)).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html += '<li>' + item + '</li>';
      } else {
        if (inList) { html += '</ul>'; inList = false; }
        if (trimmed) {
          let seg = esc(trimmed).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
          seg = seg.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
          seg = seg.replace(/(\/[a-z][\w\-\/]*)/gi, function (m) {
            if (m.length < 3 || m.includes('//')) return m;
            return '<a href="' + m + '">' + m + '</a>';
          });
          html += '<p style="margin:0 0 4px">' + seg + '</p>';
        }
      }
    });
    if (inList) html += '</ul>';
    return html || esc(text);
  }

  function saveHistory() {
    try {
      const items = [];
      msgs.querySelectorAll('.ai-msg-wrap').forEach(function (wrap) {
        const msg = wrap.querySelector('.ai-msg');
        if (!msg || msg.classList.contains('typing')) return;
        const role = wrap.classList.contains('user') ? 'user' : 'bot';
        items.push({ role: role, text: msg.dataset.raw || msg.textContent });
      });
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(-MAX_HISTORY)));
    } catch (e) { /* ignore */ }
  }

  function loadHistory() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const items = JSON.parse(raw);
      if (!Array.isArray(items) || !items.length) return false;
      items.forEach(function (item) { addMsg(item.text, item.role, true); });
      return true;
    } catch (e) { return false; }
  }

  /* ── Messages ──────────────────────────────────────────────── */
  function addMsg(text, role, skipSave) {
    const wrap = document.createElement('div');
    wrap.className = 'ai-msg-wrap ' + role;

    const time = document.createElement('div');
    time.className = 'ai-msg-time';
    time.textContent = nowTime();

    const div = document.createElement('div');
    div.className = 'ai-msg ' + role;
    div.dataset.raw = text;

    if (role === 'bot') {
      div.innerHTML = formatReply(text);
      const actions = document.createElement('div');
      actions.className = 'ai-msg-actions';
      const copyBtn = document.createElement('button');
      copyBtn.className = 'ai-msg-action';
      copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy';
      copyBtn.onclick = function () {
        navigator.clipboard.writeText(text).then(function () {
          copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied';
          setTimeout(function () { copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy'; }, 1500);
        });
      };
      actions.appendChild(copyBtn);
      wrap.appendChild(time);
      wrap.appendChild(div);
      wrap.appendChild(actions);
    } else {
      div.textContent = text;
      wrap.appendChild(time);
      wrap.appendChild(div);
    }

    msgs.appendChild(wrap);
    msgs.scrollTop = msgs.scrollHeight;
    if (!skipSave) saveHistory();
    return wrap;
  }

  function addTyping() {
    const wrap = document.createElement('div');
    wrap.className = 'ai-msg-wrap bot ai-typing-wrap';
    const div = document.createElement('div');
    div.className = 'ai-msg typing';
    div.innerHTML = '<span></span><span></span><span></span>';
    wrap.appendChild(div);
    msgs.appendChild(wrap);
    msgs.scrollTop = msgs.scrollHeight;
    return wrap;
  }

  function removeErrorBar() {
    const bar = document.getElementById('ai-error-bar');
    if (bar) bar.remove();
  }

  function showErrorBar(query) {
    removeErrorBar();
    lastFailedQuery = query;
    const bar = document.createElement('div');
    bar.id = 'ai-error-bar';
    bar.className = 'ai-error-bar';
    bar.innerHTML = '<span><i class="fas fa-exclamation-circle"></i> Could not reach Guardian</span>' +
      '<button class="ai-retry-btn" type="button">Retry</button>';
    bar.querySelector('.ai-retry-btn').onclick = function () {
      removeErrorBar();
      if (lastFailedQuery) sendQuery(lastFailedQuery);
    };
    panel.querySelector('.ai-input-area').appendChild(bar);
  }

  /* ── Chips / suggestions ───────────────────────────────────── */
  function renderChips(suggestions) {
    if (!chips) return;
    chips.innerHTML = '';
    if (!suggestions || !suggestions.length) return;

    const label = document.createElement('div');
    label.className = 'ai-chips-label';
    label.textContent = 'Suggested questions';
    chips.appendChild(label);

    suggestions.forEach(function (s) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ai-chip';
      btn.disabled = aiTyping;
      const icon = s.icon ? '<i class="fas fa-' + esc(s.icon) + '"></i> ' : '';
      btn.innerHTML = icon + esc(s.label || s.query);
      btn.onclick = function () { quickAI(s.query || s.label); };
      chips.appendChild(btn);
    });
  }

  function updateChipState() {
    if (!chips) return;
    chips.querySelectorAll('.ai-chip').forEach(function (c) { c.disabled = aiTyping; });
    if (sendBtn) sendBtn.disabled = aiTyping;
  }

  /* ── API ───────────────────────────────────────────────────── */
  function fetchMeta() {
    return fetch('/api/ai-meta')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        meta = d;
        if (hdrSub && d.portal) {
          hdrSub.textContent = d.portal + ' \u2022 Online';
        }
        renderChips(d.suggestions);
        return d;
      })
      .catch(function () { return null; });
  }

  function sendQuery(text) {
    if (!text || aiTyping) return;
    addMsg(text, 'user');
    input.value = '';
    autoResize();
    const loader = addTyping();
    aiTyping = true;
    updateChipState();
    removeErrorBar();

    fetch('/api/ai-ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: text })
    })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        loader.remove();
        addMsg(d.reply || 'Sorry, I could not process that.', 'bot');
        if (d.suggestions && d.suggestions.length) renderChips(d.suggestions);
      })
      .catch(function () {
        loader.remove();
        addMsg('Connection error — please check your network and try again.', 'bot');
        showErrorBar(text);
      })
      .finally(function () {
        aiTyping = false;
        updateChipState();
        input.focus();
      });
  }

  /* ── Public API ────────────────────────────────────────────── */
  window.toggleAI = function () {
    const open = panel.classList.contains('ai-open');
    if (open) {
      panel.classList.remove('ai-open', 'ai-expanded');
      fab.classList.remove('ai-fab-hidden');
    } else {
      panel.classList.add('ai-open');
      fab.classList.add('ai-fab-hidden');
      if (!msgs.querySelector('.ai-msg-wrap')) {
        fetchMeta().then(function (d) {
          if (d && d.greeting) addMsg(d.greeting, 'bot');
          else if (!loadHistory()) {
            addMsg("Hello! I'm **TTTI Guardian** — your AI academic assistant.\nAsk me anything about your portal, or tap a suggestion below.", 'bot');
          }
        });
      }
      input.focus();
    }
  };

  window.sendAI = function () {
    sendQuery(input.value.trim());
  };

  window.quickAI = function (q) {
    if (!panel.classList.contains('ai-open')) toggleAI();
    sendQuery(q);
  };

  window.clearAIChat = function () {
    msgs.innerHTML = '';
    sessionStorage.removeItem(STORAGE_KEY);
    removeErrorBar();
    if (meta && meta.greeting) addMsg(meta.greeting, 'bot');
    else addMsg("Chat cleared. How can I help you?", 'bot');
  };

  window.toggleAIExpand = function () {
    panel.classList.toggle('ai-expanded');
    const btn = document.getElementById('ai-expand-btn');
    if (btn) {
      const expanded = panel.classList.contains('ai-expanded');
      btn.innerHTML = expanded
        ? '<i class="fas fa-compress"></i>'
        : '<i class="fas fa-expand"></i>';
      btn.title = expanded ? 'Collapse' : 'Expand';
    }
  };

  /* ── Input helpers ─────────────────────────────────────────── */
  function autoResize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
  }

  input.addEventListener('input', autoResize);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendAI();
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && panel.classList.contains('ai-open')) toggleAI();
  });

  fetchMeta();
})();
