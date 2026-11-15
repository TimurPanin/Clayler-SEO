// Решения по семантике на странице «Семантика» (сервер: window/semdec.py, логика: semantics/decisions.py).
// Заполняет места, оставленные в semantics.html: галочки у задач (.task-ck, #taskDone), блок «В группе смешаны…»
// на странице группы (#grpMixed), решения и задачи разработчику по страницам, которые мешают друг другу
// (#cannProgress, .case-st, .cann-decision, .cann-task, #cannFoot), экраны «Похоже, не та страница» (#landing) и
// «Группы из текста кнопок и меню» (#junk). Всё сохраняется по сайту и не пропадает между запусками.
// Пользуется общими esc, num, path, plural, DATA, FOLDER, TASKS, loadData из semantics.js.
(() => {
let SD = null, NEWER = null, polling = false;

async function api(url, body){
  const r = await fetch(url, body ? {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(Object.assign({f: FOLDER}, body))} : undefined);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || 'Не получилось.');
  return j;
}
const qWord = n => `${num(n)} ${plural(n, 'запрос', 'запроса', 'запросов')}`;
const bar = (done, total, text) => `<div class="sd-prog"><div class="sd-prog-t">${text}</div>
  <div class="sd-bar"><i style="width:${total ? Math.round(done / total * 100) : 0}%"></i></div></div>`;
function flash(el, text){ if (!el) return; const was = el.textContent; el.textContent = text; setTimeout(() => { el.textContent = was; }, 1800); }
function oops(e){ alert(e.message || 'Не получилось.'); }

// ---------- загрузка: после loadData() в semantics.js
async function load(newer){
  NEWER = newer; SD = null;
  if (!FOLDER) return;
  const f = FOLDER;
  let sd;
  try { sd = await api('/api/semdec?f=' + encodeURIComponent(f)); } catch (e) { return; }
  if (f !== FOLDER) return;   // пока грузилось, выбрали другой сайт
  SD = sd;
  fill();
  if (SD.recheck_state && SD.recheck_state.running) poll();
}
// решение поменяло группы (разделили, убрали, другая страница): перечитать всю семантику, остаться на месте
async function reload(){
  const y = window.scrollY;
  await loadData(FOLDER, NEWER);
  window.scrollTo(0, y);
}
function fill(){
  if (!SD || !DATA) return;
  tasks(); cann(); landingScreen(); junkScreen();
  const m = /^#g\/(\d+)/.exec(location.hash); if (m) group(+m[1]);
}

// ---------- задачи: галочки «сделано», счётчик, «После правок проверить снова»
function recheckLine(){
  const st = SD.recheck_state || {}, R = SD.recheck;
  if (st.running) return `<span class="sd-run">Перепроверяю страницы: ${num(st.done)} из ${num(st.total)}…</span>`;
  if (st.error) return `<span class="err">${esc(st.error)}</span>`;
  if (!R) return SD.recheck_pages ? `<span class="mut">Перепроверятся только страницы из задач: ${num(SD.recheck_pages)}</span>` : '';
  const s = R.summary || {};
  const parts = [];
  if (s.problems_total) parts.push(`замечаний к страницам исправлено ${num(s.problems_fixed)} из ${num(s.problems_total)}`);
  if (s.problems_manual) parts.push(`ещё ${num(s.problems_manual)} проверьте сами (программа не видит разницы с тем, что было)`);
  if (s.cases_total) parts.push(`мешающих страниц решено ${num(s.cases_fixed)} из ${num(s.cases_total)}`);
  return `<span class="mut">Перепроверено ${esc(R.at)}: ${num(s.pages)} ${plural(s.pages, 'страница', 'страницы', 'страниц')}${parts.length ? ', ' + parts.join(', ') : ''}.</span>`;
}
function recheckBtn(){
  const st = SD.recheck_state || {};
  return `<button class="btn small" data-sd="recheck"${st.running || !SD.recheck_pages ? ' disabled' : ''} title="Заново открыть только страницы из задач, без полной проверки сайта, и отметить, что исправилось">После правок проверить снова</button>`;
}
function tasks(){
  const list = typeof TASKS !== 'undefined' ? TASKS : [];
  const done = list.filter(t => SD.done[t.id]).length;
  const box = $('taskDone');
  if (box) { box.hidden = !list.length;
    box.innerHTML = list.length ? `${bar(done, list.length, `Сделано <b>${num(done)}</b> из ${num(list.length)} ${plural(list.length, 'задачи', 'задач', 'задач')}`)}
      <div class="sd-recheck">${recheckBtn()}<span class="sd-rl">${recheckLine()}</span></div>` : ''; }
  const R = SD.recheck && SD.recheck.summary;
  document.querySelectorAll('.task-ck[data-task]').forEach(el => {
    const id = el.dataset.task, t = list.find(x => x.id === id), on = !!SD.done[id];
    el.innerHTML = `<label class="sd-ck" title="${on ? 'Сделано ' + esc(SD.done[id]) : 'Отметить сделанным'}"><span class="sr">Отметить сделанным: ${esc(t ? t.title : id)}</span><input type="checkbox" data-sd-done="${esc(id)}"${on ? ' checked' : ''}></label>`;
    const art = el.closest('.task'); if (!art) return;
    art.classList.toggle('sd-done', on);
    const pr = art.querySelector('.prio');
    if (pr) { if (!pr.dataset.was) pr.dataset.was = pr.textContent; pr.textContent = on ? 'Сделано' : pr.dataset.was; pr.classList.toggle('p-done', on); }
    let res = art.querySelector('.sd-res');
    const txt = !R ? '' : id === 'fix' && R.problems_total ? `После правок исправлено ${num(R.problems_fixed)} из ${num(R.problems_total)} замечаний, страниц без замечаний: ${num(R.groups_fixed)} из ${num(R.groups_total)}`
      : id === 'cannibal' && R.cases_total ? `После правок решено ${num(R.cases_fixed)} из ${num(R.cases_total)} случаев с выбранным решением` : '';
    if (txt) { if (!res) { res = document.createElement('div'); res.className = 'sd-res'; art.querySelector('.task-main').appendChild(res); } res.textContent = txt; }
    else if (res) res.remove();
  });
}

// ---------- страницы, которые мешают друг другу
const ST = {main: 'Решено', merge: 'Решено', split: 'Решено', ok: 'Скрыто'};
function cann(){
  const P = SD.progress || {decided: 0, total: 0};
  const pg = $('cannProgress'); if (pg) pg.innerHTML = P.total ? bar(P.decided, P.total, `Решено <b>${num(P.decided)}</b> из ${num(P.total)}`) : '';
  const R = (SD.recheck || {}).cannibal || {};
  SD.cannibal.forEach(c => {
    const i = c.case, ch = c.decision, rc = ch && ch !== 'ok' ? R[c.key] : null;
    const st = document.querySelector(`.case-st[data-case="${i}"]`);
    if (st) st.innerHTML = rc ? (rc.fixed ? '<span class="sd-st ok">Исправлено</span>' : rc.manual ? '<span class="sd-st need">Проверьте сами</span>' : '<span class="sd-st bad">Ещё не исправлено</span>')
      : `<span class="sd-st ${ch ? 'ok' : 'need'}">${ch ? ST[ch] : 'Нужно решение'}</span>`;
    const det = document.querySelector(`details.case[data-case="${i}"]`);
    if (det) {
      det.classList.toggle('sd-hidden', ch === 'ok');
      det.querySelectorAll('.case-p').forEach((row, k) => {   // «главная» по решению человека
        const p = c.pages[k]; if (!p) return; const last = row.lastElementChild; if (!last || last.tagName === 'A') return;
        last.outerHTML = p.url === c.main && ch !== 'ok' && ch !== 'split' ? '<span class="pill p-page">главная</span>'
          : `<span class="mut">${ch === 'merge' ? '301-переадресация на главную' : ch === 'main' ? 'ссылка на главную, свои title и H1' : p.group ? 'свои title и H1 по своей группе' : 'свои title и H1'}</span>`;
      });
    }
    const dec = document.querySelector(`.cann-decision[data-case="${i}"]`);
    if (dec) dec.innerHTML = `<div class="f-label">Решение</div>
      <div class="sd-opts">${Object.entries(SD.choices).map(([id, o]) => `<button class="sd-opt${ch === id ? ' on' : ''}" aria-pressed="${ch === id}" data-sd-case="${esc(c.key)}" data-choice="${id}"><b>${esc(o.label)}</b><span>${esc(o.hint)}</span></button>`).join('')}</div>
      ${ch === 'main' || ch === 'merge' ? `<label class="sd-main">Главная страница <select data-sd-main="${esc(c.key)}">${c.pages.map(p => `<option value="${esc(p.url)}"${p.url === c.main ? ' selected' : ''}>${esc(path(p.url))}</option>`).join('')}</select></label>` : ''}
      ${c.auto && !ch ? '' : c.auto ? `<p class="hint">${esc(c.auto)}.</p>` : ''}`;
    const task = document.querySelector(`.cann-task[data-case="${i}"]`);
    if (task) task.innerHTML = ch && ch !== 'ok' && c.task ? `<div class="sd-task"><div class="f-label">Задача разработчику</div>
      <div class="sd-task-t">${esc(c.task)}</div>
      ${rc && rc.manual ? `<div class="sd-notes manual">${esc(rc.notes[0])}</div>` : rc && rc.notes.length ? `<div class="sd-notes"><b>Проверено после правок, ещё не так:</b>${rc.notes.map(n => `<div>${esc(n)}</div>`).join('')}</div>` : rc ? '<div class="sd-notes ok">Проверено после правок: всё сделано.</div>' : ''}
      <div class="sd-acts"><button class="btn small" data-copy="${esc(c.task)}">Скопировать</button>
      <button class="btn small" data-sd-tg="${esc(c.key)}"${SD.telegram ? '' : ' disabled title="Бот не настроен: «Настройки», раздел Telegram"'}>Отправить в Telegram</button>
      <button class="btn small ghost" data-sd-case="${esc(c.key)}" data-choice="undo">Отменить решение</button></div></div>`
      : ch === 'ok' ? `<div class="sd-acts"><button class="btn small ghost" data-sd-case="${esc(c.key)}" data-choice="undo">Вернуть случай</button></div>` : '';
  });
  const foot = $('cannFoot');
  if (foot) {
    foot.querySelectorAll('.sd-foot').forEach(x => x.remove());
    const n = SD.cannibal.filter(c => c.decision && c.decision !== 'ok').length;
    foot.insertAdjacentHTML('afterbegin', `<a class="btn primary sd-foot${n ? '' : ' disabled'}" href="/api/semdec/docx?f=${encodeURIComponent(FOLDER)}"${n ? ' download' : ' aria-disabled="true" title="Сначала выберите решение хотя бы по одному случаю"'}>Скачать все задачи (Word)${n ? ' · ' + num(n) : ''}</a>`);
    foot.insertAdjacentHTML('beforeend', `<span class="sd-foot sd-recheck">${recheckBtn()}<span class="sd-rl">${recheckLine()}</span></span>`);
  }
}

// ---------- страница группы: смешанная группа, не та страница, похоже на мусор, итог перепроверки
// newFirst: «Создать новую страницу» первой (как в макете смешанной группы), иначе первой лучшая найденная страница
function pageSelect(attr, cands, newFirst){
  const nw = '<option value="new">Создать новую страницу</option>', opts = cands.map(u => `<option value="${esc(u)}">${esc(path(u))}</option>`).join('');
  return `<select ${attr}>${newFirst ? nw + opts : opts + nw}</select>`;
}
function mixedCard(m){
  const [a, b] = m.parts;
  const col = (p, ok) => `<div class="sd-part"><div class="sd-part-h"><i class="${ok ? 'ok' : 'bad'}"></i><b>${esc(p.label)}</b><span class="mut">· ${qWord(p.n)}${p.neutral ? `, из них без уточнения ${num(p.neutral)}` : ''}</span></div>
    <div class="qchips">${p.sample.map(q => `<span>${esc(q)}</span>`).join('')}</div>
    ${p.page ? `<div class="sd-pg">Страница: <a class="mono" href="${esc(p.page)}" target="_blank">${esc(path(p.page))}</a>${p.fits ? ' <span class="good">подходит</span>' : ''}</div>`
      : `<div class="sd-pg">Страница: <span class="crit">подходящей нет</span></div>
        <label class="sd-bind">Привязать к ${pageSelect('data-sd-mixpage', p.candidates || [], true)}</label>`}</div>`;
  return `<section class="card sd-warn"><div class="sd-warn-h"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>
    <div><div class="sd-warn-t">${esc(m.title)}</div><div class="sd-warn-d">${esc(m.text)}</div></div></div>
    <div class="sd-parts">${col(a, !!a.page)}${col(b, false)}</div>
    <div class="sd-acts"><button class="btn primary" data-sd-mix="split" data-axis="${m.axis}" data-group="${esc(m.name)}">Разделить на две группы</button>
    <button class="btn" data-sd-mix="keep" data-axis="${m.axis}" data-group="${esc(m.name)}">Оставить как есть</button></div></section>`;
}
// сравнение текущей страницы и кандидатов (идея из разговора с ChatGPT, 29.10.2026): выбирать не вслепую
function compareHtml(L){
  const C = L.compare || []; if (C.length < 2) return '';
  return `<table class="sd-cmp"><thead><tr><th>Страница</th><th title="Сколько слов из названия группы есть в title и H1 страницы">Слов группы в title и H1</th>
    <th title="Про что страница по признакам: онлайн или офлайн, детям или взрослым и т. п.">Про что</th><th>Уже привязана к группе</th></tr></thead><tbody>
    ${C.map(r => `<tr><td><a class="mono" href="${esc(r.url)}" target="_blank" title="${esc(r.title)}">${esc(path(r.url))}</a>${r.url === L.page ? ' <span class="mut">сейчас</span>' : ''}</td>
      <td>${esc(r.words || '-')}</td><td>${esc(r.side || '-')}</td><td>${r.busy ? esc(r.busy) : '<span class="mut">нет</span>'}</td></tr>`).join('')}</tbody></table>`;
}
function landingCard(L, short){
  return `<section class="card sd-warn"><div class="sd-warn-h"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>
    <div><div class="sd-warn-t">${short ? `<a href="#g/${L.group}">${esc(L.name)}</a>` : 'Похоже, не та страница'}</div>
    <div class="sd-warn-d">Группа привязана к <a class="mono" href="${esc(L.page)}" target="_blank">${esc(path(L.page))}</a>: ${esc(L.why)}.${L.mixed ? ' В группе ещё и смешаны разные запросы: их можно разделить на странице группы.' : ''}</div></div></div>
    ${compareHtml(L)}
    <div class="sd-acts"><label class="sd-bind">Правильная страница ${pageSelect('data-sd-landpage', L.candidates || [], false)}</label>
    <button class="btn primary" data-sd-land="set" data-group="${esc(L.name)}">Привязать</button>
    <button class="btn" data-sd-land="keep" data-group="${esc(L.name)}">Страница верная</button>
    ${short && L.mixed ? `<a class="btn ghost" href="#g/${L.group}">Разделить группу</a>` : ''}</div></section>`;
}
const note = (html, btn) => `<div class="sd-note">${html}${btn ? ' ' + btn : ''}</div>`;
function group(i){
  const box = document.querySelector(`#grpMixed[data-group="${i}"]`); if (!box || !SD) return;
  const g = DATA.groups[i]; if (!g) return;
  let h = '';
  const m = SD.mixed.find(x => x.group === i); if (m) h += mixedCard(m);
  const L = SD.landing.find(x => x.group === i); if (L && !m) h += landingCard(L);  // смешанную группу решает разделение
  const s = SD.splits.find(x => x.group === i);
  if (s) h += note(`Эта группа отделена от «${esc(s.from)}»: здесь запросы про «${esc(s.side)}».`,
    `<button class="btn small ghost" data-sd-mix="undo" data-axis="${s.axis}" data-group="${esc(s.from)}">Вернуть одну группу</button>`);
  SD.kept.filter(x => x.group === i).forEach(k => { h += note(esc(k.title) + '.', `<button class="btn small ghost" data-sd-mix="undo" data-axis="${k.axis}" data-group="${esc(k.name)}">Предложить разделить снова</button>`); });
  const ls = SD.landing_set.find(x => x.group === i);
  if (ls) h += note(ls.choice === 'keep' ? 'Вы отметили, что страница группы верная.' : ls.choice === 'new' ? 'Под группу решено создать новую страницу.' : `Страница группы выбрана вручную${ls.from ? `, раньше была ${esc(path(ls.from))}` : ''}.`,
    `<button class="btn small ghost" data-sd-land="undo" data-group="${esc(ls.name)}">Отменить</button>`);
  const J = SD.junk.find(x => x.group === i);
  if (J) h += note('Похоже, группа собрана из текста кнопки или меню сайта, а не из того, что ищут клиенты.',
    `<button class="btn small" data-sd-junk="${esc(J.name)}">Убрать в отсеянное</button>`);
  const rc = ((SD.recheck || {}).groups || {})[g.name];
  if (rc) h += `<section class="card sd-rc"><div class="f-label">Проверено после правок ${esc(SD.recheck.at)}</div>
    ${rc.error ? `<div class="crit">${esc(rc.error)}</div>` : ''}
    ${rc.fixed.map(p => `<div class="sd-rc-i ok">✓ ${esc(p.problem)}</div>`).join('')}
    ${rc.left.map(p => `<div class="sd-rc-i bad">✗ ${esc(p.problem)}${p.note ? ` <span class="mut">(${esc(p.note)})</span>` : ''}</div>`).join('')}
    ${(rc.manual || []).length ? `<div class="sd-rc-i mut">Проверьте сами, программа не видит разницы с тем, что было: ${rc.manual.map(p => esc(p.problem)).join('; ')}</div>` : ''}</section>`;
  box.innerHTML = h;
}

// ---------- экраны «Похоже, не та страница» и «Группы из текста кнопок и меню»
function landingScreen(){
  const box = $('sdLanding'); if (!box) return;
  const mixed = SD.mixed.filter(m => !SD.landing.some(L => L.group === m.group));
  box.innerHTML = (SD.landing.length ? SD.landing.map(L => landingCard(L, true)).join('') : '')
    + (mixed.length ? `<h2 class="sd-h2">В группе смешаны разные запросы</h2><p class="mut">Одна страница не закроет оба запроса. Откройте группу и разделите её на две.</p>
      <div class="card sd-list">${mixed.map(m => `<a class="sd-row" href="#g/${m.group}"><b>${esc(m.name)}</b><span class="mut">${esc(m.title)}</span><span class="mono">${m.page ? esc(path(m.page)) : 'страницы нет'}</span></a>`).join('')}</div>` : '')
    + (SD.landing_set.length ? `<h2 class="sd-h2">Уже решено</h2><div class="card sd-list">${SD.landing_set.map(x => `<div class="sd-row"><a href="#g/${x.group}"><b>${esc(x.name)}</b></a><span class="mut">${x.choice === 'keep' ? 'страница верная' : x.choice === 'new' ? 'создать новую страницу' : 'страница: ' + esc(path(x.page))}</span><button class="btn small ghost" data-sd-land="undo" data-group="${esc(x.name)}">Отменить</button></div>`).join('')}</div>` : '')
    || '<div class="card sem-none"><p class="mut">Все группы привязаны к подходящим страницам.</p></div>';
}
function junkScreen(){
  const box = $('sdJunk'); if (!box) return;
  box.innerHTML = (SD.junk.length ? `<div class="card sd-list">${SD.junk.map(j => `<label class="sd-row"><input type="checkbox" data-sd-jk="${esc(j.name)}" checked>
      <span><b>${esc(j.name)}</b><span class="mut"> · ${qWord(j.n)}</span><br><span class="sd-sample">${j.sample.map(q => '«' + esc(q) + '»').join(', ')}</span></span>
      ${j.page ? `<span class="mono">${esc(path(j.page))}</span>` : ''}</label>`).join('')}</div>
    <div class="sd-acts"><button class="btn primary" id="sdJunkGo">Убрать отмеченные в отсеянное</button><span class="mut">Запросы попадут на вкладку «Отсеяно», вернуть можно здесь же.</span></div>`
    : '<div class="card sem-none"><p class="mut">Групп из текста кнопок и меню не нашлось.</p></div>')
    + (SD.junk_removed.length ? `<h2 class="sd-h2">Уже убраны</h2><div class="card sd-list">${SD.junk_removed.map(j => `<div class="sd-row"><b>${esc(j.name)}</b><span class="mut">${qWord(j.n)}</span><button class="btn small ghost" data-sd-back="${esc(j.name)}">Вернуть</button></div>`).join('')}</div>` : '');
}

// ---------- «После правок проверить снова»
async function poll(){
  if (polling) return; polling = true;
  try {
    while (true) {
      await new Promise(r => setTimeout(r, 1500));
      SD = await api('/api/semdec?f=' + encodeURIComponent(FOLDER));
      document.querySelectorAll('.sd-rl').forEach(x => x.innerHTML = recheckLine());
      if (!(SD.recheck_state || {}).running) break;
    }
  } catch (e) { /* окно закрыли или сервер перезапустили */ }
  polling = false;
  fill();
}

// ---------- нажатия
document.addEventListener('change', async e => {
  const ck = e.target.closest('[data-sd-done]');
  if (ck) { try { SD = await api('/api/semdec/done', {id: ck.dataset.sdDone, done: ck.checked}); tasks(); } catch (err) { ck.checked = !ck.checked; oops(err); } return; }
  const sm = e.target.closest('[data-sd-main]');
  if (sm) { const c = SD.cannibal.find(x => x.key === sm.dataset.sdMain);
    try { SD = await api('/api/semdec/cannibal', {key: c.key, choice: c.decision, main: sm.value}); cann(); } catch (err) { oops(err); } }
});
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-sd],[data-sd-case],[data-sd-tg],[data-sd-mix],[data-sd-land],[data-sd-junk],[data-sd-back],#sdJunkGo');
  if (!b || !SD) return;
  e.preventDefault();
  if (b.disabled) return;
  try {
    if (b.dataset.sd === 'recheck') {
      SD = await api('/api/semdec/recheck', {}); fill(); poll();
    } else if (b.dataset.sdCase) {
      const det = b.closest('details'); const wasOpen = det && det.open;
      SD = await api('/api/semdec/cannibal', {key: b.dataset.sdCase, choice: b.dataset.choice}); cann();
      if (det) det.open = b.dataset.choice === 'ok' ? false : wasOpen;
    } else if (b.dataset.sdTg) {
      b.disabled = true; await api('/api/semdec/telegram', {key: b.dataset.sdTg}); b.disabled = false; flash(b, 'Отправлено');
    } else if (b.dataset.sdMix) {
      const card = b.closest('.sd-warn'), sel = card && card.querySelector('[data-sd-mixpage]');
      SD = await api('/api/semdec/mixed', {group: b.dataset.group, axis: b.dataset.axis, choice: b.dataset.sdMix, page: sel ? sel.value : 'new'});
      await reload();
    } else if (b.dataset.sdLand) {
      const card = b.closest('.sd-warn'), sel = card && card.querySelector('[data-sd-landpage]');
      const v = sel ? sel.value : 'new', act = b.dataset.sdLand;
      SD = await api('/api/semdec/landing', {group: b.dataset.group, choice: act === 'set' ? (v === 'new' ? 'new' : 'page') : act, page: v});
      await reload();
    } else if (b.dataset.sdJunk || b.id === 'sdJunkGo') {
      const names = b.dataset.sdJunk ? [b.dataset.sdJunk] : [...document.querySelectorAll('[data-sd-jk]:checked')].map(x => x.dataset.sdJk);
      if (!names.length) return;
      SD = await api('/api/semdec/junk', {groups: names});
      if (b.dataset.sdJunk) location.hash = '#groups';
      await reload();
    } else if (b.dataset.sdBack) {
      SD = await api('/api/semdec/junk', {groups: [b.dataset.sdBack], back: true}); await reload();
    }
  } catch (err) { b.disabled = false; oops(err); }
});
window.addEventListener('hashchange', () => { const m = /^#g\/(\d+)/.exec(location.hash); if (m && SD) setTimeout(() => group(+m[1]), 0); });

window.semDec = {load, fill, group: i => SD && group(i), tasks: () => SD && tasks(), cann: () => SD && cann()};
})();
