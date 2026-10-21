/* Ask Oloid: topbar button (next to search) + right-hand chatbot sidebar.
   Mintlify runs every .js file in the content directory on every page.
   React components only render inside page content, so the navbar button
   is injected with plain DOM code here. */
(function () {
  if (window.__askOloidLoaded) return;
  window.__askOloidLoaded = true;

  var BUTTON_ID = 'ask-oloid-button';
  var PANEL_ID = 'ask-oloid-panel';
  var OVERLAY_ID = 'ask-oloid-overlay';

  var BOT_ICON =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<rect x="4" y="8" width="16" height="12" rx="3"/>' +
      '<path d="M12 4v4"/><circle cx="12" cy="3" r="1"/>' +
      '<circle cx="9" cy="14" r="1.2" fill="currentColor"/><circle cx="15" cy="14" r="1.2" fill="currentColor"/>' +
    '</svg>';
  var CHAT_ICON =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>' +
    '</svg>';
  var SEND_ICON =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/>' +
    '</svg>';

  var SUGGESTIONS = [
    'How do I set up Windows Login?',
    'How do I add a new user?',
    'What devices are supported?'
  ];

  function openPanel() {
    document.documentElement.classList.add('ask-oloid-open');
    var input = document.getElementById('ask-oloid-input');
    if (input) setTimeout(function () { input.focus(); }, 150);
  }

  function closePanel() {
    document.documentElement.classList.remove('ask-oloid-open');
  }

  function scrollToBottom() {
    var list = document.getElementById('ask-oloid-messages');
    if (list) list.scrollTop = list.scrollHeight;
  }

  function addMessage(role, text) {
    var list = document.getElementById('ask-oloid-messages');
    var row = document.createElement('div');
    row.className = 'ask-oloid-row ask-oloid-row-' + role;
    if (role === 'bot') {
      var avatar = document.createElement('div');
      avatar.className = 'ask-oloid-avatar';
      avatar.innerHTML = BOT_ICON;
      row.appendChild(avatar);
    }
    var bubble = document.createElement('div');
    bubble.className = 'ask-oloid-bubble';
    bubble.textContent = text;
    row.appendChild(bubble);
    list.appendChild(row);
    scrollToBottom();
    return row;
  }

  function addTyping() {
    var row = addMessage('bot', '');
    row.classList.add('ask-oloid-typing');
    row.querySelector('.ask-oloid-bubble').innerHTML = '<span></span><span></span><span></span>';
    scrollToBottom();
    return row;
  }

  function removeSuggestions() {
    var s = document.getElementById('ask-oloid-suggestions');
    if (s) s.remove();
  }

  function ask(text) {
    text = (text || '').trim();
    if (!text) return;
    removeSuggestions();
    addMessage('user', text);
    var typing = addTyping();
    /* TODO: replace this placeholder with a call to your backend and
       render the real answer with addMessage('bot', answer). */
    setTimeout(function () {
      typing.remove();
      addMessage('bot', "Thanks for your question! I'm not connected to an answer service yet, but I will be soon.");
    }, 900);
  }

  function buildPanel() {
    if (document.getElementById(PANEL_ID)) return;

    var overlay = document.createElement('div');
    overlay.id = OVERLAY_ID;
    overlay.addEventListener('click', closePanel);

    var panel = document.createElement('aside');
    panel.id = PANEL_ID;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Ask Oloid');
    panel.innerHTML =
      '<div class="ask-oloid-header">' +
        '<div class="ask-oloid-header-info">' +
          '<div class="ask-oloid-avatar ask-oloid-avatar-lg">' + BOT_ICON + '</div>' +
          '<div>' +
            '<div class="ask-oloid-title">Ask Oloid</div>' +
            '<div class="ask-oloid-status"><span class="ask-oloid-dot"></span>Online</div>' +
          '</div>' +
        '</div>' +
        '<button type="button" class="ask-oloid-close" aria-label="Close">&times;</button>' +
      '</div>' +
      '<div class="ask-oloid-body" id="ask-oloid-messages" aria-live="polite"></div>' +
      '<form class="ask-oloid-form" id="ask-oloid-form">' +
        '<input id="ask-oloid-input" type="text" autocomplete="off" placeholder="Type a message..." />' +
        '<button type="submit" class="ask-oloid-send" aria-label="Send">' + SEND_ICON + '</button>' +
      '</form>';

    panel.querySelector('.ask-oloid-close').addEventListener('click', closePanel);
    panel.querySelector('#ask-oloid-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var input = document.getElementById('ask-oloid-input');
      ask(input.value);
      input.value = '';
    });

    document.body.appendChild(overlay);
    document.body.appendChild(panel);

    addMessage('bot', "Hi there! 👋 I'm Oloid's assistant. How can I help you today?");

    var chips = document.createElement('div');
    chips.id = 'ask-oloid-suggestions';
    chips.className = 'ask-oloid-suggestions';
    SUGGESTIONS.forEach(function (q) {
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'ask-oloid-chip';
      chip.textContent = q;
      chip.addEventListener('click', function () { ask(q); });
      chips.appendChild(chip);
    });
    document.getElementById('ask-oloid-messages').appendChild(chips);
  }

  function injectButton() {
    if (document.getElementById(BUTTON_ID)) return;

    var btn = document.createElement('button');
    btn.id = BUTTON_ID;
    btn.type = 'button';
    btn.innerHTML = CHAT_ICON + '<span>Ask Oloid</span>';
    btn.addEventListener('click', function () {
      if (document.documentElement.classList.contains('ask-oloid-open')) {
        closePanel();
      } else {
        openPanel();
      }
    });

    /* Prefer placing the button right after the search field */
    var search =
      document.getElementById('search-bar-entry') ||
      document.getElementById('assistant-entry');
    if (search && search.parentElement) {
      search.insertAdjacentElement('afterend', btn);
      return;
    }
    var target =
      document.querySelector('.topbar-right-container') ||
      document.querySelector('#navbar');
    if (!target) return;
    target.insertBefore(btn, target.firstChild);
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
  /* the topbar can mount after scripts run; retry briefly */
  var tries = 0;
  var timer = setInterval(function () {
    injectButton();
    if (document.getElementById(BUTTON_ID) || ++tries > 20) clearInterval(timer);
  }, 250);
})();
