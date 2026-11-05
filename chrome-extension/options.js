'use strict';
var $ = function (id) { return document.getElementById(id); };
var statusEl = $('status');

function show(msg, kind) { statusEl.textContent = msg; statusEl.className = 'status ' + (kind || ''); }

chrome.storage.local.get({ serverUrl: '', apiToken: '', userName: '' }).then(function (s) {
  $('serverUrl').value = s.serverUrl;
  $('apiToken').value = s.apiToken;
  $('userName').value = s.userName;
});

async function save() {
  var serverUrl = $('serverUrl').value.trim().replace(/\/+$/, '');
  try { new URL(serverUrl); } catch (e) { show('Enter a full address, e.g. http://127.0.0.1:5000', 'err'); return false; }
  await chrome.storage.local.set({
    serverUrl: serverUrl, apiToken: $('apiToken').value.trim(), userName: $('userName').value.trim()
  });
  $('serverUrl').value = serverUrl;
  show('Saved.', 'ok');
  return true;
}

$('save').addEventListener('click', save);

$('test').addEventListener('click', async function () {
  if (!(await save())) return;
  show('Testing…');
  try {
    var headers = {};
    var token = $('apiToken').value.trim();
    if (token) headers.Authorization = 'Bearer ' + token;
    var resp = await fetch($('serverUrl').value + '/api/ping', { headers: headers });
    var body = await resp.json().catch(function () { return {}; });
    if (resp.ok && body.ok) show('Connected to Casework.', 'ok');
    else show(body.error || ('Server returned ' + resp.status), 'err');
  } catch (e) {
    show('Could not reach the server. Check the address, that Casework is running, and (for HTTPS) that this PC trusts its certificate.', 'err');
  }
});
