'use strict';
/* Notes (1.4): quick pages for links, call prep, anything to keep. List on the left, one page on the right.
   Loaded after app.js / more.js and shares S, $, esc, call, twice, closeMenu and the ACT table.
   The page is written in place: a reload keeps the open page as it is and only redraws the list. */

MORE_TABS.push('notes');
Object.assign(S, { noteId: null, nq: '' });

const NOTE_SAVE_MS = 400;
let notePending = null, noteTimer = null;

/* ---------- cleaning: only the few things a note can hold survive (pasted or stored HTML) ---------- */
const NOTE_TAGS = new Set(['P', 'DIV', 'BR', 'H2', 'UL', 'OL', 'LI', 'B', 'STRONG', 'I', 'EM', 'U', 'S', 'A', 'SPAN']);
const NOTE_DROP = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'IMG', 'SVG', 'VIDEO', 'AUDIO', 'LINK', 'META', 'TEMPLATE', 'FORM', 'INPUT', 'BUTTON', 'TEXTAREA', 'SELECT']);
const NOTE_CLASSES = new Set(['todo', 'done', 'box', 'tdt', 'lnk', 'fav', 'lt', 'lu']);
const webUrl = u => /^https?:\/\/[^\s<>"]+$/i.test(String(u || '').trim());

function cleanNode(n) {
  for (const c of [...n.childNodes]) {
    if (c.nodeType === 3) continue;
    if (c.nodeType !== 1 || NOTE_DROP.has(c.tagName)) { c.remove(); continue; }
    cleanNode(c);
    if (!NOTE_TAGS.has(c.tagName)) { c.replaceWith(...c.childNodes); continue; }
    const cls = [...c.classList].filter(k => NOTE_CLASSES.has(k));
    const href = c.getAttribute('href'), url = c.getAttribute('data-url');
    for (const a of [...c.attributes]) c.removeAttribute(a.name);
    if (cls.length) c.className = cls.join(' ');
    if (c.tagName === 'A') { if (webUrl(href)) c.setAttribute('href', href); else c.replaceWith(...c.childNodes); }
    if (c.classList.contains('lnk')) {
      if (!webUrl(url)) { c.remove(); continue; }
      c.setAttribute('data-url', url); c.setAttribute('contenteditable', 'false');
    }
    if (c.classList.contains('box')) c.setAttribute('contenteditable', 'false');
  }
}
function cleanHTML(html) {
  const t = document.createElement('template');           // inert: nothing runs, nothing loads
  t.innerHTML = String(html || '');
  cleanNode(t.content);
  const d = document.createElement('div'); d.appendChild(t.content);
  return d.innerHTML;
}

/* ---------- list ---------- */
function noteWhen(ts) {
  const d = new Date(ts * 1000), now = new Date();
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  const days = (now - d) / 864e5;
  if (days < 6) return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
  return `${d.getDate()} ${MON[d.getMonth()].slice(0, 3)}`;
}
function noteName(n) {
  if (n.title && n.title.trim()) return n.title.trim();
  const first = (n.text || '').split('\n').map(s => s.trim()).find(Boolean);
  return first || 'New note';
}
function notePreview(n) {
  const lines = (n.text || '').split('\n').map(s => s.trim()).filter(Boolean);
  if (!(n.title && n.title.trim())) lines.shift();
  return lines.join('  ') || 'No text';
}
function noteListHTML() {
  const q = S.nq.trim().toLowerCase();
  const all = (S.d.notes || []).filter(n => !q || (n.title + '\n' + n.text).toLowerCase().includes(q));
  const cur = S.d.note && S.d.note.id;
  const row = n => `<div class="nitem ${n.id === cur ? 'on' : ''}" data-act="nopen" data-id="${n.id}">
      <div class="nt">${esc(noteName(n))}</div><div class="np">${esc(notePreview(n))}</div>
      <span class="nd">${noteWhen(n.updated)}</span><button class="x" data-act="ndel" data-id="${n.id}" title="Delete">${ICON.x || '&times;'}</button></div>`;
  const pin = all.filter(n => n.pinned), rest = all.filter(n => !n.pinned);
  if (!all.length) return `<div class="nempty">${q ? 'No notes match' : 'No notes yet'}</div>`;
  return (pin.length ? `<div class="cap">Pinned</div>${pin.map(row).join('')}` : '')
    + (rest.length ? `<div class="cap">${pin.length ? 'Notes' : ''}</div>${rest.map(row).join('')}` : '');
}

/* ---------- the page ---------- */
const NI = {
  h: 'H',
  b: 'B',
  ul: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/></svg>',
  todo: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="4"/><path d="m8.5 12 2.5 2.5 4.5-5"/></svg>',
  search: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
};
function noteMeta(n) {
  return `Edited ${noteWhen(n.updated).replace(/^(\d)/, '$1')}${n.pinned ? ' &middot; Pinned' : ''}`;
}
function notesShell() {
  const n = S.d.note;
  return `<div class="notes">
    <section class="nlist">
      <label class="nsearch">${NI.search}<input id="nq" placeholder="Search notes" autocomplete="off" spellcheck="false" value="${esc(S.nq)}"></label>
      <button class="nnew" data-act="nnew">${ICON.plus} New note <kbd>Ctrl N</kbd></button>
      <div class="nitems" id="nitems">${noteListHTML()}</div>
    </section>
    <section class="ned">${n ? `
      <div class="nbar">
        <button data-act="nfmt" data-v="h" title="Heading  (# then space)">${NI.h}</button>
        <button data-act="nfmt" data-v="b" title="Bold  (Ctrl B)">${NI.b}</button>
        <span class="sep"></span>
        <button data-act="nfmt" data-v="ul" title="List  (- then space)">${NI.ul}</button>
        <button data-act="nfmt" data-v="todo" title="Checkbox  ([] then space)">${NI.todo}</button>
        <span class="nsaved" id="nsaved">Saved</span>
      </div>
      <div class="npage" id="npage">
        <input id="ntitle" class="ntitle" placeholder="Title" autocomplete="off" spellcheck="false" value="${esc(n.title)}">
        <div class="nmeta" id="nmeta">${noteMeta(n)}</div>
        <div id="nbody" class="nbody" contenteditable="true" spellcheck="true"></div>
      </div>` : `<div class="nblank"><b>Notes</b><span>Links, call prep, anything you want to keep.</span><button class="tbtn" data-act="nnew">New note</button></div>`}
    </section></div>`;
}
function notesRender(m) {
  const n = S.d.note, same = $('#nbody') && n && m.dataset.nid === String(n.id);
  if (same) {                                   // a reload: leave the page alone, redraw the list
    $('#nitems').innerHTML = noteListHTML();
    $('#nmeta').innerHTML = noteMeta(n);
    return;
  }
  m.innerHTML = notesShell();
  m.dataset.nid = n ? String(n.id) : '';
  S.noteId = n ? n.id : null;
  if (n) {
    $('#nbody').innerHTML = cleanHTML(n.body) || '<p><br></p>';
    if (S.nfocus) { const f = S.nfocus; S.nfocus = null; (f === 'title' ? $('#ntitle') : $('#nbody')).focus(); }
  }
}

/* ---------- saving: what to save is read the moment you type, so leaving the tab never loses it ---------- */
function noteText(body) {
  const out = [];
  for (const b of body.children) {
    if (b.classList.contains('lnk')) { out.push(b.querySelector('.lt') ? b.querySelector('.lt').textContent : b.dataset.url); continue; }
    if (b.tagName === 'UL' || b.tagName === 'OL') { for (const li of b.children) out.push(li.textContent); continue; }
    out.push(b.textContent);
  }
  if (!body.children.length) out.push(body.textContent);
  return out.join('\n').replace(/\u00a0/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
}
function noteChanged() {
  const n = S.d && S.d.note; if (!n || !$('#nbody')) return;
  const title = $('#ntitle').value, body = $('#nbody');
  notePending = { id: n.id, fields: { title, body: cleanHTML(body.innerHTML), text: noteText(body) } };
  const L = (S.d.notes || []).find(x => x.id === n.id);
  if (L) { L.title = title; L.text = notePending.fields.text; L.updated = Date.now() / 1000; }
  n.updated = Date.now() / 1000;
  $('#nsaved').textContent = 'Saving';
  clearTimeout(noteTimer); noteTimer = setTimeout(noteFlush, NOTE_SAVE_MS);
  clearTimeout(noteChanged.list); noteChanged.list = setTimeout(() => { if ($('#nitems')) $('#nitems').innerHTML = noteListHTML(); }, 250);
}
async function noteFlush() {
  clearTimeout(noteTimer);
  const p = notePending; notePending = null;
  if (!p) return;
  try {
    await call('save_note', p.id, p.fields);
    if ($('#nsaved') && !notePending) $('#nsaved').textContent = 'Saved';
  } catch (e) {
    if (!notePending) notePending = p;                  // keep it; the next keystroke or switch tries again
    if ($('#nsaved')) $('#nsaved').textContent = 'Not saved';
  }
}
async function noteLeave() {                           // before opening another note: save, drop an empty one
  await noteFlush();
  const n = S.d && S.d.note;
  if (n && $('#nbody') && !$('#ntitle').value.trim() && !noteText($('#nbody'))) {
    await call('delete_note', n.id).catch(() => {});
  }
}

/* ---------- typing helpers: # heading, - list, [] checkbox, Enter on a checkbox makes the next one ---------- */
function caretBlock() {
  const body = $('#nbody'), s = getSelection();
  if (!body || !s.rangeCount) return null;
  let n = s.anchorNode;
  while (n && n.parentNode !== body) n = n.parentNode;
  return n && n !== body ? n : null;
}
function placeCaret(el, atEnd = true) {
  const r = document.createRange(); r.selectNodeContents(el); r.collapse(!atEnd);
  const s = getSelection(); s.removeAllRanges(); s.addRange(r);
}
function makeTodo(text = '', done = false) {
  const d = document.createElement('div'); d.className = 'todo' + (done ? ' done' : '');
  d.innerHTML = `<span class="box" contenteditable="false"></span><span class="tdt">${text ? esc(text) : '<br>'}</span>`;
  return d;
}
function wrapLoose(body) {                               // bare text typed straight into the page gets a <p>
  const s = getSelection(); const n = s.anchorNode;
  if (n && n.nodeType === 3 && n.parentNode === body) {
    const p = document.createElement('p'); n.replaceWith(p); p.appendChild(n);
    const off = s.anchorOffset; const r = document.createRange(); r.setStart(n, Math.min(off, n.length)); r.collapse(true);
    s.removeAllRanges(); s.addRange(r);
  }
}
function markdownShortcut(body) {
  wrapLoose(body);
  const b = caretBlock(); if (!b || b.nodeType !== 1 || !/^(P|DIV)$/.test(b.tagName) || b.classList.contains('todo') || b.classList.contains('lnk')) return false;
  const t = b.textContent.replace(/\u00a0/g, ' ');
  let m;
  if ((m = t.match(/^#{1,3} (.*)$/s))) {
    const h = document.createElement('h2'); h.textContent = m[1]; if (!m[1]) h.innerHTML = '<br>';
    b.replaceWith(h); placeCaret(h); return true;
  }
  if ((m = t.match(/^[-*] (.*)$/s))) {
    const ul = document.createElement('ul'), li = document.createElement('li');
    li.textContent = m[1]; if (!m[1]) li.innerHTML = '<br>';
    ul.appendChild(li); b.replaceWith(ul); placeCaret(li); return true;
  }
  if ((m = t.match(/^\[( |x)?\] (.*)$/s))) {
    const d = makeTodo(m[2], m[1] === 'x'); b.replaceWith(d); placeCaret(d.querySelector('.tdt')); return true;
  }
  return false;
}
function todoKey(e) {
  const b = caretBlock(); if (!b || !b.classList || !b.classList.contains('todo')) return false;
  const tt = b.querySelector('.tdt'), s = getSelection();
  const empty = !tt.textContent.replace(/\u00a0/g, '').trim();
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (empty) { const p = document.createElement('p'); p.innerHTML = '<br>'; b.replaceWith(p); placeCaret(p); return true; }
    const r = s.getRangeAt(0); const tail = document.createRange();          // text after the caret moves down
    tail.setStart(r.endContainer, r.endOffset); tail.setEnd(tt, tt.childNodes.length);
    const rest = tail.extractContents().textContent;
    if (!tt.textContent) tt.innerHTML = '<br>';
    const d = makeTodo(rest); b.after(d); placeCaret(d.querySelector('.tdt'), false); return true;
  }
  if (e.key === 'Backspace') {
    const r = s.getRangeAt(0); const head = document.createRange();
    head.setStart(tt, 0); head.setEnd(r.startContainer, r.startOffset);
    if (r.collapsed && !head.toString().length) {                            // at the start: back to plain text
      e.preventDefault();
      const p = document.createElement('p'); p.textContent = tt.textContent; if (!p.textContent) p.innerHTML = '<br>';
      b.replaceWith(p); placeCaret(p, false); return true;
    }
  }
  return false;
}
function toggleBlock(kind) {
  const body = $('#nbody'); body.focus();
  wrapLoose(body);
  const b = caretBlock();
  if (kind === 'b') { document.execCommand('bold'); return; }
  if (kind === 'ul') { document.execCommand('insertUnorderedList'); return; }
  if (!b) { const p = document.createElement('p'); p.innerHTML = '<br>'; body.appendChild(p); placeCaret(p); return toggleBlock(kind); }
  if (kind === 'h') {
    const to = b.tagName === 'H2' ? 'p' : 'h2';
    const el = document.createElement(to); el.innerHTML = b.innerHTML || '<br>'; b.replaceWith(el); placeCaret(el);
  }
  if (kind === 'todo') {
    if (b.classList && b.classList.contains('todo')) {
      const p = document.createElement('p'); p.textContent = b.querySelector('.tdt').textContent; if (!p.textContent) p.innerHTML = '<br>';
      b.replaceWith(p); placeCaret(p);
    } else if (b.tagName === 'UL' || b.tagName === 'OL') {
      const items = [...b.children].map(li => makeTodo(li.textContent)); b.replaceWith(...items); placeCaret(items[items.length - 1].querySelector('.tdt'));
    } else { const d = makeTodo(b.textContent); b.replaceWith(d); placeCaret(d.querySelector('.tdt')); }
  }
}

/* ---------- pasting: always plain text; a lone link becomes a card with the page's title ---------- */
function linkCard(url) {
  let host = ''; try { host = new URL(url).hostname.replace(/^www\./, ''); } catch (e) { host = url; }
  const id = 'l' + Math.random().toString(36).slice(2, 9);
  return { id, html: `<div class="lnk" contenteditable="false" data-url="${esc(url)}" data-lid="${id}"><span class="fav">${esc((host[0] || '?').toUpperCase())}</span><span class="lt">${esc(host)}</span><span class="lu">${esc(url)}</span></div><p><br></p>` };
}
function linkify(line) {
  return esc(line).replace(/https?:\/\/[^\s<>"]+/gi, u => `<a href="${u}">${u}</a>`);
}
async function notePaste(e) {
  e.preventDefault();
  const t = (e.clipboardData.getData('text/plain') || '').replace(/\r\n?/g, '\n');
  if (!t) return;
  const one = t.trim();
  if (webUrl(one)) {
    const c = linkCard(one);
    document.execCommand('insertHTML', false, c.html);
    noteChanged();
    const title = await api.link_title(one).catch(() => '');
    const el = document.querySelector(`[data-lid="${c.id}"]`);
    if (title && el) { el.querySelector('.lt').textContent = title; el.removeAttribute('data-lid'); noteChanged(); }
    else if (el) el.removeAttribute('data-lid');
    return;
  }
  if (!t.includes('\n') && !/https?:\/\//i.test(t)) { document.execCommand('insertText', false, t); return; }
  const lines = t.split('\n');
  document.execCommand('insertHTML', false, lines.map((l, i) => (i ? '<br>' : '') + linkify(l)).join(''));
}

/* ---------- wiring ---------- */
Object.assign(ACT, {
  nopen: async el => {
    const id = Number(el.dataset.id);
    if (S.d.note && S.d.note.id === id) return;
    await noteLeave(); S.noteId = id; S.armed = null; load();
  },
  nnew: async () => {
    await noteLeave();
    const n = await call('add_note');
    S.noteId = n.id; S.nq = ''; S.nfocus = 'title'; load();
  },
  ndel: el => twice(el, async () => {
    closeMenu();
    const id = Number(el.dataset.id);
    if (notePending && notePending.id === id) notePending = null;
    await call('delete_note', id);
    if (S.noteId === id) S.noteId = null;
    if ($('#main')) $('#main').dataset.nid = '';
    load();
  }, el.closest('#menu') ? 'Click again to delete' : 'Delete'),
  npin: async el => {
    closeMenu(); await noteFlush();
    const n = (S.d.notes || []).find(x => x.id === Number(el.dataset.id)); if (!n) return;
    await call('save_note', n.id, { pinned: !n.pinned }); load();
  },
  nfmt: el => { toggleBlock(el.dataset.v); noteChanged(); },
});

document.addEventListener('input', e => {
  if (e.target.id === 'nq') { S.nq = e.target.value; $('#nitems').innerHTML = noteListHTML(); return; }
  if (e.target.id === 'ntitle') return noteChanged();
  if (e.target.id === 'nbody') {
    if (e.inputType === 'insertText' && e.data === ' ') markdownShortcut(e.target);
    noteChanged();
  }
});
document.addEventListener('keydown', e => {
  if (S.tab !== 'notes') return;
  if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'n') { e.preventDefault(); ACT.nnew(); return; }
  if (e.target.id === 'ntitle' && (e.key === 'Enter' || e.key === 'ArrowDown')) {
    e.preventDefault(); const b = $('#nbody'); b.focus(); placeCaret(b.firstElementChild || b, false); return;
  }
  if (e.target.id === 'nbody') {
    if (todoKey(e)) { noteChanged(); return; }
    if (e.ctrlKey && e.key.toLowerCase() === 's') { e.preventDefault(); noteFlush(); }
  }
  if (e.target.id === 'nq' && e.key === 'Escape') { S.nq = ''; e.target.value = ''; $('#nitems').innerHTML = noteListHTML(); }
}, true);
document.addEventListener('paste', e => { if (e.target.closest && e.target.closest('#nbody')) notePaste(e); });
document.addEventListener('mousedown', e => {
  const box = e.target.closest && e.target.closest('#nbody .box');
  if (box) { e.preventDefault(); box.parentElement.classList.toggle('done'); noteChanged(); return; }
  const card = e.target.closest && e.target.closest('#nbody .lnk');
  if (card && e.button === 0) { e.preventDefault(); api.open_url(card.dataset.url); return; }
  const a = e.target.closest && e.target.closest('#nbody a[href]');
  if (a && e.button === 0 && e.ctrlKey) { e.preventDefault(); api.open_url(a.getAttribute('href')); }
});
document.addEventListener('contextmenu', e => {
  const it = e.target.closest && e.target.closest('.nitem[data-id]'); if (!it) return;
  e.preventDefault();
  const n = (S.d.notes || []).find(x => x.id === Number(it.dataset.id)); if (!n) return;
  const m = $('#menu');
  m.innerHTML = `<button data-act="npin" data-id="${n.id}"><i></i>${n.pinned ? 'Unpin' : 'Pin to top'}</button><hr>
    <button class="mdel" data-act="ndel" data-id="${n.id}"><i></i>Delete</button>`;
  m.classList.add('show');
  m.style.left = Math.max(8, Math.min(e.clientX, innerWidth - m.offsetWidth - 8)) + 'px';
  m.style.top = Math.max(8, Math.min(e.clientY, innerHeight - m.offsetHeight - 8)) + 'px';
  S.menu = 1;
});
window.addEventListener('blur', () => { noteFlush(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) noteFlush(); });
