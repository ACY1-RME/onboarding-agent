// ==UserScript==
// @name         A to Z Completed Training Scraper (ACY1 RME Onboarding Agent) v2
// @namespace    acy1-rme-onboarding
// @version      2.0
// @description  Scrapes your completed trainings list on A to Z (title + link) into a copyable list for the Onboarding Agent project.
// @match        https://atoz.amazon.work/*
// @grant        none
// ==/UserScript==

(function () {
  'use strict';

  const LANG_NAMES = /^(english|spanish|french|german|italian|portuguese|korean|turkish|dutch|polish|japanese|czech|malay|kannada|gujarati|tamil|telugu|marathi|hindi|punjabi|haitian creole|arabic|chinese|asl)\b/i;

  function buildPanel() {
    if (document.getElementById('acy1-scraper-panel')) return;

    const panel = document.createElement('div');
    panel.id = 'acy1-scraper-panel';
    panel.style.cssText = [
      'position:fixed', 'bottom:16px', 'right:16px', 'width:440px', 'max-height:70vh',
      'background:#111', 'color:#eee', 'border:2px solid #00CC99', 'border-radius:10px',
      'z-index:999999', 'font-family:sans-serif', 'font-size:12px', 'box-shadow:0 4px 20px rgba(0,0,0,.6)',
      'display:flex', 'flex-direction:column', 'overflow:hidden'
    ].join(';');

    panel.innerHTML = `
      <div style="padding:8px 12px;background:#004225;font-weight:bold;display:flex;justify-content:space-between;align-items:center;">
        <span>ACY1 RME Training Scraper v2</span>
        <button id="acy1-close" style="background:transparent;border:none;color:#fff;cursor:pointer;font-size:14px;">✕</button>
      </div>
      <div style="padding:8px 12px;">
        <button id="acy1-scan" style="padding:6px 12px;background:#00CC99;color:#04170c;border:none;border-radius:6px;cursor:pointer;font-weight:bold;">Scan this page</button>
        <button id="acy1-copy" style="padding:6px 12px;background:transparent;color:#00CC99;border:1px solid #00CC99;border-radius:6px;cursor:pointer;margin-left:6px;">Copy results</button>
        <div id="acy1-count" style="margin-top:6px;color:#7aad85;"></div>
      </div>
      <textarea id="acy1-output" style="flex:1;margin:0 12px 12px;background:#0d1f12;color:#eee;border:1px solid #2a4a30;border-radius:6px;padding:8px;font-family:monospace;font-size:11px;resize:none;" placeholder="Click 'Scan this page' after the completed trainings list has fully loaded..."></textarea>
    `;
    document.body.appendChild(panel);

    document.getElementById('acy1-close').onclick = () => panel.remove();
    document.getElementById('acy1-copy').onclick = () => {
      const ta = document.getElementById('acy1-output');
      ta.select();
      document.execCommand('copy');
      const btn = document.getElementById('acy1-copy');
      const old = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => (btn.textContent = old), 1200);
    };
    document.getElementById('acy1-scan').onclick = scan;
  }

  // Walk up from a node to find the smallest ancestor that contains "Completed:" text
  // and treat that ancestor as one "row" for a completed training item.
  function findCompletedRows() {
    const all = document.evaluate(
      "//*[contains(text(),'Completed:')]",
      document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
    );
    const rows = new Set();
    for (let i = 0; i < all.snapshotLength; i++) {
      let node = all.snapshotItem(i);
      // climb up a few levels to get the row/card container, not just the text node's parent
      let el = node.nodeType === 3 ? node.parentElement : node;
      for (let hop = 0; hop < 6 && el && el.parentElement; hop++) {
        el = el.parentElement;
        // stop climbing once this ancestor also contains a link (title link) - good sign it's the row
        if (el.querySelector('a[href]')) break;
      }
      if (el) rows.add(el);
    }
    return Array.from(rows);
  }

  function extractTitle(row) {
    // Prefer explicit heading-ish elements first
    const headingEl = row.querySelector('h1,h2,h3,h4,[class*="title"],[class*="name"],strong,b');
    if (headingEl && headingEl.textContent.trim().length > 3) {
      return headingEl.textContent.trim().replace(/\s+/g, ' ');
    }
    // Fallback: first link's text, if it's not just "View details" and not a language name
    const a = row.querySelector('a[href]');
    if (a) {
      const t = a.textContent.trim().replace(/\s+/g, ' ');
      if (t && !/^view details$/i.test(t) && !LANG_NAMES.test(t)) return t;
    }
    // Fallback: first reasonably long text node directly in the row
    const walker = document.createTreeWalker(row, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const t = n.textContent.trim();
      if (t.length > 6 && !/completed:/i.test(t) && !LANG_NAMES.test(t)) return t;
    }
    return '(title not found)';
  }

  function scan() {
    const rows = findCompletedRows();
    const results = [];
    const seenHref = new Set();

    rows.forEach((row) => {
      const links = Array.from(row.querySelectorAll('a[href]')).filter((a) => {
        const t = (a.textContent || '').trim();
        return !LANG_NAMES.test(t); // drop language-picker links
      });
      const href = links.length ? links[0].href : '(no link found in this row)';
      if (href !== '(no link found in this row)' && seenHref.has(href)) return;
      if (href !== '(no link found in this row)') seenHref.add(href);

      const title = extractTitle(row);
      results.push({ title, href });
    });

    const out = results.map((r) => `${r.title}\n${r.href}`).join('\n\n');
    document.getElementById('acy1-output').value = out || '(No "Completed:" rows found on this page. Make sure the transcript/completed-trainings list is visible and scrolled into view.)';
    document.getElementById('acy1-count').textContent = results.length + ' completed training row(s) found.';
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(buildPanel, 800);
  } else {
    window.addEventListener('DOMContentLoaded', () => setTimeout(buildPanel, 800));
  }
})();
