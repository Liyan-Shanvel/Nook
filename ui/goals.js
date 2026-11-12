'use strict';
/* Goals (the list, one goal, the form) and the Vision Board. Loaded after more.js. */

MORE_TABS.push('vision');
Object.assign(S, { goal: null, vimg: new Map(), vfull: null, vadd: false });

/* what moves a goal: [key, name in the picker, one plain line] */
const SOURCES = [
  ['hand', 'I add it myself', 'Press + on the goal each time. Good for money, books, anything Nook cannot see.'],
  ['calls', 'Sales calls, from Fathom', 'Counts each recorded call where the other person showed up. A no-show does not count.'],
  ['calendar', 'Calendar events with a word', 'Counts each calendar event with that word in its name, once it is over.'],
  ['focus_all', 'All my focus time', 'Every focus session adds its hours.'],
  ['focus_word', 'Focus on some tasks', 'Focus time on tasks with the word in their name, or on tasks you link by right-click.'],
  ['linked', 'Tasks and habits I link', 'Each linked task or habit adds 1 when you tick it. Right-click a task to link it.'],
  ['tasks_word', 'Ticked tasks with a word', 'Each ticked task with that word in its name adds 1.'],
  ['value', 'A number that moves', 'Like body weight. You log the new number and Nook shows how far you have come.'],
  ['steps', 'A list of steps', 'Break it into steps and tick them off.'],
];
const WORD_SRC = { calendar: 'Word in the event name', tasks_word: 'Word in the task name',
  focus_word: 'Word in the task name (optional)', calls: 'Only calls with this word (optional)' };

const money = g => g.unit === '$';
const gnum = (g, v) => (money(g) ? '$' + num(v) : num(v));
const gunit = g => (!money(g) && g.unit ? ' ' + esc(g.unit) : '');
function amountText(g) {
  if (g.source === 'value') return `${gnum(g, g.done)}${gunit(g)} now, going to ${gnum(g, g.target)}${gunit(g)}`;
  if (g.source === 'steps') return g.steps_total ? `${g.steps_done} of ${plural(g.steps_total, 'step')}` : 'No steps yet';
  return `${gnum(g, g.done)} of ${gnum(g, g.target)}${gunit(g)}${g.period ? ' this ' + g.period : ''}`;
}
function feedsText(g) {
  const w = g.match ? ` with "${esc(g.match)}"` : '';
  if (g.source === 'calls') return `Counts recorded calls${w} where they showed up`;
  if (g.source === 'calendar') return `Counts past calendar events${w}`;
  if (g.source === 'focus_all') return 'All focus time counts';
  if (g.source === 'focus_word') return g.match ? `Focus on tasks${w}` : 'Focus on linked tasks';
  if (g.source === 'tasks_word') return `Ticked tasks${w}`;
  if (g.source === 'value') return 'You log the number';
  if (g.source === 'steps') return 'A list of steps';
  if (g.source === 'linked') {
    const fed = [...g.habits.map(h => `${esc(h.title)} habit`), ...g.tasks_today.map(t => `${esc(t)} (today)`)];
    return fed.length ? 'Moved by: ' + fed.join(' · ') : 'Right-click a task, or edit a habit, to link it';
  }
  return 'You add it';
}
function paceHTML(g) {
  const p = g.pace; if (!p) return '';
  if (p.state === 'done') return '<span class="ptag ok">Done</span>';
  if (p.state === 'late') return '<span class="ptag bad">Past the date</span>';
  const tag = { on: '<span class="ptag">On track</span>', ahead: '<span class="ptag ok">Ahead</span>', behind: '<span class="ptag bad">Behind</span>' }[p.state];
  if (p.per) return `${tag}${gnum(g, p.left)}${gunit(g)} left this ${p.per}`;
  if (p.week_only) return `${tag}${gnum(g, p.need)}${gunit(g)} to go`;
  return `${tag}Need ${gnum(g, p.need)} a week. You are doing ${gnum(g, p.doing)}.`;
}
function whenText(g) {
  if (g.period) return `every ${g.period}`;
  if (!g.deadline) return '';
  const n = g.days_left;
  return `by ${dayMon(g.deadline)} · ${n > 0 ? plural(n, 'day') + ' left' : n === 0 ? 'today' : plural(-n, 'day') + ' past'}`;
}
function ring(p, size, w) {
  const r = (size - w) / 2, C = 2 * Math.PI * r, c = size / 2;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"><circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="rgba(255,255,255,.10)" stroke-width="${w}"/>
    ${p > 0 ? `<circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${p >= 100 ? 'var(--green)' : '#fff'}" stroke-width="${w}" stroke-linecap="round" stroke-dasharray="${C * p / 100} ${C}" transform="rotate(-90 ${c} ${c})"/>` : ''}</svg>`;
}

/* ---------- the list ---------- */
function goalRow(g) {
  const off = g.status !== 'active';
  const plus = off || g.source === 'steps' ? '' : g.source === 'value'
    ? `<button class="gplus" data-act="gopen" data-id="${g.id}" title="Log the new number">Log</button>`
    : `<button class="gplus" data-act="gplus" data-id="${g.id}" title="Add ${num(g.step)}">+${num(g.step)}</button>`;
  return `<div class="grow ${off ? 'off' : ''}" data-act="gopen" data-id="${g.id}">${ring(g.pct, 64, 7)}
    <div class="info"><div class="tt"><b>${esc(g.title)}</b><span>${whenText(g)}</span></div>
      <span class="amt">${amountText(g)}</span>
      <span class="fed">${paceHTML(g) || feedsText(g)}</span></div>
    ${plus}<span class="pct" ${g.pct >= 100 ? 'style="color:var(--green)"' : ''}>${g.pct >= 100 ? 'Done' : g.pct + '%'}</span></div>`;
}
function goalsHTML() {
  const gs = S.d.goals, by = st => gs.filter(g => g.status === st);
  const act = by('active');
  const sec = (name, list) => list.length ? `<span class="cap gsec">${name}</span>${list.map(goalRow).join('')}` : '';
  const head = act.length ? `<div><div class="bigt">${plural(act.length, 'goal')}</div><div class="sub">Click one to see it. Press + when you move it.</div></div>`
    : `<div><div class="bigt">Goals</div><div class="sub">Something big you want. Nook counts it for you where it can.</div></div>`;
  return `<div class="page"><div class="col760"><div class="head2">${head}<button class="newbtn" data-act="newgoal">${ICON.plus}New goal</button></div>
    <div class="glist">${act.map(goalRow).join('')}${sec('Paused', by('paused'))}${sec('Done', by('done'))}${sec('Archived', by('archived'))}</div>
    ${gs.length ? '' : '<div class="empty2">Like "30 sales calls by 31 Dec", "120 focused hours" or "Gain 3 kg".</div>'}</div></div>`;
}

/* ---------- one goal ---------- */
function fathomHTML(g) {
  if (g.source !== 'calls') return '';
  const c = S.d.calls || {};
  if (!c.connected) return `<div class="note"><b>Connect Fathom to count calls</b>
      <span>In Fathom open Settings, then API Access, make a key and paste it here. It stays on this PC. Nook only reads.</span>
      <div class="inrow"><input id="fkey" type="password" placeholder="Fathom API key"><button class="btn main" data-act="fconnect">Connect</button></div></div>`;
  const line = c.error ? `Could not sync: ${esc(c.error)}` : `${plural(c.count || 0, 'recording')} seen, ${c.real || 0} real ${c.real === 1 ? 'call' : 'calls'}${c.at ? ' · synced ' + ago(c.at) : ''}`;
  return `<div class="fline"><span>Fathom · ${line}</span><button data-act="fsync">Sync now</button><button data-act="fdisconnect">Disconnect</button></div>`;
}
function goalDetailHTML() {
  const g = S.d.goal, p = g.pace, isVal = g.source === 'value', isSteps = g.source === 'steps';
  const stats = [`<div><b>${gnum(g, g.done)}</b><span>${isVal ? (g.unit ? esc(g.unit) + ' now' : 'now') : isSteps ? (g.done === 1 ? 'step done' : 'steps done') : `of ${gnum(g, g.target)}${gunit(g)}`}</span></div>`];
  if (p && p.need != null && !p.week_only) stats.push(`<div><b>${gnum(g, p.need)}</b><span>needed a week</span></div><div><b>${gnum(g, p.doing)}</b><span>a week now</span></div>`);
  else if (g.days_left != null && g.days_left >= 0) stats.push(`<div><b>${g.days_left}</b><span>days left</span></div>`);
  const steps = !isSteps ? '' : `<div class="gsteps"><span class="cap">Steps</span>
      ${g.steps.map(s => `<div class="row ${s.done ? 'done' : ''}"><button class="chk" data-act="gsteptick" data-id="${s.id}" data-on="${s.done ? 0 : 1}">${s.done ? ICON.check : ''}</button>
        <span class="t">${esc(s.title)}</span><button class="x" data-act="gstepdel" data-id="${s.id}" title="Delete">${ICON.x}</button></div>`).join('')}
      <div class="addrow"><span class="plus">+</span><input id="gstepin" placeholder="Add a step, press Enter"></div></div>`;
  const logrow = isSteps ? '' : `<div class="glog"><input id="glogamt" inputmode="decimal" placeholder="${isVal ? 'New number' : num(g.step)}">
      <input id="glogday" type="date" value="${g.today}" max="${g.today}"><input id="glognote" placeholder="Note (optional)">
      <button class="btn main" data-act="glogadd">${isVal ? 'Log' : 'Add'}</button></div>`;
  const max = Math.max(...g.weeks.map(w => w.amount), 0);
  const bars = g.weeks.length ? `<span class="cap">Last 12 weeks</span><div class="gbars">${g.weeks.map((w, i) =>
    `<i title="Week of ${dayMon(w.a)}: ${gnum(g, w.amount)}${gunit(g)}" class="${i === 11 ? 'now' : ''}" style="height:${max ? Math.max(2, Math.round(w.amount / max * 96)) : 2}px"></i>`).join('')}</div>
    <div class="gbl"><span>${dayMon(g.weeks[0].a)}</span><span>this week</span></div>` : '';
  const hist = isSteps ? '' : `<span class="cap" style="margin-top:${bars ? 28 : 0}px">${isVal ? 'Readings' : 'Added by hand'}</span>
    ${g.logs.length ? g.logs.map(l => `<div class="glrow"><span>${dayMon(l.day)}</span><b>${isVal || l.amount < 0 ? '' : '+'}${gnum(g, l.amount)}</b><small>${esc(l.note)}</small>
      <button class="x" data-act="glogdel" data-id="${l.id}" title="Remove">${ICON.x}</button></div>`).join('')
      : `<div class="quiet">${isVal ? 'No readings yet. Log the first one.' : 'Nothing yet. Whatever Nook counts by itself is not listed here.'}</div>`}`;
  const st = g.status;
  return `<div class="page"><div class="hd"><div class="l" style="gap:26px">
      <div style="display:flex;flex-direction:column;gap:10px">
        <button class="back" data-act="gback">${ICON.left}<span>Goals</span></button>
        <div class="ghead">${ring(g.pct, 84, 9)}<div><div class="bigt" style="font-size:32px;line-height:38px">${esc(g.title)}</div>
          <span class="sub" style="font-size:14px">${[whenText(g), feedsText(g), st !== 'active' ? st : ''].filter(Boolean).join(' · ')}</span></div></div></div>
      <div class="stats">${stats.join('')}<div><b>${g.pct}%</b><span>there</span></div></div>
      ${paceHTML(g) ? `<div class="fed" style="font-size:14px">${paceHTML(g)}</div>` : ''}
      ${g.why ? `<div class="note"><b>Why</b><span>${esc(g.why)}</span></div>` : ''}
      ${fathomHTML(g)}${logrow}${steps}
      <div class="links"><button data-act="gedit" data-id="${g.id}">Edit</button>
        ${st === 'active' ? '<button data-act="gstatus" data-v="paused">Pause</button><button data-act="gstatus" data-v="done">Mark done</button>'
          : '<button data-act="gstatus" data-v="active">Make active</button>'}
        ${st !== 'archived' ? '<button data-act="gstatus" data-v="archived">Archive</button>' : ''}
        <button data-act="gdel">Delete</button></div>
    </div><div class="gside">${bars}${hist}</div></div></div>`;
}

/* ---------- the form ---------- */
function goalFormHTML(m) {
  const src = m.source, info = SOURCES.find(x => x[0] === src), word = WORD_SRC[src];
  const isVal = src === 'value', isSteps = src === 'steps', isFocus = src.startsWith('focus');
  const count = isSteps ? '' : isVal
    ? `<div class="f"><label>From, to, unit</label><div class="three"><input data-k="base" type="number" step="any" value="${esc(m.base)}" placeholder="58">
        <input data-k="target" type="number" step="any" value="${esc(m.target)}" placeholder="61"><input data-k="unit" value="${esc(m.unit)}" placeholder="kg"></div></div>`
    : `<div class="f"><label>How many</label><div class="two"><input data-k="target" type="number" step="any" min="0" value="${esc(m.target)}" placeholder="30">
        ${isFocus ? '<input value="hours" disabled>' : `<input data-k="unit" value="${esc(m.unit)}" placeholder="${src === 'hand' ? 'books, $' : 'calls'}">`}</div></div>`;
  const repeat = isVal || isSteps ? '' : `<div class="f"><label>Repeats</label><div class="seg3">${[['', 'Once'], ['week', 'Every week'], ['month', 'Every month']].map(([v, l]) =>
    `<button class="${m.period === v ? 'on' : ''}" data-act="mperiod" data-v="${v}">${l}</button>`).join('')}</div></div>`;
  const more = !m.more ? '<button class="more" data-act="mmore">More options</button>' : `
    <div class="f"><label>Count from</label><input data-k="start" type="date" value="${esc(m.start || '')}"><span class="help">Empty counts everything ever.</span></div>
    ${isVal || isSteps ? '' : `<div class="f"><label>The + button adds</label><input data-k="step" type="number" step="any" min="0" value="${esc(m.step)}"></div>`}
    <div class="f"><label>Why it matters (optional)</label><input data-k="why" value="${esc(m.why)}" placeholder="One line for the hard days"></div>`;
  return `<h2>${m.id ? 'Edit goal' : 'New goal'}</h2>
    <div class="f"><label>What do you want</label><input data-k="title" value="${esc(m.title)}" placeholder="30 sales calls" id="mfirst"></div>
    <div class="f"><label>What moves it?</label><select data-k="source" id="msrc">${SOURCES.map(([v, l]) => `<option value="${v}" ${v === src ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <span class="help">${info[2]}</span></div>
    ${word ? `<div class="f"><label>${word}</label><input data-k="match" value="${esc(m.match)}" placeholder="discovery"><span class="help">Whole words only. Use commas for more than one.</span></div>` : ''}
    ${count}${repeat}
    ${m.period ? '' : `<div class="f"><label>By (optional)</label><input data-k="deadline" type="date" value="${esc(m.deadline || '')}"></div>`}
    ${more}
    <div class="btns"><button class="btn" data-act="mclose">Cancel</button><button class="btn main" data-act="msave">${m.id ? 'Save' : 'Add goal'}</button></div>
    ${m.id ? '<button class="danger" data-act="mdelgoal">Delete this goal</button>' : ''}`;
}
async function saveGoal(m) {
  if (!m.title.trim()) return toast('Say what you want');
  const steps = m.source === 'steps';
  if (!steps && m.target === '') return toast('It needs a number');
  const f = { title: m.title, source: m.source, match: WORD_SRC[m.source] ? m.match : '', target: steps ? 1 : Number(m.target),
    base: m.source === 'value' ? Number(m.base) || 0 : 0, unit: m.unit, period: m.source === 'value' || steps ? '' : m.period,
    deadline: m.period ? null : (m.deadline || null), start: m.start || null, step: Number(m.step) || 1, why: m.why };
  const g = m.id ? await call('update_goal', m.id, f) : await call('add_goal', f);
  if (!m.id && steps) S.goal = g.id;              // straight to the page where the steps are added
  closeModal(); load();
}
document.getElementById('modal').addEventListener('change', e => { if (e.target.id === 'msrc') renderModal(); });

const goalNow = id => (S.d.goal && S.d.goal.id === Number(id) ? S.d.goal : (S.d.goals || []).find(x => x.id === Number(id)));
Object.assign(ACT, {
  newgoal: () => openModal({ kind: 'goal', title: '', source: 'hand', match: '', target: '', base: '', unit: '', period: '', deadline: '',
    start: S.today, step: 1, why: '', fresh: true }),
  gedit: el => {
    const g = goalNow(el.dataset.id); if (!g) return;
    openModal({ kind: 'goal', id: g.id, title: g.title, source: g.source, match: g.match, target: g.target, base: g.base, unit: g.unit,
      period: g.period, deadline: g.deadline || '', start: g.start || '', step: g.step, why: g.why, fresh: true });
  },
  mperiod: el => { S.modal.period = el.dataset.v; renderModal(); },
  mmore: () => { S.modal.more = true; renderModal(); },
  gopen: el => { S.tab = 'goals'; S.goal = Number(el.dataset.id); closeFull(); load(); },
  gback: () => { S.goal = null; load(); },
  gplus: async el => {
    const g = goalNow(el.dataset.id); if (!g) return;
    const got = await call('log_goal', g.id, g.step);
    await load();
    toast(`Added ${gnum(g, g.step)} to ${g.title}`, async () => { await call('delete_goal_log', got.log_id); load(); });
  },
  glogadd: async () => {
    const v = Number($('#glogamt').value.trim() || ($('#glogamt').placeholder.match(/^[\d.]+$/) ? $('#glogamt').placeholder : NaN));
    if (!isFinite(v)) return toast('Type a number');
    await call('log_goal', S.goal, v, $('#glogday').value || null, $('#glognote').value);
    load();
  },
  glogdel: el => twice(el, async () => { await call('delete_goal_log', Number(el.dataset.id)); load(); }, 'Remove'),
  gstatus: async el => { await call('update_goal', S.goal, { status: el.dataset.v }); if (el.dataset.v === 'archived') S.goal = null; load(); },
  gdel: el => twice(el, async () => { await call('delete_goal', S.goal); S.goal = null; load(); }, 'Click again to delete'),
  gsteptick: async el => { await call('update_goal_step', Number(el.dataset.id), { done: el.dataset.on === '1' }); load(); },
  gstepdel: el => twice(el, async () => { await call('delete_goal_step', Number(el.dataset.id)); load(); }),
  fconnect: async el => {
    const key = $('#fkey').value.trim(); if (!key) return toast('Paste the key first');
    el.textContent = 'Checking…'; el.disabled = true;
    try { await call('calls_connect', key); } finally { load(); }
  },
  fsync: async el => { el.textContent = 'Syncing…'; el.disabled = true; await call('calls_sync').catch(() => {}); load(); },
  fdisconnect: el => twice(el, async () => { await call('calls_connect', ''); load(); }, 'Click again to disconnect'),
});
document.addEventListener('keydown', async e => {
  if (e.key !== 'Enter') return;
  const id = e.target.id;
  if (id === 'glogamt' || id === 'glognote') { e.preventDefault(); ACT.glogadd(); }
  if (id === 'fkey') { e.preventDefault(); ACT.fconnect($('[data-act="fconnect"]')); }
  if (id === 'gstepin' && e.target.value.trim()) {
    const v = e.target.value.trim(); e.target.value = '';
    await call('add_goal_step', S.goal, v).catch(() => {}); S.refocus = '#gstepin'; load();
  }
  if (id === 'vaddin' && e.target.value.trim()) {
    const v = e.target.value.trim(); S.vadd = false;
    await call('add_vision_text', v).catch(() => {}); load();
  }
  if (e.target.dataset && e.target.dataset.vcap) { e.preventDefault(); e.target.blur(); }
});

/* ---------- Vision Board ---------- */
function vcard(c) {
  const g = c.goal_id && S.d.goals.find(x => x.id === c.goal_id);
  const body = c.kind === 'image' ? `<img data-vid="${c.id}" src="${S.vimg.get(c.id) || ''}" alt="" draggable="false" data-act="vopen" data-id="${c.id}">`
    : `<div class="vtxt" data-act="vopen" data-id="${c.id}">${esc(c.text)}</div>`;
  const opts = `<option value="">No goal</option>${S.d.goals.filter(x => x.status !== 'archived').map(x => `<option value="${x.id}" ${x.id === c.goal_id ? 'selected' : ''}>${esc(x.title)}</option>`).join('')}`;
  return `<div class="vcard ${c.wide ? 'wide' : ''}" draggable="true" data-id="${c.id}" data-vcard="1">${body}
    <div class="vtools"><select data-vgoal="${c.id}" title="Link to a goal">${opts}</select>
      <button data-act="vwide" data-id="${c.id}">${c.wide ? 'Narrow' : 'Wide'}</button>
      <button class="vx" data-act="vdel" data-id="${c.id}" title="Remove">${ICON.x}</button></div>
    <div class="vcap" contenteditable="true" spellcheck="false" data-vcap="${c.id}" data-ph="Add a caption">${esc(c.caption)}</div>
    ${g ? `<button class="vgoal" data-act="gopen" data-id="${g.id}">${ring(g.pct, 18, 3)}<span>${esc(g.title)}</span><small>${amountText(g)}</small></button>` : ''}</div>`;
}
function visionHTML() {
  const cs = S.d.cards;
  const add = S.vadd ? `<div class="addrow" style="margin-top:20px"><span class="plus">+</span><input id="vaddin" maxlength="400" placeholder="Type the words, press Enter"></div>` : '';
  return `<div class="page" id="vpage"><div class="vwrap"><div class="head2"><div><div class="bigt">Vision</div><div class="sub">What you are working for. Look at it every day.</div></div>
      <div class="vbtns">${cs.length > 1 ? '<button class="newbtn" data-act="vshow">Show</button>' : ''}
        <button class="newbtn" data-act="vtext">${ICON.plus}Words</button><button class="newbtn" data-act="vpick">${ICON.plus}Picture</button></div></div>
    ${add}
    ${cs.length ? `<div class="vgrid">${cs.map(vcard).join('')}</div>`
      : '<div class="empty2">Add pictures of what you want: the place, the body, the number.<br>Press Picture, drop files here, or paste with Ctrl+V. They stay on this PC.</div>'}
    <input type="file" id="vfile" accept="image/*" multiple hidden></div></div>`;
}
function wireMore() {                              // runs after every render
  if (S.tab !== 'vision') return;
  if (S.vadd) { const i = $('#vaddin'); if (i && document.activeElement !== i) i.focus(); }
  document.querySelectorAll('img[data-vid]').forEach(async img => {
    const id = Number(img.dataset.vid);
    if (S.vimg.has(id)) return;
    try { const u = await api.vision_image(id); S.vimg.set(id, u); img.src = u; } catch (e) { img.closest('.vcard').classList.add('gone'); }
  });
}
async function addPicture(file) {                  // shrink in the page, so the app never stores a giant photo
  if (!file || !file.type.startsWith('image/')) return;
  const url = URL.createObjectURL(file);
  try {
    const img = new Image(); img.src = url; await img.decode();
    const k = Math.min(1, 1600 / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(img.naturalWidth * k)); c.height = Math.max(1, Math.round(img.naturalHeight * k));
    const ctx = c.getContext('2d'); ctx.fillStyle = '#161618'; ctx.fillRect(0, 0, c.width, c.height); ctx.drawImage(img, 0, 0, c.width, c.height);
    const data = c.toDataURL('image/jpeg', 0.85);
    const row = await call('add_vision_image', data);
    S.vimg.set(row.id, data);
  } catch (e) { toast('Nook could not read that picture'); } finally { URL.revokeObjectURL(url); }
}
async function addPictures(files) { for (const f of [...files]) await addPicture(f); load(); }

function closeFull() { S.vfull = null; clearInterval(S.vT); const b = $('#vfull'); if (b) b.remove(); }
function drawFull() {
  const cs = S.d.cards || [], c = cs[S.vfull.i]; if (!c) return closeFull();
  let b = $('#vfull');
  if (!b) { b = document.createElement('div'); b.id = 'vfull'; document.body.appendChild(b); b.addEventListener('click', closeFull); }
  b.innerHTML = (c.kind === 'image' ? `<img src="${S.vimg.get(c.id) || ''}" alt="">` : `<div class="vbig">${esc(c.text)}</div>`)
    + (c.caption ? `<span>${esc(c.caption)}</span>` : '');
}
function stepFull(n) { const len = (S.d.cards || []).length; if (!len) return; S.vfull.i = (S.vfull.i + n + len) % len; drawFull(); }
Object.assign(ACT, {
  vpick: () => $('#vfile').click(),
  vtext: () => { S.vadd = !S.vadd; render(); },
  vwide: async el => { const c = S.d.cards.find(x => x.id === Number(el.dataset.id)); await call('update_vision', c.id, { wide: !c.wide }); load(); },
  vdel: el => twice(el, async () => { const id = Number(el.dataset.id); await call('delete_vision', id); S.vimg.delete(id); load(); }, 'Remove'),
  vopen: el => { S.vfull = { i: S.d.cards.findIndex(x => x.id === Number(el.dataset.id)) }; drawFull(); },
  vshow: () => { S.vfull = { i: 0 }; drawFull(); clearInterval(S.vT); S.vT = setInterval(() => stepFull(1), 6000); },
});
document.addEventListener('change', async e => {
  if (e.target.id === 'vfile') return addPictures(e.target.files);
  if (e.target.dataset.vgoal) { await call('update_vision', Number(e.target.dataset.vgoal), { goal_id: e.target.value ? Number(e.target.value) : null }); load(); }
});
document.addEventListener('focusout', async e => {
  const id = e.target.dataset && e.target.dataset.vcap; if (!id) return;
  const c = (S.d.cards || []).find(x => x.id === Number(id)), v = e.target.textContent.trim();
  if (c && v !== c.caption) { await call('update_vision', c.id, { caption: v }).catch(() => {}); load(); }
});
document.addEventListener('paste', e => {
  if (S.tab !== 'vision' || e.target.matches('input, [contenteditable=true]')) return;
  const files = [...(e.clipboardData ? e.clipboardData.files : [])].filter(f => f.type.startsWith('image/'));
  if (files.length) { e.preventDefault(); addPictures(files); }
});
document.addEventListener('dragover', e => { if (S.tab === 'vision' && e.target.closest('#vpage')) e.preventDefault(); });
document.addEventListener('drop', async e => {
  if (S.tab !== 'vision' || !e.target.closest('#vpage')) return;
  e.preventDefault();
  if (e.dataTransfer.files.length) return addPictures(e.dataTransfer.files);
  const cs = S.d.cards, a = cs.find(x => x.id === Number(e.dataTransfer.getData('text/plain')));
  const over = e.target.closest('.vcard'), b = over && cs.find(x => x.id === Number(over.dataset.id));
  if (!a || !b || a === b) return;
  const i = cs.indexOf(b), prev = cs[i - 1] && cs[i - 1] !== a ? cs[i - 1].pos : b.pos - 1;   // land just before the one you dropped on
  await call('update_vision', a.id, { pos: (prev + b.pos) / 2 }); load();
});
document.addEventListener('keydown', e => {
  if (!S.vfull) return;
  if (e.key === 'Escape') { e.stopPropagation(); closeFull(); }
  if (e.key === 'ArrowRight') stepFull(1);
  if (e.key === 'ArrowLeft') stepFull(-1);
}, true);
