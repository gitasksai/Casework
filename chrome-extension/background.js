// Opens the settings page the first time the extension is installed.
chrome.runtime.onInstalled.addListener(function (details) {
  if (details.reason === 'install') chrome.runtime.openOptionsPage();
});
