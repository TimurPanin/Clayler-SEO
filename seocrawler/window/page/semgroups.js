// Часть страницы «Семантика» (page/semantics.js - выбор сайта, загрузка, сбор, экраны по адресу после #): вкладка «Группы запросов» и страница группы (ТЗ, настоящие запросы, у конкурентов).
// Общие $, esc, num, plural, host, path, DATA, FOLDER, KIND, PAGE_SIZE и др. - из semantics.js (подключён раньше).
// ---------- вкладка «Группы запросов»: строка на группу, нажатие - страница группы
function rowsOf(g, q){
  const base = (STOP.size || PICK.size) ? g.q.filter(r => !hiddenRow(r)) : g.q;
  if (!base.length) return null;
  if (!q && !intent) return base;
  const byIntent = intent ? base.filter(r => r[2] === intent) : base;
  if (q && g.lname.includes(q)) return byIntent.length ? byIntent : null;
  const rows = q ? byIntent.filter(r => r[0].includes(q) || (r[14] || []).some(f => f.includes(q))) : byIntent;
  return rows.length ? rows : null;
}

function render(){
  if (!DATA) return;
  const q = $('semQ').value.trim().toLowerCase();
  LIST = [];
  for (const g of DATA.groups) {
    if (tab !== 'all' && g.kind !== tab) continue;
    if ($('semFix').checked && !(g.a && g.a.problems.length)) continue;
    const rows = rowsOf(g, q);
    if (rows) LIST.push([g, rows]);
  }
  $('semSrc').innerHTML = srcNote(['freq', 'sug', 'real']);
  $('semGroups').innerHTML = LIST.length ? LIST.slice(0, shown).map(([g, rows]) => groupRow(g, rows, q)).join('')
    : '<p class="mut sem-none">Ничего не нашлось. Попробуйте другое слово или «Все».</p>';
  $('semMore').innerHTML = LIST.length > shown ? `Показано ${num(shown)} из ${num(LIST.length)} ${plural(LIST.length, 'группы', 'групп', 'групп')}  <button class="btn small" id="semShowMore">Показать ещё</button>` : '';
}

function mark(text, q){ const t = esc(text); if (!q) return t;
  const i = text.indexOf(q); return i < 0 ? t : esc(text.slice(0, i)) + '<mark>' + esc(text.slice(i, i + q.length)) + '</mark>' + esc(text.slice(i + q.length)); }

function pills(g){
  return `<span class="pill p-${g.kind}">${KIND[g.kind][0]}</span>${g.ptype === 'article' ? `<span class="pill p-art" title="Информационных запросов: ${g.info}, коммерческих: ${g.comm}. Под такие запросы нужна статья, а не страница товара или услуги">Под статью</span>` : g.ptype === 'both' ? `<span class="pill p-art" title="Информационных запросов: ${g.info}, коммерческих: ${g.comm}. Нужна страница и статья, которая на неё ведёт">+ статья</span>` : ''}`;
}
function groupRow(g, rows, q){
  const good = rows.filter(r => !r[7]);
  const sample = good.filter(r => r[0] !== g.lname).slice(0, 2), more = good.length - sample.length;
  const page = g.page ? `<span class="mono gurl" title="${esc(g.page)}">${esc(path(g.page))}</span>`
    : `<span class="gurl none">${g.near ? (g.todo.includes('товары') ? 'страницы нет, товары есть' : 'страницы нет') : 'страницы на сайте нет'}</span>`;
  const np = g.a ? g.a.problems.length : 0;
  return `<a class="grow" href="#g/${g.idx}" data-k="${g.kind}">
    <div class="gmain"><div class="gname"><b>${mark(g.name, q)}</b>${pills(g)}${g.mixed ? `<span class="pill p-warn" title="${esc(g.mixed.text)}">смешаны «${esc(g.mixed.a)}» и «${esc(g.mixed.b)}»</span>` : ''}${g.landing ? `<span class="pill p-warn" title="${esc(g.landing.why)}">не та страница?</span>` : ''}</div>
      <div class="qchips">${sample.map(r => `<span>${mark(r[0], q)}</span>`).join('')}${more > 0 ? `<em>ещё ${num(more)}</em>` : ''}</div></div>
    <div class="gpage">${page}${g.kind !== 'page' ? `<span class="gtodo">${esc(g.todo)}</span>` : ''}</div>
    <div class="r gn"><b>${num(good.length)}</b>${g.freq ? `<span class="gfreq" title="Спрос в месяц: ${esc(freqSrc())}">${num(g.freq)}/мес</span>` : `<span class="sig l${g.level}" title="Спрос ${['', 'низкий', 'средний', 'высокий'][g.level]} (примерный, по месту в подсказках)"><i></i><i></i><i></i></span>`}</div>
    <div>${np ? `<span class="pill p-fix" title="${esc(g.a.problems.join(' · '))}">${np} ${plural(np, 'замечание', 'замечания', 'замечаний')}</span>` : ''}</div>
    <span class="gopen" aria-hidden="true">›</span></a>`;
}

// ---------- страница группы
let grpShown = 30;
function groupPage(i){
  const g = DATA.groups[i]; if (!g) { location.hash = '#groups'; return; }
  const rows = rowsOf(g, '') || [], ok = rows.filter(r => !r[7]), odd = rows.filter(r => r[7]);
  const ptxt = g.page ? `привязана к <a class="mono" href="${esc(g.page)}" target="_blank">${esc(path(g.page))}</a>` : esc(g.todo);
  const it = {}; ok.forEach(r => { if (r[2] && r[2] !== 'Общий') it[r[2]] = (it[r[2]] || 0) + 1; });
  const main = Object.entries(it).sort((a, b) => b[1] - a[1])[0];
  const links = [];
  if (!g.page && g.land && g.land.url) links.push(`<div><span>Адрес новой страницы</span><span class="mono">${esc(g.land.url)}</span></div>`);
  if (!g.page && g.near) links.push(`<div><span>${g.todo.includes('товары') ? `Пример товара (всего ${num(g.products)})` : 'Ближайшая страница'}</span><a class="mono" href="${esc(g.near)}" target="_blank">${esc(path(g.near))}</a></div>`);
  if (g.rivals.length) links.push(`<div><span>У конкурента</span><div>${g.rivals.map(u => `<a class="mono" href="${esc(u)}" target="_blank">${esc(host(u) + path(u))}</a>`).join('<br>')}</div></div>`);
  const max = Math.max(1, ...rows.map(r => r[3]));
  const tr = r => `<div class="qrow"${r[7] ? ` title="${esc(r[7])}"` : ''}><span>${esc(r[0])}${r[1] ? ` <span class="xtra" title="Уточнение: слова запроса сверх названия группы">+ ${esc(r[1])}</span>` : ''}${formsTag(r)}${r[6] ? ` <span class="tag" title="Показы в Вебмастере / Search Console">${num(r[6])} показов</span>` : ''}${r[8] ? ` <span class="tag pos${r[8] >= 11 && r[8] <= 20 ? ' near' : ''}" title="Средняя позиция сайта в поиске по этому запросу">${String(r[8]).replace('.', ',')} место</span>` : ''}</span>
    <span class="intent i-${esc(r[2])}">${esc(r[2] === 'Общий' ? '' : r[2])}</span>
    ${r[11] ? `<span class="qfreq" title="Спрос в месяц: ${esc(freqSrc())}${lvlTitle(r[11])}">${lvlTag(r[11])}${num(r[11])}</span>`
      : `<span title="Примерный спрос. Место в подсказках: Яндекс ${r[4] || '-'}, Google ${r[5] || '-'}"><span class="qbar"><i style="width:${Math.max(6, r[3] / max * 100).toFixed(0)}%"></i></span></span>`}</div>`;
  const fixCard = briefHtml(g) + faqHtml(g) + fltHtml(g);
  $('grpPage').innerHTML = `<div class="sub-head"><div><div class="gname"><h1>${esc(g.name)}</h1>${pills(g)}${g.a && g.a.problems.length ? `<span class="pill p-fix">${g.a.problems.length} ${plural(g.a.problems.length, 'замечание', 'замечания', 'замечаний')} к странице</span>` : ''}</div>
      <p class="mut">${num(ok.length)} ${plural(ok.length, 'запрос', 'запроса', 'запросов')}${main ? ` · тип «${esc(main[0])}»` : ''} · ${ptxt}</p></div>
    <div class="sem-dl">${g.a && (g.a.title || g.a.h1) ? `<button class="btn" data-copy="${esc(briefText(g))}">Скопировать задание</button>` : ''}${g.page ? `<a class="btn" href="${esc(g.page)}" target="_blank">Открыть страницу ↗</a>` : ''}</div></div>
  <div class="grp-mixed" id="grpMixed" data-group="${i}"></div>
  <div class="grp-cols">
    <div class="grp-left">${realHtml(g)}${fixCard ? `<section class="card"><div class="card-h"><h2>${g.a && g.a.new ? 'Заготовка новой страницы' : 'Что поправить на странице'}</h2>${g.page ? `<a class="mono" href="${esc(g.page)}" target="_blank">${esc(path(g.page))} ↗</a>` : ''}</div>${fixCard}</section>`
      : `<section class="card"><h2>Что поправить на странице</h2><p class="mut">Замечаний к странице нет.</p></section>`}
      ${links.length ? `<section class="card"><h2>Страницы</h2><div class="sg-links">${links.join('')}</div></section>` : ''}</div>
    <section class="card grp-q"><div class="card-h"><h2>Запросы группы</h2><span class="mut">${num(ok.length)}</span></div>
      <div class="qrow qhead"><span>Запрос</span><span>Намерение</span><span>Спрос</span></div>
      ${ok.slice(0, grpShown).map(tr).join('')}
      ${srcNote(['freq', 'sug', 'real'])}
      ${ok.length > grpShown ? `<button class="btn small" id="grpMore">Показать ещё ${num(Math.min(ok.length - grpShown, 100))}</button>` : ''}
      ${odd.length ? `<details class="sg-odd"><summary>Сомнительные: ${num(odd.length)} <span class="mut">в запросе слова, которых нет на сайтах; возможно, про другое</span></summary>${odd.map(tr).join('')}</details>` : ''}</section>
  </div>`;
  const b = $('grpMore'); if (b) b.onclick = () => { grpShown += 100; groupPage(i); };
  if (window.semDec) semDec.group(i);
}

function briefText(g){ const a = g.a || {}, t = g.tz || {}, L = g.land || {};
  return [g.name, L.new && L.url && 'Адрес: ' + L.url, a.title && 'Title: ' + a.title, a.h1 && 'H1: ' + a.h1, a.description && 'Описание: ' + a.description, a.words && 'В тексте раскрыть: ' + a.words,
    t.volume && 'Объём текста: ' + t.volume.text, t.h2 && t.h2.length && 'Подзаголовки (H2):\n' + t.h2.map(h => '- ' + h).join('\n'),
    ...(a.problems || []).map(p => '- ' + p)].filter(Boolean).join('\n'); }

function briefHtml(g){
  const a = g.a; if (!a || !(a.problems.length || a.new)) return tzHtml(g);
  const now = a.now || {}, L = g.land || {};
  const row = (label, cur, sug) => sug ? `<div class="bf-row"><span class="bf-l">${label}</span><div>${cur != null ? `<div class="bf-now">Сейчас: ${cur ? esc(cur) : '<i>нет</i>'}</div>` : ''}
    <div class="bf-new"><span>Лучше: ${esc(sug)}</span><button class="btn small" data-copy="${esc(sug)}">Скопировать</button></div></div></div>` : '';
  return `<div class="brief">
  ${a.problems.length ? `<ul class="bf-probs">${a.problems.map(p => `<li><span class="pill p-fix">Замечание</span>${esc(p)}</li>`).join('')}</ul>` : ''}
  ${L.new && L.url ? row('Адрес', null, L.url) : ''}${row('Title', a.new ? null : now.title, a.title)}${row('H1', a.new ? null : now.h1, a.h1)}${row('Описание', a.new ? null : now.description, a.description)}
  ${a.words ? `<div class="bf-words"><div class="f-label">Слова для текста</div><div class="qchips">${a.words.split(/,\s*/).filter(Boolean).map(w => `<span>${esc(w)}</span>`).join('')}</div><p class="hint">Из запросов группы. Нужны в тексте, а не списком в подвале.</p></div>` : ''}${tzInner(g)}</div>`;
}
// объём текста по конкурентам и подзаголовки H2 (plan.py)
function tzInner(g){
  const t = g.tz; if (!t) return '';
  const now = (g.a && !g.a.new && g.a.now) ? g.a.now.words : null;
  return `${t.volume ? `<div class="bf-row"><span class="bf-l">Объём</span><div>${esc(t.volume.text)}${now != null ? `<div class="bf-now">Сейчас: ${num(now)} ${plural(now, 'слово', 'слова', 'слов')}</div>` : ''}</div></div>` : ''}
  ${t.h2 && t.h2.length ? `<div class="bf-row"><span class="bf-l">Подзаголовки H2</span><div><ol class="bf-h2">${t.h2.map(h => `<li>${esc(h)}</li>`).join('')}</ol>
    <button class="btn small" data-copy="${esc(t.h2.join('\n'))}">Скопировать</button></div></div>` : ''}`;
}
// откуда настоящие запросы: Вебмастер, Search Console, выгрузка из файла
const realSrc = () => { const R = DATA.real || {}; return [R.wm === 'ok' && 'Яндекс Вебмастер', R.gsc === 'ok' && 'Google Search Console', R.file === 'ok' && 'файл выгрузки'].filter(Boolean).join(', '); };
function realLine(R){ return [R.shows && `${num(R.shows)} ${plural(R.shows, 'показ', 'показа', 'показов')}`, R.clicks && `${num(R.clicks)} ${plural(R.clicks, 'переход', 'перехода', 'переходов')}`,
  R.pos && `${String(R.pos).replace('.', ',')} место`].filter(Boolean).join(' · '); }
// настоящие запросы группы (Вебмастер и Search Console)
function realHtml(g){
  const R = g.real; if (!R) return '';
  return `<section class="card"><h2>Настоящие запросы</h2><p class="mut">За 4 недели до ${esc((DATA.made || '').slice(0, 10))} (${esc(realSrc())}) по ${num(R.n)} ${plural(R.n, 'запросу', 'запросам', 'запросам')} группы: <b>${realLine(R)}</b>.</p>
    ${R.other ? `<div class="alert warn sem-other"><div class="alert-t">Google по этим запросам показывает <a class="mono" href="${esc(R.other.url)}" target="_blank">${esc(path(R.other.url))}</a>${g.page ? `, а не <span class="mono">${esc(path(g.page))}</span>` : ''}. Либо сделайте её страницей группы, либо усильте нужную: title, H1, текст и внутренние ссылки.</div></div>` : ''}
    <table class="sq"><thead><tr><th>Запрос</th><th>Показов</th><th>Место</th></tr></thead><tbody>${R.top.map(([q, s, p]) => `<tr><td>${esc(q)}</td><td>${num(s)}</td><td>${p ? String(p).replace('.', ',') : '-'}</td></tr>`).join('')}</tbody></table></section>`;
}
// темы конкурентов, которых нет у вас: по всем конкурентам, одна тема - один раз
function rivalGaps(){
  const by = new Map();
  (DATA.rival_gaps || []).forEach(e => e.missing.forEach(m => { const x = by.get(m.i) || Object.assign({}, m, {hosts: [], urls: []});
    x.hosts.push(e.host); x.urls.push(m.url); by.set(m.i, x); }));
  return [...by.values()].sort((a, b) => b.score - a.score);
}
let rvShown = 40;
function rivalsPage(){
  const E = DATA.rival_gaps || [], all = rivalGaps();
  $('rvT').textContent = all.length ? `Темы конкурентов, которых нет у вас: ${num(all.length)}` : 'Темы конкурентов';
  if (!E.length) { $('rvList').innerHTML = `<div class="card sem-none"><p class="mut">${DATA.competitors.length ? 'У конкурентов не нашлось тем, которых нет у вас.' : 'Семантика собрана без конкурентов. Добавьте их в «Конкуренты и режим сбора» (можно просто адресами сайтов) и нажмите «Собрать заново».'}</p></div>`; return; }
  const sum = `<div class="sem-tiles rv-tiles">${E.map(e => `<div class="stile"><b>${num(e.missing.length)}</b><span>${plural(e.missing.length, 'тема', 'темы', 'тем')} есть у ${esc(e.host)}, а у вас нет${e.have ? ` · общих: ${num(e.have)}` : ''}</span></div>`).join('')}</div>`;
  $('rvList').innerHTML = sum + `<div class="card glist"><div class="lprow ghead"><span>Тема и спрос</span><span>Страница у конкурента</span><span>Что сделать</span><span></span></div>
    ${all.slice(0, rvShown).map(m => { const g = DATA.groups[m.i];
      return `<div class="lprow"><div class="lp-g"><a href="#g/${m.i}">${esc(m.name)}</a><div class="lp-main">${num(m.n)} ${plural(m.n, 'запрос', 'запроса', 'запросов')}</div></div>
        <div>${m.urls.map(u => `<a class="mono gurl" href="${esc(u)}" target="_blank" title="${esc(u)}">${esc(host(u) + path(u))}</a>`).join('')}${g && g.land && g.land.url ? `<div class="lp-new">Предлагаемый адрес: <span class="mono">${esc(g.land.url)}</span></div>` : ''}</div>
        <div><span class="pill ${m.st === 'create' ? 'p-create' : 'p-absent'}">${m.st === 'create' ? LAND.create[0] : LAND.absent[0]}</span>${g && g.todo ? `<div class="lp-new">${esc(g.todo)}</div>` : ''}</div><a class="gopen" href="#g/${m.i}" aria-label="Открыть группу">›</a></div>`; }).join('')}
    ${all.length > rvShown ? `<p class="sem-more"><button class="btn small" id="rvMore">Показать ещё ${num(Math.min(all.length - rvShown, 100))}</button></p>` : ''}</div>`;
  const b = $('rvMore'); if (b) b.onclick = () => { rvShown += 100; rivalsPage(); };
}
function tzHtml(g){ const x = tzInner(g); return x.trim() ? `<div class="brief">${x}</div>` : ''; }
