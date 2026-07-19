// ==UserScript==
// @name         A to Z Network Spy - Training Capture
// @namespace    acy1-rme-onboarding
// @version      1.1
// @description  Passively captures fetch/XHR API responses on atoz.amazon.work so we can extract training titles+URLs/IDs without relying on rendered links. Scroll the Completed Trainings list to the bottom, then click Export.
// @match        https://atoz.amazon.work/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_deleteValue
// ==/UserScript==

(function () {
  'use strict';

  const STORE_KEY = 'atoz_spy_captures_v1';
  let captures = GM_getValue(STORE_KEY, []);

  function persist() {
    // Cap stored size so we don't blow up storage; keep newest 500
    if (captures.length > 500) captures = captures.slice(captures.length - 500);
    GM_setValue(STORE_KEY, captures);
  }

  function looksRelevant(bodyText) {
    if (!bodyText) return false;
    const t = bodyText.toLowerCase();
    return t.includes('training') || t.includes('learn') || t.includes('completed') || t.includes('checklist') || t.includes('curriculum');
  }

  function record(url, method, status, bodyText) {
    try {
      if (!looksRelevant(bodyText) && !looksRelevant(url)) return;
      captures.push({
        ts: Date.now(),
        url: String(url),
        method: method || 'GET',
        status: status || 0,
        body: bodyText && bodyText.length > 5000000 ? bodyText.slice(0, 5000000) + '...[truncated]' : bodyText
      });
      persist();
      updatePanel();
    } catch (e) {
      console.warn('[A2Z Spy] record failed', e);
    }
  }

  // ---- Hook fetch ----
  const origFetch = window.fetch;
  window.fetch = function (...args) {
    const url = args[0] && args[0].url ? args[0].url : args[0];
    const method = (args[1] && args[1].method) || 'GET';
    return origFetch.apply(this, args).then((resp) => {
      try {
        const cloned = resp.clone();
        cloned.text().then((bodyText) => record(url, method, resp.status, bodyText)).catch(() => {});
      } catch (e) {}
      return resp;
    });
  };

  // ---- Hook XHR ----
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this._spy_method = method;
    this._spy_url = url;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    this.addEventListener('loadend', () => {
      try {
        record(this._spy_url, this._spy_method, this.status, this.responseText);
      } catch (e) {}
    });
    return origSend.apply(this, args);
  };

  // ---- Floating control panel ----
  let panel;
  function buildPanel() {
    panel = document.createElement('div');
    panel.style.cssText = `
      position: fixed; bottom: 16px; right: 16px; z-index: 999999;
      background: #1b1f23; color: #fff; font-family: Arial, sans-serif;
      font-size: 13px; padding: 12px 14px; border-radius: 10px;
      box-shadow: 0 4px 16px rgba(0,0,0,.4); width: 240px;
    `;
    panel.innerHTML = `
      <div style="font-weight:bold; margin-bottom:6px;">🕵️ A2Z Network Spy v1.1</div>
      <div id="a2z-spy-count" style="margin-bottom:8px;">Captured: 0 responses</div>
      <button id="a2z-spy-autoscroll" style="width:100%; margin-bottom:6px; padding:6px; cursor:pointer;">Start Auto-Scroll</button>
      <button id="a2z-spy-export" style="width:100%; margin-bottom:6px; padding:6px; cursor:pointer;">Export JSON</button>
      <button id="a2z-spy-clear" style="width:100%; padding:6px; cursor:pointer;">Clear Captures</button>
    `;
    document.body.appendChild(panel);

    panel.querySelector('#a2z-spy-export').onclick = exportCaptures;
    panel.querySelector('#a2z-spy-clear').onclick = () => {
      captures = [];
      GM_deleteValue(STORE_KEY);
      updatePanel();
    };
    panel.querySelector('#a2z-spy-autoscroll').onclick = toggleAutoScroll;
  }

  function updatePanel() {
    if (!panel) return;
    const el = panel.querySelector('#a2z-spy-count');
    if (el) el.textContent = `Captured: ${captures.length} responses`;
  }

  function exportCaptures() {
    const blob = new Blob([JSON.stringify(captures, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `atoz-network-capture-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  // ---- Auto-scroll to force lazy-loaded rows to fetch ----
  let scrollTimer = null;
  function findScrollableList() {
    // Heuristic: find the element with the most children that has scroll overflow
    const candidates = Array.from(document.querySelectorAll('div, ul, section'));
    let best = null, bestScore = 0;
    for (const el of candidates) {
      const style = window.getComputedStyle(el);
      const scrollable = (style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 50;
      if (scrollable) {
        const score = el.children.length;
        if (score > bestScore) { bestScore = score; best = el; }
      }
    }
    return best;
  }

  function toggleAutoScroll() {
    const btn = panel.querySelector('#a2z-spy-autoscroll');
    if (scrollTimer) {
      clearInterval(scrollTimer);
      scrollTimer = null;
      btn.textContent = 'Start Auto-Scroll';
      return;
    }
    btn.textContent = 'Stop Auto-Scroll';
    let stuckCount = 0;
    let lastHeight = 0;
    scrollTimer = setInterval(() => {
      const list = findScrollableList();
      const target = list || document.scrollingElement;
      const before = target.scrollTop;
      target.scrollTop = target.scrollTop + 600;
      window.scrollTo(0, document.body.scrollHeight);
      if (target.scrollHeight === lastHeight) {
        stuckCount++;
      } else {
        stuckCount = 0;
        lastHeight = target.scrollHeight;
      }
      if (stuckCount > 8) {
        clearInterval(scrollTimer);
        scrollTimer = null;
        btn.textContent = 'Start Auto-Scroll';
        console.log('[A2Z Spy] Auto-scroll finished (no more growth detected).');
      }
    }, 700);
  }

  window.addEventListener('load', () => setTimeout(buildPanel, 1000));
  if (document.readyState === 'complete') setTimeout(buildPanel, 1000);
})();
