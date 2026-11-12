'use strict';
/* Habits, Goals, Progress, the forms, Settings, and the right-click goal menu.
   Loaded after app.js and shares its state (S), helpers and the ACT table. */

const MORE_TABS = ['habits', 'goals', 'progress'];
const LETTER = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];               // Monday first
const DNAME = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const wd = s => (parse(s).getDay() + 6) % 7;                       // 0 = Monday
const num = n => Number(n).toLocaleString('en-US', { maximumFractionDigits: 1 });
const dayMon = s => { const d = parse(s); return `${d.getDate()} ${MON[d.getMonth()].slice(0, 3)}`; };
const monDay = s => { const d = parse(s); return `${MON[d.getMonth()].slice(0, 3)} ${d.getDate()}`; };
const lastOfMonth = s => { const d = parse(s); return iso(new Date(d.getFullYear(), d.getMonth() + 1, 0)); };
ICON.plus = '<svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M7 2v10M2 7h10"/></svg>';
ICON.gear = '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="2.2"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" stroke-linecap="round"/></svg>';
ICON.bigcheck = '<svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="#161618" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.2l2.3 2.3 4.7-5"/></svg>';

Object.assign(S, { habit: null, prog: 'week', pdate: null, modal: null, menu: null, goalNames: {} });

/* ---------- loading ---------- */
function progRange() {
  const d = S.pdate || S.today;
  if (S.prog === 'week') { const a = monday(d); return [a, addDays(a, 6)]; }
  if (S.prog === 'month') { const a = d.slice(0, 8) + '01'; return [a, lastOfMonth(a)]; }
  return [d.slice(0, 4) + '-01-01', d.slice(0, 4) + '-12-31'];
}
async function moreLoad() {
  if (S.tab === 'habits') {
    if (S.habit) {
      try { return await api.habit_detail(S.habit); } catch (e) { S.habit = null; }
    }
    return call('habits_data');
  }
  if (S.tab === 'goals') {
    if (S.goal) {
      try { return await api.goal_detail(S.goal); } catch (e) { S.goal = null; }
    }
    return call('goals_data');
  }
  if (S.tab === 'vision') return call('vision_data');
  if (S.prog === 'year') return call('year_data', (S.pdate || S.today).slice(0, 4));
  const [a, b] = progRange();
  return call('progress_data', a, b);
}
function noteGoals(d) {
  if (d && Array.isArray(d.goals)) S.goalNames = Object.fromEntries(d.goals.filter(g => !g.status || g.status === 'active' || g.status === 'paused').map(g => [g.id, g.title]));
}

function moreHTML() {
  if (S.tab === 'habits') return S.habit && S.d.habit ? habitDetailHTML() : habitsHTML();
  if (S.tab === 'goals') return S.goal && S.d.goal ? goalDetailHTML() : goalsHTML();
  if (S.tab === 'vision') return visionHTML();
  return S.prog === 'year' ? yearHTML() : S.prog === 'month' ? progMonthHTML() : progWeekHTML();
}

function moreTop() {
  if (S.tab === 'progress') {
    const [a, b] = progRange();
    let date;
    if (S.prog === 'week') {
      const A = parse(a), B = parse(b);
      date = A.getMonth() === B.getMonth() ? `${A.getDate()} – ${B.getDate()} ${MON[B.getMonth()].slice(0, 3)}`
        : `${dayMon(a)} – ${dayMon(b)}`;
    } else if (S.prog === 'month') { const A = parse(a); date = `${MON[A.getMonth()]} ${A.getFullYear()}`; }
    else date = a.slice(0, 4);
    const right = `<div class="seg">${[['week', 'Week'], ['month', 'Month'], ['year', 'Year']].map(([v, l]) =>
      `<button class="${S.prog === v ? 'on' : ''}" data-act="prog" data-v="${v}">${l}</button>`).join('')}</div>
      <button class="arrow" data-act="pstep" data-v="-1" title="Back">${ICON.left}</button>
      <button class="arrow" data-act="pstep" data-v="1" title="Next">${ICON.right}</button>`;
    return { date, right };
  }
  const f = S.d && S.d.focused !== undefined ? `<span class="goal"><b>${dur(S.d.focused)}</b> of ${dur(S.settings.goal_min)}</span>` : '';
  return { date: shortDay(S.today), right: f };
}

/* ---------- Habits ---------- */
function habitSub(h) {
  if (h.paused) return 'Paused';
  const st = h.streak ? `${h.streak} day streak` : '';
  if (h.today_done) return st;
  if (!h.due_today) return st ? `${st} · day off today` : 'Day off today';
  return st || 'Tap today to tick';
}
function dotHTML(h, c, i) {
  const today = i === 6, can = !h.paused && !['before', 'future'].includes(c.state);
  const cls = `dot32 ${c.state} ${today ? 'today' : ''}`;
  const tip = `${shortDay(c.day)}${c.state === 'done' ? ', done' : c.state === 'off' ? ', day off' : ''}`;
  return can ? `<button class="${cls}" title="${tip}" data-act="htick" data-id="${h.id}" data-day="${c.day}" data-on="${c.state === 'done' ? 0 : 1}">${c.state === 'done' && today ? ICON.bigcheck : ''}</button>`
    : `<span class="${cls}"></span>`;
}
function habitsHTML() {
  const hs = S.d.habits, active = hs.filter(h => !h.paused);
  const due = active.filter(h => h.due_today || h.today_done), done = due.filter(h => h.today_done).length;
  const days = Array.from({ length: 7 }, (_, i) => addDays(S.today, i - 6));
  const head = !hs.length ? `<div><div class="bigt">Habits</div><div class="sub">Small things you do on set days.</div></div>`
    : due.length ? `<div><div class="bigt">${done} of ${due.length}</div><div class="sub">habits done today</div></div>`
      : `<div><div class="bigt">Rest day</div><div class="sub">No habits planned today</div></div>`;
  const labels = hs.length ? `<div class="dlabels">${days.map((d, i) => `<span class="${i === 6 ? 'on' : ''}">${LETTER[wd(d)]}</span>`).join('')}</div>` : '';
  const rows = hs.map(h => `<div class="hrow ${h.paused ? 'paused' : ''}">
      <div class="info" data-act="hopen" data-id="${h.id}"><b>${esc(h.title)}</b><small>${habitSub(h)}</small></div>
      <div class="cells">${h.week.map((c, i) => dotHTML(h, c, i)).join('')}</div></div>`).join('');
  const empty = hs.length ? '' : `<div class="empty2">Add your first one, like "English, 45 min" or "Workout".<br>Tick it each day you do it. Days you skip on purpose never break the streak.</div>`;
  return `<div class="page"><div class="col720"><div class="head2">${head}${labels}</div>
    ${empty}<div class="hlist">${rows}</div>
    <button class="addline" data-act="newhabit">${ICON.plus}<span>Add a habit</span></button></div></div>`;
}
function daysText(days) {
  if (days.length === 7) return 'Every day';
  if (days.join() === '0,1,2,3,4') return 'Weekdays';
  if (days.join() === '5,6') return 'Weekends';
  return days.map(d => DNAME[d]).join(', ');
}
function habitDetailHTML() {
  const h = S.d.habit;
  const feeds = h.goal ? ` · feeds <span style="color:#fff;font-weight:600">${esc(h.goal)}</span>` : '';
  let note = '';
  if (h.streak >= 3 && h.streak >= h.best) {
    const more = !h.today_done && h.due_today ? ` Tick today to make it ${h.streak + 1}.` : '';
    note = `<div class="note"><b>Your best run yet</b><span>${h.streak} days in a row.${more}</span></div>`;
  }
  const grid = `<div class="grid12"><div class="wk hdr"><span class="wl"></span>${LETTER.map(l => `<span>${l}</span>`).join('')}<span class="wc"></span></div>
    ${h.weeks.map(w => `<div class="wk"><span class="wl">${monDay(w.start)}</span>${w.cells.map((c, i) => {
      const day = addDays(w.start, i), today = day === S.today, can = !h.paused && !['before', 'future'].includes(c);
      const cls = `sq ${c} ${today ? 'today' : ''}`;
      return can ? `<button class="${cls}" title="${shortDay(day)}" data-act="htick" data-id="${h.id}" data-day="${day}" data-on="${c === 'done' ? 0 : 1}"></button>` : `<span class="${cls}"></span>`;
    }).join('')}<span class="wc">${w.planned ? `${w.kept}/${w.planned}` : ''}</span></div>`).join('')}</div>`;
  return `<div class="page"><div class="hd"><div class="l">
      <div style="display:flex;flex-direction:column;gap:10px">
        <button class="back" data-act="hback">${ICON.left}<span>Habits</span></button>
        <div class="bigt">${esc(h.title)}</div>
        <span class="sub" style="font-size:14px">${daysText(h.days)}${feeds}${h.paused ? ' · paused' : ''}</span></div>
      <div class="stats"><div><b>${h.streak}</b><span>day streak now</span></div><div><b>${h.best}</b><span>best streak</span></div>
        <div><b>${h.rate == null ? '–' : h.rate + '%'}</b><span>last 12 weeks</span></div></div>
      ${note}
      <div class="links"><button data-act="hedit">Edit habit</button><button data-act="hpause">${h.paused ? 'Resume' : 'Pause'}</button><button data-act="hdel">Delete</button></div>
    </div>${grid}</div></div>`;
}

/* ---------- Progress ---------- */
function psumHTML(p, word) {
  const d = p.focus - p.prev_focus, past = p.b < p.today;
  const vs = past ? `vs the ${word} before` : `vs same day last ${word}`;
  const delta = p.prev_focus < 1 && p.focus < 1 ? '' : Math.abs(d) < 1 ? ` · same as last ${word}`
    : d > 0 ? ` · <span class="up">+${dur(d)}</span> ${vs}` : ` · ${dur(-d)} less ${vs}`;
  const kept = p.habits.pct == null ? '–' : p.habits.pct + '%';
  return `<div class="psum"><div><div class="n">${dur(p.focus)}</div><div class="sub">focused this ${word}${delta}</div></div>
    <div class="kpis"><div><b>${p.tasks_done}</b><span>tasks done</span></div><div><b>${kept}</b><span>habits kept</span></div>
    <div><b>${p.hit} of ${p.past_days}</b><span>days hit ${dur(p.goal_min)} goal</span></div></div></div>`;
}
function progWeekHTML() {
  const p = S.d, max = Math.max(p.goal_min * 1.33, ...p.days.map(x => x.focus)), goalY = p.goal_min / max * 96;
  const cols = p.days.map((x, i) => {
    const today = x.day === p.today, future = x.day > p.today;
    const items = [...x.done.map(t => `<span>${esc(t)}</span>`), ...(future || today ? x.open.map(t => `<span class="open">${esc(t)}</span>`) : [])];
    const shown = items.slice(0, 6).join('') + (items.length > 6 ? `<span class="open">+ ${items.length - 6} more</span>` : '');
    return `<div class="pday ${today ? 'today' : ''}" data-act="openday" data-day="${x.day}" title="Open ${shortDay(x.day)} in Calendar">
      <div class="dh"><b>${today ? 'Today' : DNAME[i]}</b><span>${parse(x.day).getDate()}</span></div>
      <div class="pbar"><i style="height:${future ? 0 : Math.min(96, x.focus / max * 96)}px;${today ? 'background:#fff' : ''}"></i><u style="bottom:${goalY}px"></u></div>
      <span class="ft ${future || x.focus < 1 ? 'none' : ''}">${future ? '–' : x.focus < 1 ? 'No focus' : dur(x.focus)}</span>
      <div class="ts">${shown}</div></div>`;
  }).join('');
  return `<div class="page prog">${psumHTML(p, 'week')}<div class="pdays">${cols}</div></div>`;
}
const heatA = f => 0.06 + 0.79 * Math.min(1, f / 240);
function progMonthHTML() {
  const p = S.d, lead = wd(p.a), cells = [];
  for (let i = 0; i < lead; i++) cells.push('<span class="hc blank"></span>');
  for (const x of p.days) {
    const future = x.day > p.today, a = future ? 0.03 : heatA(x.focus);
    cells.push(`<button class="hc ${a > 0.55 ? 'dark' : ''} ${x.day === p.today ? 'today' : ''}" style="background:rgba(255,255,255,${a.toFixed(2)})"
      data-act="openday" data-day="${x.day}" title="${shortDay(x.day)}${future ? '' : ' · ' + dur(x.focus) + ' focused'}">${parse(x.day).getDate()}</button>`);
  }
  while (cells.length % 7) cells.push('<span class="hc blank"></span>');
  const rows = [];
  for (let i = 0; i < cells.length; i += 7) rows.push(`<div class="r">${cells.slice(i, i + 7).join('')}</div>`);
  const habits = p.habits.habits.filter(h => h.planned).map(h => `<div class="kv q"><span>${esc(h.title)}</span><b>${h.kept} of ${plural(h.planned, 'day')}</b></div>`).join('');
  const best = p.best ? `<div class="sec"><span class="cap">Best day</span><div style="font-weight:600;font-size:14px;margin-top:8px">${shortDay(p.best.day)} · ${dur(p.best.focus)} focused</div></div>` : '';
  return `<div class="page prog">${psumHTML(p, 'month')}<div class="pmo"><div>
      <div class="heat"><div class="r">${DNAME.map(d => `<span>${d}</span>`).join('')}</div>${rows.join('')}</div>
      <div class="legend">Less ${[0, 60, 120, 180, 240].map(f => `<i style="background:rgba(255,255,255,${heatA(f).toFixed(2)})"></i>`).join('')} 4h+ focus</div></div>
    <div class="mside"><span class="cap">Habits this month</span>${habits || '<div class="quiet">No habits yet.</div>'}${best}</div></div></div>`;
}
function yearHTML() {
  const p = S.d, max = Math.max(1, ...p.months), nowM = Number(p.today.slice(5, 7)) - 1, nowY = Number(p.today.slice(0, 4));
  const kept = p.habits.pct == null ? '–' : p.habits.pct + '%';
  const bars = p.months.map((m, i) => {
    const future = p.year > nowY || (p.year === nowY && i > nowM), now = p.year === nowY && i === nowM;
    return `<div class="ym ${future || m < 1 ? 'future' : ''} ${now ? 'now' : ''}" data-act="pmonth" data-m="${i}" title="Open ${MON[i]}">
      <b>${future || m < 1 ? '' : dur(m)}</b><i class="b" style="height:${future ? 2 : Math.max(2, m / max * 200)}px"></i><small>${MON[i].slice(0, 3)}</small></div>`;
  }).join('');
  return `<div class="page prog"><div class="psum"><div><div class="n">${dur(p.focus)}</div><div class="sub">focused in ${p.year}</div></div>
    <div class="kpis"><div><b>${num(p.tasks_done)}</b><span>tasks done</span></div><div><b>${kept}</b><span>habits kept</span></div>
    <div><b>${p.hit}</b><span>days hit ${dur(p.goal_min)} goal</span></div></div></div><div class="yr">${bars}</div></div>`;
}

/* ---------- forms (modal) ---------- */
function openModal(m) { S.modal = m; renderModal(); }
function closeModal() { const was = S.modal; S.modal = null; renderModal(); if (was && (was.kind === 'settings' || was.kind === 'rules')) load(); }
function goalOptions(sel) {
  const gs = Object.entries(S.goalNames);
  return `<option value="">None</option>${gs.map(([id, t]) => `<option value="${id}" ${Number(id) === Number(sel) ? 'selected' : ''}>${esc(t)}</option>`).join('')}`;
}
function renderModal() {
  const box = $('#modal'), m = S.modal;
  if (!m) { box.classList.remove('show'); box.innerHTML = ''; return; }
  let h = '';
  if (m.kind === 'habit') {
    const n = m.days.length;
    h = `<h2>${m.id ? 'Edit habit' : 'New habit'}</h2>
      <div class="f"><label>Name</label><input data-k="title" value="${esc(m.title)}" placeholder="Workout" id="mfirst"></div>
      <div class="f"><label>Which days</label><div class="wd">${LETTER.map((l, i) => `<button class="${m.days.includes(i) ? 'on' : ''}" data-act="mday" data-v="${i}">${l}</button>`).join('')}</div>
        <span class="help">${n === 7 ? 'Every day' : n ? `${plural(n, 'day')} a week · off-days don't break the streak` : 'Pick at least one day'}</span></div>
      <div class="f"><label>Feeds a goal (optional)</label><select data-k="goal_id">${goalOptions(m.goal_id)}</select></div>
      <div class="btns"><button class="btn" data-act="mclose">Cancel</button><button class="btn main" data-act="msave">${m.id ? 'Save' : 'Add habit'}</button></div>`;
  } else if (m.kind === 'goal') {
    h = goalFormHTML(m);
  } else if (m.kind === 'settings') {
    const st = S.settings;
    const stepper = (k, label, fmt) => `<div class="set"><span>${label}</span><div class="stepper"><button data-act="sstep" data-k="${k}" data-v="-1">−</button><b>${fmt(st[k])}</b><button data-act="sstep" data-k="${k}" data-v="1">+</button></div></div>`;
    const sw = (k, label, on) => `<div class="set"><span>${label}</span><button class="sw ${on ? 'on' : ''}" data-act="sswitch" data-k="${k}" title="${on ? 'On' : 'Off'}"></button></div>`;
    h = `<h2>Settings</h2>
      ${accountRows(m.acct)}
      ${stepper('goal_min', 'Daily focus goal', dur)}${stepper('focus', 'Focus length', v => v + ' min')}
      ${stepper('short', 'Short break', v => v + ' min')}${stepper('long', 'Long break', v => v + ' min')}
      ${sw('tracking', 'Track apps automatically', st.tracking)}
      <div class="set"><span>Sounds</span><div style="display:flex;align-items:center;gap:12px">
        ${st.sounds ? '<button class="more" data-act="msounds">Choose ›</button>' : ''}
        <button class="sw ${st.sounds ? 'on' : ''}" data-act="sswitch" data-k="sounds" title="${st.sounds ? 'On' : 'Off'}"></button></div></div>
      <div class="set"><span>App categories</span><button class="more" data-act="mrules">Edit ›</button></div>
      ${sw('autostart', 'Start with Windows', m.autostart)}
      ${m.hidden ? `<div class="set"><span>Hidden calendar events</span><button class="more" data-act="showall">${m.hidden} · Show all</button></div>` : ''}
      ${S.upd && S.upd.current ? `<div class="help" style="margin-top:14px">Nook ${esc(S.upd.current)}</div>` : ''}
      <div class="btns"><button class="btn main" data-act="mclose">Done</button></div>`;
  } else if (m.kind === 'sounds') {
    const pick = S.settings.sound_pick || {};
    const lib = [...(m.lib || []), ['off', 'None']], nameOf = v => (lib.find(x => x[0] === v) || [, v])[1];
    h = `<h2>Sounds</h2>
      ${SOUND_MOMENTS.map(([k, label]) => `<div class="sndrow ${m.open === k ? 'open' : ''}">
        <button class="sndhead" data-act="sopen" data-k="${k}"><span>${label}</span><b>${esc(nameOf(pick[k]))}</b>${ICON_CHEV}</button>
        ${m.open === k ? `<div class="sndlist">${lib.map(([v, l]) => `<button class="${pick[k] === v ? 'on' : ''}" data-act="spick" data-k="${k}" data-v="${v}">
          <span>${esc(l)}</span>${pick[k] === v ? ICON_TICK : ''}</button>`).join('')}</div>` : ''}</div>`).join('')}
      <div class="btns"><button class="btn main" data-act="msettings">Done</button></div>`;
  } else if (m.kind === 'rules') {
    h = `<h2>App categories</h2><div class="help" style="margin:-10px 0 14px">An app or site name. Anything not listed counts as other.</div>
      <div class="rules">${m.rules.map(([name, cat], i) => `<div class="rule"><span>${esc(name)}</span>
        <div class="seg3">${[['focus', 'Focus'], ['distracted', 'Distracted'], ['other', 'Other']].map(([v, l]) =>
          `<button class="${cat === v ? 'on' : ''} ${v === 'distracted' ? 'bad' : ''}" data-act="rcat" data-i="${i}" data-v="${v}">${l}</button>`).join('')}</div>
        <button class="x" data-act="rdel" data-i="${i}" title="Remove">${ICON.x}</button></div>`).join('')}</div>
      <div class="radd"><input id="radd" placeholder="Add an app or site, press Enter"></div>
      <div class="btns"><button class="btn" data-act="msettings">Back</button><button class="btn main" data-act="rsave">Save</button></div>`;
  }
  const keep = document.activeElement && document.activeElement.closest('#modal') ? document.activeElement.dataset.k : null;
  box.innerHTML = `<div class="card">${h}</div>`;
  box.classList.add('show');
  const f = keep ? box.querySelector(`[data-k="${keep}"]`) : (m.fresh && box.querySelector('#mfirst'));
  if (f) { f.focus(); if (f.setSelectionRange && f.type === 'text') f.setSelectionRange(f.value.length, f.value.length); }
  m.fresh = false;
}
document.getElementById('modal').addEventListener('input', e => {
  const k = e.target.dataset.k; if (k && S.modal) S.modal[k] = e.target.value;
});
document.getElementById('modal').addEventListener('mousedown', e => { if (e.target.id === 'modal') closeModal(); });
document.getElementById('modal').addEventListener('keydown', e => {
  if (e.key === 'Escape') { e.stopPropagation(); closeModal(); return; }
  if (e.target.id === 'radd' && e.key === 'Enter') {
    const v = e.target.value.trim().toLowerCase();
    if (v && !S.modal.rules.some(r => r[0] === v)) S.modal.rules.unshift([v, 'distracted']);
    renderModal(); const i = $('#radd'); if (i) i.focus(); return;
  }
  if (e.key === 'Enter' && e.target.matches('input[data-k]')) { e.preventDefault(); MORE_ACT.msave(); }
});

async function saveModal() {
  const m = S.modal;
  if (m.kind === 'habit') {
    if (!m.title.trim()) return toast('Give it a name');
    const goal_id = m.goal_id ? Number(m.goal_id) : null;
    if (m.id) await call('update_habit', m.id, { title: m.title, days: m.days, goal_id });
    else await call('add_habit', m.title, m.days, goal_id);
  } else if (m.kind === 'goal') return saveGoal(m);
  closeModal(); load();
}

const ICON_CHEV = '<svg class="chev" width="10" height="10" viewBox="0 0 10 10"><path d="M2.5 4l2.5 2.5L7.5 4" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICON_TICK = '<svg width="12" height="12" viewBox="0 0 12 12"><path d="M2.5 6.3l2.3 2.3 4.7-5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const SOUND_MOMENTS = [['focus_done', 'Focus done', 'when a focus timer ends'],
  ['break_done', 'Break over', 'when a break ends'], ['task_done', 'Task ticked', 'when you tick a task']];
const STEP = { goal_min: [30, 30, 600], focus: [5, 5, 120], short: [1, 1, 30], long: [5, 5, 60] };
const MORE_ACT = {
  hopen: el => { S.habit = Number(el.dataset.id); load(); },
  hback: () => { S.habit = null; load(); },
  htick: async el => { await call('tick_habit', Number(el.dataset.id), el.dataset.day, el.dataset.on === '1'); load(); },
  newhabit: () => openModal({ kind: 'habit', title: '', days: [0, 1, 2, 3, 4, 5, 6], goal_id: '', fresh: true }),
  hedit: () => { const h = S.d.habit; openModal({ kind: 'habit', id: h.id, title: h.title, days: [...h.days], goal_id: h.goal_id || '', fresh: true }); },
  hpause: async () => { const h = S.d.habit; await call('update_habit', h.id, { paused: !h.paused }); load(); },
  hdel: el => twice(el, async () => { await call('delete_habit', S.d.habit.id); S.habit = null; load(); }, 'Click again to delete'),
  mday: el => {
    const i = Number(el.dataset.v), d = S.modal.days;
    S.modal.days = d.includes(i) ? d.filter(x => x !== i) : [...d, i].sort();
    renderModal();
  },
  mdelgoal: el => twice(el, async () => { await call('delete_goal', S.modal.id); S.goal = null; closeModal(); load(); }, 'Click again to delete'),
  mclose: () => closeModal(),
  msave: () => saveModal().catch(() => {}),
  settings: () => openSettings(),
  msettings: () => openSettings(),
  sstep: async el => {
    const k = el.dataset.k, [st, lo, hi] = STEP[k];
    const v = clamp(Number(S.settings[k]) + st * Number(el.dataset.v), lo, hi);
    if (v === S.settings[k]) return;
    S.settings = await call('set_setting', k, v); renderModal();
  },
  sswitch: async el => {
    const k = el.dataset.k;
    if (k === 'autostart') { S.modal.autostart = await call('autostart', !S.modal.autostart); renderModal(); return; }
    S.settings = await call('set_setting', k, !S.settings[k]); renderModal();
  },
  signout: el => twice(el, async () => { await call('sign_out'); location.reload(); }, 'Click again to sign out'),
  gconnect: async () => {
    S.modal.acct = await call('sign_in').catch(() => S.modal.acct); renderModal();
    const poll = setInterval(async () => {
      const x = await call('account_status').catch(() => null);
      if (!x || !S.modal || S.modal.kind !== 'settings') { clearInterval(poll); return; }
      S.modal.acct = x; renderModal();
      if (!x.busy) { clearInterval(poll); if (x.user) load(); }
    }, 1000);
  },
  gsync: async el => {
    el.textContent = 'Syncing…'; el.disabled = true;
    S.modal.acct = await call('sync_calendar').catch(() => S.modal.acct); renderModal();
  },
  msounds: async () => openModal({ kind: 'sounds', lib: await call('sound_styles').catch(() => []), open: 'focus_done' }),
  sopen: el => { S.modal.open = S.modal.open === el.dataset.k ? null : el.dataset.k; renderModal(); },
  spick: async el => {
    const k = el.dataset.k, v = el.dataset.v;
    S.settings = await call('set_setting', 'sound_pick', { ...(S.settings.sound_pick || {}), [k]: v });
    const list = document.querySelector('#modal .sndlist'), top = list ? list.scrollTop : 0;
    renderModal();
    const nl = document.querySelector('#modal .sndlist'); if (nl) nl.scrollTop = top;
    if (v !== 'off') call('preview_sound', k, v).catch(() => {});
  },
  mrules: () => openModal({ kind: 'rules', rules: S.settings.rules.map(r => [...r]) }),
  rcat: el => { S.modal.rules[Number(el.dataset.i)][1] = el.dataset.v; renderModal(); },
  rdel: el => { S.modal.rules.splice(Number(el.dataset.i), 1); renderModal(); },
  rsave: async () => { S.settings = await call('set_setting', 'rules', S.modal.rules); MORE_ACT.msettings(); },
  prog: el => { const v = el.dataset.v; if (S.prog === v) S.pdate = S.today; S.prog = v; load(); },
  pstep: el => {
    const n = Number(el.dataset.v), d = parse(S.pdate || S.today);
    if (S.prog === 'week') d.setDate(d.getDate() + 7 * n);
    else if (S.prog === 'month') { d.setDate(1); d.setMonth(d.getMonth() + n); }
    else { d.setMonth(0, 1); d.setFullYear(d.getFullYear() + n); }
    S.pdate = iso(d); load();
  },
  pmonth: el => { S.prog = 'month'; S.pdate = `${S.d.year}-${pad(Number(el.dataset.m) + 1)}-01`; load(); },
  mgoal: async el => {
    const id = Number(el.dataset.id), v = el.dataset.v === '' ? null : Number(el.dataset.v);
    closeMenu(); await call('update_task', id, { goal_id: v }); load();
  },
  mnewgoal: () => { closeMenu(); ACT.newgoal(); },
  mstart: el => { closeMenu(); return ACT.start(el); },
  mtoggle: el => { closeMenu(); return ACT.toggle(el); },
  muntime: el => { closeMenu(); return ACT.untime(el); },
  mrename: el => { closeMenu(); const t = document.querySelector(`[data-edit="${el.dataset.id}"]`); if (t) renameEl(t); },
  mmove: async el => { const t = findTask(el.dataset.id); closeMenu(); if (!t) return; await call('update_task', t.id, { day: addDays(t.day, 1) }); load(); },
  mdup: async el => { closeMenu(); await call('duplicate_task', Number(el.dataset.id)); load(); },
  mhide: async el => { closeMenu(); await call('hide_event', el.dataset.id); load(); toast('Hidden in Nook. It stays in Google Calendar.'); },
  showall: async () => { await call('show_all_events'); S.modal.hidden = 0; renderModal(); },
};
Object.assign(ACT, MORE_ACT);

/* ---------- right-click: everything you can do with a task, in one small menu ---------- */
function closeMenu() { S.menu = null; const m = $('#menu'); m.classList.remove('show'); m.innerHTML = ''; }
document.addEventListener('contextmenu', e => {
  const meet = e.target.closest('[data-meet]');
  const el = meet ? null : e.target.closest('.row[data-id], .blk.task[data-id], .it[data-id]');
  if (!meet && !el) return;
  e.preventDefault();
  const m = $('#menu');
  if (meet) {
    m.innerHTML = `<button data-act="mhide" data-id="${esc(meet.dataset.meet)}"><i></i>Hide in Nook</button><span class="mnote">It stays in your Google Calendar.</span>`;
  } else {
    const t = findTask(el.dataset.id); if (!t) return;
    const gs = Object.entries(S.goalNames);
    const b = (act, label) => `<button data-act="${act}" data-id="${t.id}"><i></i>${label}</button>`;
    m.innerHTML = `${!t.done && !running(t.id) ? b('mstart', 'Start focus') : ''}${b('mtoggle', t.done ? 'Not done' : 'Done')}${b('mrename', 'Rename')}<hr>
      ${b('mmove', 'Move to tomorrow')}<label class="mdate"><i></i><span>Move to</span><input type="date" data-mdate="${t.id}" value="${t.day}"></label>
      ${b('mdup', 'Duplicate')}${t.start_min != null ? b('muntime', 'Remove time') : ''}<hr>
      <span class="cap">Counts toward</span>${gs.length ? gs.map(([id, title]) =>
        `<button data-act="mgoal" data-id="${t.id}" data-v="${id}"><i>${Number(id) === t.goal_id ? '&#10003;' : ''}</i>${esc(title)}</button>`).join('')
        + `<button data-act="mgoal" data-id="${t.id}" data-v=""><i>${t.goal_id ? '' : '&#10003;'}</i><span class="q">No goal</span></button>`
        : `<button data-act="mnewgoal"><i>+</i>New goal</button>`}<hr>
      <button class="mdel" data-act="del" data-id="${t.id}"><i></i>Delete</button>`;
  }
  m.classList.add('show');
  m.style.left = Math.max(8, Math.min(e.clientX, innerWidth - m.offsetWidth - 8)) + 'px';
  m.style.top = Math.max(8, Math.min(e.clientY, innerHeight - m.offsetHeight - 8)) + 'px';
  S.menu = 1;
});
document.addEventListener('change', async e => {
  const id = e.target.dataset && e.target.dataset.mdate; if (!id || !e.target.value) return;
  closeMenu(); await call('update_task', Number(id), { day: e.target.value }); load();
});
document.addEventListener('mousedown', e => { if (S.menu && !e.target.closest('#menu')) closeMenu(); }, true);
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (S.menu) { e.stopPropagation(); closeMenu(); } else if (S.modal) { e.stopPropagation(); closeModal(); }
}, true);

/* ---------- account: sign-in screen + settings rows ---------- */
async function openSettings() {
  const [a, acct, hidden] = await Promise.all([call('autostart').catch(() => false), call('account_status').catch(() => null), call('hidden_events').catch(() => 0)]);
  openModal({ kind: 'settings', autostart: a, acct, hidden });
}
function ago(ts) {
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
}
function accountRows(a) {
  if (!a) return '';
  if (!a.user) return `<div class="set acct"><div class="who"><b>Google Calendar</b><span>${a.busy ? 'Finish signing in in your browser…'
      : a.error ? esc(a.error) : 'Not connected'}</span></div>
      ${a.busy ? '' : '<button class="more" data-act="gconnect">Connect</button>'}</div>`;
  const c = a.calendar;
  const cal = !c ? 'Not synced yet'
    : c.ok ? `Synced ${ago(c.at)} · ${c.count} meeting${c.count === 1 ? '' : 's'}`
      : `Didn't sync: ${esc(c.error || 'unknown error')}`;
  return `<div class="set acct"><div class="who"><b>${esc(a.user.name)}</b><span>${esc(a.user.email)}</span></div>
      <button class="more" data-act="signout">Sign out</button></div>
    <div class="set acct"><div class="who"><b>Google Calendar</b><span>${cal}</span></div>
      <button class="more" data-act="gsync">Sync now</button></div>`;
}
const GLOGO = '<svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>';
function loginHTML(a) {
  const busy = a && a.busy;
  return `<div class="login">
    <img class="lmark" src="logo.png" width="64" height="64" alt="">
    <h1>Nook</h1>
    <p class="sub">Your day, one focus at a time.</p>
    <button class="gbtn" data-act="signin" ${busy ? 'disabled' : ''}>${busy ? 'Finish signing in in your browser…' : GLOGO + 'Continue with Google'}</button>
    ${a && a.error ? `<div class="lerr">${esc(a.error)}</div>` : ''}
    ${busy ? '' : '<button class="link lskip" data-act="skipsignin">Use without an account</button>'}
    <div class="help">Google brings in your calendar meetings, read-only. Your tasks stay on this PC.</div>
  </div>`;
}
function loginGate(a) {
  return new Promise(done => {
    $('#top').innerHTML = '';
    const show = x => { $('#main').innerHTML = loginHTML(x); };
    show(a);
    let poll = null;
    const check = async () => {
      const x = await call('account_status').catch(() => null);
      if (!x) return;
      if (x.user) { clearInterval(poll); ACT.signin = null; done(); return; }
      show(x);
      if (!x.busy) { clearInterval(poll); poll = null; }
    };
    ACT.signin = async () => {
      show(await call('sign_in'));
      if (!poll) poll = setInterval(check, 1000);
    };
    ACT.skipsignin = async () => {
      await call('skip_sign_in').catch(() => {});
      clearInterval(poll); ACT.signin = null; ACT.skipsignin = null; done();
    };
  });
}
