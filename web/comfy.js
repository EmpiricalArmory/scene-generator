// The connection to ComfyUI: queue workflows at /prompt and follow them on its websocket.

const clientId = (() => {
  try {
    let id = sessionStorage.getItem('ea-client-id');
    if (!id) { id = 'ea-' + Math.random().toString(36).slice(2, 10); sessionStorage.setItem('ea-client-id', id); }
    return id;
  } catch { return 'ea-' + Math.random().toString(36).slice(2, 10); }
})();

const listeners = new Set();
const watched = new Map();   // prompt_id -> { onProgress, onNode, onOutput, onDone, onError, last }
let ws = null;
let wsOpen = false;
let retry = 1000;
let queueRemaining = 0;

export function on(fn) { listeners.add(fn); return () => listeners.delete(fn); }
function emit(type, data) { for (const fn of listeners) { try { fn(type, data); } catch (e) { console.error(e); } } }

export function connected() { return wsOpen; }
export function remaining() { return queueRemaining; }

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws?clientId=${clientId}`);
  ws.addEventListener('open', () => { wsOpen = true; retry = 1000; emit('connection', true); recheck(); });
  ws.addEventListener('close', () => {
    wsOpen = false; emit('connection', false);
    setTimeout(connect, retry); retry = Math.min(retry * 1.6, 8000);
  });
  ws.addEventListener('message', (ev) => {
    if (typeof ev.data !== 'string') return;         // binary previews are not used
    let msg; try { msg = JSON.parse(ev.data); } catch { return; }
    const { type, data } = msg;
    if (type === 'status') {
      queueRemaining = data?.status?.exec_info?.queue_remaining ?? 0;
      emit('queue', queueRemaining);
      return;
    }
    const w = data?.prompt_id ? watched.get(data.prompt_id) : null;
    if (type === 'execution_start' && w) w.onNode?.('start');
    if (type === 'executing' && w) { if (data.node) w.onNode?.(data.node); }
    if (type === 'progress' && w) w.onProgress?.(data.value, data.max, data.node);
    if (type === 'executed' && w) w.onOutput?.(data.node, data.output || {});
    if (type === 'execution_error' && w) { watched.delete(data.prompt_id); w.onError?.(data.exception_message || 'The model stopped with an error.', data); }
    if (type === 'execution_interrupted' && w) { watched.delete(data.prompt_id); w.onError?.('Stopped.', data); }
    if (type === 'execution_success' && w) { watched.delete(data.prompt_id); w.onDone?.(); }
    emit(type, data);
  });
}

// After a reconnect (ComfyUI restarted, or the page slept) finish anything that completed meanwhile.
async function recheck() {
  for (const [pid, w] of [...watched]) {
    try {
      const h = await (await fetch('/history/' + pid, { cache: 'no-store' })).json();
      const rec = h[pid];
      if (!rec) continue;
      for (const [node, out] of Object.entries(rec.outputs || {})) w.onOutput?.(node, out);
      watched.delete(pid);
      if (rec.status?.status_str === 'error') w.onError?.('The model stopped with an error.', rec);
      else w.onDone?.();
    } catch { /* still running, or ComfyUI not up yet */ }
  }
}

export async function queue(prompt, handlers = {}) {
  const res = await fetch('/prompt', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, client_id: clientId }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.error) {
    const errs = body.node_errors ? Object.values(body.node_errors).flatMap((e) => e.errors || []).map((e) => e.details || e.message) : [];
    throw new Error([body.error?.message || body.error || 'ComfyUI refused the job.', ...errs].filter(Boolean).join(' '));
  }
  watched.set(body.prompt_id, handlers);
  return body.prompt_id;
}

export async function interrupt() { await fetch('/interrupt', { method: 'POST' }); }
export async function clearQueue() { await fetch('/queue', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clear: true }) }); }
export async function cancel(promptId) {
  await fetch('/queue', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ delete: [promptId] }) });
  const w = watched.get(promptId);
  if (w) { watched.delete(promptId); w.onError?.('Removed from the queue.'); }
}

// Queue a workflow and resolve with its outputs when it finishes.
export function run(prompt, { onProgress, onNode } = {}) {
  return new Promise((resolve, reject) => {
    const outputs = {};
    queue(prompt, {
      onProgress, onNode,
      onOutput: (node, out) => { outputs[node] = out; },
      onDone: () => resolve(outputs),
      onError: (msg) => reject(new Error(msg)),
    }).catch(reject);
  });
}

connect();
