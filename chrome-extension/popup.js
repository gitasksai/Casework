'use strict';
var statusEl = document.getElementById('status');

function show(msg, kind) {
  statusEl.textContent = msg;
  statusEl.className = 'status ' + (kind || '');
}

function getSettings() {
  return chrome.storage.local.get({ serverUrl: '', apiToken: '', userName: '' });
}

async function runExtractor(options) {
  var [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https:\/\//.test(tab.url || '')) throw new Error('Open the Salesforce case in this tab first.');
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['extractor.js'] });
  var [res] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: function (opts) { return window.__caseworkExtract(opts); },
    args: [options]
  });
  if (!res || !res.result) throw new Error('Could not read this page.');
  return res.result;
}

document.getElementById('settings').addEventListener('click', function (e) {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

document.getElementById('capture').addEventListener('click', async function () {
  var btn = this;
  btn.disabled = true;
  try {
    var s = await getSettings();
    if (!s.serverUrl) { show('Set your Casework server address in Settings first.', 'err'); return; }
    show('Reading the case…');
    var data = await runExtractor({ userName: s.userName, expand: document.getElementById('expand').checked });
    show('Found case ' + (data.caseNumber || '(no number)') + ': ' + data.fields.length + ' fields, ' +
         data.feed.length + ' feed items.\nSending to Casework…');
    var headers = { 'Content-Type': 'application/json' };
    if (s.apiToken) headers.Authorization = 'Bearer ' + s.apiToken;
    var resp = await fetch(s.serverUrl.replace(/\/+$/, '') + '/api/import', {
      method: 'POST', headers: headers, body: JSON.stringify(data)
    });
    var body = await resp.json().catch(function () { return {}; });
    if (!resp.ok || !body.ok) throw new Error(body.error || ('Server returned ' + resp.status));
    show('Sent. ' + body.counts.included + ' items suggested, ' + body.counts.ignored + ' ignored. Opening review…', 'ok');
    chrome.tabs.create({ url: body.reviewUrl });
  } catch (err) {
    var msg = err.message || String(err);
    if (/Failed to fetch/i.test(msg)) {
      msg = 'Could not reach the Casework server. Check the address in Settings, that the server is running, ' +
            'and (for HTTPS) that this PC trusts its certificate.';
    }
    show(msg, 'err');
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('debugBtn').addEventListener('click', async function (e) {
  e.preventDefault();
  try {
    var data = await runExtractor({ debug: true, expand: false });
    var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'casework-page-structure.json'; a.click();
    show('Saved casework-page-structure.json. It lists page element names and counts, not case text.', 'ok');
  } catch (err) {
    show(err.message || String(err), 'err');
  }
});
