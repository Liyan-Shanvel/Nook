'use strict';
/* Deepcus screens. One store behind it: a task, a calendar block and a focus session are one item. */

const START = 6, END = 24, H = 48, SNAP = 15;           // day grid: 6 AM to midnight, 48 px per hour
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pad = n => String(n).padStart(2, '0');
const iso = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parse = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const addDays = (s, n) => { const d = parse(s); d.setDate(d.getDate() + n); return iso(d); };
const monday = s => { const d = parse(s); d.setDate(d.getDate() - (d.getDay() + 6) % 7); return iso(d); };
const DOW = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const hm = m => { m = Math.round(m); return `${(Math.floor(m / 60) % 24) % 12 || 12}:${pad(m % 60)}`; };
const half = m => (m < 720 || m >= 1440 ? 'AM' : 'PM');
const range = (a, b) => (half(a) === half(b) ? `${hm(a)} – ${hm(b)} ${half(b)}` : `${hm(a)} ${half(a)} – ${hm(b)} ${half(b)}`);
const longDur = m => { const h = Math.floor(m / 60), r = m % 60;
  return !h ? `${r} min` : r ? `${h}h ${r}m` : h === 1 ? '1 hour' : `${h} hours`; };
const dur = m => { m = Math.round(m); const h = Math.floor(m / 60), r = m % 60; return h ? (r ? `${h}h ${r}m` : `${h}h`) : `${r}m`; };
const nowMin = () => { const d = new Date(); return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60; };
const y = m => (m - START * 60) / 60 * H;
const snap = m => Math.round(m / SNAP) * SNAP;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const shortDay = s => { const d = parse(s); return `${DOW[d.getDay()].slice(0, 3)}, ${d.getDate()} ${MON[d.getMonth()].slice(0, 3)}`; };

const ICON = {
  check: '<svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 5.2l2 2 4-4.4" stroke="#161618" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  play: '<svg width="9" height="9" viewBox="0 0 8 8"><path d="M2 1l5 3-5 3V1z" fill="currentColor"/></svg>',
  x: '<svg width="10" height="10" viewBox="0 0 10 10"><path d="M2.5 2.5l5 5M7.5 2.5l-5 5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  reset: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8a5 5 0 1 0 1.5-3.6M3 2.5v2.5h2.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  note: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 3h8M2 6h8M2 9h5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
  clock: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6.5" r="4.3" stroke="currentColor" stroke-width="1.2"/><path d="M6 4.3v2.4l1.5 1M4.6 1.2h2.8" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  cal: '<svg width="11" height="11" viewBox="0 0 12 12" fill="none"><rect x="1.5" y="2.5" width="9" height="8" rx="2" stroke="currentColor" stroke-width="1.2"/><path d="M1.5 5h9M4 1.2v2M8 1.2v2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
  left: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M7.5 2.5L4 6l3.5 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  right: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4.5 2.5L8 6 4.5 9.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

/* ---------- talking to Python (pywebview in the app, a small dev server in tests) ---------- */
const api = new Proxy({}, {
  get: (_, name) => (...args) => (window.pywebview && window.pywebview.api)
    ? window.pywebview.api[name](...args)
    : fetch('/api/' + name, { method: 'POST', body: JSON.stringify(args) })
      .then(r => r.json()).then(j => { if (j.error) throw new Error(j.error); return j.ok; }),
});

let toastTimer;
function toast(msg, undo) {                    // one quiet line at the bottom; an Undo word when there is something to undo
  const t = $('#toast'); t.textContent = msg; t.classList.add('show'); t.classList.toggle('act', !!undo);
  if (undo) {
    const b = document.createElement('button'); b.textContent = 'Undo';
    b.addEventListener('click', e => { e.stopPropagation(); t.classList.remove('show', 'act'); undo(); });
    t.appendChild(b);
  }
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show', 'act'), undo ? 6000 : 3000);
}
async function call(name, ...args) {
  try { return await api[name](...args); }
  catch (e) { toast(String((e && e.message) || e).replace(/^.*?Error:\s*/, '')); throw e; }
}

const S = { tab: 'today', view: 'day', date: null, today: null, d: null, timer: null, settings: null,
  sel: null, pop: null, msel: null, adding: null, refocus: null, busy: false, scrollKey: null };

/* ---------- load + render ---------- */
async function load() {
  if (S.tab === 'today') S.d = await call('today_data');
  else if (S.tab === 'calendar') {
    if (S.view === 'day') S.d = await call('day_data', S.date);
    else if (S.view === 'week') { const a = monday(S.date); S.d = await call('range_data', a, addDays(a, 6)); S.d.a = a; }
    else { const a = monday(S.date.slice(0, 8) + '01'); S.d = await call('range_data', a, addDays(a, 41)); S.d.a = a; }
  } else S.d = await moreLoad();
  if (!S.d.timer) S.d.timer = await call('timer');
  noteGoals(S.d);
  S.timer = S.d.timer;
  if (S.d.settings) S.settings = S.d.settings;
  S.upd = await call('update_status').catch(() => S.upd);
  if (S.d.today) {
    if (S.today && S.d.today !== S.today && S.date === S.today) S.date = S.d.today;   // midnight passed
    S.today = S.d.today;
  }
  render();
}

function renderUpd() {                          // a thin strip at the bottom, never a popup
  const on = !!(S.upd && S.upd.ready), box = $('#upd');
  document.body.classList.toggle('hasupd', on);
  if (!on) { box.innerHTML = ''; return; }
  if (box.dataset.v === S.upd.latest && box.innerHTML) return;      // keep "Restarting..." while it installs
  box.dataset.v = S.upd.latest;
  box.innerHTML = `<span>&uarr;&nbsp; Version ${esc(S.upd.latest || '')} is ready</span><button data-act="update">Restart to update</button>`;
}
/* risky buttons: the first click turns the button into its own red word, the second click does it */
function twice(el, fn, word = 'Delete') {
  if (el.classList.contains('armed')) { const off = S.armed; S.armed = null; clearTimeout(S.armT); if (off) off(); return fn(); }
  if (S.armed) S.armed();
  const html = el.innerHTML;
  el.textContent = word; el.classList.add('armed');
  S.armed = () => { clearTimeout(S.armT); S.armed = null; if (el.isConnected) { el.innerHTML = html; el.classList.remove('armed'); } };
  S.armT = setTimeout(() => S.armed && S.armed(), 3000);
}

function render() {
  renderTop(); renderUpd();
  const m = $('#main');
  const keep = $('.tlwrap') ? $('.tlwrap').scrollTop : null;
  if (S.tab === 'today') m.innerHTML = todayHTML();
  else if (S.tab === 'calendar') m.innerHTML = S.view === 'day' ? calDayHTML() : S.view === 'week' ? weekHTML() : monthHTML();
  else {
    const pg = $('.page'), keepY = pg && S.lastTab === S.tab + S.habit + S.goal ? pg.scrollTop : 0;
    m.innerHTML = moreHTML();
    if ($('.page')) $('.page').scrollTop = keepY;
  }
  S.lastTab = S.tab + S.habit + S.goal;
  if (S.tab === 'calendar' && S.view === 'day') wireDay(keep);
  if (S.tab === 'calendar' && S.view === 'week') wireWeek();
  if (S.refocus) { const el = $(S.refocus); if (el) el.focus(); S.refocus = null; }
  tick();
  if (typeof wireMore === 'function') wireMore();
}

function renderTop() {
  const tabs = ['Today', 'Calendar', 'Habits', 'Goals', 'Vision', 'Progress'];
  let date = shortDay(S.today), right = '';
  if (S.tab === 'calendar') {
    if (S.view === 'week') {
      const a = parse(monday(S.date)), b = parse(addDays(monday(S.date), 6));
      date = a.getMonth() === b.getMonth() ? `${a.getDate()} – ${b.getDate()} ${MON[b.getMonth()].slice(0, 3)}`
        : `${a.getDate()} ${MON[a.getMonth()].slice(0, 3)} – ${b.getDate()} ${MON[b.getMonth()].slice(0, 3)}`;
    } else if (S.view === 'month') { const d = parse(S.date); date = `${MON[d.getMonth()]} ${d.getFullYear()}`; }
    else date = shortDay(S.date);
    right = `<div class="seg">${[['day', 'Today'], ['week', 'Week'], ['month', 'Month']].map(([v, l]) =>
      `<button class="${S.view === v ? 'on' : ''}" data-act="view" data-v="${v}">${l}</button>`).join('')}</div>
      <button class="arrow" data-act="step" data-v="-1" title="Back">${ICON.left}</button>
      <button class="arrow" data-act="step" data-v="1" title="Next">${ICON.right}</button>`;
  } else if (S.tab === 'today' && S.d && S.d.focused !== undefined) {
    right = `<span class="goal"><b>${dur(S.d.focused)}</b> of ${dur(S.settings.goal_min)}</span>`;
  } else if (MORE_TABS.includes(S.tab)) ({ date, right } = moreTop());
  right += `<button class="gear" data-act="settings" title="Settings">${ICON.gear}</button>`;
  $('#top').innerHTML = `<div><span class="brand">deep<i>cus</i><b>.</b></span><span class="date">${date}</span></div>
    <div class="tabs">${tabs.map(t => `<button class="tab ${S.tab === t.toLowerCase() ? 'on' : ''}" data-act="tab" data-v="${t.toLowerCase()}">${t}</button>`).join('')}</div>
    <div class="right">${right}</div>`;
}

/* ---------- shared bits ---------- */
const running = id => S.timer && S.timer.running && S.timer.task_id === id;
function findTask(id) {
  id = Number(id);
  const pools = [S.d.tasks || [], S.d.carry || [], S.d.current ? [S.d.current] : []];
  for (const p of pools) { const t = p.find(x => x.id === id); if (t) return t; }
  return null;
}
function taskRow(x, { drag = false, rowAct = '', chip = false } = {}) {
  const now = running(x.id);
  const time = x.start_min != null ? `<span class="time">${hm(x.start_min)}</span>`
    : chip && !x.done ? '<span class="chip">No time</span>' : '<span class="time"></span>';
  return `<div class="row ${x.done ? 'done' : ''} ${now ? 'now' : ''}" data-id="${x.id}" ${rowAct ? `data-act="${rowAct}"` : ''} ${drag && !x.done ? 'draggable="true"' : ''}>
    <button class="chk" data-act="toggle" data-id="${x.id}" title="${x.done ? 'Not done' : 'Done'}">${x.done ? ICON.check : now ? ICON.play : ''}</button>
    <span class="t" data-edit="${x.id}">${esc(x.title)}</span>
    ${x.notes || S.note === x.id ? `<button class="nb ${S.note === x.id ? 'on' : ''}" data-act="note" data-id="${x.id}" title="Description">${ICON.note}</button>` : ''}
    ${x.goal_id && S.goalNames[x.goal_id] ? `<span class="gtag" title="Counts toward ${esc(S.goalNames[x.goal_id])}">${esc(S.goalNames[x.goal_id])}</span>` : ''}
    ${now ? '' : !x.done ? `<button class="play" data-act="start" data-id="${x.id}" title="Start now">${ICON.play}</button>` : ''}
    ${x.done ? '' : S.tlen === x.id
      ? `<input class="lenin" id="tlenin" data-id="${x.id}" value="${x.focus_min || ''}" placeholder="${S.settings.focus}" inputmode="numeric" maxlength="3">`
      : `<button class="len ${x.focus_min ? 'set' : ''}" data-act="tlen" data-id="${x.id}" title="Focus length: scroll or click">${x.focus_min ? x.focus_min + 'm' : ICON.clock}</button>`}
    ${time}
    <button class="x" data-act="del" data-id="${x.id}" title="Delete">${ICON.x}</button></div>${S.note === x.id
      ? `<div class="desc"><textarea id="noteta" data-id="${x.id}" maxlength="4000" placeholder="What to do, files, steps">${esc(x.notes || '')}</textarea></div>` : ''}`;
}
const LIMIT = { focus: [1, 180], short: [1, 60], long: [1, 90] };
/* "25", "1:30", "1h30", "90m" -> minutes */
function parseMin(s) {
  s = String(s).trim().toLowerCase();
  let m = s.match(/^(\d{1,2}):(\d{2})$/); if (m) return +m[1] * 60 + +m[2];
  m = s.match(/^(?:(\d{1,2})\s*h)?\s*(?:(\d{1,3})\s*m?)?$/); if (m && (m[1] || m[2])) return (+m[1] || 0) * 60 + (+m[2] || 0);
  return NaN;
}
const addRow = (day, ph = 'Add a task, press Enter') =>
  `<div class="addrow"><span class="plus">+</span><input data-addday="${day}" placeholder="${ph}" id="add-${day}"></div>`;

/* ---------- Today tab ---------- */
function ringSVG() {
  const R1 = 138, R2 = 116, C1 = 2 * Math.PI * R1, C2 = 2 * Math.PI * R2;
  const tasks = S.d.tasks, q = tasks.length ? tasks.filter(t => t.done).length / tasks.length : 0;
  const brk = S.timer.mode !== 'focus';
  return `<svg width="300" height="300" viewBox="0 0 300 300">
    <circle cx="150" cy="150" r="${R1}" fill="none" stroke="var(--track)" stroke-width="10"/>
    <circle id="arc1" cx="150" cy="150" r="${R1}" fill="none" stroke="${brk ? 'rgba(255,255,255,.55)' : '#fff'}" stroke-width="10" stroke-linecap="round" stroke-dasharray="${C1}" stroke-dashoffset="${C1}" data-c="${C1}"/>
    <circle cx="150" cy="150" r="${R2}" fill="none" stroke="var(--track)" stroke-width="6"/>
    <circle cx="150" cy="150" r="${R2}" fill="none" stroke="rgba(255,255,255,.55)" stroke-width="6" stroke-linecap="round" stroke-dasharray="${C2}" stroke-dashoffset="${C2 * (1 - q)}" opacity="${q ? 1 : 0}"/>
  </svg>`;
}

function todayHTML() {
  const d = S.d, t = S.timer, tasks = d.tasks, done = tasks.filter(x => x.done).length;
  const cur = t.task_id ? (d.current || findTask(t.task_id)) : null;
  const total = Math.round(t.total / 60);
  let center, onWhat, ctrls;
  if (t.just_done) {
    const wasFocus = t.done_mode === 'focus';
    center = `<div class="clock" style="font-size:44px">${total} min</div><div class="of">done</div>`;
    onWhat = wasFocus && cur ? `<span class="cap">Is it finished?</span><div class="task">${esc(cur.title)}</div>`
      : wasFocus && t.label ? `<span class="cap">Nice work</span><div class="task">${esc(t.label)}</div>`
      : `<span class="cap">${wasFocus ? 'Nice work' : 'Break over'}</span>`;
    ctrls = wasFocus
      ? `${cur && !cur.done ? '<button class="big" data-act="tickoff">Tick it off</button>' : ''}
         <button class="ghostbtn" data-act="mode" data-v="short">Take ${S.settings.short} min break</button>
         <button class="ghostbtn" data-act="mode" data-v="focus">Keep going</button>`
      : `<button class="big" data-act="mode" data-v="focus">Start focus</button><button class="ghostbtn" data-act="dismiss">Not now</button>`;
  } else {
    const label = t.running ? 'Pause' : t.remaining < t.total - 0.5 ? 'Resume' : 'Start';
    const ofTxt = `of ${total} min${t.mode !== 'focus' ? ' break' : ''}`;
    // idle: scroll on the ring changes the length, click the time to type it
    center = t.running ? `<div class="clock" id="clock">0:00</div><div class="of">${ofTxt}</div>`
      : `<div class="clock settable" id="clock" data-act="lenedit" title="Scroll or click to change">0:00</div><div class="of" id="ofmin">${ofTxt}</div>`;
    onWhat = t.mode !== 'focus' ? `<span class="cap">On a break</span><div class="task none">Stand up. Drink water.</div>`
      : cur ? `<span class="cap">Focusing on</span><div class="task ${t.running ? '' : 'relabel'}" ${t.running ? '' : 'data-act="unlabel" title="Change"'}>${esc(cur.title)}</div>`
        : t.label ? `<span class="cap">Focusing on</span><div class="task ${t.running ? '' : 'relabel'}" ${t.running ? '' : 'data-act="unlabel" title="Change"'}>${esc(t.label)}</div>`
          : `<span class="cap">Focusing on</span><div class="fname"><input class="focusname" id="focusname" placeholder="Name or task" autocomplete="off" spellcheck="false"><div id="fsugg" class="fsugg"></div></div>`;
    ctrls = `<button class="ctl" data-act="reset" title="Reset">${ICON.reset}</button>
      <button class="big" data-act="go">${label}</button>
      <span class="ctl" style="visibility:hidden"></span>`;
  }
  const modes = t.just_done ? '' : `<div class="modes">${[['focus', 'Focus'], ['short', 'Short break'], ['long', 'Long break']].map(([v, l]) =>
    `<button class="${t.mode === v ? 'on' : ''}" data-act="mode" data-v="${v}">${l}</button>`).join('')}</div>`;

  let list;
  const carry = d.carry.length ? `<div class="carry"><div class="head"><span class="cap">From yesterday</span>
      <button class="small" data-act="movecarry">Move all to today</button></div>
      ${d.carry.slice(0, 4).map(x => `<div class="item">${esc(x.title)}</div>`).join('')}
      ${d.carry.length > 4 ? `<div class="item" style="color:var(--fg3)">+ ${d.carry.length - 4} more</div>` : ''}</div>` : '';
  if (!tasks.length && !d.carry.length) {
    list = `<div class="dayone"><h1>What's today about?</h1><div class="sub">Write 1 to 3 things you want done. Press Enter after each.</div>${addRow(S.today, 'The first thing...')}</div>`;
    S.refocus = S.refocus || `#add-${S.today}`;
  } else {
    list = `${carry}<span class="cap">Today</span><div style="margin-top:6px">${tasks.map(x => taskRow(x, { rowAct: 'start' })).join('')}</div>
      ${addRow(S.today)}<div class="hint">Click a task to start it. Double-click to rename. Right-click for more. Give it a time in Calendar.</div>`;
  }
  return `<div class="todaytab"><section class="focus">
      <div class="ring">${ringSVG()}<div class="center">${center}</div></div>
      <div class="on-what">${onWhat}<span class="sub">${done} of ${plural(tasks.length, 'task')} done</span></div>
      <div class="ctrls">${ctrls}</div>${modes}</section>
    <section class="list">${list}</section></div>`;
}

/* ---------- Calendar: day ---------- */
function blockHTML(x) {
  const now = running(x.id), h = y(x.end_min) - y(x.start_min) - 2, tall = now && h >= 40, sel = S.sel === x.id;
  const left = now ? `, ${Math.max(1, Math.ceil(S.timer.remaining / 60))} min left` : '';
  const time = `${hm(x.start_min)} – ${hm(x.end_min)}${left}`;
  const acts = sel ? `<span class="acts">${!x.done && !now ? `<button class="main" data-act="start" data-id="${x.id}">Start</button>` : ''}
      <button data-act="toggle" data-id="${x.id}">${x.done ? 'Undo' : 'Done'}</button>
      <button data-act="untime" data-id="${x.id}">Remove time</button></span>`
    : x.done ? '<span class="tick">&#10003;</span>' : now ? '<span class="nowtag">NOW</span>' : '';
  return `<div class="blk task ${x.done ? 'done' : ''} ${now ? 'now' : ''} ${tall ? 'tall' : ''} ${sel ? 'sel' : ''}" data-id="${x.id}" ${x.notes ? `title="${esc(x.notes)}"` : ''} style="top:${y(x.start_min) + 1}px;height:${h}px">
    ${tall ? `<span class="t"><span data-edit="${x.id}">${esc(x.title)}</span><small>${time}</small></span>` : `<span class="t" data-edit="${x.id}">${esc(x.title)}</span><small>${time}</small>`}
    ${acts}<i class="grip"></i></div>`;
}

function sideHTML(isToday) {
  const d = S.d, st = S.settings;
  const next = isToday ? d.meetings.find(m => m.start_min > nowMin()) : null;
  const meet = next ? `<div class="sec"><span class="cap">Next meeting</span><div style="font-weight:600;font-size:14px;margin-top:6px">${esc(next.title)}</div>
      <div class="sub">${hm(next.start_min)} ${half(next.start_min)}, in ${dur(next.start_min - nowMin())}</div></div>` : '';
  const cap = `<span class="cap">${isToday ? 'Tracked today' : 'Tracked'}</span>`;
  if (!st.tracking) return `<div class="side">${cap}<div class="quiet">Auto tracking is off.</div>
      <button class="link" data-act="tracking" data-v="1">Turn it on</button>${meet}</div>`;
  if (S.date > d.today) return `<div class="side">${cap}<div class="quiet">Nothing yet. This day hasn't happened.</div>${meet}</div>`;
  const sm = d.summary;
  if (sm.total < 1) return `<div class="side">${cap}<div class="quiet">Nothing tracked yet. Deepcus notes which app is in front while you work. It stays on this PC.</div>${meet}</div>`;
  const row = (c, l, v) => `<div class="kv"><i class="dot" style="background:${c}"></i><span>${l}</span><b>${dur(v)}</b></div>`;
  return `<div class="side">${cap}<div class="bignum">${dur(sm.total)}</div>
    <div class="bar">${sm.focus ? `<i style="flex:${sm.focus};background:#fff"></i>` : ''}${sm.distracted ? `<i style="flex:${sm.distracted};background:var(--red)"></i>` : ''}${sm.other ? `<i style="flex:${sm.other};background:rgba(255,255,255,.25)"></i>` : ''}</div>
    ${row('#fff', 'Focus', sm.focus)}${row('var(--red)', 'Distracted', sm.distracted)}${row('rgba(255,255,255,.25)', 'Other', sm.other)}
    <div class="sec"><span class="cap">Top apps</span>${sm.apps.map(a => `<div class="kv q"><span>${esc(a.app)}</span><b>${dur(a.mins)}</b></div>`).join('')}</div>
    ${meet}
    <div class="sec"><button class="link" style="margin:0;color:var(--fg3);font-weight:500" data-act="tracking" data-v="0">Turn off tracking</button></div></div>`;
}

function calDayHTML() {
  const d = S.d, isToday = S.date === d.today, tasks = d.tasks, meets = d.meetings;
  const done = tasks.filter(x => x.done).length;
  const hours = [];
  for (let h = START; h < END; h++) hours.push(`<span style="position:absolute;top:${(h - START) * H - (h === START ? 0 : 6)}px;right:10px">${h === 12 ? '12 PM' : h % 12 || 12}${h < 12 && (h === START || h === 8) ? ' AM' : ''}</span>`);
  const timed = tasks.filter(x => x.start_min != null && x.end_min > START * 60);
  const lane = d.lane.filter(e => e.end_min > START * 60).map(e => {
    const hh = y(e.end_min) - y(e.start_min) - 2;
    const cls = e.category === 'focus' ? '' : e.category;
    return hh >= 30 ? `<div class="ent ${cls}" style="top:${y(e.start_min) + 1}px;height:${hh}px" title="${esc(e.label)}">${esc(e.label)}<small>${dur(e.mins)}</small></div>`
      : `<div class="ent one ${cls}" style="top:${y(e.start_min) + 1}px;height:${Math.max(hh, 12)}px" title="${esc(e.label)}">${esc(e.label)}, ${dur(e.mins)}</div>`;
  }).join('');
  const meetBlocks = meets.map(m => `<div class="blk meet" data-meet="${esc(m.id)}" style="top:${y(m.start_min) + 1}px;height:${Math.max(18, y(m.end_min) - y(m.start_min) - 2)}px">
      <span class="t">${esc(m.title)}</span><small>${hm(m.start_min)} – ${hm(m.end_min)}, Google Calendar</small></div>`).join('');
  const nowLine = isToday ? `<div class="nowline" id="nowline" style="top:${y(nowMin())}px"><b><i id="nowlbl">${hm(nowMin())}</i></b><u></u></div>` : '';
  return `<div class="cal">
    <section class="ctasks"><h1>${DOW[parse(S.date).getDay()]}</h1>
      <div class="sub" style="margin-top:4px">${plural(tasks.length, 'task')}${meets.length ? `, ${plural(meets.length, 'call')}` : ''}. ${done} done.</div>
      <span class="cap lbl">${isToday ? "Today's tasks" : 'Tasks'}</span>
      ${tasks.map(x => taskRow(x, { drag: true, chip: true })).join('')}
      ${addRow(S.date, 'Add a task')}
      <div class="hint">Drag a task onto the day to give it a time. Drag a block up or down to change its time. Right-click for more.</div></section>
    <section class="day"><div class="heads"><span class="cap">Plan</span><span class="cap">What happened</span></div>
      <div class="tlwrap"><div class="tl" style="height:${(END - START) * H}px">
        <div class="hours" style="position:relative">${hours.join('')}</div>
        <div class="lanes"><div class="plan" id="plan">${meetBlocks}${timed.map(blockHTML).join('')}</div>
          <div class="real">${lane}</div>${nowLine}</div></div></div></section>
    ${sideHTML(isToday)}</div>`;
}

function place(el, s, en) {
  el.style.top = (y(s) + 1) + 'px';
  el.style.height = (y(en) - y(s) - 2) + 'px';
  const sm = el.querySelector('small');
  if (sm) sm.textContent = `${hm(s)} – ${hm(en)}`;
}

function wireDay(keepScroll) {
  const plan = $('#plan'), wrap = $('.tlwrap');
  const key = S.date;
  if (S.scrollKey === key && keepScroll != null) wrap.scrollTop = keepScroll;
  else { wrap.scrollTop = Math.max(0, y((S.date === S.today ? nowMin() : 9 * 60) - 90)); S.scrollKey = key; }
  plan.addEventListener('pointerdown', onPlanDown);
  plan.addEventListener('dragover', e => { e.preventDefault(); plan.classList.add('dropping'); });
  plan.addEventListener('dragleave', () => plan.classList.remove('dropping'));
  plan.addEventListener('drop', async e => {
    e.preventDefault(); plan.classList.remove('dropping');
    const x = findTask(e.dataTransfer.getData('text/plain'));
    if (!x) return;
    const len = x.start_min != null ? x.end_min - x.start_min : 30;
    const m = (e.clientY - plan.getBoundingClientRect().top) / H * 60 + START * 60;
    const s = clamp(snap(m), START * 60, END * 60 - len);
    await call('update_task', x.id, { day: S.date, start_min: s, end_min: s + len });
    load();
  });
}

function onPlanDown(e) {
  if (e.button !== 0 || e.target.closest('button, .editing')) return;
  if (S.pop) { closePop(); return; }
  const plan = e.currentTarget, top = plan.getBoundingClientRect().top;
  const toMin = cy => (cy - top) / H * 60 + START * 60;
  const blk = e.target.closest('.blk');
  if (blk && blk.classList.contains('meet')) return;
  let moved = false, s, en;
  const finish = (mv, up) => {
    plan.setPointerCapture(e.pointerId);
    S.busy = true;
    plan.addEventListener('pointermove', mv);
    plan.addEventListener('pointerup', function done(ev) {
      plan.removeEventListener('pointermove', mv); plan.removeEventListener('pointerup', done);
      S.busy = false; up(ev);
    });
  };
  if (blk) {                                   // move or resize a block
    const x = findTask(blk.dataset.id), resize = e.target.classList.contains('grip');
    const m0 = toMin(e.clientY), len = x.end_min - x.start_min;
    s = x.start_min; en = x.end_min;
    finish(ev => {
      if (!moved && Math.abs(ev.clientY - e.clientY) < 4) return;
      moved = true;
      const m = toMin(ev.clientY);
      if (resize) en = clamp(snap(m), s + SNAP, END * 60);
      else { s = clamp(snap(x.start_min + (m - m0)), START * 60, END * 60 - len); en = s + len; }
      place(blk, s, en);
    }, async () => {
      if (moved) { S.sel = null; await call('update_task', x.id, { start_min: s, end_min: en }).catch(() => {}); }
      else S.sel = S.sel === x.id ? null : x.id;
      load();
    });
    return;
  }
  S.sel = null;                                // draw a new block on empty space
  const a0 = clamp(Math.floor(toMin(e.clientY) / SNAP) * SNAP, START * 60, END * 60 - SNAP);
  s = a0; en = Math.min(a0 + 60, END * 60);
  const g = document.createElement('div');
  g.className = 'blk ghost tall';
  g.innerHTML = '<span class="t">New block<small></small></span>';
  plan.appendChild(g); place(g, s, en);
  finish(ev => {
    if (!moved && Math.abs(ev.clientY - e.clientY) < 4) return;
    moved = true;
    const m = clamp(snap(toMin(ev.clientY)), START * 60, END * 60);
    if (m >= a0 + SNAP) { s = a0; en = m; } else { s = Math.min(m, a0); en = a0 + SNAP; }
    place(g, s, en);
  }, () => openPop(g, s, en));
}

function openPop(g, s, en) {
  const opts = S.d.tasks.filter(t => !t.done);
  S.pop = { s, en, pick: null };
  const el = document.createElement('div');
  el.className = 'pop'; el.id = 'pop';
  el.innerHTML = `<div class="when">${range(s, en)}<small>${longDur(en - s)}</small></div>
    <input id="popin" placeholder="Type something new, press Enter">
    ${opts.length ? `<span class="cap">Or pick a task</span><div class="opts">${opts.map(t => `<button class="opt" data-pick="${t.id}">
      <span class="chk"></span><span>${esc(t.title)}</span><small>${t.start_min != null ? 'moves from ' + hm(t.start_min) : 'no time yet'}</small></button>`).join('')}</div>` : ''}
    <div class="btns"><button class="btn" data-act="popcancel">Cancel</button><button class="btn main" data-act="popadd" disabled>Add to day</button></div>`;
  document.body.appendChild(el);
  const r = g.getBoundingClientRect();
  const left = r.right + 316 < innerWidth ? r.right + 12 : Math.max(16, r.left - 312);
  el.style.left = (r.right + 316 < innerWidth ? left : Math.min(left, r.left + 40)) + 'px';
  el.style.top = clamp(r.top, 16, innerHeight - el.offsetHeight - 16) + 'px';
  const inp = $('#popin');
  const sync = () => { $('#pop .main').disabled = !(inp.value.trim() || S.pop.pick); };
  inp.addEventListener('input', () => { if (inp.value) { S.pop.pick = null; document.querySelectorAll('.opt').forEach(o => o.classList.remove('sel')); } sync(); });
  inp.addEventListener('keydown', ev => { if (ev.key === 'Enter') popAdd(); if (ev.key === 'Escape') closePop(); });
  el.addEventListener('click', ev => {
    const o = ev.target.closest('.opt'); if (!o) return;
    const id = Number(o.dataset.pick);
    S.pop.pick = S.pop.pick === id ? null : id;
    document.querySelectorAll('.opt').forEach(b => b.classList.toggle('sel', Number(b.dataset.pick) === S.pop.pick));
    if (S.pop.pick) inp.value = '';
    sync();
  });
  inp.focus();
}
function closePop() {
  const p = $('#pop'); if (p) p.remove();
  document.querySelectorAll('.blk.ghost').forEach(g => g.remove());
  S.pop = null;
}
async function popAdd() {
  if (!S.pop) return;
  const { s, en, pick } = S.pop, text = $('#popin').value.trim();
  if (!text && !pick) return;
  try {
    if (text) await call('add_task', text, S.date, s, en);
    else await call('update_task', pick, { day: S.date, start_min: s, end_min: en });
  } finally { closePop(); load(); }
}

/* ---------- Calendar: week ---------- */
function itemsFor(day) {
  const ms = S.d.meetings.filter(m => m.day === day).map(m => ({ ...m, meet: true }));
  const ts = S.d.tasks.filter(t => t.day === day);
  return [...ms, ...ts].sort((a, b) => (a.start_min ?? 9999) - (b.start_min ?? 9999));
}
function itemHTML(x) {
  if (x.meet) return `<div class="it meet" data-meet="${esc(x.id)}"><span>${esc(x.title)}</span><small>${hm(x.start_min)}, Google Calendar</small></div>`;
  const now = running(x.id);
  return `<div class="it ${x.done ? 'done' : ''} ${now ? 'now' : ''}" draggable="true" data-id="${x.id}" data-act="openday" data-day="${x.day}"><span data-edit="${x.id}">${esc(x.title)}</span>
    <small>${x.start_min != null ? hm(x.start_min) : 'No time'}${now ? ', now' : ''}</small></div>`;
}
function weekHTML() {
  const d = S.d, a = d.a, goal = S.settings.goal_min;
  const days = [...Array(7)].map((_, i) => addDays(a, i));
  const hasToday = days.includes(d.today);
  const focus = Object.values(d.focus).reduce((p, v) => p + v, 0);
  const cols = days.map(day => {
    const kind = day < d.today ? 'past' : day === d.today ? 'today' : 'future';
    const its = itemsFor(day), f = d.focus[day] || 0;
    let foot = '';
    if (S.adding === day) foot = `<input id="wkadd" data-addday="${day}" placeholder="New task, Enter">`;
    else {
      if (kind !== 'future') foot += `<b>${dur(f)}</b><small>focus</small><div class="meter"><i style="width:${Math.min(100, f / goal * 100)}%"></i></div>`;
      if (kind !== 'past') foot += `<button class="add" data-act="adding" data-day="${day}" style="margin-top:${kind === 'today' ? 10 : 0}px">+ Add</button>`;
    }
    const dd = parse(day);
    return `<div class="col ${kind}" data-day="${day}"><span class="dn">${DOW[dd.getDay()].slice(0, 3)}</span>
      <span class="dd" data-act="openday" data-day="${day}" title="Open this day">${dd.getDate()}</span>
      <div class="items">${its.length ? its.map(itemHTML).join('') : '<div class="empty">Nothing planned</div>'}</div>
      <div class="foot">${foot}</div></div>`;
  }).join('');
  const nT = d.tasks.length, nM = d.meetings.length, ad = parse(a);
  return `<div class="wkhead"><h1>${hasToday ? 'This week' : `Week of ${ad.getDate()} ${MON[ad.getMonth()].slice(0, 3)}`}</h1>
      <div class="sub" style="margin-top:4px">${plural(nT, 'thing')} planned${nM ? `, ${plural(nM, 'call')}` : ''}. ${dur(focus)} of focus${hasToday ? ' so far' : ''}.</div></div>
    <div class="wk">${cols}</div>
    <div class="hint" style="margin-top:12px">Drag a thing to another day to move it. Right-click it for more. Click a date to open that day.</div>`;
}
function wireWeek() {
  if (S.adding) S.refocus = '#wkadd';
  document.querySelectorAll('.col').forEach(col => {
    col.addEventListener('dragover', e => { e.preventDefault(); col.classList.add('drop'); });
    col.addEventListener('dragleave', e => { if (!col.contains(e.relatedTarget)) col.classList.remove('drop'); });
    col.addEventListener('drop', async e => {
      e.preventDefault(); col.classList.remove('drop');
      const id = e.dataTransfer.getData('text/plain');
      if (id) { await call('update_task', Number(id), { day: col.dataset.day }); load(); }
    });
  });
  const w = $('#wkadd');
  if (w) w.addEventListener('blur', () => setTimeout(() => { if (S.adding && !w.value.trim()) { S.adding = null; render(); } }, 150));
}

/* ---------- Calendar: month ---------- */
function monthHTML() {
  const d = S.d, a = d.a, cur = parse(S.date), mon = cur.getMonth(), goal = S.settings.goal_min;
  const last = new Date(cur.getFullYear(), mon + 1, 0).getDate();
  const lead = (new Date(cur.getFullYear(), mon, 1).getDay() + 6) % 7;
  const rows = Math.ceil((lead + last) / 7);
  const sel = S.msel || (parse(S.date).getMonth() === mon ? S.date : null);
  let cells = '';
  for (let i = 0; i < rows * 7; i++) {
    const day = addDays(a, i), dd = parse(day);
    if (dd.getMonth() !== mon) { cells += `<div class="cell blank" style="height:${100 / rows}%"></div>`; continue; }
    const ms = d.meetings.filter(m => m.day === day), ts = d.tasks.filter(t => t.day === day), f = d.focus[day] || 0;
    const kind = day < d.today ? 'past' : day === d.today ? 'today' : '';
    cells += `<div class="cell ${kind} ${day === sel ? 'sel' : ''}" style="height:${100 / rows}%" data-act="msel" data-day="${day}">
      <span class="n">${dd.getDate()}</span>${ms.slice(0, 2).map(m => `<span class="m">${esc(m.title)}</span>`).join('')}
      ${ts.length ? `<span>${ts.length} planned</span>` : ''}
      ${f > 0 ? `<div class="meter"><i style="width:${Math.min(100, f / goal * 100)}%"></i></div>` : ''}</div>`;
  }
  let side = '';
  if (sel) {
    const its = itemsFor(sel), sd = parse(sel);
    side = `<div class="side" style="padding-top:12px"><span class="cap">${DOW[sd.getDay()]} ${sd.getDate()}</span>
      <div style="margin-top:8px">${its.length ? its.map(itemHTML).join('') : '<div class="empty">Nothing planned</div>'}</div>
      <div class="foot" style="margin-top:10px"><input id="moadd" data-addday="${sel}" placeholder="+ Add a task, Enter"></div>
      <div class="btns" style="margin-top:18px"><button class="btn main" data-act="openday" data-day="${sel}">Open this day</button></div></div>`;
  }
  return `<div class="cal"><section class="mo"><h1>${MON[mon]}</h1>
      <div class="sub" style="margin-top:4px">The bar under a day is focus time against your ${dur(goal)} goal.</div>
      <div class="mhead">${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(x => `<span>${x}</span>`).join('')}</div>
      <div class="mgrid">${cells}</div></section>${side}</div>`;
}


/* ---------- timer tick ---------- */
function tick() {
  const t = S.timer; if (!t) return;
  const rem = t.running ? Math.max(0, t.end - Date.now() / 1000) : t.remaining;
  const c = $('#clock');
  if (c) { const r = Math.ceil(rem); c.textContent = `${Math.floor(r / 60)}:${pad(r % 60)}`; }
  const arc = $('#arc1');
  if (arc) {
    const p = t.just_done ? 1 : clamp(1 - rem / t.total, 0, 1), C = Number(arc.dataset.c);
    arc.setAttribute('stroke-dashoffset', C * (1 - p)); arc.setAttribute('opacity', p > 0.002 ? 1 : 0);
  }
  const nl = $('#nowline');
  if (nl) { nl.style.top = y(nowMin()) + 'px'; $('#nowlbl').textContent = hm(nowMin()); }
  if (t.running && rem <= 0 && !S.settling) { S.settling = true; setTimeout(() => load().finally(() => { S.settling = false; }), 400); }
}

/* ---------- clicks, keys, drags ---------- */
async function step(n) {
  if (S.view === 'day') S.date = addDays(S.date, n);
  else if (S.view === 'week') S.date = addDays(S.date, 7 * n);
  else { const d = parse(S.date); d.setDate(1); d.setMonth(d.getMonth() + n); S.date = iso(d); }
  S.sel = null; S.msel = null; load();
}
const ACT = {
  tab: el => { S.tab = el.dataset.v; S.sel = null; S.adding = null; S.habit = null; S.goal = null; if (!S.date) S.date = S.today; load(); },
  view: el => { const v = el.dataset.v; if (S.view === v) S.date = S.today; S.view = v; S.sel = null; S.msel = null; S.adding = null; load(); },
  step: el => step(Number(el.dataset.v)),
  start: async el => {
    const x = findTask(el.dataset.id);
    if (!x || x.done || running(x.id)) return;
    await call('timer_start', x.id); load();
  },
  toggle: async el => { const x = findTask(el.dataset.id); if (!x) return; await call('update_task', x.id, { done: !x.done }); load(); },
  untime: async el => { S.sel = null; await call('update_task', Number(el.dataset.id), { start_min: null, end_min: null }); load(); },
  del: el => {
    const x = findTask(el.dataset.id);
    if (x) return twice(el, async () => { closeMenu(); await call('delete_task', x.id); load(); }, el.closest('#menu') ? 'Click again to delete' : 'Delete');
  },
  go: async () => { await call(S.timer.running ? 'timer_pause' : 'timer_start'); load(); },
  reset: async () => { await call('timer_reset'); load(); },
  mode: async el => { await call('timer_start', null, el.dataset.v); load(); },
  tickoff: async () => { await call('update_task', S.timer.task_id, { done: true }); await call('timer_dismiss'); load(); },
  dismiss: async () => { await call('timer_dismiss'); load(); },
  lenedit: el => {                       // click the idle time: type a new length in place
    if (S.timer.running || $('#clockin')) return;
    const inp = document.createElement('input');
    inp.id = 'clockin'; inp.className = 'clock clockin'; inp.value = Math.round(S.timer.total / 60);
    inp.setAttribute('inputmode', 'numeric'); inp.maxLength = 5; inp.spellcheck = false;
    el.replaceWith(inp); $('#ofmin').textContent = 'minutes · Enter'; inp.focus(); inp.select();
    inp.addEventListener('blur', () => commitClock(inp, true), { once: true });
  },
  update: async el => {
    el.textContent = 'Restarting…'; el.disabled = true;
    if (!(await call('update_now').catch(() => false))) { el.textContent = 'Update failed · try later'; }
  },
  tlen: el => { S.tlen = Number(el.dataset.id); S.refocus = '#tlenin'; render(); },
  note: el => { const id = Number(el.dataset.id); S.note = S.note === id ? null : id; render(); },
  unlabel: async () => { await call('timer_unlabel'); S.refocus = '#focusname'; load(); },
  movecarry: async () => { await call('move_to_today'); load(); },
  openday: el => { S.tab = 'calendar'; S.view = 'day'; S.date = el.dataset.day; S.sel = null; load(); },
  msel: el => { S.msel = el.dataset.day; render(); },
  adding: el => { S.adding = el.dataset.day; render(); },
  tracking: async el => { await call('set_setting', 'tracking', el.dataset.v === '1'); load(); },
  popcancel: () => closePop(),
  popadd: () => popAdd(),
};
/* ---------- timer length: type it, or scroll the ring ---------- */
async function commitClock(inp, fromBlur) {
  const m = parseMin(inp.value), [lo, hi] = LIMIT[S.timer.mode];
  if (!inp.dataset.cancel && m >= lo && m <= hi && m !== Math.round(S.timer.total / 60)) {
    await call('timer_length', m).catch(() => {});
  }
  load();
}
function previewLen(m) {                       // show the new length at once, save it a moment later
  S.timer.total = S.timer.remaining = m * 60; S.timer.left = null;
  const of = $('#ofmin'); if (of) of.textContent = `of ${m} min${S.timer.mode !== 'focus' ? ' break' : ''}`;
  tick();
}
document.addEventListener('wheel', e => {
  const ring = e.target.closest('.todaytab .ring');
  const chip = e.target.closest('.row .len');
  if (ring && S.timer && !S.timer.running && !S.timer.just_done && !$('#clockin')) {
    e.preventDefault();
    const [lo, hi] = LIMIT[S.timer.mode], step = e.shiftKey ? 5 : 1;
    const m = clamp(Math.round(S.timer.total / 60) + (e.deltaY < 0 ? step : -step), lo, hi);
    if (m === Math.round(S.timer.total / 60)) return;
    previewLen(m); S.busy = true;
    clearTimeout(S.wheelT);
    S.wheelT = setTimeout(async () => { await call('timer_length', m).catch(() => {}); S.busy = false; load(); }, 450);
  } else if (chip) {
    e.preventDefault();
    const x = findTask(chip.dataset.id); if (!x) return;
    const base = S.wheelTask && S.wheelTask.id === x.id ? S.wheelTask.m : (x.focus_min || S.settings.focus);
    const m = clamp(base + (e.deltaY < 0 ? 5 : -5), 5, 180);
    S.wheelTask = { id: x.id, m }; chip.textContent = m + 'm'; chip.classList.add('set'); S.busy = true;
    clearTimeout(S.wheelT);
    S.wheelT = setTimeout(async () => {
      await call('update_task', x.id, { focus_min: m }).catch(() => {}); S.wheelTask = null; S.busy = false; load();
    }, 450);
  }
}, { passive: false });
document.addEventListener('focusout', e => {            // description saves when you click away
  if (e.target.id !== 'noteta') return;
  const t = findTask(e.target.dataset.id), v = e.target.value.trim();
  if (!t || v === (t.notes || '')) return;
  t.notes = v; call('update_task', t.id, { notes: v }).catch(() => {});
});
document.addEventListener('focusout', async e => {
  if (e.target.id !== 'tlenin') return;
  const inp = e.target, id = Number(inp.dataset.id), v = inp.value.trim();
  S.tlen = null;
  if (!inp.dataset.cancel) {
    const m = v === '' ? null : parseMin(v);
    if (m === null || (m >= 1 && m <= 180)) await call('update_task', id, { focus_min: m }).catch(() => {});
  }
  load();
});

/* ---------- "Focusing on": a name, or one of today's tasks ---------- */
function drawSugg() {
  const box = $('#fsugg'); if (!box) return;
  box.innerHTML = (S.sugg || []).map((x, i) =>
    `<button class="${i === S.sugI ? 'on' : ''}" data-act="start" data-id="${x.id}">${esc(x.title)}</button>`).join('');
}
document.addEventListener('input', e => {
  if (e.target.id !== 'focusname') return;
  const q = e.target.value.trim().toLowerCase();
  S.sugg = q ? (S.d.tasks || []).filter(x => !x.done && x.title.toLowerCase().includes(q)).slice(0, 3) : [];
  S.sugI = -1; drawSugg();
});

document.addEventListener('click', e => {
  if (S.pop && !e.target.closest('#pop') && !e.target.closest('#plan')) closePop();
  if (S.armed && !e.target.closest('.armed')) S.armed();
  const el = e.target.closest('[data-act]');
  if (el && ACT[el.dataset.act]) {
    e.stopPropagation();
    if (el.classList.contains('row') || el.classList.contains('it')) {   // wait a moment: a double-click means rename
      const act = ACT[el.dataset.act];
      clearTimeout(S.clickT); S.clickT = setTimeout(() => Promise.resolve(act(el)).catch(() => {}), 250); return;
    }
    Promise.resolve(ACT[el.dataset.act](el)).catch(() => {});
    return;
  }
  if (S.sel && !e.target.closest('#plan')) { S.sel = null; render(); }   // plan clicks are handled by its pointer code
});
document.addEventListener('dblclick', e => { const t = e.target.closest('[data-edit]'); if (t) renameEl(t); });
function renameEl(t) {                                  // rename in place
  clearTimeout(S.clickT);
  const x = findTask(t.dataset.edit); if (!x || t.isContentEditable) return;
  t.contentEditable = 'true'; t.classList.add('editing'); t.focus();
  document.getSelection().selectAllChildren(t);
  let done = false;
  const save = async ok => {
    if (done) return; done = true;
    t.contentEditable = 'false'; t.classList.remove('editing');
    const v = t.textContent.trim();
    if (ok && v && v !== x.title) await call('update_task', x.id, { title: v }).catch(() => {});
    load();
  };
  t.addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); save(true); } if (ev.key === 'Escape') save(false); });
  t.addEventListener('blur', () => save(true), { once: true });
}
document.addEventListener('keydown', async e => {
  if (e.target.id === 'focusname') {
    const list = S.sugg || [];
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && list.length) {
      e.preventDefault();
      S.sugI = ((S.sugI ?? -1) + (e.key === 'ArrowDown' ? 1 : -1) + list.length + 1) % (list.length + 1);
      if (S.sugI === list.length) S.sugI = -1;
      drawSugg(); return;
    }
    if (e.key === 'Enter' && e.target.value.trim()) {
      const v = e.target.value.trim();
      const exact = list.find(x => x.title.toLowerCase() === v.toLowerCase());
      const pick = S.sugI >= 0 ? list[S.sugI] : exact;
      e.target.value = ''; S.sugg = []; S.sugI = -1; e.target.blur();
      await (pick ? call('timer_start', pick.id) : call('timer_label', v)).catch(() => {});
      load(); return;
    }
    if (e.key === 'Escape') { e.target.value = ''; S.sugg = []; drawSugg(); e.target.blur(); return; }
  }
  if (e.target.id === 'clockin') {
    if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); }
    if (e.key === 'Escape') { e.target.dataset.cancel = '1'; e.target.blur(); }
    return;
  }
  if (e.target.id === 'tlenin') {
    if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); }
    if (e.key === 'Escape') { e.target.dataset.cancel = '1'; e.target.blur(); }
    return;
  }
  const inp = e.target.closest && e.target.closest('input[data-addday]');
  if (inp && e.key === 'Enter' && inp.value.trim()) {
    const day = inp.dataset.addday, v = inp.value.trim();
    inp.value = '';
    await call('add_task', v, day).catch(() => {});
    S.refocus = inp.id === 'wkadd' || inp.id === 'moadd' ? '#' + inp.id : `#add-${day}`;
    load(); return;
  }
  if (inp && e.key === 'Escape') { inp.value = ''; inp.blur(); if (S.adding) { S.adding = null; render(); } return; }
  if (e.target.matches && e.target.matches('input, [contenteditable=true]')) return;
  if (e.key === 'Escape') { if (S.armed) S.armed(); else if (S.pop) closePop(); else if (S.sel) { S.sel = null; render(); } }
  if ((e.key === 'Delete' || e.key === 'Backspace') && S.sel && S.tab === 'calendar') {
    const id = S.sel; S.sel = null;
    await call('update_task', id, { start_min: null, end_min: null }).catch(() => {}); load();
  }
});
document.addEventListener('dragstart', e => {
  const r = e.target.closest && e.target.closest('[draggable=true]');
  if (!r) return;
  e.dataTransfer.setData('text/plain', r.dataset.id);
  e.dataTransfer.effectAllowed = 'move';
});

/* ---------- start ---------- */
let started = false;
async function boot() {
  if (started) return; started = true;
  const acct = await call('account_status').catch(() => null);
  if (acct && !acct.user && !acct.skipped) await loginGate(acct);
  await load();
  S.date = S.today;
  setInterval(tick, 250);
  setInterval(() => {
    const typing = document.activeElement && document.activeElement.matches('input, textarea, [contenteditable=true]');
    if (!typing && !S.pop && !S.busy && !S.modal && !S.menu && !S.armed) load().catch(() => {});
  }, 15000);
}
if (window.pywebview && window.pywebview.api) boot();
else {
  window.addEventListener('pywebviewready', boot);
  setTimeout(() => { if (!window.pywebview) boot(); }, 300);
}
