/* Ask Oloid: custom topbar button (far right) + modern AI assistant sidebar.
   Mintlify runs every .js file in the content directory on every page.
   React components only render inside page content, so the navbar button
   is injected with plain DOM code here. */
(function () {
  if (window.__askOloidLoaded) return;
  window.__askOloidLoaded = true;

  var BUTTON_ID = 'ask-oloid-button';
  var PANEL_ID = 'ask-oloid-panel';
  var OVERLAY_ID = 'ask-oloid-overlay';

  var SPARKLE_ICON =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">' +
      '<path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9z"/>' +
      '<path d="M19 14l.9 2.6 2.6.9-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9z"/>' +
    '</svg>';
  var SEND_ICON =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>' +
    '</svg>';
  var NEW_CHAT_ICON =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>' +
    '</svg>';
  var CLOSE_ICON =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M18 6 6 18"/><path d="M6 6l12 12"/>' +
    '</svg>';

  /* Example prompts shown on the welcome screen. Replace with real ones. */
  var SUGGESTIONS = [
    { title: 'Set up Windows Login', prompt: 'How do I set up Oloid Windows Login?' },
    { title: 'Add a new user', prompt: 'How do I add a new user?' },
    { title: 'Supported devices', prompt: 'Which devices does Oloid support?' },
    { title: 'Create a workflow', prompt: 'How do I create a workflow?' }
  ];

  var busy = false;

  function $(id) { return document.getElementById(id); }

  function openPanel() {
    document.documentElement.classList.add('ask-oloid-open');
    var btn = $(BUTTON_ID);
    if (btn) btn.setAttribute('aria-expanded', 'true');
    var input = $('ask-oloid-input');
    if (input) setTimeout(function () { input.focus(); }, 200);
  }

  function closePanel() {
    document.documentElement.classList.remove('ask-oloid-open');
    var btn = $(BUTTON_ID);
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function togglePanel() {
    if (document.documentElement.classList.contains('ask-oloid-open')) closePanel();
    else openPanel();
  }

  function scrollToBottom() {
    var list = document.querySelector('.ask-oloid-scroll');
    if (list) list.scrollTop = list.scrollHeight;
  }

  function showWelcome(show) {
    var panel = $(PANEL_ID);
    if (panel) panel.classList.toggle('ask-oloid-has-messages', !show);
  }

  function addMessage(role, text) {
    var list = $('ask-oloid-messages');
    var row = document.createElement('div');
    row.className = 'ask-oloid-msg ask-oloid-msg-' + role;
    if (role === 'assistant') {
      var avatar = document.createElement('div');
      avatar.className = 'ask-oloid-msg-avatar';
      avatar.innerHTML = SPARKLE_ICON;
      row.appendChild(avatar);
    }
    var content = document.createElement('div');
    content.className = 'ask-oloid-msg-content';
    content.textContent = text;
    row.appendChild(content);
    list.appendChild(row);
    scrollToBottom();
    return row;
  }

  function addThinking() {
    var row = addMessage('assistant', '');
    row.classList.add('ask-oloid-thinking');
    row.querySelector('.ask-oloid-msg-content').innerHTML =
      '<span class="ask-oloid-thinking-text">Thinking</span>' +
      '<span class="ask-oloid-dots"><i></i><i></i><i></i></span>';
    scrollToBottom();
    return row;
  }

  function resizeInput() {
    var input = $('ask-oloid-input');
    if (!input) return;
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
    var send = document.querySelector('.ask-oloid-send');
    if (send) send.disabled = !input.value.trim() || busy;
  }

  function ask(text) {
    text = (text || '').trim();
    if (!text || busy) return;
    busy = true;
    showWelcome(false);
    addMessage('user', text);
    var thinking = addThinking();
    resizeInput();

    /* TODO: replace this placeholder with a call to your backend and
       render the real answer with addMessage('assistant', answer). */
    setTimeout(function () {
      thinking.remove();
      addMessage(
        'assistant',
        "Thanks for your question! I'm not connected to an answer service yet, so I can't answer this right now."
      );
      busy = false;
      resizeInput();
    }, 1000);
  }

  function newChat() {
    var list = $('ask-oloid-messages');
    if (list) list.innerHTML = '';
    busy = false;
    showWelcome(true);
    var input = $('ask-oloid-input');
    if (input) { input.value = ''; resizeInput(); input.focus(); }
  }

  function buildPanel() {
    if ($(PANEL_ID)) return;

    var overlay = document.createElement('div');
    overlay.id = OVERLAY_ID;
    overlay.addEventListener('click', closePanel);

    var cards = SUGGESTIONS.map(function (s, i) {
      return '<button type="button" class="ask-oloid-card" data-index="' + i + '">' +
        '<span class="ask-oloid-card-title"></span>' +
        '<span class="ask-oloid-card-prompt"></span>' +
      '</button>';
    }).join('');

    var panel = document.createElement('aside');
    panel.id = PANEL_ID;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Ask Oloid');
    panel.innerHTML =
      '<header class="ask-oloid-header">' +
        '<div class="ask-oloid-header-title">' +
          '<span class="ask-oloid-logo">' + SPARKLE_ICON + '</span>' +
          '<span>Ask Oloid</span>' +
        '</div>' +
        '<div class="ask-oloid-header-actions">' +
          '<button type="button" class="ask-oloid-icon-btn ask-oloid-new" aria-label="New chat" title="New chat">' + NEW_CHAT_ICON + '</button>' +
          '<button type="button" class="ask-oloid-icon-btn ask-oloid-close" aria-label="Close" title="Close (Esc)">' + CLOSE_ICON + '</button>' +
        '</div>' +
      '</header>' +
      '<div class="ask-oloid-scroll">' +
        '<section class="ask-oloid-welcome">' +
          '<div class="ask-oloid-welcome-icon">' + SPARKLE_ICON + '</div>' +
          '<h2 class="ask-oloid-welcome-title">How can I help you today?</h2>' +
          '<p class="ask-oloid-welcome-sub">Ask anything about Oloid products, setup, and administration.</p>' +
          '<div class="ask-oloid-cards">' + cards + '</div>' +
        '</section>' +
        '<div class="ask-oloid-messages" id="ask-oloid-messages" aria-live="polite"></div>' +
      '</div>' +
      '<footer class="ask-oloid-footer">' +
        '<form class="ask-oloid-form" id="ask-oloid-form">' +
          '<textarea id="ask-oloid-input" rows="1" placeholder="Ask a question..." aria-label="Ask a question"></textarea>' +
          '<button type="submit" class="ask-oloid-send" aria-label="Send" disabled>' + SEND_ICON + '</button>' +
        '</form>' +
        '<p class="ask-oloid-disclaimer">AI answers can be inaccurate. Verify important information.</p>' +
      '</footer>';

    /* Fill card text safely */
    panel.querySelectorAll('.ask-oloid-card').forEach(function (card) {
      var s = SUGGESTIONS[+card.getAttribute('data-index')];
      card.querySelector('.ask-oloid-card-title').textContent = s.title;
      card.querySelector('.ask-oloid-card-prompt').textContent = s.prompt;
      card.addEventListener('click', function () { ask(s.prompt); });
    });

    panel.querySelector('.ask-oloid-close').addEventListener('click', closePanel);
    panel.querySelector('.ask-oloid-new').addEventListener('click', newChat);

    var form = panel.querySelector('#ask-oloid-form');
    var input = panel.querySelector('#ask-oloid-input');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var text = input.value;
      input.value = '';
      ask(text);
    });
    input.addEventListener('input', resizeInput);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        if (form.requestSubmit) form.requestSubmit();
        else form.dispatchEvent(new Event('submit', { cancelable: true }));
      }
    });

    document.body.appendChild(overlay);
    document.body.appendChild(panel);
  }

  function injectButton() {
    var existing = $(BUTTON_ID);
    if (existing && document.body.contains(existing)) return;
    if (existing) existing.remove();

    var target =
      document.querySelector('.topbar-right-container') ||
      document.querySelector('#navbar nav') ||
      document.querySelector('#navbar');

    var btn = document.createElement('button');
    btn.id = BUTTON_ID;
    btn.type = 'button';
    btn.setAttribute('aria-haspopup', 'dialog');
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = SPARKLE_ICON + '<span>Ask Oloid</span>';
    btn.addEventListener('click', togglePanel);

    if (target) {
      /* Far right corner: last item in the navbar's right side */
      target.appendChild(btn);
    } else {
      /* Fallback: pin the button to the top-right corner of the window */
      btn.classList.add('ask-oloid-button-fixed');
      document.body.appendChild(btn);
    }
  }

  function init() {
    buildPanel();
    injectButton();
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closePanel();
  });

  init();
  window.addEventListener('mintlify:navigate', init);

  /* The topbar can mount or re-render after scripts run, which can remove
     the injected button. Re-check once a second and re-add it if missing. */
  setInterval(function () {
    var btn = $(BUTTON_ID);
    var navbar = document.querySelector('.topbar-right-container, #navbar');
    if (!btn || (btn.classList.contains('ask-oloid-button-fixed') && navbar)) {
      if (btn) btn.remove();
      init();
    }
  }, 1000);
})();
