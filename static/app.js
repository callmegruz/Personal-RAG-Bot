let SESSION_ID = localStorage.getItem('active_session_id');
if (!SESSION_ID) {
  SESSION_ID = Math.random().toString(36).slice(2);
  localStorage.setItem('active_session_id', SESSION_ID);
}
let isStreaming = false, sidebarOn = window.innerWidth >= 768, msgCount = 0;

// Set up initial responsive sidebar visibility
if (!sidebarOn) {
  document.getElementById('sidebar').classList.add('hidden');
  const sbBtn = document.getElementById('sb-btn');
  if (sbBtn) sbBtn.classList.remove('active');
}
let currentAbortController = null;
const modelUsage = {};
const activeTheme = window.ACTIVE_THEME || "classic";
const MODEL_COLORS = activeTheme === 'fire'
  ? ['#ff3b00', '#ffb703', '#d90429', '#ff7b00', '#f72585', '#b7094c']
  : ['#8b5cf6', '#10b981', '#3b82f6', '#f59e0b', '#ec4899', '#f43f5e'];
const modelColor = {}; let colorIdx = 0;
function getModelColor(n) { if (!modelColor[n]) modelColor[n] = MODEL_COLORS[colorIdx++ % MODEL_COLORS.length]; return modelColor[n]; }

function onModelChange() {
  const m = document.getElementById('model-select').value;
  document.getElementById('pill-model').textContent = m;
  fetch('/api/switch-model', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: SESSION_ID, model: m }) });
}

function onThemeChange() {
  const t = document.getElementById('theme-select').value;

  // Update body class dynamically
  if (t === 'fire') {
    document.body.classList.remove('theme-classic');
    document.body.classList.add('theme-fire');
    // Update color palette swatches
    MODEL_COLORS.length = 0;
    MODEL_COLORS.push('#ff3b00', '#ffb703', '#d90429', '#ff7b00', '#f72585', '#b7094c');
  } else {
    document.body.classList.remove('theme-fire');
    document.body.classList.add('theme-classic');
    // Update color palette swatches
    MODEL_COLORS.length = 0;
    MODEL_COLORS.push('#8b5cf6', '#10b981', '#3b82f6', '#f59e0b', '#ec4899', '#f43f5e');
  }

  // Clear model colors cache and redraw models list
  for (const k in modelColor) delete modelColor[k];
  colorIdx = 0;
  updateModelHistory('');

  // Save it to a 30-day cookie so backend serves this theme next time
  document.cookie = `theme=${t};path=/;max-age=${30 * 24 * 60 * 60}`;
}

// Poll for newly pulled models every 30s
async function pollModels() {
  try {
    const data = await (await fetch('/api/models')).json();
    const sel = document.getElementById('model-select');
    const have = [...sel.options].map(o => o.value);
    let added = false;
    for (const m of data.models) {
      if (!have.includes(m)) {
        const o = document.createElement('option'); o.value = o.textContent = m;
        sel.appendChild(o); added = true;
      }
    }
    if (added) showToast('New model available in dropdown');
  } catch { }
}
setInterval(pollModels, 30000);

let toastTimeoutId = null;
function showToast(msg) {
  let t = document.querySelector('.toast-notification');
  if (t) {
    t.querySelector('span').textContent = msg;
    if (toastTimeoutId) {
      clearTimeout(toastTimeoutId);
    }
  } else {
    t = document.createElement('div');
    t.className = 'toast-notification';
    t.innerHTML = `
      <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
      <span>${msg}</span>
    `;
    document.body.appendChild(t);
  }
  toastTimeoutId = setTimeout(() => {
    t.remove();
    toastTimeoutId = null;
  }, 3500);
}

function updateModelHistory(model) {
  modelUsage[model] = (modelUsage[model] || 0) + 1;
  const list = document.getElementById('model-history-list'); list.innerHTML = '';
  for (const [name, turns] of Object.entries(modelUsage)) {
    const color = getModelColor(name);
    const el = document.createElement('div'); el.className = 'mh-item';
    el.innerHTML = `<span class="mh-dot" style="background:${color};box-shadow:0 0 5px ${color}"></span>
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(name)}</span>
        <span class="mh-turns">${turns}t</span>`;
    list.appendChild(el);
  }
}

function insertSwitchEvent(from, to) {
  const el = document.createElement('div'); el.className = 'switch-event';
  el.innerHTML = `<div class="switch-badge">
      <svg viewBox="0 0 24 24" width="11" height="11" stroke="currentColor" stroke-width="2" fill="none"><path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5"></path></svg>
      <span>${esc(from)} &rarr; ${esc(to)}</span>
    </div>`;
  document.getElementById('messages').appendChild(el); scrollBottom();
}

function toggleSidebar() {
  sidebarOn = !sidebarOn;
  document.getElementById('sidebar').classList.toggle('hidden', !sidebarOn);
  const sbBtn = document.getElementById('sb-btn');
  if (sbBtn) sbBtn.classList.toggle('active', sidebarOn);

  // Handle smooth backdrop animation on mobile devices
  const overlay = document.getElementById('sidebar-overlay');
  if (overlay) {
    if (sidebarOn && window.innerWidth <= 768) {
      overlay.style.display = 'block';
      overlay.offsetHeight; // Force DOM reflow to trigger transition animation smoothly
      overlay.style.opacity = '1';
    } else {
      overlay.style.opacity = '0';
      setTimeout(() => {
        // Ensure sidebar is still closed when animation ends
        if (!sidebarOn || window.innerWidth > 768) {
          overlay.style.display = 'none';
        }
      }, 250);
    }
  }
}

async function refreshDocs() {
  const data = await (await fetch('/api/documents')).json();
  document.getElementById('chunk-count').textContent = `${data.total_chunks} chunks`;
  const list = document.getElementById('doc-list');
  if (!data.documents.length) {
    list.innerHTML = '<div class="doc-empty">No documents yet.</div>';
    document.getElementById('pill-rag').textContent = 'RAG IDLE';
    document.getElementById('pill-rag').classList.remove('rag');
    return;
  }
  list.innerHTML = '';
  for (const name of data.documents) {
    const row = document.createElement('div'); row.className = 'doc-item';
    row.innerHTML = `<div style="display:flex;align-items:center;gap:6px;overflow:hidden;">
        <svg viewBox="0 0 24 24" width="12" height="12" stroke="var(--info)" stroke-width="2" fill="none" style="flex-shrink:0;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
        <span class="doc-name" title="${esc(name)}">${esc(name)}</span>
      </div>
      <span class="doc-del" onclick="deleteDoc('${esc(name)}')">&times;</span>`;
    list.appendChild(row);
  }
  document.getElementById('pill-rag').textContent = `RAG ✓ (${data.documents.length})`;
  document.getElementById('pill-rag').classList.add('rag');
}

async function deleteDoc(name) {
  if (!await showConfirm('Remove Document', `Are you sure you want to remove "${name}"? This will delete all its vector embeddings.`)) return;
  await fetch('/api/documents/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ filename: name }) });
  refreshDocs();
}

let dragCounter = 0;
window.addEventListener('dragenter', (e) => {
  e.preventDefault();
  dragCounter++;
  if (dragCounter === 1) {
    document.getElementById('drag-overlay').style.display = 'flex';
  }
});

window.addEventListener('dragleave', (e) => {
  e.preventDefault();
  dragCounter--;
  if (dragCounter === 0) {
    document.getElementById('drag-overlay').style.display = 'none';
  }
});

window.addEventListener('dragover', (e) => {
  e.preventDefault();
});

window.addEventListener('drop', (e) => {
  e.preventDefault();
  dragCounter = 0;
  document.getElementById('drag-overlay').style.display = 'none';
  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
    uploadFile(e.dataTransfer.files[0]);
  }
});

async function uploadFile(file) {
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) {
    showToast("File size exceeds the 10MB maximum limit.");
    return;
  }
  const prog = document.getElementById('upload-progress'), bar = document.getElementById('prog-bar'), lbl = document.getElementById('prog-label');
  prog.style.display = 'block'; bar.style.width = '10%'; lbl.textContent = `Indexing ${file.name}…`;
  const fd = new FormData(); fd.append('file', file);
  let pct = 10; const tick = setInterval(() => { pct = Math.min(pct + 5, 85); bar.style.width = pct + '%'; }, 400);
  try {
    const data = await (await fetch('/api/documents/upload', { method: 'POST', body: fd })).json(); clearInterval(tick);
    if (data.error) { lbl.textContent = `Error: ${data.error}`; bar.style.background = 'var(--danger)'; }
    else { bar.style.width = '100%'; lbl.textContent = `✓ Indexed ${data.filename}`; refreshDocs(); }
  } catch (err) { clearInterval(tick); lbl.textContent = `Failed: ${err.message}`; }
  setTimeout(() => { prog.style.display = 'none'; bar.style.width = '0'; bar.style.background = 'var(--accent)'; }, 3000);
  document.getElementById('file-input').value = '';
}

async function refreshMemory() {
  const mem = await (await fetch('/api/memory')).json();
  const list = document.getElementById('mem-list');
  if (!Object.keys(mem).length) { list.innerHTML = '<div class="mem-empty">No facts yet.</div>'; return; }
  list.innerHTML = '';
  for (const [k, v] of Object.entries(mem)) {
    const el = document.createElement('div'); el.className = 'mem-item';
    el.innerHTML = `<div class="mem-key">${esc(k)}</div><div>${esc(String(v))}</div>`;
    list.appendChild(el);
  }
}

async function loadChatHistory() {
  try {
    const res = await fetch(`/api/chat/history?session_id=${SESSION_ID}`);
    if (!res.ok) {
      const es = document.getElementById('empty-state');
      if (es) es.style.display = 'flex';
      return;
    }
    const data = await res.json();
    
    if (data.messages && data.messages.length > 0) {
      removeEmptyState();
      const container = document.getElementById('messages');
      container.innerHTML = '';
      
      msgCount = data.messages.length;
      
      data.messages.forEach(msg => {
        appendMessage(msg.role, parseMarkdown(msg.content));
      });
      
      if (msgCount > 6 || data.summary) {
        const pillSum = document.getElementById('pill-sum');
        if (pillSum) {
          pillSum.textContent = 'SUMMARY ✓';
          pillSum.classList.add('sum');
        }
      }
      
      scrollBottom();
    } else {
      const es = document.getElementById('empty-state');
      if (es) es.style.display = 'flex';
    }
  } catch (err) {
    console.error("Failed to load chat history:", err);
    const es = document.getElementById('empty-state');
    if (es) es.style.display = 'flex';
  }
}

async function clearMemory() {
  if (!await showConfirm('Clear Facts', 'Are you sure you want to clear all remembered facts about yourself? This cannot be undone.')) return;
  await fetch('/api/memory', { method: 'DELETE' });
  refreshMemory();
}

const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function autoResize(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px'; }
function handleKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }
function scrollBottom() { const m = document.getElementById('messages'); m.scrollTop = m.scrollHeight; }
function removeEmptyState() { const es = document.getElementById('empty-state'); if (es) es.remove(); }

function clickSuggestion(text) {
  const input = document.getElementById('user-input');
  input.value = text;
  input.focus();
  autoResize(input);
}

/* Custom Confirmation Modal */
let modalResolve = null;
function showConfirm(title, message) {
  document.getElementById('modal-title-text').textContent = title;
  document.getElementById('modal-body-text').textContent = message;
  document.getElementById('confirm-modal').classList.add('active');
  return new Promise((resolve) => {
    modalResolve = resolve;
  });
}
function closeModal() {
  document.getElementById('confirm-modal').classList.remove('active');
  if (modalResolve) {
    modalResolve(false);
    modalResolve = null;
  }
}
document.getElementById('modal-confirm-btn').onclick = () => {
  document.getElementById('confirm-modal').classList.remove('active');
  if (modalResolve) {
    modalResolve(true);
    modalResolve = null;
  }
};

/* Premium Markdown Parser */
function parseMarkdown(text) {
  if (!text) return "";

  // Auto-close open code block during streaming
  let cleanText = text;
  const matchTicks = text.match(/```/g);
  if (matchTicks && matchTicks.length % 2 !== 0) {
    cleanText += "\n```";
  }

  let escaped = cleanText
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Extract code blocks first to protect them
  const codeBlocks = [];
  escaped = escaped.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
    const placeholder = `:::CODEBLOCK_${codeBlocks.length}:::`;
    codeBlocks.push({ lang: lang || "code", code: code });
    return placeholder;
  });

  // Process line-by-line
  const lines = escaped.split('\n');
  let result = [];
  let inList = false;
  let listType = null; // 'ul' or 'ol'

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    const ulMatch = line.match(/^[\-\*]\s+(.*)/);
    const olMatch = line.match(/^(\d+)\.\s+(.*)/);
    const headerMatch = line.match(/^(#{1,6})\s+(.*)/);

    if (ulMatch) {
      if (!inList || listType !== 'ul') {
        if (inList) result.push(`</${listType}>`);
        result.push('<ul>');
        inList = true;
        listType = 'ul';
      }
      result.push(`<li>${processInlineStyles(ulMatch[1])}</li>`);
    } else if (olMatch) {
      if (!inList || listType !== 'ol') {
        if (inList) result.push(`</${listType}>`);
        result.push('<ol>');
        inList = true;
        listType = 'ol';
      }
      result.push(`<li>${processInlineStyles(olMatch[2])}</li>`);
    } else {
      if (inList) {
        result.push(`</${listType}>`);
        inList = false;
        listType = null;
      }

      if (headerMatch) {
        const level = headerMatch[1].length;
        result.push(`<h${level}>${processInlineStyles(headerMatch[2])}</h${level}>`);
      } else if (line.trim() === '') {
        result.push('<div class="spacer"></div>');
      } else {
        if (line.includes(':::CODEBLOCK_')) {
          result.push(line);
        } else {
          result.push(`<p>${processInlineStyles(line)}</p>`);
        }
      }
    }
  }

  if (inList) {
    result.push(`</${listType}>`);
  }

  let htmlResult = result.join('\n');

  // Restore code blocks with beautiful headers & copy buttons
  for (let idx = 0; idx < codeBlocks.length; idx++) {
    const { lang, code } = codeBlocks[idx];
    const placeholder = `:::CODEBLOCK_${idx}:::`;

    const codeBlockHtml = `
        <div class="code-container">
          <div class="code-header">
            <span class="code-lang">${lang.toUpperCase()}</span>
            <button class="code-copy-btn" onclick="copyCode(this)">
              <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              <span>Copy</span>
            </button>
          </div>
          <pre><code class="language-${lang}">${code.trim()}</code></pre>
        </div>
      `;
    htmlResult = htmlResult.replace(placeholder, codeBlockHtml);
  }

  return htmlResult;
}

function processInlineStyles(text) {
  let s = text.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*([\s\S]+?)\*/g, '<em>$1</em>');
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  return s;
}

function copyCode(btn) {
  const codeEl = btn.closest('.code-container').querySelector('code');
  if (!codeEl) return;
  const text = codeEl.textContent;
  navigator.clipboard.writeText(text).then(() => {
    const label = btn.querySelector('span');
    const origText = label.textContent;
    label.textContent = 'Copied!';
    btn.classList.add('copied');
    const origSvg = btn.querySelector('svg').innerHTML;
    btn.querySelector('svg').innerHTML = '<polyline points="20 6 9 17 4 12"></polyline>';
    setTimeout(() => {
      label.textContent = origText;
      btn.classList.remove('copied');
      btn.querySelector('svg').innerHTML = origSvg;
    }, 2000);
  }).catch(err => {
    console.error('Failed to copy code: ', err);
  });
}

function appendMessage(role, html = '', model = '') {
  removeEmptyState();
  const container = document.getElementById('messages');
  const wrap = document.createElement('div'); wrap.className = `message ${role}`;

  const av = document.createElement('div'); av.className = 'avatar';
  if (role === 'user') {
    av.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`;
  } else {
    av.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>`;
  }

  const bub = document.createElement('div'); bub.className = 'bubble';
  if (role === 'bot' && model) {
    const color = getModelColor(model);
    bub.innerHTML = `<span class="model-tag" style="border-color:${color};color:${color};background:${color}18">${esc(model)}</span><br>` + html;
  }
  else bub.innerHTML = html;
  wrap.appendChild(av); wrap.appendChild(bub); container.appendChild(wrap); scrollBottom();
  return bub;
}

function updateSendButtonState(isProcessing) {
  const sendBtn = document.getElementById('send-btn');
  if (isProcessing) {
    sendBtn.classList.add('stop-mode');
    sendBtn.title = "Stop Generating";
    sendBtn.innerHTML = `
          <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2.5" fill="currentColor">
            <rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>
          </svg>
        `;
  } else {
    sendBtn.classList.remove('stop-mode');
    sendBtn.title = "Send Message";
    sendBtn.innerHTML = `
          <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2.5" fill="none"
            style="transform: translate(1px, -1px)">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
        `;
  }
}

async function sendMessage() {
  if (isStreaming) {
    if (currentAbortController) {
      currentAbortController.abort();
    }
    return;
  }

  // Reset active Speech Synthesis readback
  window.speechSynthesis.cancel();
  speechQueue = [];
  isSpeaking = false;
  activeUtterance = null;
  lastSentenceIndex = 0;

  const input = document.getElementById('user-input');
  const msg = input.value.trim(); if (!msg) return;
  const model = document.getElementById('model-select').value;

  isStreaming = true;
  currentAbortController = new AbortController();
  const signal = currentAbortController.signal;
  updateSendButtonState(true);

  input.value = ''; input.style.height = 'auto';
  appendMessage('user', parseMarkdown(msg));
  const botBubble = appendMessage('bot', '<span class="cursor"></span>', model);
  let botText = '', metaSeen = false, sourcesData = null;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, session_id: SESSION_ID, model }),
      signal: signal
    });
    const reader = res.body.getReader(), decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      for (const line of decoder.decode(value).split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.slice(6));
        if (!metaSeen && data.sources !== undefined) {
          metaSeen = true; sourcesData = data;
          if (data.model_switched) insertSwitchEvent(data.prev_model, data.current_model);
          if (data.sources.length) {
            document.getElementById('pill-rag').textContent = 'RAG ACTIVE ✓';
            document.getElementById('pill-rag').classList.add('rag');
          }
        }
        if (data.error) { botBubble.innerHTML = `<span class="error-msg"><svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg> ${data.error}</span>`; break; }
        if (data.token !== undefined) {
          botText += data.token;
          const color = getModelColor(model);
          const tag = `<span class="model-tag" style="border-color:${color};color:${color};background:${color}18">${esc(model)}</span><br>`;
          botBubble.innerHTML = tag + parseMarkdown(botText) + (data.done ? '' : '<span class="cursor"></span>');

          // Process Speech Synthesis dynamically sentence-by-sentence
          processStreamingTTS(botText, data.done);

          if (data.done) {
            if (sourcesData?.sources?.length) {
              const sd = document.createElement('div');
              sd.className = 'sources';
              for (const s of sourcesData.sources) {
                const t = document.createElement('span');
                t.className = 'source-tag';
                t.innerHTML = `<svg viewBox="0 0 24 24" width="10" height="10" stroke="currentColor" stroke-width="2" fill="none"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                    <span>${s}</span>`;
                sd.appendChild(t);
              }
              botBubble.appendChild(sd);
            }
            msgCount += 2; updateModelHistory(model);
            if (msgCount > 6) {
              document.getElementById('pill-sum').textContent = 'SUMMARY ✓';
              document.getElementById('pill-sum').classList.add('sum');
            }
            setTimeout(refreshMemory, 1800);
          }
          scrollBottom();
        }
      }
    }

    // Finalize speech synthesis for any leftover sentence
    processStreamingTTS(botText, true);
  } catch (err) {
    if (err.name === 'AbortError') {
      // Remove streaming cursor
      const cursor = botBubble.querySelector('.cursor');
      if (cursor) cursor.remove();

      botBubble.innerHTML += `<div style="font-size:11px;color:var(--muted);font-style:italic;margin-top:5px;border-top:1px solid var(--border);padding-top:4px;">Generation stopped by user.</div>`;

      // Cancel active speech playback
      window.speechSynthesis.cancel();
      speechQueue = [];
      isSpeaking = false;
      activeUtterance = null;
    } else {
      botBubble.innerHTML = `<span class="error-msg"><svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg> ${err.message}</span>`;
    }
  } finally {
    isStreaming = false;
    currentAbortController = null;
    updateSendButtonState(false);
    input.focus();
  }
}

async function clearChat() {
  if (!await showConfirm('Clear Chat', 'Are you sure you want to clear the conversation history? This will reset all summary context.')) return;

  // Cancel active speech
  window.speechSynthesis.cancel();
  speechQueue = [];
  isSpeaking = false;
  activeUtterance = null;

  await fetch('/api/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: SESSION_ID }) });
  msgCount = 0; Object.keys(modelUsage).forEach(k => delete modelUsage[k]);
  document.getElementById('pill-sum').textContent = 'NO SUMMARY'; document.getElementById('pill-sum').classList.remove('sum');
  document.getElementById('model-history-list').innerHTML = '<div class="doc-empty" style="padding:8px 0">None yet.</div>';
  document.getElementById('messages').innerHTML = `<div class="empty-state" id="empty-state">
      <div class="empty-logo">
        <svg viewBox="0 0 24 24" width="48" height="48" stroke="var(--accent)" stroke-width="1.5" fill="none" style="filter: drop-shadow(0 0 8px var(--accent-glow))"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"></polygon><line x1="12" y1="2" x2="12" y2="22"></line><line x1="12" y1="12" x2="22" y2="8.5"></line><line x1="12" y1="12" x2="2" y2="8.5"></line></svg>
      </div>
      <h2>Local RAG Assistant</h2>
      <p class="subtitle">Fully local chat with document embedding &amp; session memory</p>
    </div>`;
  updateEmptyStateGreeting();
}

// ==========================================
// STT (SPEECH-TO-TEXT) & TTS (TEXT-TO-SPEECH) SYSTEM
// ==========================================
let ttsEnabled = false;
let speechQueue = [];
let isSpeaking = false;
let activeUtterance = null;
let lastSentenceIndex = 0;

let recording = false;
let audioCtx = null;
let micStream = null;
let processorNode = null;
let audioBuffer = [];

function toggleMute() {
  const btn = document.getElementById('tts-btn');
  ttsEnabled = !ttsEnabled;

  if (ttsEnabled) {
    btn.classList.add('active');
    btn.title = "Mute Voice Readback";
    btn.querySelector('span').textContent = "VOICE ON";
    const w1 = document.getElementById('tts-wave-1');
    const w2 = document.getElementById('tts-wave-2');
    if (w1) w1.style.display = 'block';
    if (w2) w2.style.display = 'block';
    showToast("Voice readback enabled");

    // Register user gesture and play audio cue
    const confirmation = new SpeechSynthesisUtterance("Voice readback active");
    confirmation.rate = 1.05;
    window.speechSynthesis.speak(confirmation);
  } else {
    btn.classList.remove('active');
    btn.title = "Unmute Voice Readback";
    btn.querySelector('span').textContent = "MUTED";
    const w1 = document.getElementById('tts-wave-1');
    const w2 = document.getElementById('tts-wave-2');
    if (w1) w1.style.display = 'none';
    if (w2) w2.style.display = 'none';

    window.speechSynthesis.cancel();
    speechQueue = [];
    isSpeaking = false;
    activeUtterance = null;
    showToast("Voice readback muted");
  }
}

function cleanTextForSpeech(text) {
  let cleaned = text;
  // Remove code blocks
  cleaned = cleaned.replace(/```[\s\S]*?```/g, '');
  // Remove inline code ticks
  cleaned = cleaned.replace(/`([^`]+)`/g, '$1');
  // Remove markdown headers
  cleaned = cleaned.replace(/^#{1,6}\s+/gm, '');
  // Remove bold & italic formatting
  cleaned = cleaned.replace(/\*\*([^*]+)\*\*/g, '$1');
  cleaned = cleaned.replace(/\*([^*]+)\*/g, '$1');
  cleaned = cleaned.replace(/__([^_]+)__/g, '$1');
  cleaned = cleaned.replace(/_([^_]+)_/g, '$1');
  // Clean up lists
  cleaned = cleaned.replace(/^[\-\*]\s+/gm, '');
  cleaned = cleaned.replace(/^\d+\.\s+/gm, '');
  // Clean double spaces
  cleaned = cleaned.replace(/\s+/g, ' ').trim();
  return cleaned;
}

function processStreamingTTS(text, isDone) {
  if (!ttsEnabled) return;

  let remainingText = text.substring(lastSentenceIndex);
  const sentenceEndReg = /[.!?](\s+|$)/;

  while (true) {
    let match = remainingText.match(sentenceEndReg);
    if (!match) {
      if (isDone && remainingText.trim().length > 0) {
        queueSentence(remainingText.trim());
        lastSentenceIndex = text.length;
      }
      break;
    }

    let sentenceLength = match.index + match[0].length;
    let sentence = remainingText.substring(0, match.index + 1).trim();

    lastSentenceIndex += sentenceLength;
    remainingText = text.substring(lastSentenceIndex);

    if (sentence.length > 0) {
      queueSentence(sentence);
    }
  }
}

function queueSentence(sentence) {
  let clean = cleanTextForSpeech(sentence);
  if (!clean || clean.length < 2) return;
  speechQueue.push(clean);
  speakNext();
}

function speakNext() {
  if (!ttsEnabled || isSpeaking || speechQueue.length === 0) return;

  const textToSpeak = speechQueue.shift();
  isSpeaking = true;

  const utterance = new SpeechSynthesisUtterance(textToSpeak);
  activeUtterance = utterance;

  // Store utterance globally to prevent garbage collection issues in Chrome
  window.utterances = window.utterances || [];
  window.utterances.push(utterance);

  utterance.rate = 1.05;
  utterance.pitch = 1.0;

  utterance.onend = () => {
    const idx = window.utterances.indexOf(utterance);
    if (idx > -1) window.utterances.splice(idx, 1);
    isSpeaking = false;
    activeUtterance = null;
    speakNext();
  };

  utterance.onerror = (e) => {
    console.error("SpeechSynthesis error:", e);
    const idx = window.utterances.indexOf(utterance);
    if (idx > -1) window.utterances.splice(idx, 1);
    isSpeaking = false;
    activeUtterance = null;
    speakNext();
  };

  window.speechSynthesis.speak(utterance);
}

async function toggleRecord() {
  const btn = document.getElementById('mic-btn');
  const input = document.getElementById('user-input');

  if (!recording) {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showToast("⚠️ Secure context required: Access the app via http://localhost:5000 or configure HTTPS.");
        console.warn("navigator.mediaDevices or getUserMedia is undefined. This is likely due to accessing the server over an insecure HTTP connection from a remote IP.");
        return;
      }
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioBuffer = [];
      recording = true;
      btn.classList.add('recording');
      btn.title = "Stop Recording";
      input.placeholder = "Listening... Speak now. Click mic again to finish.";

      audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }
      const source = audioCtx.createMediaStreamSource(micStream);
      processorNode = audioCtx.createScriptProcessor(4096, 1, 1);

      processorNode.onaudioprocess = (e) => {
        if (!recording) return;
        const inputData = e.inputBuffer.getChannelData(0);
        audioBuffer.push(new Float32Array(inputData));
      };

      source.connect(processorNode);
      processorNode.connect(audioCtx.destination);
      showToast("Recording started...");
    } catch (err) {
      console.error("Error starting recording:", err);
      showToast("Could not access microphone: " + err.message);
    }
  } else {
    try {
      recording = false;
      btn.classList.remove('recording');
      btn.title = "Record Voice";
      input.placeholder = "Ask anything…";

      if (processorNode) {
        processorNode.disconnect();
        processorNode = null;
      }
      if (micStream) {
        micStream.getTracks().forEach(track => track.stop());
        micStream = null;
      }
      if (audioCtx) {
        audioCtx.close();
        audioCtx = null;
      }

      if (audioBuffer.length === 0) {
        showToast("No audio recorded");
        return;
      }

      let totalLength = audioBuffer.reduce((acc, val) => acc + val.length, 0);
      let mergedBuffer = new Float32Array(totalLength);
      let offset = 0;
      for (let chunk of audioBuffer) {
        mergedBuffer.set(chunk, offset);
        offset += chunk.length;
      }

      showToast("Transcribing audio...");
      input.placeholder = "Transcribing voice...";
      input.disabled = true;

      const wavBlob = encodeWAV(mergedBuffer, 16000);
      const fd = new FormData();
      fd.append('file', wavBlob, 'recording.wav');

      const res = await fetch('/api/transcribe', {
        method: 'POST',
        body: fd
      });
      const data = await res.json();
      input.disabled = false;
      input.placeholder = "Ask anything…";

      if (data.error) {
        showToast("Transcription error: " + data.error);
      } else if (data.text) {
        let text = data.text.trim();
        // Clean common Whisper silence hallucinations
        const lowerText = text.toLowerCase().replace(/[.,!?]/g, '').trim();
        const hallucinations = ["thank you", "thank you for watching", "thank you very much", "you", "ub", "bye"];
        if (hallucinations.includes(lowerText)) {
          text = "";
        }

        if (text) {
          if (input.value) {
            input.value += " " + text;
          } else {
            input.value = text;
          }
          autoResize(input);
          input.focus();
        } else {
          showToast("No speech detected.");
        }
      }
    } catch (err) {
      input.disabled = false;
      input.placeholder = "Ask anything…";
      showToast("Failed to transcribe: " + err.message);

      // Guarantee mic shutdown and release on exception
      if (micStream) {
        micStream.getTracks().forEach(track => track.stop());
        micStream = null;
      }
      if (audioCtx) {
        audioCtx.close();
        audioCtx = null;
      }
    }
  }
}

function encodeWAV(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);
  floatTo16BitPCM(view, 44, samples);
  return new Blob([view], { type: 'audio/wav' });
}

function floatTo16BitPCM(output, offset, input) {
  for (let i = 0; i < input.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, input[i]));
    output.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
}

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

// ==========================================
// JWT AUTHENTICATION SYSTEM
// ==========================================
let currentUser = null;
let isAuthModeLogin = true;

function updateEmptyStateGreeting() {
  if (!currentUser) return;
  const hour = new Date().getHours();
  let greeting = "Good Evening";
  if (hour < 12) {
    greeting = "Good Morning";
  } else if (hour < 17) {
    greeting = "Good Afternoon";
  }
  const emptyStateTitle = document.querySelector('.empty-state h2');
  if (emptyStateTitle) {
    const formattedUser = currentUser.charAt(0).toUpperCase() + currentUser.slice(1);
    emptyStateTitle.textContent = `${greeting}, ${formattedUser}!`;
  }
}

async function checkAuthStatus() {
  try {
    const res = await fetch('/api/me');
    const data = await res.json();
    if (data.logged_in) {
      currentUser = data.username;
      document.getElementById('auth-modal').style.display = 'none';
      document.getElementById('user-profile-container').style.display = 'block';
      document.getElementById('username-text').textContent = data.username.toUpperCase();

      // If user is an admin, show the Admin Dashboard button in the profile dropdown
      const adminBtn = document.getElementById('admin-dashboard-btn');
      if (adminBtn) {
        adminBtn.style.display = data.role === 'admin' ? 'flex' : 'none';
      }

      // Set dynamic greeting message based on local machine time
      updateEmptyStateGreeting();

      // Only load RAG & Memory data once user identity is verified!
      refreshDocs();
      refreshMemory();
      loadChatHistory();
    } else {
      document.getElementById('auth-modal').style.display = 'flex';
    }
  } catch (err) {
    document.getElementById('auth-modal').style.display = 'flex';
  }
}

function onUsernameFocus() {
  const input = document.getElementById('auth-username');
  input.style.borderColor = 'var(--accent)';
  
  try {
    const recent = JSON.parse(localStorage.getItem('recent_usernames') || '[]');
    const dropdown = document.getElementById('auth-username-suggestions');
    if (!dropdown) return;
    
    if (recent.length === 0) {
      dropdown.style.display = 'none';
      return;
    }
    
    dropdown.innerHTML = '';
    recent.forEach(user => {
      const item = document.createElement('div');
      item.style.padding = '8px 14px';
      item.style.fontSize = '13px';
      item.style.color = 'var(--text)';
      item.style.cursor = 'pointer';
      item.style.display = 'flex';
      item.style.alignItems = 'center';
      item.style.gap = '8px';
      item.style.transition = 'var(--transition)';
      item.style.borderRadius = '4px';
      
      item.onmouseenter = () => {
        item.style.background = 'var(--accent-dim)';
        item.style.color = 'var(--accent)';
      };
      item.onmouseleave = () => {
        item.style.background = 'transparent';
        item.style.color = 'var(--text)';
      };
      
      item.innerHTML = `
        <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2.5" fill="none" style="flex-shrink: 0;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
        <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${user}</span>
      `;
      
      item.onmousedown = (e) => {
        e.preventDefault();
        input.value = user;
        dropdown.style.display = 'none';
        document.getElementById('auth-password').focus();
      };
      
      dropdown.appendChild(item);
    });
    
    dropdown.style.display = 'flex';
  } catch (e) {}
}

function onUsernameBlur() {
  const input = document.getElementById('auth-username');
  input.style.borderColor = 'var(--border)';
  
  const dropdown = document.getElementById('auth-username-suggestions');
  if (dropdown) {
    dropdown.style.display = 'none';
  }
}

function toggleAuthMode(e) {
  if (e && e.preventDefault) e.preventDefault();
  isAuthModeLogin = !isAuthModeLogin;
  const title = document.querySelector('#auth-modal h2');
  const subtitle = document.getElementById('auth-subtitle');
  const submitBtn = document.getElementById('auth-submit-btn');
  const toggleMsg = document.getElementById('auth-toggle-msg');
  const toggleLink = document.getElementById('auth-toggle-link');
  document.getElementById('auth-error').style.display = 'none';

  const loginGroup = document.getElementById('login-username-group');
  const regNameGroup = document.getElementById('register-name-group');
  const regEmailGroup = document.getElementById('register-email-group');
  const regConfirmGroup = document.getElementById('register-confirm-password-group');
  const regRoleGroup = document.getElementById('register-role-group');

  if (isAuthModeLogin) {
    title.textContent = "Welcome to RAG Bot";
    subtitle.textContent = "Login to access your local AI assistant";
    submitBtn.textContent = "SIGN IN";
    toggleMsg.textContent = "Don't have an account?";
    toggleLink.textContent = "Sign Up";

    if (loginGroup) loginGroup.style.display = 'flex';
    if (regNameGroup) regNameGroup.style.display = 'none';
    if (regEmailGroup) regEmailGroup.style.display = 'none';
    if (regConfirmGroup) regConfirmGroup.style.display = 'none';
    if (regRoleGroup) regRoleGroup.style.display = 'none';
  } else {
    title.textContent = "Create Account";
    subtitle.textContent = "Register a new local account";
    submitBtn.textContent = "REGISTER";
    toggleMsg.textContent = "Already have an account?";
    toggleLink.textContent = "Sign In";

    if (loginGroup) loginGroup.style.display = 'none';
    if (regNameGroup) regNameGroup.style.display = 'flex';
    if (regEmailGroup) regEmailGroup.style.display = 'flex';
    if (regConfirmGroup) regConfirmGroup.style.display = 'flex';
    if (regRoleGroup) regRoleGroup.style.display = 'flex';
  }
}

async function submitAuth() {
  const errorDiv = document.getElementById('auth-error');
  const errorText = document.getElementById('auth-error-text');
  errorDiv.style.display = 'none';

  let payload = {};
  const endpoint = isAuthModeLogin ? '/api/login' : '/api/register';

  if (isAuthModeLogin) {
    const username = document.getElementById('auth-username').value.trim();
    const password = document.getElementById('auth-password').value.trim();

    if (!username || !password) {
      errorDiv.style.display = 'flex';
      errorText.textContent = "Both fields are required.";
      return;
    }
    payload = { username, password };
  } else {
    const firstName = document.getElementById('auth-first-name').value.trim();
    const lastName = document.getElementById('auth-last-name').value.trim();
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value.trim();
    const confirmPassword = document.getElementById('auth-confirm-password').value.trim();
    const role = document.getElementById('auth-role').value.trim();

    if (!firstName || !lastName || !email || !password || !confirmPassword || !role) {
      errorDiv.style.display = 'flex';
      errorText.textContent = "All fields are required.";
      return;
    }

    if (password !== confirmPassword) {
      errorDiv.style.display = 'flex';
      errorText.textContent = "Passwords do not match.";
      return;
    }

    if (password.length < 6) {
      errorDiv.style.display = 'flex';
      errorText.textContent = "Password must be at least 6 characters.";
      return;
    }

    payload = {
      first_name: firstName,
      last_name: lastName,
      email: email,
      password: password,
      role: role
    };
  }

  const submitBtn = document.getElementById('auth-submit-btn');
  const spinnerSvg = `<svg viewBox="0 0 50 50" style="animation: spin 0.8s linear infinite; margin-right: 8px; display: inline-block; vertical-align: middle; width: 14px; height: 14px;"><circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="5" stroke-dasharray="80, 200" stroke-dashoffset="0" stroke-linecap="round"></circle></svg>`;
  
  submitBtn.disabled = true;
  submitBtn.style.opacity = '0.85';
  submitBtn.innerHTML = spinnerSvg + (isAuthModeLogin ? "SIGNING IN..." : "REGISTERING...");

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      errorDiv.style.display = 'flex';
      errorText.textContent = data.error || "Authentication failed.";
      
      submitBtn.disabled = false;
      submitBtn.style.opacity = '1';
      submitBtn.innerHTML = isAuthModeLogin ? "SIGN IN" : "REGISTER";
      return;
    }

    if (isAuthModeLogin) {
      const displayName = data.username || payload.username;
      
      // Save successfully logged-in username to local suggestions
      try {
        const recent = JSON.parse(localStorage.getItem('recent_usernames') || '[]');
        const usernameInput = payload.username;
        const updated = [usernameInput, ...recent.filter(u => u !== usernameInput)].slice(0, 3);
        localStorage.setItem('recent_usernames', JSON.stringify(updated));
      } catch (e) {}

      showToast(`Welcome back, ${displayName}!`);
      window.location.reload();
    } else {
      showToast("Registration successful! Please log in.");
      isAuthModeLogin = true;
      toggleAuthMode();
      
      submitBtn.disabled = false;
      submitBtn.style.opacity = '1';
      submitBtn.innerHTML = "SIGN IN";
      
      // Clean form inputs
      document.getElementById('auth-first-name').value = '';
      document.getElementById('auth-last-name').value = '';
      document.getElementById('auth-email').value = '';
      document.getElementById('auth-password').value = '';
      document.getElementById('auth-confirm-password').value = '';
      document.getElementById('auth-role').value = 'user';
    }
  } catch (err) {
    errorDiv.style.display = 'flex';
    errorText.textContent = "Server communication error.";
    
    submitBtn.disabled = false;
    submitBtn.style.opacity = '1';
    submitBtn.innerHTML = isAuthModeLogin ? "SIGN IN" : "REGISTER";
  }
}

async function logoutUser() {
  if (!await showConfirm("Logout", "Are you sure you want to log out of your session?")) return;
  try {
    localStorage.removeItem('active_session_id');
    await fetch('/api/logout', { method: 'POST' });
    window.location.reload();
  } catch (err) {
    showToast("Failed to logout safely.");
  }
}

function toggleProfileDropdown(event) {
  if (event) event.stopPropagation();
  const container = document.getElementById('user-profile-container');
  if (container) container.classList.toggle('active');
}

window.addEventListener('click', (e) => {
  const container = document.getElementById('user-profile-container');
  if (container && !container.contains(e.target)) {
    container.classList.remove('active');
  }
});

checkAuthStatus();
