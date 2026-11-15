// Вкладка «Обновления» на странице «Семантика»: даты обновлений Google и Яндекса на графиках сайта
// (Вебмастер, Search Console, Метрика) и «Что просело» - до и после даты по группам семантики и страницам.
// Сервер: window/semupd.py (/api/semupd), semantics/updates.py. Общие $, esc, num, plural, FOLDER - из semantics.js.
let UP = null, upLoaded = '', upSpan = 180, upBusy = false;
const upDate = s => s ? s.slice(8, 10) + '.' + s.slice(5, 7) + '.' + s.slice(0, 4) : '';
const upDay = s => new Date(s + 'T00:00:00Z').getTime() / 864e5;
const upIso = d => new Date(d * 864e5).toISOString().slice(0, 10);

function upOpen(){
  if (upLoaded === FOLDER && UP) return;
  upLoaded = FOLDER; UP = null; $('upView').hidden = true; $('upWait').hidden = false;
  $('upWait').textContent = 'Смотрю, что уже загружено…';
  fetch('/api/semupd?f=' + encodeURIComponent(FOLDER)).then(r => r.json()).then(j => {
    if (upLoaded !== FOLDER) return;
    if (j.error) { $('upWait').textContent = j.error; return; }
    UP = j; $('upWait').hidden = true; $('upView').hidden = false; upDraw();
    if (j.stale) upPost({load: 1}, null, 'Загружаю даты обновлений и данные сайта по дням…');
  }).catch(() => { $('upWait').textContent = 'Не получилось открыть. Обновите страницу.'; });
}

async function upPost(body, btn, wait){
  if (upBusy) return;
  upBusy = true; if (btn) btn.disabled = true;
  if (UP && body.load) { upDraw(); btn = $('upLoad'); if (btn) btn.disabled = true; }   // «загружаю…» у источников
  const msg = $('upMsg'); if (msg) { msg.className = 'mut'; msg.textContent = wait || 'Секунду…'; }
  try {
    const r = await fetch('/api/semupd', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.assign({f: FOLDER}, body))});
    const j = await r.json();
    upBusy = false;
    if (!r.ok) { if (btn) btn.disabled = false; const m = $('upMsg'); if (m) { m.className = 'err'; m.textContent = j.error || 'Не получилось.'; } return false; }
    UP = j; upDraw(); return true;
  } catch (e) {
    upBusy = false; if (btn) btn.disabled = false;
    const m = $('upMsg'); if (m) { m.className = 'err'; m.textContent = 'Программа не ответила. Она запущена?'; }
    return false;
  }
}

const UP_ST = {not_connected: 'не подключено', no_access: 'нет доступа к этому сайту', no_data: 'Яндекс ещё не собрал данные', ok: 'загружено'};
// нет статуса - данные сайта ещё не загружали (или загрузка идёт); сетевой обрыв (VPN, «handshake timed out») - не
// техническая строка, а «нет связи»; не загрузилось, но есть прошлые данные - они на графике, с датой
const UP_NET = /timed out|urlopen|10054|10060|handshake|Connection|getaddrinfo/i;
const upSt = (s, old) => !s ? (upBusy ? 'загружаю…' : 'ещё не загружалось')
  : old ? 'не обновилось (нет связи), на графике данные на ' + old
  : UP_ST[s] || (UP_NET.test(s) ? 'нет связи, нажмите «Загрузить заново»' : 'ошибка: ' + s.replace(/^error: /, ''));

function upHead(){
  const S = UP.series || {}, st = S.status || {}, old = S.old || {};
  const src = [['wm', 'Яндекс Вебмастер'], ['gsc', 'Google Search Console'], ['metrika', 'Яндекс Метрика']]
    .map(([k, n]) => `<span class="${st[k] === 'ok' ? 'bx-good' : 'mut'}">${n}: ${esc(upSt(st[k], old[k]))}</span>`).join('');
  const none = S.status && !['wm', 'gsc', 'metrika'].some(k => st[k] === 'ok');
  return `<section class="card"><h2>Обновления поиска <span class="mut">и что просело после них</span></h2>
    <p class="mut">Когда Google или Яндекс меняют правила, позиции скачут у всех сайтов темы. Здесь на графиках сайта отмечены даты обновлений: сразу видно, совпало ли падение с ними. Google публикует свои обновления сам, даты берутся автоматически. У Яндекса общего списка нет: отмечены обновления поисковой базы (из Вебмастера) и встряски, которые заметили SEO-сервисы (список ниже, можно дополнить).</p>
    <div class="up-src">${src}</div>
    ${none ? '<p class="mut">Чтобы увидеть графики сайта, подключите Вебмастер, Search Console или Метрику в «Настройках» (вход через Яндекс и Google) или попросите у клиента гостевой доступ. Даты обновлений и список ниже работают и без этого.</p>' : ''}
    ${UP.google_err ? `<p class="${UP.err_quiet ? 'mut' : 'err'}">${esc(UP.google_err)}${UP.err_quiet ? ' Показаны прежние даты, повторю через час.' : ''}</p>` : ''}${UP.yandex_err ? `<p class="${UP.yandex_quiet ? 'mut' : 'err'}">${esc(UP.yandex_err)}${UP.yandex_quiet ? ' Показаны прежние даты, повторю через час.' : ''}</p>` : ''}
    <div class="dm-go"><button class="btn small" id="upLoad">Загрузить заново</button><span class="mut">${S.fetched ? 'Данные сайта на ' + esc(S.fetched) : ''}</span></div>
    <p class="mut" id="upMsg"></p></section>`;
}

// ---------- графики: линия по дням и отметки обновлений
function upChart(title, note, lines, marks){
  lines = lines.filter(l => l.pts && l.pts.length);
  if (!lines.length) return '';
  const W = 900, H = 170, L = 44, R = 10, T = 18, B = 26;
  const end = Math.max(...lines.map(l => upDay(l.pts[l.pts.length - 1][0])));
  const start = end - upSpan;
  const sel = lines.map(l => ({...l, pts: l.pts.filter(p => upDay(p[0]) >= start)}));
  const vals = sel.flatMap(l => l.pts.map(p => p[1]));
  const inv = !!lines[0].inv;   // позиция: меньше - лучше, ось перевёрнута
  let max = Math.max(...vals, 1), min = inv ? Math.min(...vals) : 0;
  if (inv) { max = Math.ceil(max); min = Math.max(1, Math.floor(min)); if (max === min) max = min + 1; }
  const x = d => L + (d - start) / (end - start || 1) * (W - L - R);
  const y = v => inv ? T + (v - min) / (max - min) * (H - T - B) : H - B - v / max * (H - T - B);
  let svg = '';
  // отметки обновлений: полосы и линии под графиком, ручки сверху (на них подсказка и нажатие)
  let under = '', over = '';
  for (const m of marks) {
    const a = upDay(m.date), z = m.end ? upDay(m.end) : (m.kind === 'google' ? end : a);
    if (z < start || a > end) continue;
    const xa = x(Math.max(a, start)), xz = x(Math.min(z, end));
    const tip = `<title>${esc(`${m.name}: ${upDate(m.date)}${m.end ? ' - ' + upDate(m.end) : m.kind === 'google' ? ', ещё идёт' : ''}. Нажмите, чтобы сравнить до и после`)}</title>`;
    if (m.kind === 'google') {
      under += `<rect x="${xa}" y="${T}" width="${Math.max(xz - xa, 3)}" height="${H - T - B}" class="up-band"/>`;
      over += `<g class="up-mk" data-d="${m.date}">${tip}<rect x="${xa}" y="${T - 8}" width="${Math.max(xz - xa, 8)}" height="8" rx="2" class="up-gh"/></g>`;
    } else if (m.kind === 'yandex') {
      under += `<line x1="${xa}" x2="${xa}" y1="${T}" y2="${H - B}" class="up-shake"/>`;
      over += `<g class="up-mk" data-d="${m.date}">${tip}<circle cx="${xa}" cy="${T - 4}" r="4.5" class="up-yh"/></g>`;
    } else over += `<g class="up-mk" data-d="${m.date}">${tip}<rect x="${xa - 3}" y="${H - B}" width="6" height="8" fill="transparent"/><line x1="${xa}" x2="${xa}" y1="${H - B}" y2="${H - B + 6}" class="up-base"/></g>`;
  }
  svg += under;
  // сетка и подписи
  for (const v of [min, (max + min) / 2, max]) {
    const r = Math.round(v);
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="up-grid"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" class="up-ax">${num(r)}</text>`;
  }
  const step = upSpan > 200 ? 60 : upSpan > 100 ? 30 : 14;
  for (let d = end; d >= start + step / 3; d -= step) svg += `<text x="${x(d)}" y="${H - 6}" text-anchor="${d === end ? 'end' : 'middle'}" class="up-ax">${upDate(upIso(d)).slice(0, 5)}</text>`;
  sel.forEach((l, i) => {
    if (!l.pts.length) return;
    svg += `<polyline class="up-l${i}" points="${l.pts.map(p => `${x(upDay(p[0])).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ')}"/>`;
  });
  // подсказка по дню
  const days = {};
  sel.forEach(l => l.pts.forEach(p => { (days[p[0]] = days[p[0]] || []).push(`${l.name}: ${num(p[1])}`); }));
  const w = Math.max((W - L - R) / (end - start || 1), 2);
  for (const [d, t] of Object.entries(days)) svg += `<rect x="${x(upDay(d)) - w / 2}" y="${T}" width="${w}" height="${H - T - B}" class="up-hit"><title>${upDate(d)}: ${esc(t.join(', '))}</title></rect>`;
  svg += over;
  const legend = sel.map((l, i) => `<span><i class="up-k${i}"></i>${esc(l.name)}</span>`).join('');
  return `<div class="up-ch"><h3>${esc(title)}</h3>${note ? `<p class="mut up-note">${note}</p>` : ''}<div class="up-legend">${legend}</div>
    <svg viewBox="0 0 ${W} ${H}" class="up-svg" role="img" aria-label="${esc(title)}">${svg}</svg></div>`;
}

function upCharts(){
  const S = UP.series || {}, E = UP.events;
  const G = E.filter(e => e.kind === 'google'), Y = E.filter(e => e.kind !== 'google');
  const wm = S.wm || {}, gsc = S.gsc || {}, mt = S.metrika || {};
  const parts = [
    upChart('Яндекс: переходы из поиска по дням', 'Вебмастер. Пунктир - встряски выдачи, засечки внизу - обновления поисковой базы.', [{name: 'Переходы', pts: wm.clicks}], Y),
    upChart('Яндекс: средняя позиция по дням', 'Вебмастер, по всем запросам с показами. Чем выше линия, тем лучше.', [{name: 'Средняя позиция', pts: wm.pos, inv: true}], Y),
    upChart('Яндекс: страниц в поиске', 'Вебмастер, на каждое обновление поисковой базы.', [{name: 'Страниц в поиске', pts: wm.in_search}], Y),
    upChart('Google: клики из поиска по дням', 'Search Console. Полосы - обновления Google от начала до конца раскатки.', [{name: 'Клики', pts: gsc.clicks}], G),
    upChart('Google: средняя позиция по дням', 'Search Console. Чем выше линия, тем лучше.', [{name: 'Средняя позиция', pts: gsc.pos, inv: true}], G),
    upChart('Посетители из поиска по дням', 'Метрика: визиты из поиска Яндекса и Google. Отмечены обновления обоих поисковиков.', [{name: 'Из Яндекса', pts: mt.yandex}, {name: 'Из Google', pts: mt.google}], E),
  ].filter(Boolean);
  if (!parts.length) return '';
  const spans = [[90, '3 месяца'], [180, 'полгода'], [365, 'год']];
  return `<section class="card"><h2>Графики сайта с отметками обновлений</h2>
    <div class="up-legend"><span><i class="up-kg"></i>обновление Google</span><span><i class="up-ky"></i>встряска Яндекса (SEO-сервисы)</span><span><i class="up-kb"></i>обновление базы Яндекса</span>
    <span class="seg up-span">${spans.map(([d, t]) => `<button data-span="${d}" class="${d === upSpan ? 'on' : ''}">${t}</button>`).join('')}</span></div>
    <p class="mut up-note">Наведите на график, чтобы увидеть число за день и название обновления. Нажмите на отметку - сравню «до» и «после» этой даты.</p>
    ${parts.join('')}</section>`;
}

// ---------- список обновлений и свои даты встрясок
function upList(){
  const E = UP.events;
  const G = E.filter(e => e.kind === 'google').reverse(), Y = E.filter(e => e.kind === 'yandex').reverse();
  const B = E.filter(e => e.kind === 'base').reverse();
  const go = d => `<button class="btn small" data-cmp="${d}">Что просело</button>`;
  const g = G.map(e => `<div class="up-ev"><span class="up-dt">${upDate(e.date)}${e.end ? ' - ' + upDate(e.end) : ''}</span>
    <span>${e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.name)}</a>` : esc(e.name)}${e.end ? '' : ' <span class="pill">ещё идёт</span>'}</span>${go(e.date)}</div>`).join('');
  const y = Y.map(e => `<div class="up-ev"><span class="up-dt">${upDate(e.date)}</span>
    <span>${e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.name)}</a>` : esc(e.name)}</span>${go(e.date)}<button class="btn small" data-rm="${esc(e.id)}" title="Убрать из списка">убрать</button></div>`).join('');
  return `<section class="card"><h2>Обновления поиска</h2>
    <h3>Google <span class="mut">со страницы статуса поиска Google, автоматически</span></h3>
    ${g || '<p class="mut">Список ещё не загружался.</p>'}
    <h3>Встряски выдачи Яндекса <span class="mut">что заметили SEO-сервисы: Pixel Tools, PR-CY, XTOOL. Это их наблюдение, а не слова Яндекса</span></h3>
    ${y || '<p class="mut">Пока пусто.</p>'}
    <div class="up-add"><input type="date" id="upAddDate" aria-label="Дата встряски"><input id="upAddName" placeholder="Что случилось, например «PR-CY: выдача изменилась на 15 %»" aria-label="Что случилось"><input id="upAddSrc" placeholder="Ссылка на источник (можно пусто)" aria-label="Ссылка"><button class="btn small" id="upAdd">Добавить</button></div>
    <h3>Обновления поисковой базы Яндекса <span class="mut">из Вебмастера, обычно каждые несколько дней</span></h3>
    <p class="up-bases">${B.length ? B.slice(0, 40).map(e => upDate(e.date)).join(', ') + (B.length > 40 ? ` и ещё ${num(B.length - 40)}` : '') : '<span class="mut">Нет данных: войдите через Яндекс в «Настройках» (нужен хотя бы один свой сайт в Вебмастере).</span>'}</p></section>`;
}

// ---------- «Что просело»
const upArrow = (b, a, inv) => {
  if (b == null || a == null) return '';
  const d = inv ? b - a : a - b;
  return d > 0 ? 'bx-good' : d < 0 ? 'up-bad' : '';
};
const upPair = (v, inv, fix) => v ? `<span class="${upArrow(v[0], v[1], inv)}">${v[0] == null ? '-' : fix ? String(v[0]).replace('.', ',') : num(v[0])} → ${v[1] == null ? '-' : fix ? String(v[1]).replace('.', ',') : num(v[1])}</span>` : '<span class="mut">-</span>';

function upCompare(){
  const C = UP.compare;
  const opts = UP.events.filter(e => e.kind !== 'base').slice().reverse().slice(0, 30)
    .map(e => `<option value="${e.date}">${upDate(e.date)} - ${esc(e.name)}</option>`).join('');
  const date = (C && C.date) || UP.default_date;
  let out = `<section class="card" id="upCmp"><h2>Что просело</h2>
    <p class="mut">Сравню по ${num(28)} дней до даты и после (меньше, если после даты прошло меньше): переходы и позиции по группам семантики, страницы, с которых стало меньше посетителей из поиска, и что на них нашла проверка. Внизу - готовый текст для клиента.</p>
    <div class="up-add"><input type="date" id="upCmpDate" value="${esc(date)}" aria-label="Дата"><select id="upCmpPick" aria-label="Обновление"><option value="">или выберите обновление…</option>${opts}</select>
    <button class="btn small primary" id="upCmpGo">Что просело</button></div><p class="mut" id="upCmpMsg"></p>`;
  if (!C) return out + '</section>';
  const T = C.total, ENG = {yandex: 'Яндекс', google: 'Google'};
  const tot = Object.entries(T).map(([e, t]) => `<tr><td><b>${ENG[e]}</b></td><td class="num">${upPair(t.visits)}</td><td class="num">${upPair(t.clicks)}</td><td class="num">${upPair(t.shows)}</td><td class="num">${upPair(t.pos, true, true)}</td>
    <td class="num">${t.pct == null ? '-' : `<b class="${t.pct < -4 ? 'up-bad' : t.pct > 4 ? 'bx-good' : ''}">${t.pct > 0 ? '+' : ''}${t.pct} %</b>`}</td></tr>`).join('');
  out += `<h3>${upDate(C.date)}: ${C.days} ${plural(C.days, 'день', 'дня', 'дней')} до (${upDate(C.before[0])} - ${upDate(C.before[1])}) и после (${upDate(C.after[0])} - ${upDate(C.after[1])})</h3>
    <div class="up-verdict">${C.verdict.lines.map(l => `<p>${esc(l)}</p>`).join('')}</div>
    <div class="br-scroll"><table class="br-table dm-t"><tr><th>Поисковик</th><th>Визиты (Метрика)</th><th>Переходы</th><th>Показы</th><th>Средняя позиция</th><th>Изменение</th></tr>${tot}</table></div>`;
  const G = C.groups.filter(g => g.fell || g.grew);
  out += `<h3>Группы семантики <span class="mut">просело ${num(C.fell)}, выросло ${num(C.grew)}</span></h3>`;
  out += G.length ? G.slice(0, 60).map(g => {
    const e = Object.entries(g.eng).map(([k, v]) => `${ENG[k]}: переходы ${upPair(v.clicks)}, позиция ${upPair(v.pos, true, true)}`).join(' · ');
    const qs = g.queries.map(q => `<div class="bx-q"><span>${esc(q.q)} <i>${ENG[q.e]}</i></span><span class="bx-num">${upPair(q.clicks)}</span><span>позиция ${upPair(q.pos, true, true)}</span></div>`).join('');
    return `<details class="bx-g"><summary><b class="${g.fell ? 'up-bad' : 'bx-good'}">${g.fell ? 'Просела' : 'Выросла'}</b> ${esc(g.name)}${g.page ? ` <a class="gurl mut" href="${esc(g.page)}" target="_blank" rel="noopener">${esc(path(g.page))}</a>` : ''}
      <div class="bx-sum">${e}${g.visits ? ` · визиты на страницу ${upPair(g.visits)}` : ''}</div></summary>${qs || '<p class="mut">По отдельным запросам заметных изменений нет.</p>'}</details>`;
  }).join('') : '<p class="mut">Заметных изменений по группам нет (или запросы сайта не попали в группы семантики).</p>';
  out += `<h3>Страницы, с которых стало меньше посетителей из поиска <span class="mut">${num(C.pages.length + C.pages_more)}</span></h3>`;
  out += C.pages.length ? `<div class="br-scroll"><table class="br-table dm-t"><tr><th>Страница</th><th>${C.pages[0].src === 'visits' ? 'Визиты из поиска' : 'Клики Google'}</th><th>Что нашла проверка на странице</th></tr>${C.pages.map(p => `<tr><td><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(path(p.url))}</a>${p.groups.length ? `<br><span class="mut">${esc(p.groups.join(', '))}</span>` : ''}</td>
      <td class="num">${upPair([p.before, p.after])}${p.yandex && p.google ? `<br><span class="mut">Яндекс ${num(p.yandex[0])} → ${num(p.yandex[1])}, Google ${num(p.google[0])} → ${num(p.google[1])}</span>` : ''}</td>
      <td>${p.problems.length ? `<ul class="up-pr">${p.problems.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : `<span class="mut">${C.with_problems ? 'проблем не найдено' : 'нет разбора проверки: «⋯ → Обновить отчёт»'}</span>`}</td></tr>`).join('')}</table></div>`
    : '<p class="mut">Страниц с заметным падением нет.</p>';
  out += `<h3>Текст для клиента</h3><p class="mut">Можно скопировать в переписку как есть или поправить.</p>
    <textarea id="upClient" rows="16" class="up-client">${esc(C.verdict.client)}</textarea>
    <div class="dm-go"><button class="btn small" id="upCopy">Скопировать</button><span class="mut">Разбор от ${esc(C.made)}</span></div>`;
  return out + '</section>';
}

function upDraw(){
  $('upView').innerHTML = upHead() + upCompare() + upCharts() + upList();
}

$('upView').addEventListener('click', async ev => {
  const t = ev.target.closest('button, .up-mk');
  if (!t) return;
  if (t.id === 'upLoad') return upPost({load: 1}, t, 'Загружаю даты обновлений и данные сайта по дням…');
  if (t.dataset.span) { upSpan = +t.dataset.span; return upDraw(); }
  if (t.dataset.rm) return upPost({remove: t.dataset.rm}, t);
  if (t.id === 'upAdd') return upPost({add: {date: $('upAddDate').value, name: $('upAddName').value, src: $('upAddSrc').value}}, t);
  if (t.id === 'upCopy') { const a = $('upClient'); a.select(); try { await navigator.clipboard.writeText(a.value); t.textContent = 'Скопировано'; } catch (e) { document.execCommand('copy'); } return; }
  const d = t.id === 'upCmpGo' ? $('upCmpDate').value : t.dataset.cmp || t.dataset.d;
  if (!d) return;
  if (t.id !== 'upCmpGo') { $('upCmpDate').value = d; $('upCmp').scrollIntoView({block: 'start', behavior: 'smooth'}); }
  const btn = $('upCmpGo');
  $('upCmpMsg').className = 'mut';
  $('upCmpMsg').textContent = `Загружаю данные до и после ${upDate(d)} из Вебмастера, Search Console и Метрики…`;
  btn.disabled = true;
  try {
    const r = await fetch('/api/semupd', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({f: FOLDER, compare: d})});
    const j = await r.json();
    if (!r.ok) { $('upCmpMsg').className = 'err'; $('upCmpMsg').textContent = j.error || 'Не получилось.'; btn.disabled = false; return; }
    UP = j; upDraw(); $('upCmp').scrollIntoView({block: 'start'});
  } catch (e) { $('upCmpMsg').className = 'err'; $('upCmpMsg').textContent = 'Программа не ответила. Она запущена?'; btn.disabled = false; }
});
$('upView').addEventListener('change', ev => {
  if (ev.target.id === 'upCmpPick' && ev.target.value) $('upCmpDate').value = ev.target.value;
});
