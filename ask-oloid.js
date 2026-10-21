/* Ask Oloid: topbar button + right-hand sidebar with an input field.
   Mintlify runs every .js file in the content directory on every page.
   React components only render inside page content, so the navbar button
   is injected with plain DOM code here. */
(function () {
  if (window.__askOloidLoaded) return;
  window.__askOloidLoaded = true;

  var BUTTON_ID = 'ask-oloid-button';
  var PANEL_ID = 'ask-oloid-panel';
  var OVERLAY_ID = 'ask-oloid-overlay';

  function openPanel() {
    document.documentElement.classList.add('ask-oloid-open');
    var input = document.getElementById('ask-oloid-input');
    if (input) setTimeout(function () { input.focus(); }, 150);
  }

  function closePanel() {
    document.documentElement.classList.remove('ask-oloid-open');
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
        '<span class="ask-oloid-title">Ask Oloid</span>' +
        '<button type="button" class="ask-oloid-close" aria-label="Close">&times;</button>' +
      '</div>' +
      '<div class="ask-oloid-body" id="ask-oloid-messages">' +
        '<p class="ask-oloid-empty">Ask a question about Oloid.</p>' +
      '</div>' +
      '<form class="ask-oloid-form" id="ask-oloid-form">' +
        '<input id="ask-oloid-input" type="text" autocomplete="off" placeholder="Type your question..." />' +
        '<button type="submit" class="ask-oloid-send">Send</button>' +
      '</form>';

    panel.querySelector('.ask-oloid-close').addEventListener('click', closePanel);

    panel.querySelector('#ask-oloid-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var input = document.getElementById('ask-oloid-input');
      var text = input.value.trim();
      if (!text) return;
      var list = document.getElementById('ask-oloid-messages');
      var empty = list.querySelector('.ask-oloid-empty');
      if (empty) empty.remove();
      var msg = document.createElement('div');
      msg.className = 'ask-oloid-message';
      msg.textContent = text;
      list.appendChild(msg);
      list.scrollTop = list.scrollHeight;
      input.value = '';
      /* TODO: send `text` to your backend and render the answer here. */
    });

    document.body.appendChild(overlay);
    document.body.appendChild(panel);
  }

  function injectButton() {
    if (document.getElementById(BUTTON_ID)) return;
    var target =
      document.querySelector('.topbar-right-container') ||
      document.querySelector('#navbar');
    if (!target) return;

    var btn = document.createElement('button');
    btn.id = BUTTON_ID;
    btn.type = 'button';
    btn.textContent = 'Ask Oloid';
    btn.addEventListener('click', function () {
      if (document.documentElement.classList.contains('ask-oloid-open')) {
        closePanel();
      } else {
        openPanel();
      }
    });
    target.appendChild(btn);
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
