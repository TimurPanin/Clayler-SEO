// Часть страницы «Семантика» (page/semantics.js - выбор сайта, загрузка, сбор, экраны по адресу после #): «Запрос → страница», настоящие запросы, план статей, страницы мешают друг другу, GEO, страницы-фильтры, слова в запросах.
// Общие $, esc, num, plural, host, path, DATA, FOLDER, KIND, PAGE_SIZE и др. - из semantics.js (подключён раньше).
// ---------- вкладка «Запрос → страница»: какая страница под каждую группу
const LAND = {ok: ['Подходит', 'p-ok'], fix: ['Доработать', 'p-fix'], wrong: ['Не та страница', 'p-wrong'],
              create: ['Создать', 'p-create'], absent: ['Решить, нужна ли', 'p-absent']};
let lpSt = '', lpShown = PAGE_SIZE, LPLIST = [];
// видимость в Яндексе по группе (Букварикс, вкладка «Видимость»): [запросов, в десятке]; null - свой сайт не загружен
const yaOf = g => DATA.yandex ? DATA.yandex.groups[g.idx] || [0, 0] : null;
const yaText = v => !v ? 'нет данных' : v[0] ? `виден по ${num(v[0])} ${plural(v[0], 'запросу', 'запросам', 'запросам')}, в десятке ${num(v[1])}` : 'не виден';
function landPage(){
  const G = DATA.groups.filter(g => g.land && LAND[g.land.st]);
  const Y = DATA.yandex, nya = Y ? G.filter(g => !yaOf(g)[0]).length : 0;
  $('lpYaBox').hidden = !nya; if (!nya) $('lpYa').checked = false;
  $('lpYaBox').querySelector('span').textContent = `Не видны в Яндексе · ${num(nya)}`;
  $('lpSrc').innerHTML = srcNote(['freq', 'real', 'ya']) || (Y ? '' : '<p class="mut src-note">«В Яндексе»: загрузите ваш сайт во вкладке «Видимость» (Букварикс, бесплатно), и здесь будет видно, по каким группам сайт уже находится.</p>');
  const n = {}; G.forEach(g => n[g.land.st] = (n[g.land.st] || 0) + 1);
  n.other = G.filter(g => g.real && g.real.other).length;
  if (lpSt && !n[lpSt]) lpSt = '';
  $('cntPages').textContent = num(G.length);
  $('lpFlt').innerHTML = [['', 'Все', G.length], ...Object.keys(LAND).filter(k => n[k]).map(k => [k, LAND[k][0], n[k]]), ...(n.other ? [['other', 'Поиск показывает другую', n.other]] : [])]
    .map(([k, t, c]) => `<button class="fpill${k === lpSt ? ' on' : ''}" data-st="${k}">${t} <small>${num(c)}</small></button>`).join('');
  const q = $('lpQ').value.trim().toLowerCase();
  const byReal = G.some(g => g.real);   // есть настоящие запросы - сверху группы с большими показами
  const noYa = $('lpYa').checked;
  LPLIST = G.filter(g => (!lpSt || (lpSt === 'other' ? g.real && g.real.other : g.land.st === lpSt)) && (!noYa || !yaOf(g)[0]) && (!q || g.lname.includes(q) || (g.land.url || '').toLowerCase().includes(q)));
  if (byReal) LPLIST = LPLIST.slice().sort((a, b) => ((b.real || {}).shows || 0) - ((a.real || {}).shows || 0));
  else if (G.some(g => g.freq)) LPLIST = LPLIST.slice().sort((a, b) => (b.freq || 0) - (a.freq || 0));
  const main = g => (g.a && g.a.main) || ((g.q.find(r => !r[7]) || [])[0]) || '';
  $('lpList').innerHTML = LPLIST.length ? LPLIST.slice(0, lpShown).map(g => { const L = g.land, nq = g.q.filter(r => !r[7]).length;
    const page = L.new ? `<span class="mono gurl none" title="Предлагаемый адрес">${esc(L.url)}</span>${L.why ? `<div class="lp-why mut">${esc(L.why)}</div>` : ''}<div class="lp-new">${L.h1 ? `<div><b>H1:</b> ${esc(L.h1)}</div>` : ''}${L.title ? `<div><b>Title:</b> ${esc(L.title)}</div>` : ''}
        <button class="btn small" data-copy="${esc([L.url, L.h1 && 'H1: ' + L.h1, L.title && 'Title: ' + L.title].filter(Boolean).join('\n'))}">Скопировать</button></div>`
      : `<a class="mono gurl" href="${esc(L.url)}" target="_blank" title="${esc(L.url)}">${esc(path(L.url))}</a>${L.why ? `<div class="lp-why mut" title="Почему программа привязала группу к этой странице">${esc(L.why)}</div>` : ''}${faqLine(g)}${L.st === 'fix' ? `<div class="lp-new">${esc(g.a.problems[0])}${g.a.problems.length > 1 ? ` и ещё ${g.a.problems.length - 1}` : ''}</div>` : L.st === 'wrong' && g.landing ? `<div class="lp-new">${esc(g.landing.why || '')}</div>` : ''}`;
    const R = g.real, ya = yaOf(g);
    return `<div class="lprow lp5"><div class="lp-g"><a href="#g/${g.idx}">${esc(g.name)}</a><div class="lp-main">«${esc(main(g))}» · ${num(nq)} ${plural(nq, 'запрос', 'запроса', 'запросов')}${g.freq ? ` · <span title="Спрос в месяц: ${esc(freqSrc())}">спрос ${num(g.freq)} в месяц</span>` : ''}</div>${R ? `<div class="lp-real" title="Показы, переходы и место за 4 недели (Вебмастер, Search Console)">${realLine(R)}</div>` : ''}</div>
      <div>${page}${R && R.other ? `<div class="lp-new lp-other">Google показывает: <a class="mono" href="${esc(R.other.url)}" target="_blank">${esc(path(R.other.url))}</a></div>` : ''}</div><div><span class="pill ${LAND[L.st][1]}">${LAND[L.st][0]}</span></div>
      <div class="lp-ya"${ya ? '' : ' title="Загрузите ваш сайт во вкладке «Видимость»"'}><span class="${ya && ya[0] ? 'bx-good' : 'mut'}">${yaText(ya)}</span></div><a class="gopen" href="#g/${g.idx}" aria-label="Открыть группу">›</a></div>`; }).join('')
    : '<p class="mut sem-none">Ничего не нашлось.</p>';
  $('lpMore').innerHTML = LPLIST.length > lpShown ? `Показано ${num(lpShown)} из ${num(LPLIST.length)}  <button class="btn small" id="lpShowMore">Показать ещё</button>` : '';
}
$('lpYa').addEventListener('change', () => { lpShown = PAGE_SIZE; landPage(); });
$('lpFlt').addEventListener('click', e => { const b = e.target.closest('[data-st]'); if (!b) return; lpSt = b.dataset.st; lpShown = PAGE_SIZE; landPage(); });
let lpt; $('lpQ').addEventListener('input', () => { clearTimeout(lpt); lpt = setTimeout(() => { lpShown = PAGE_SIZE; landPage(); }, 150); });
$('lpMore').addEventListener('click', e => { if (e.target.id === 'lpShowMore') { lpShown += PAGE_SIZE; landPage(); } });
$('lpCopy').onclick = async () => {
  const cell = s => String(s || '').replace(/[\t\n]+/g, ' ');
  const Y = DATA.yandex, ya = Y ? `В Яндексе (Букварикс, ${Y.region}, ${Y.at})` : 'В Яндексе';
  const rows = [['Группа', 'Страница', 'Что с ней', 'Почему эта страница', ya, 'H1 новой', 'Title новой'], ...LPLIST.map(g => [g.name, g.land.url, LAND[g.land.st][0] + (g.land.new ? ' (новый адрес)' : ''), g.land.why || '', yaText(yaOf(g)), g.land.new ? g.land.h1 : '', g.land.new ? g.land.title : ''])];
  const b = $('lpCopy'), was = b.textContent;
  try { await navigator.clipboard.writeText(rows.map(r => r.map(cell).join('\t')).join('\n')); b.textContent = 'Скопировано'; } catch { b.textContent = 'Не вышло'; }
  setTimeout(() => { b.textContent = was; }, 1500); };

// ---------- настоящие запросы: Вебмастер и Search Console, запросы на 11–20 месте
const REAL_STATE = {not_connected: 'вход не подключён (меню слева, «Подключения»)',
  no_access: 'сайта нет в подключённом аккаунте: попросите владельца сайта дать вам доступ',
  no_data: 'запросов пока нет', error: 'не ответил, попробуйте собрать позже',
  no_link: 'нет связи (часто из-за VPN): выключите VPN или включите его для всех сайтов и соберите заново',
  no_scope: 'при входе в Google не отмечена галочка Search Console: «Подключения», «Подключить заново», отметить галочку',
  '': 'не загружались: семантика собрана старой версией, нажмите «Собрать заново»'};
function nearList(){
  const near = [];
  if (realOk()) DATA.groups.forEach(g => g.q.forEach(r => { if (r[8] >= 11 && r[8] <= 20) near.push([r, g]); }));
  return near.sort((a, b) => b[0][6] - a[0][6] || a[0][8] - b[0][8]);
}
function realCard(){
  const R = DATA.real || {}, near = nearList();
  if (!realOk()) {
    $('semNearT').textContent = 'Подключить Вебмастер и Search Console';
    $('semNearBody').innerHTML = `<p>Точные запросы, по которым сайт уже показывается в поиске (с показами и местом), берутся из Яндекс Вебмастера и Google Search Console, если у вас есть доступ к сайту.</p>
      <ul class="real-st"><li>Яндекс Вебмастер: ${esc(REAL_STATE[R.wm || ''] || R.wm)}</li><li>Google Search Console: ${esc(REAL_STATE[R.gsc || ''] || R.gsc)}</li></ul>
      <p class="mut">Владелец сайта может дать доступ в Вебмастере («Права доступа», делегировать ваш логин Яндекса) и в Search Console («Настройки», «Пользователи и разрешения», добавить вашу почту Google). Потом подключите вход в меню слева и нажмите «Собрать заново».</p>
      <div class="st-btns"><a class="btn primary" href="/#yandex">Подключить Яндекс</a><a class="btn" href="/#google">Подключить Google</a></div>`;
    return;
  }
  $('semNearT').textContent = near.length ? `Почти на первой странице: ${num(near.length)} ${plural(near.length, 'запрос', 'запроса', 'запросов')}` : 'Настоящие запросы';
  const src = [R.wm === 'ok' && 'Яндекс Вебмастера', R.gsc === 'ok' && 'Google Search Console', R.file === 'ok' && 'добавленных файлов'].filter(Boolean).join(' и ');
  $('semNearBody').innerHTML = `<p class="mut">Из ${src}: средняя позиция сайта за последние недели. Страница уже рядом с первой страницей выдачи: часто хватает поправить title и H1 под запрос, добавить абзац текста и пару внутренних ссылок.</p>`
    + (near.length ? `<table class="sq"><thead><tr><th>Запрос</th><th>Место</th><th>Показов</th><th>Группа</th></tr></thead><tbody>${near.slice(0, 40).map(([r, g]) =>
      `<tr><td>${esc(r[0])}</td><td>${String(r[8]).replace('.', ',')}</td><td>${num(r[6])}</td><td><a href="#g/${g.idx}">${esc(g.name)}</a></td></tr>`).join('')}</tbody></table>`
      + (near.length > 40 ? `<p class="mut">и ещё ${num(near.length - 40)}, все в Excel</p>` : '') : '<p class="mut">Запросов на 11–20 месте нет.</p>');
}

// ---------- план статей: информационные запросы → темы для блога
let artShown = 15;
function articlesCard(){
  const A = DATA.articles || [];
  if (!A.length) return;
  $('semArtT').textContent = `План статей для блога: ${num(A.length)} ${plural(A.length, 'тема', 'темы', 'тем')}`;
  $('semArtList').innerHTML = A.slice(0, artShown).map(a => `<div class="art"><div class="art-t"><b>${esc(a.title)}</b><span class="mut">${num(a.n)} ${plural(a.n, 'запрос', 'запроса', 'запросов')} · группа «${esc(a.group)}»</span></div>
    <div class="art-q">${a.queries.slice(0, 6).map(q => `<span>${esc(q)}</span>`).join('')}</div>
    ${a.link ? `<div class="mut">Ссылка из статьи: <a href="${esc(a.link)}" target="_blank">${esc(path(a.link))}</a></div>` : ''}</div>`).join('');
  $('semArtMore').innerHTML = A.length > artShown ? `<button class="btn small" id="semArtAll">Показать все ${num(A.length)}</button> <span class="mut">Весь план на листе «План статей» в Excel.</span>` : '';
}
$('semArtMore').addEventListener('click', e => { if (e.target.id === 'semArtAll') { artShown = 1e9; articlesCard(); } });

// ---------- страницы мешают друг другу
function cannPage(){
  const C = DATA.cannibal || [];
  $('semCann').innerHTML = C.length ? C.map((c, i) => `<details class="case card" data-case="${i}"${i === 0 ? ' open' : ''}>
    <summary><b>${esc(c.why)}</b><span class="mut">${c.pages.length} ${plural(c.pages.length, 'страница', 'страницы', 'страниц')}</span><span class="case-st" data-case="${i}"></span></summary>
    <div class="case-body"><div class="f-label">Страницы</div>
      ${c.pages.map(p => `<div class="case-p"><a class="mono" href="${esc(p.url)}" target="_blank">${esc(path(p.url))}</a>
        <span class="mut">${p.group ? 'группа «' + esc(p.group) + '»' : ''}</span>${p.url === c.main ? '<span class="pill p-page">оставить главной</span>' : `<span class="mut">${p.group ? 'свои title и H1 по своей группе' : 'свои title и H1'}</span>`}</div>`).join('')}
      <div class="cann-decision" data-case="${i}"></div><div class="cann-task" data-case="${i}"></div></div></details>`).join('')
    : '<div class="card sem-none"><p class="mut">Страниц, которые мешают друг другу, не найдено.</p></div>';
  if (window.semDec) semDec.cann();
}

// ---------- GEO: готовность к нейросетям и вопросы для блоков «вопрос - ответ»
function geoCard(){
  const geo = DATA.geo || {checks: []}, list = geo.checks || [];
  const ok = list.filter(c => c.ok).length;
  $('semGeoT').textContent = `Готовность к нейросетям (GEO): ${ok} из ${list.length}`;
  $('semGeoList').innerHTML = list.map(c => `<div class="geo-row"><span class="geo-ic ${c.ok ? 'ok' : c.ok === false ? 'bad' : 'unk'}">${c.ok ? '✓' : c.ok === false ? '✗' : '?'}</span>
    <div><b>${esc(c.name)}</b><div class="mut">${esc(c.text)}</div>${c.fix ? `<div class="geo-fix">${esc(c.fix)}</div>` : ''}</div></div>`).join('');
  const withFaq = DATA.groups.filter(g => g.faq && g.faq.length);
  $('semFaq').hidden = !withFaq.length;
  $('semFaqList').innerHTML = withFaq.map(g => `<div class="faq-g"><div class="art-t"><a href="#g/${g.idx}"><b>${esc(g.name)}</b></a>${g.page ? `<span class="mono mut">${esc(path(g.page))}</span>` : ''}</div>
    <ol class="faq">${g.faq.map(q => `<li>${esc(q)}</li>`).join('')}</ol></div>`).join('');
}
// «Запрос → страница»: вопросы «что это» в группе - не повод для отдельной страницы, а блок «вопрос - ответ» на этой
// (идея из разговора с ChatGPT, 29.10.2026; сами вопросы - в карточке группы и в ТЗ копирайтеру)
function faqLine(g){
  const n = (g.faq || []).length; if (!n) return '';
  return `<div class="lp-why mut" title="${esc(g.faq.slice(0, 5).join('; '))}">Вопросов «что это, как» в группе: ${num(n)} - ответить блоком «вопрос - ответ» на этой странице, <a href="#g/${g.idx}">список</a></div>`;
}
function faqHtml(g){
  if (!g.faq || !g.faq.length) return '';
  const has = g.page && ((DATA.geo || {}).faq_pages || []).includes(g.page);
  return `<div class="brief"><div class="bf-h">Вопросы для блока «вопрос - ответ» <span class="mut">· такие ответы чаще всего берут Нейро и другие нейросети</span></div>
    <ol class="faq">${g.faq.map(q => `<li>${esc(q)}</li>`).join('')}</ol>
    <p class="mut">${has ? 'Разметка FAQPage на странице уже есть: дополните вопросами.' : 'Ответ: 2–3 предложения с конкретикой (цифры, модели, цены), блок разметить FAQPage.'}
    <button class="btn small" data-copy="${esc(g.faq.join('\n'))}">Скопировать</button></p></div>`;
}

// ---------- страницы-фильтры
function fltHtml(g){
  if (!g.f || !g.f.length) return '';
  return `<div class="brief"><div class="bf-h">Страницы-фильтры в этой группе</div>${g.f.map(f => `<div class="flt-row in">
    <span title="${esc(f.sample.join(' · '))}">${esc(f.name)}</span><span>${num(f.queries)} ${plural(f.queries, 'запрос', 'запроса', 'запросов')}</span>
    <span class="fp${f.products >= 3 ? ' ok' : ''}">${f.products ? (f.example ? `<a href="${esc(f.example)}" target="_blank">${num(f.products)} ${plural(f.products, 'товар', 'товара', 'товаров')}</a>` : num(f.products)) : 'нет товаров'}</span></div>`).join('')}</div>`;
}
function fltList(){
  const all = [];
  DATA.groups.forEach(g => (g.f || []).forEach(f => all.push([g, f])));
  return all.sort((a, b) => (b[1].products >= 3) - (a[1].products >= 3) || b[1].queries - a[1].queries);
}
function filtersCard(){
  const all = fltList(), ok = all.filter(([, f]) => f.products >= 3).length;
  if (!all.length) return;
  $('semFltT').textContent = `Страницы-фильтры: ${num(all.length)}${ok ? `, под ${num(ok)} на сайте уже есть товары` : ''}`;
  const draw = () => {
    $('semFltList').innerHTML = all.slice(0, fltShown).map(([g, f]) => `<div class="flt-row">
      <span title="${esc(f.sample.join(' · '))}"><b>${esc(f.name)}</b></span><a class="mut" href="#g/${g.idx}">${esc(g.name)}</a>
      <span>${num(f.queries)}</span><span class="fp${f.products >= 3 ? ' ok' : ''}">${f.products ? (f.example ? `<a href="${esc(f.example)}" target="_blank">${num(f.products)}</a>` : num(f.products)) : '-'}</span></div>`).join('');
    $('semFltMore').innerHTML = all.length > fltShown ? `<button class="btn small" id="semFltAll">Показать все ${num(all.length)}</button>` : '';
  };
  draw();
  $('semFltMore').onclick = e => { if (e.target.id === 'semFltAll') { fltShown = all.length; draw(); } };
}

// ---------- слова в запросах: выбрать лишние и убрать
function words(){
  // сначала - слова из сомнительных запросов (их нет на страницах сайтов): чаще всего это и есть лишнее
  const cnt = new Map(), odd = new Map();
  // город сайта в любой форме («уфа», «уфе», «уфы») - не лишнее слово; до 16.10.2026 здесь были зашиты «уфа», «уфе»
  const city = toks((DATA.city || '').toLowerCase()).filter(w => w.length >= 3).map(w => w.slice(0, -1));
  DATA.groups.forEach(g => g.q.forEach(r => new Set(toks(r[0])).forEach(t => {
    if (t.length < 3 || WSKIP.has(t) || /^\d+$/.test(t) || city.some(c => t.startsWith(c))) return;
    cnt.set(t, (cnt.get(t) || 0) + 1);
    if (r[7] && r[7].includes(t)) odd.set(t, (odd.get(t) || 0) + 1); })));
  WORDS = [...cnt].map(([w, n]) => [w, n, odd.get(w) || 0]).sort((a, b) => (b[2] > 0) - (a[2] > 0) || b[2] - a[2] || b[1] - a[1]);
  drawWords();
}
function drawWords(){
  const q = $('semWq').value.trim().toLowerCase();
  const list = WORDS.filter(([w]) => !STOP.has(w) && (!q || w.includes(q))).slice(0, q ? 300 : 400);
  $('semWlist').innerHTML = list.map(([w, n, o]) => `<button class="wchip${PICK.has(w) ? ' on' : ''}${o ? ' odd' : ''}" data-w="${esc(w)}"${o ? ' title="Этого слова нет на страницах сайтов, возможно, лишнее"' : ''}>${esc(w)} <span>${num(n)}</span></button>`).join('') || '<span class="mut">Нет таких слов.</span>';
  $('semWsaved').innerHTML = STOP.size ? `<span class="mut">Убираются всегда:</span> ${[...STOP].map(w => `<button class="wchip saved" data-unstop="${esc(w)}" title="Вернуть">${esc(w)} ×</button>`).join('')}` : '';
  $('semWsave').disabled = !PICK.size;
  $('semWsave').textContent = PICK.size ? `Запомнить (${PICK.size})` : 'Запомнить';
  $('semWclear').hidden = !PICK.size;
}
async function saveStop(body){
  const r = await fetch('/api/semantics_stop', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (r.ok) STOP = new Set((await r.json()).words);
}
$('semWlist').addEventListener('click', e => { const b = e.target.closest('[data-w]'); if (!b) return;
  const w = b.dataset.w; PICK.has(w) ? PICK.delete(w) : PICK.add(w); drawWords(); shown = PAGE_SIZE; render(); });
$('semWsaved').addEventListener('click', async e => { const b = e.target.closest('[data-unstop]'); if (!b) return;
  await saveStop({remove: [b.dataset.unstop]}); drawWords(); render(); });
$('semWsave').onclick = async () => { await saveStop({add: [...PICK]}); PICK.clear(); drawWords(); render(); };
$('semWclear').onclick = () => { PICK.clear(); drawWords(); render(); };
let wt; $('semWq').addEventListener('input', () => { clearTimeout(wt); wt = setTimeout(drawWords, 150); });
