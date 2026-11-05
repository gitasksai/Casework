/*
 * Reads the case that is open in the Salesforce Lightning console.
 * Injected into the page by popup.js; defines window.__caseworkExtract(options).
 *
 * Lightning renders most of the page inside (synthetic or native) shadow DOM, so normal
 * document.querySelectorAll() can't see it. Everything here walks shadow roots, and only
 * looks at elements that are visible, so other console tabs open in the background
 * (which Salesforce keeps in the page but hides) are ignored.
 */
(function () {
  'use strict';

  var FIELD_ITEM = 'records-record-layout-item, .slds-form-element, force-record-layout-item, .forcePageBlockItem';
  var FIELD_LABEL = '.test-id__field-label, .slds-form-element__label, .test-id__field-label-container';
  var FIELD_VALUE = '.test-id__field-value, .slds-form-element__static, .slds-form-element__control, .itemBody';
  var FEED_ITEM = '.cuf-feedElement, .cuf-feedItem, article.forceChatterFeedItem, [class*="feedElement"], [class*="FeedItem"], [data-feed-item-id], [data-feed-element-id]';
  var FEED_AUTHOR = '.cuf-entityLink, a.forceChatterEntityLink, [class*="actorName"], [class*="entityLink"], .slds-media__body a[data-recordid], .slds-media__body a';
  var FEED_TIME = '.cuf-timestamp, [class*="timeStamp"], [class*="timestamp"], lightning-formatted-date-time, lightning-relative-date-time, time';
  var SKIP_CLASS = /(^|\s)(assistiveText|slds-assistive-text|slds-hide|hidden)(\s|$)/;

  function children(node) {
    // Shadow content first (if any), then light children (which are slotted into it).
    var out = [];
    if (node.shadowRoot) out.push.apply(out, node.shadowRoot.children);
    if (node.children) out.push.apply(out, node.children);
    return out;
  }

  function deepQueryAll(root, selector) {
    var found = [], stack = [root];
    while (stack.length) {
      var n = stack.pop();
      if (n.nodeType === 1 && n.matches(selector)) found.push(n);
      var kids = children(n);
      for (var i = kids.length - 1; i >= 0; i--) stack.push(kids[i]);
    }
    return found;
  }

  function deepQuery(root, selector) {
    var all = deepQueryAll(root, selector);
    return all.length ? all[0] : null;
  }

  function isVisible(el) {
    if (!el.getClientRects || !el.getClientRects().length) return false;
    var cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none';
  }

  function composedParent(n) {
    return n.parentNode && n.parentNode.nodeType === 11 ? n.parentNode.host : n.parentNode;
  }

  function isInside(el, set) {
    for (var p = composedParent(el); p; p = composedParent(p)) if (set.has(p)) return true;
    return false;
  }

  var BLOCK = /^(block|flex|grid|list-item|table|table-row|flow-root)$/;

  // Visible text of an element, walking shadow roots and slots, with line breaks between blocks.
  function deepText(root) {
    var parts = [];
    (function walk(node) {
      if (node.nodeType === 3) { parts.push(node.nodeValue); return; }
      if (node.nodeType !== 1 && node.nodeType !== 11) return;
      if (node.nodeType === 1) {
        var tag = node.tagName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEMPLATE' || tag === 'SVG' || tag === 'svg') return;
        if (typeof node.className === 'string' && SKIP_CLASS.test(node.className)) return;
        if (tag === 'BR') { parts.push('\n'); return; }
        var cs = getComputedStyle(node);
        if (cs.display === 'none' || cs.visibility === 'hidden') return;
        var block = BLOCK.test(cs.display) || /^(P|DIV|LI|TR|BUTTON|H[1-6])$/.test(tag);
        if (block) parts.push('\n');
        if (tag === 'SLOT') {
          node.assignedNodes({ flatten: true }).forEach(walk);
        } else if (node.shadowRoot) {
          Array.prototype.forEach.call(node.shadowRoot.childNodes, walk);
        } else {
          Array.prototype.forEach.call(node.childNodes, walk);
        }
        if (block) parts.push('\n');
        return;
      }
      Array.prototype.forEach.call(node.childNodes, walk);  // shadow root
    })(root);
    return parts.join('')
      .replace(/[ \t ]+/g, ' ')
      .split('\n').map(function (l) { return l.trim(); }).join('\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function visibleFeedItems() {
    var items = deepQueryAll(document, FEED_ITEM).filter(isVisible);
    var set = new Set(items);
    return items.filter(function (el) { return !isInside(el, set); });  // outermost only
  }

  // Click "Show more" inside posts and "View more"/"Load more" at the end of the feed.
  var IN_POST = /^(show|see|view|read) (more|all|full (email|message))$|^more$|^expand( post| email)?$/i;
  var IN_FEED = /^(show|see|view|load) (more|all)( (posts|updates|feed items|activity|emails))?$/i;

  function clickMatching(scope, regex) {
    var n = 0;
    deepQueryAll(scope, 'button, a').forEach(function (b) {
      var t = (b.innerText || b.textContent || '').replace(/\s+/g, ' ').trim();
      if (t.length < 30 && regex.test(t) && !b.dataset.caseworkClicked && isVisible(b)) {
        b.dataset.caseworkClicked = '1';
        b.click();
        n++;
      }
    });
    return n;
  }

  async function expandFeed(maxRounds) {
    for (var round = 0; round < maxRounds; round++) {
      var items = visibleFeedItems();
      if (!items.length) return;
      var clicked = 0;
      items.forEach(function (it) { clicked += clickMatching(it, IN_POST); });
      var feed = items[0];  // climb a few levels to reach the feed list's "View more" button
      for (var i = 0; i < 4 && composedParent(feed) && composedParent(feed).nodeType === 1; i++) feed = composedParent(feed);
      clicked += clickMatching(feed, IN_FEED);
      if (!clicked) return;
      await sleep(1500);
    }
  }

  function readFields() {
    var fields = [], seen = new Set();
    deepQueryAll(document, FIELD_ITEM).filter(isVisible).forEach(function (item) {
      var labelEl = deepQuery(item, FIELD_LABEL);
      var label = labelEl ? deepText(labelEl) : '';
      var valueEl = deepQuery(item, FIELD_VALUE);
      var value = valueEl ? deepText(valueEl) : '';
      label = label.split('\n')[0].trim();
      if (!label) {
        var lines = deepText(item).split('\n').filter(Boolean);
        label = (lines.shift() || '').trim();
        value = value || lines.join('\n');
      } else if (valueEl && valueEl.contains(labelEl)) {
        value = value.slice(value.indexOf(label) + label.length).trim();  // value container also holds the label
      }
      if (!label || label.length > 80 || seen.has(label.toLowerCase())) return;
      seen.add(label.toLowerCase());
      fields.push({ label: label, value: value.slice(0, 20000) });
    });
    return fields;
  }

  function readFeed() {
    return visibleFeedItems().map(function (item) {
      var authorEl = deepQuery(item, FEED_AUTHOR);
      var timeEl = deepQuery(item, FEED_TIME);
      var timeTitle = '';
      if (timeEl) {
        timeTitle = timeEl.getAttribute('title') || timeEl.getAttribute('datetime') ||
                    timeEl.getAttribute('value') || '';
        var a = timeEl.closest && timeEl.closest('a[title]');
        if (!timeTitle && a) timeTitle = a.getAttribute('title');
      }
      return {
        author: authorEl ? deepText(authorEl).split('\n')[0] : '',
        timeText: timeEl ? deepText(timeEl) : '',
        timeTitle: timeTitle,
        text: deepText(item).slice(0, 100000)
      };
    });
  }

  function caseNumber(fields) {
    for (var i = 0; i < fields.length; i++) {
      if (/^case (number|no\.?|#)$/i.test(fields[i].label) && fields[i].value) return fields[i].value.split('\n')[0];
    }
    var m = (document.title || '').match(/\b(\d{5,})\b/);
    if (m) return m[1];
    var tabs = deepQueryAll(document, '[role="tab"][aria-selected="true"], .tabItem.active, li.slds-is-active');
    for (var j = 0; j < tabs.length; j++) {
      var t = deepText(tabs[j]).match(/\b(\d{5,})\b/);
      if (t) return t[1];
    }
    return '';
  }

  // Structure-only outline (tag + classes, no text) to help fix selectors without sharing case data.
  function outline(root, depth, maxDepth, out) {
    if (depth > maxDepth || out.length > 4000) return out;
    children(root).forEach(function (el) {
      if (!isVisible(el)) return;
      var cls = (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/).slice(0, 4).join('.');
      out.push(new Array(depth + 1).join('  ') + el.tagName.toLowerCase() + (cls ? '.' + cls : '') +
               (el.shadowRoot ? ' #shadow' : ''));
      outline(el, depth + 1, maxDepth, out);
    });
    return out;
  }

  window.__caseworkExtract = async function (options) {
    options = options || {};
    var warnings = [];
    if (options.expand !== false) {
      try { await expandFeed(6); } catch (e) { warnings.push('Could not expand the feed: ' + e.message); }
    }
    var fields = readFields();
    var feed = readFeed();
    if (!fields.length) warnings.push('No case fields were found on the page.');
    if (!feed.length) warnings.push('No feed items were found. Open the case feed (All Updates) and try again.');
    var result = {
      source: 'salesforce-lightning',
      version: 1,
      url: location.href,
      title: document.title,
      capturedAt: new Date().toISOString(),
      userName: options.userName || '',
      caseNumber: caseNumber(fields),
      fields: fields,
      feed: feed,
      warnings: warnings
    };
    if (options.debug) {
      result.debug = {
        fieldItemCount: deepQueryAll(document, FIELD_ITEM).length,
        feedItemCandidates: deepQueryAll(document, FEED_ITEM).length,
        outline: outline(document.body, 0, 40, [])
      };
      result.fields = fields.map(function (f) { return { label: f.label, value: '(' + f.value.length + ' chars)' }; });
      result.feed = feed.map(function (f) {
        return { author: f.author ? '(author)' : '', timeText: f.timeText, timeTitle: f.timeTitle,
                 text: '(' + f.text.length + ' chars)' };
      });
    }
    return result;
  };
})();
