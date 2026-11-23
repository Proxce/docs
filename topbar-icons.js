/* ==========================================================================
   Topbar icons: round, icon-only Search and Ask Assistant buttons.

   Mintlify loads every .js file in the repo on every page. On desktop
   (>= 1024px) this puts two 36px icon buttons at the start of the topbar's
   right-hand controls - Search, then Ask Assistant (the Oloid drop) - before
   Log Out and the theme toggle. Each one forwards its click to Mintlify's own
   control, so the built-in search dialog and AI assistant open exactly as
   before, and Ctrl/Cmd+K and Ctrl/Cmd+I keep working (those listeners belong
   to Mintlify and are never touched).

   Fail safe: Mintlify's own controls are only hidden once a replacement is
   mounted, via the html classes oloid-has-search / oloid-has-assistant that
   topbar-icons.css keys on. If this file does not load, or a control cannot
   be found, the default control stays visible and usable. The Ask Assistant
   icon only appears when the site actually has the assistant.

   Styles: topbar-icons.css.
   ========================================================================== */
(function () {
  if (window.__oloidTopbarIcons) return;
  window.__oloidTopbarIcons = true;

  var DESKTOP = window.matchMedia('(min-width: 1024px)');
  var IS_MAC = /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent || '');
  var MOD = IS_MAC ? '⌘' : 'Ctrl';
  var WRAP_ID = 'oloid-topbar-icons';

  var SEARCH_SVG =
    '<svg viewBox="0 0 18 18" width="16" height="16" fill="none" stroke="currentColor" ' +
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
    '<path d="M15.25 15.25L11.285 11.285"/>' +
    '<path d="M7.75 12.75a5 5 0 1 0 0-10 5 5 0 0 0 0 10z"/></svg>';

  // The Oloid drop from logo/light.svg, gradients kept, ids namespaced.
  var DROP_SVG =
    '<svg viewBox="0 0 36 37" width="20" height="20" fill="none" aria-hidden="true" focusable="false">' +
    '<path fill-rule="evenodd" clip-rule="evenodd" fill="url(#oloid-ast-g0)" d="M23.7568 6.39085C22.903 5.52162 20.9867 2.08418 18.098 2.22906C15.6396 2.13687 14.0131 4.5119 12.3207 6.39085C4.80268 14.7803 5.42387 21.7803 5.42387 21.7803C5.63021 28.1591 11.3878 34.1318 17.9641 34.0703C24.4241 34.0703 30.0083 28.8637 30.5681 22.3751C31.3956 15.4234 25.3373 8.17981 23.759 6.39085H23.7568ZM21.0604 21.2615C20.9243 22.8419 19.5151 24.1348 17.9435 24.1348C16.3433 24.1502 14.9407 22.6971 14.8902 21.143C14.8902 21.143 14.9517 19.7338 16.1106 17.3829C16.4618 16.6541 16.9601 15.4051 17.972 15.4051C18.9247 15.4051 19.3088 16.518 19.7895 17.3982C20.0463 17.9404 21.0934 20.0059 21.0583 21.2615L21.0604 21.2615Z"/>' +
    '<path fill-rule="evenodd" clip-rule="evenodd" fill="url(#oloid-ast-g1)" d="M9.26247 26.1654C9.68173 27.9829 11.1195 32.9129 17.0131 34.0258C17.0131 34.0258 19.0787 34.2892 21.7303 33.5231C22.3098 33.3475 23.967 32.7461 25.644 31.4203C26.0479 31.0998 28.0125 29.6094 29.38 26.7207C29.8892 25.4959 31.0087 23.4479 30.5434 19.2532C30.3568 18.1337 29.6105 15.245 28.5547 13.32C27.861 11.7352 25.396 8.12216 23.708 6.20589C23.1175 5.52324 21.8554 4.22816 21.5481 3.91208C21.4449 3.78697 22.211 4.79669 22.2637 4.89106C22.3471 5.02058 22.999 6.02591 23.438 7.0027C23.5412 7.23098 24.7485 9.7004 25.058 11.9064C25.5014 13.9763 25.4355 13.8907 25.4772 15.5677C25.4575 16.5401 25.5497 18.4871 24.3797 20.7963C24.2546 21.0136 22.92 23.8518 19.0765 24.1723C15.9178 24.721 15.0552 21.9685 15.0749 22.0607C14.9871 21.716 14.671 20.0127 16.1724 17.405C16.1724 17.405 16.8705 16.1318 17.2436 15.7433C17.4917 15.5875 18.2928 15.087 19.0106 16.0111C19.0106 16.0111 19.0106 16.0177 19.0106 15.9914C19.0106 15.9914 18.0975 13.3661 14.5723 14.3451C14.4471 14.3912 12.2741 15.1221 10.8451 17.0933C10.72 17.2491 8.07934 20.5724 9.26026 26.1654C9.89029 26.1654 9.26247 26.1654 9.26247 26.1654Z"/>' +
    '<defs>' +
    '<linearGradient id="oloid-ast-g0" x1="18.0278" y1="2.22466" x2="18.0278" y2="19.0387" gradientUnits="userSpaceOnUse">' +
    '<stop stop-color="#0074F3"/><stop offset="0.99" stop-color="#005284"/></linearGradient>' +
    '<linearGradient id="oloid-ast-g1" x1="13.8984" y1="18.9854" x2="32.3916" y2="18.9854" gradientUnits="userSpaceOnUse">' +
    '<stop stop-color="#0179FF"/><stop offset="0.99" stop-color="#57AFFF"/></linearGradient>' +
    '</defs></svg>';

  /* ------------------------------------------------------- Mintlify controls */
  function mine(el) { return el && el.closest && el.closest('#' + WRAP_ID); }

  function first(selectors) {
    for (var i = 0; i < selectors.length; i++) {
      var list = document.querySelectorAll(selectors[i]);
      for (var j = 0; j < list.length; j++) {
        if (!mine(list[j])) return list[j];
      }
    }
    return null;
  }

  function clickable(el) {
    if (!el) return null;
    if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') return el;
    return el.querySelector('button, [role="button"], input') || el;
  }

  function nativeSearch() {
    return clickable(first([
      '[data-search-item="trigger"]',
      '[data-layout-item="search-entry"]',
      '#search-bar-entry'
    ]));
  }

  function nativeAssistant() {
    return clickable(first([
      '[data-layout-item="assistant-entry"]',
      '#assistant-entry'
    ]));
  }

  function rightContainer() {
    return document.querySelector('.topbar-right-container');
  }

  /* Keyboard fallback if the native control vanished after mounting. */
  function shortcut(key) {
    var opts = { key: key, code: 'Key' + key.toUpperCase(), bubbles: true, cancelable: true };
    opts[IS_MAC ? 'metaKey' : 'ctrlKey'] = true;
    document.dispatchEvent(new KeyboardEvent('keydown', opts));
  }

  /* ------------------------------------------------------------- our buttons */
  function makeButton(kind, label, tip, keys, svg, onClick) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'oloid-icon-btn oloid-icon-btn--' + kind;
    b.setAttribute('aria-label', label + ' (' + keys + ')');
    b.setAttribute('aria-keyshortcuts', (IS_MAC ? 'Meta' : 'Control') + '+' + keys.slice(-1));
    b.setAttribute('data-tip', tip);
    b.setAttribute('data-keys', keys);
    b.innerHTML = svg;
    b.addEventListener('click', onClick);
    return b;
  }

  function openSearch() {
    var n = nativeSearch();
    if (n) n.click(); else shortcut('k');
  }

  function openAssistant() {
    var n = nativeAssistant();
    if (n) n.click(); else shortcut('i');
  }

  function unmount() {
    var w = document.getElementById(WRAP_ID);
    if (w) w.remove();
    document.documentElement.classList.remove('oloid-has-search', 'oloid-has-assistant');
  }

  function mount() {
    if (!DESKTOP.matches) { unmount(); return; }
    var right = rightContainer();
    var search = nativeSearch();
    var assistant = nativeAssistant();
    if (!right || (!search && !assistant)) return;      // nothing to replace yet

    var wrap = document.getElementById(WRAP_ID);
    if (wrap && wrap.parentNode !== right) { wrap.remove(); wrap = null; }
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.id = WRAP_ID;
      right.insertBefore(wrap, right.firstChild);
    } else if (right.firstChild !== wrap) {
      right.insertBefore(wrap, right.firstChild);        // keep it first
    }

    var hasS = wrap.querySelector('.oloid-icon-btn--search');
    if (search && !hasS) {
      wrap.insertBefore(makeButton('search', 'Search', 'Search', MOD + ' K',
                                   SEARCH_SVG, openSearch), wrap.firstChild);
    }
    var hasA = wrap.querySelector('.oloid-icon-btn--assistant');
    if (assistant && !hasA) {
      wrap.appendChild(makeButton('assistant', 'Ask Assistant',
                                  'Ask Assistant: ask questions if you have any doubts',
                                  MOD + ' I', DROP_SVG, openAssistant));
    } else if (!assistant && hasA) {
      hasA.remove();
    }

    var root = document.documentElement.classList;
    root.toggle('oloid-has-search', !!wrap.querySelector('.oloid-icon-btn--search'));
    root.toggle('oloid-has-assistant', !!wrap.querySelector('.oloid-icon-btn--assistant'));
  }

  /* The topbar is rendered by React after hydration and re-rendered on
     navigation, so re-check on DOM changes (batched to one frame). */
  var queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { queued = false; mount(); });
  }

  /* Crossing 1024px: Mintlify swaps its mobile and desktop topbars a moment
     after the media query flips, so one check can land before the desktop
     controls exist. Re-check a few times over ~2s. */
  function settle() {
    var n = 0;
    (function tick() {
      mount();
      if (++n < 8) setTimeout(tick, 250);
    })();
  }

  function start() {
    mount();
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
    if (DESKTOP.addEventListener) DESKTOP.addEventListener('change', settle);
    else if (DESKTOP.addListener) DESKTOP.addListener(settle);
  }

  /* Never touch the topbar before React has hydrated it: inserting a node
     into server-rendered markup that React has not claimed yet makes it throw
     a hydration error (#418) and re-render the page on the client. So wait
     for the load event, then for the browser to go idle. */
  function boot() {
    var idle = window.requestIdleCallback || function (fn) { return setTimeout(fn, 200); };
    idle(start, { timeout: 2000 });
  }

  if (document.readyState === 'complete') boot();
  else window.addEventListener('load', boot, { once: true });
})();
