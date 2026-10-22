/* ==========================================================================
   Ask Oloid: topbar button + chat sidebar
   --------------------------------------------------------------------------
   Mintlify loads every .js file in the content directory on every page, so
   this is the only way to put a custom control in the topbar (MDX/React
   snippets only render inside page content). Styles live in ask-oloid.css.

   Claude integration
   ------------------
   NEVER put the Claude API key in this file: every .js file here is shipped
   to every visitor's browser, so anyone could copy the key.

   The key lives only in the backend proxy, ask-oloid-worker/ (Cloudflare
   Worker secret ANTHROPIC_API_KEY). The proxy searches an index of these docs
   built from the .mdx pages and has Claude answer from the matching sections.
   Set CONFIG.endpoint below to the proxy URL once it is deployed.

   The endpoint receives:
     POST { messages: [{ role: "user" | "assistant", content: string }], page }
   and returns:
     { reply: string }  or  { error: string }
   ========================================================================== */
(function () {
  if (window.__askOloidLoaded) return;
  window.__askOloidLoaded = true;

  var CONFIG = {
    title: 'Ask Oloid',
    subtitle: 'AI assistant for Oloid docs',
    buttonLabel: 'Ask Oloid',
    placeholder: 'Ask a question about Oloid...',
    // Backend proxy URL (holds the Claude key): ask-oloid-worker/
    endpoint: 'https://ask-oloid.ask-oloid.workers.dev',
    suggestions: [
      'How do I set up Windows login?',
      'How do I enroll a face in DeviceLock?',
      'Which URLs need to be whitelisted?'
    ],
    storageKey: 'ask-oloid-history'
  };

  var ICONS = {
    sparkle:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z"/></svg>',
    close:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>',
    send:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
    reset:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>'
  };

  /* ---------------------------------------------------------------- state */
  var state = {
    open: false,
    loading: false,
    messages: loadHistory()
  };

  function loadHistory() {
    try {
      var raw = sessionStorage.getItem(CONFIG.storageKey);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function saveHistory() {
    try {
      sessionStorage.setItem(CONFIG.storageKey, JSON.stringify(state.messages));
    } catch (e) {}
  }

  /* -------------------------------------------------------------- helpers */
  function el(tag, attrs, html) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        node.setAttribute(k, attrs[k]);
      });
    }
    if (html != null) node.innerHTML = html;
    return node;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /* Minimal, safe Markdown: escape everything first, then add code blocks,
     tables, inline code, bold, italics, headings, bullets and http(s) /
     site-relative links. */
  function inline(html) {
    return html
      .replace(/`([^`\n]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, '$1<em>$2</em>')
      .replace(
        /\[([^\]]+)\]\((https?:\/\/[^\s)]+|\/(?!\/)[^\s)]*)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
      );
  }

  function tableHtml(lines) {
    var rows = lines.filter(function (_, i) { return i !== 1; }).map(function (line) {
      return line.trim().replace(/^\||\|$/g, '').split('|').map(function (c) {
        return inline(c.trim());
      });
    });
    var head = '<tr><th>' + rows[0].join('</th><th>') + '</th></tr>';
    var body = rows.slice(1).map(function (r) {
      return '<tr><td>' + r.join('</td><td>') + '</td></tr>';
    }).join('');
    return '<div class="ask-oloid-table"><table><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div>';
  }

  function formatText(str) {
    var blocks = [];
    function stash(markup) {
      blocks.push(markup);
      return '\u0000' + (blocks.length - 1) + '\u0000';
    }
    var html = escapeHtml(str).replace(/```[\w-]*\n?([\s\S]*?)```/g, function (_, code) {
      return stash('<pre><code>' + code.replace(/\n$/, '') + '</code></pre>');
    });
    // a table: header row, |---|---| separator, then body rows
    html = html.replace(/(^\|.*\|[ \t]*\n\|[ \t:|-]+\|[ \t]*(?:\n\|.*\|[ \t]*)*)/gm, function (t) {
      return stash(tableHtml(t.split('\n')));
    });
    html = inline(html)
      .replace(/^#{1,6}\s+(.+)$/gm, '<strong>$1</strong>')
      .replace(/^\s*[-*]\s+(.+)$/gm, '&bull; $1')
      .replace(/\n/g, '<br>');
    return html.replace(/\u0000(\d+)\u0000/g, function (_, i) {
      return blocks[+i];
    });
  }

  /* ------------------------------------------------------------- backend */
  function getReply(messages) {
    if (!CONFIG.endpoint) {
      return new Promise(function (resolve) {
        setTimeout(function () {
          resolve(
            'Thanks for your question. The Ask Oloid assistant is not connected to Claude yet, so I cannot answer for real. Once the backend endpoint is configured, answers will appear here.'
          );
        }, 900);
      });
    }

    return fetch(CONFIG.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: messages, page: location.pathname })
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok || data.error) {
            var err = new Error(data.error || 'Request failed: ' + res.status);
            err.fromServer = !!data.error; // safe, user-facing text from the proxy
            throw err;
          }
          return data.reply || 'Sorry, I did not get a response.';
        });
      });
  }

  /* ------------------------------------------------------------------ UI */
  var ui = {};

  function buildPanel() {
    ui.backdrop = el('div', { class: 'ask-oloid-backdrop', 'aria-hidden': 'true' });

    ui.panel = el('aside', {
      class: 'ask-oloid-panel',
      role: 'dialog',
      'aria-modal': 'true',
      'aria-label': CONFIG.title,
      'aria-hidden': 'true'
    });

    ui.panel.innerHTML =
      '<header class="ask-oloid-header">' +
      '  <div class="ask-oloid-header-info">' +
      '    <span class="ask-oloid-avatar">' + ICONS.sparkle + '</span>' +
      '    <div>' +
      '      <div class="ask-oloid-title">' + escapeHtml(CONFIG.title) + '</div>' +
      '      <div class="ask-oloid-subtitle"><span class="ask-oloid-dot"></span>' + escapeHtml(CONFIG.subtitle) + '</div>' +
      '    </div>' +
      '  </div>' +
      '  <div class="ask-oloid-header-actions">' +
      '    <button type="button" class="ask-oloid-icon-btn" data-action="reset" title="New chat" aria-label="New chat">' + ICONS.reset + '</button>' +
      '    <button type="button" class="ask-oloid-icon-btn" data-action="close" title="Close" aria-label="Close">' + ICONS.close + '</button>' +
      '  </div>' +
      '</header>' +
      '<div class="ask-oloid-messages" aria-live="polite"></div>' +
      '<form class="ask-oloid-composer">' +
      '  <div class="ask-oloid-input-wrap">' +
      '    <textarea class="ask-oloid-input" rows="1" placeholder="' + escapeHtml(CONFIG.placeholder) + '" aria-label="Message"></textarea>' +
      '    <button type="submit" class="ask-oloid-send" aria-label="Send" disabled>' + ICONS.send + '</button>' +
      '  </div>' +
      '  <p class="ask-oloid-disclaimer">AI responses may be inaccurate. Verify important details in the docs.</p>' +
      '</form>';

    document.body.appendChild(ui.backdrop);
    document.body.appendChild(ui.panel);

    ui.messages = ui.panel.querySelector('.ask-oloid-messages');
    ui.form = ui.panel.querySelector('.ask-oloid-composer');
    ui.input = ui.panel.querySelector('.ask-oloid-input');
    ui.send = ui.panel.querySelector('.ask-oloid-send');

    ui.backdrop.addEventListener('click', close);
    ui.panel.querySelector('[data-action="close"]').addEventListener('click', close);
    ui.panel.querySelector('[data-action="reset"]').addEventListener('click', reset);

    ui.form.addEventListener('submit', function (e) {
      e.preventDefault();
      submit(ui.input.value);
    });

    ui.input.addEventListener('input', function () {
      autoGrow();
      updateSendState();
    });

    ui.input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        submit(ui.input.value);
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && state.open) close();
    });

    renderMessages();
  }

  function autoGrow() {
    ui.input.style.height = 'auto';
    ui.input.style.height = Math.min(ui.input.scrollHeight, 160) + 'px';
  }

  function updateSendState() {
    ui.send.disabled = state.loading || !ui.input.value.trim();
  }

  function renderWelcome() {
    var wrap = el('div', { class: 'ask-oloid-welcome' });
    wrap.innerHTML =
      '<span class="ask-oloid-welcome-icon">' + ICONS.sparkle + '</span>' +
      '<h3>How can I help?</h3>' +
      '<p>Ask anything about Oloid products, setup, and configuration.</p>';

    var list = el('div', { class: 'ask-oloid-suggestions' });
    CONFIG.suggestions.forEach(function (text) {
      var chip = el('button', { type: 'button', class: 'ask-oloid-suggestion' });
      chip.textContent = text;
      chip.addEventListener('click', function () {
        submit(text);
      });
      list.appendChild(chip);
    });
    wrap.appendChild(list);
    return wrap;
  }

  function renderMessage(msg) {
    var row = el('div', { class: 'ask-oloid-row ask-oloid-row--' + msg.role });
    if (msg.role === 'assistant') {
      row.appendChild(el('span', { class: 'ask-oloid-avatar ask-oloid-avatar--sm' }, ICONS.sparkle));
    }
    var bubble = el('div', {
      class: 'ask-oloid-bubble' + (msg.error ? ' ask-oloid-bubble--error' : '')
    });
    bubble.innerHTML = formatText(msg.content);
    row.appendChild(bubble);
    return row;
  }

  function renderTyping() {
    var row = el('div', { class: 'ask-oloid-row ask-oloid-row--assistant' });
    row.appendChild(el('span', { class: 'ask-oloid-avatar ask-oloid-avatar--sm' }, ICONS.sparkle));
    row.appendChild(
      el('div', { class: 'ask-oloid-bubble ask-oloid-typing', 'aria-label': 'Assistant is typing' },
        '<span></span><span></span><span></span>')
    );
    return row;
  }

  function renderMessages() {
    ui.messages.innerHTML = '';
    if (!state.messages.length) {
      ui.messages.appendChild(renderWelcome());
    } else {
      state.messages.forEach(function (m) {
        ui.messages.appendChild(renderMessage(m));
      });
    }
    if (state.loading) ui.messages.appendChild(renderTyping());
    ui.messages.scrollTop = ui.messages.scrollHeight;
  }

  /* -------------------------------------------------------------- actions */
  function submit(text) {
    text = (text || '').trim();
    if (!text || state.loading) return;

    state.messages.push({ role: 'user', content: text });
    state.loading = true;
    ui.input.value = '';
    autoGrow();
    updateSendState();
    renderMessages();
    saveHistory();

    var history = state.messages
      .filter(function (m) { return !m.error; })
      .map(function (m) { return { role: m.role, content: m.content }; });

    getReply(history)
      .then(function (reply) {
        state.messages.push({ role: 'assistant', content: reply });
      })
      .catch(function (err) {
        state.messages.push({
          role: 'assistant',
          content: err && err.fromServer
            ? err.message
            : 'Something went wrong while contacting the assistant. Please try again.',
          error: true
        });
      })
      .then(function () {
        state.loading = false;
        updateSendState();
        renderMessages();
        saveHistory();
      });
  }

  function reset() {
    if (state.loading) return;
    state.messages = [];
    saveHistory();
    renderMessages();
    ui.input.focus();
  }

  function open() {
    if (!ui.panel) buildPanel();
    state.open = true;
    document.documentElement.classList.add('ask-oloid-open');
    ui.panel.setAttribute('aria-hidden', 'false');
    syncButton();
    setTimeout(function () { ui.input.focus(); }, 200);
  }

  function close() {
    state.open = false;
    document.documentElement.classList.remove('ask-oloid-open');
    if (ui.panel) ui.panel.setAttribute('aria-hidden', 'true');
    syncButton();
  }

  function toggle() {
    state.open ? close() : open();
  }

  /* ------------------------------------------------------ topbar button */
  function syncButton() {
    var btn = document.getElementById('ask-oloid-button');
    if (btn) btn.setAttribute('aria-expanded', state.open ? 'true' : 'false');
  }

  /* Find the right-hand side of the topbar. Mintlify renders this hook as a
     class on some themes and as a custom element on others, so both are
     tried, then the parents of the search / built-in assistant entries. */
  function findTopbarTarget() {
    var direct =
      document.querySelector('.topbar-right-container') ||
      document.querySelector('topbar-right-container');
    if (direct) return direct;

    var anchor =
      document.getElementById('assistant-entry') ||
      document.getElementById('search-bar-entry');
    if (anchor && anchor.parentElement) return anchor.parentElement;

    return null;
  }

  function createButton(floating) {
    var btn = el('button', {
      id: 'ask-oloid-button',
      type: 'button',
      class: 'ask-oloid-button' + (floating ? ' ask-oloid-button--floating' : ''),
      'aria-haspopup': 'dialog',
      'aria-expanded': state.open ? 'true' : 'false',
      title: CONFIG.buttonLabel
    });
    btn.innerHTML = ICONS.sparkle + '<span>' + escapeHtml(CONFIG.buttonLabel) + '</span>';
    btn.addEventListener('click', toggle);
    return btn;
  }

  function mountButton() {
    var existing = document.getElementById('ask-oloid-button');
    // already in the topbar: done
    if (existing && !existing.classList.contains('ask-oloid-button--floating')) return true;

    var target = findTopbarTarget();
    if (!target) return false;

    // topbar showed up late: replace the floating fallback
    if (existing) existing.remove();
    target.appendChild(createButton(false));
    return true;
  }

  /* Fallback so the chat is always reachable: a floating bubble in the
     bottom-right corner, used only if no topbar slot is found. */
  function mountFloating() {
    if (document.getElementById('ask-oloid-button')) return;
    document.body.appendChild(createButton(true));
  }

  /* The topbar renders after hydration, so retry briefly on first load and
     again after each client-side navigation. */
  function ensureButton(attempt) {
    attempt = attempt || 0;
    if (mountButton()) return;
    if (attempt === 12) mountFloating(); // ~3s without a topbar
    if (attempt > 40) return;
    setTimeout(function () { ensureButton(attempt + 1); }, 250);
  }

  ensureButton();
  window.addEventListener('mintlify:navigate', function () { ensureButton(); });

  window.AskOloid = { open: open, close: close, toggle: toggle };
})();
