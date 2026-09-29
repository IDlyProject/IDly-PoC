// IDly 웹 페이지와 확장 사이 다리. IDly 웹(manifest의 matches)에서만 돈다.
// 웹 → 확장: window.postMessage({ source: 'idly-web', type, ... })
// 확장 → 웹: window.postMessage({ source: 'idly-ext', type, ... })

const version = chrome.runtime.getManifest().version

function announce() {
  window.postMessage({ source: 'idly-ext', type: 'READY', version }, location.origin)
}

document.documentElement.dataset.idlyExtension = version
announce()

window.addEventListener('message', (event) => {
  if (event.source !== window || event.origin !== location.origin) return
  const msg = event.data
  if (!msg || msg.source !== 'idly-web') return
  if (msg.type === 'PING') announce()
  if (msg.type === 'START') chrome.runtime.sendMessage({ type: 'IDLY_START', run: msg.run })
  if (msg.type === 'FOCUS') chrome.runtime.sendMessage({ type: 'IDLY_FOCUS', runId: msg.runId })
})
