// Вкладка «Спрос» на странице «Семантика»: Вордстат через Директ - узнаваемость, местный спрос, сезонность, ВЧ/СЧ/НЧ,
// что ещё искали, ёлочка. Сервер: window/semdemand.py (/api/semdemand), semantics/demand.py.
// Общие $, esc, num, plural, FOLDER - из semantics.js.
let DM = null, dmLoaded = '', dmTimer = null;
const dmPh = n => `${num(n)} ${plural(n, 'фраза', 'фразы', 'фраз')}`;
const dmG = (q, g) => g && g.toLowerCase() !== q.toLowerCase() ? ` <span class="mut">${esc(g)}</span>` : '';
const dmN = n => n == null ? '<span class="mut">-</span>' : num(n);

function dmOpen(){
  if (dmLoaded === FOLDER && DM) return;
  dmLoaded = FOLDER; DM = null; $('dmView').hidden = true; $('dmWait').hidden = false;
  $('dmWait').textContent = 'Смотрю, что уже загружено…';
  dmFetch();
}
async function dmFetch(){
  try {
    const j = await (await fetch('/api/semdemand?f=' + encodeURIComponent(FOLDER))).json();
    if (dmLoaded !== FOLDER) return;
    if (j.error) { $('dmWait').textContent = j.error; return; }
    DM = j; $('dmWait').hidden = true; $('dmView').hidden = false; dmDraw();
  } catch (e) { $('dmWait').textContent = 'Не получилось открыть. Обновите страницу.'; }
}
async function dmPost(body, btn){
  if (btn) btn.disabled = true;
  try {
    const r = await fetch('/api/semdemand', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.assign({f: FOLDER}, body))});
    const j = await r.json();
    if (!r.ok) { $('dmErr').textContent = j.error || 'Не получилось.'; if (btn) btn.disabled = false; return; }
    DM = j; dmDraw();
  } catch (e) { $('dmErr').textContent = 'Программа не ответила. Она запущена?'; if (btn) btn.disabled = false; }
}

// кнопка загрузки: сколько фраз уйдёт из суточного лимита
function dmBtn(act, label, cost, hint, upTo){
  const busy = (DM.run.queue || []).some(q => q.kind === act);
  if (busy) return `<button class="btn small" disabled>В очереди…</button>`;
  return `<button class="btn small primary" data-act="${act}" ${cost != null && !cost ? 'disabled' : ''} title="${esc(hint || 'Фразы уходят из того же суточного лимита Вордстата, что и загрузка частотности')}">${esc(label)}${cost ? ` (уйдёт ${upTo ? 'до ' : ''}${dmPh(cost)})` : cost === 0 && act === 'season' ? ' (бесплатно)' : ''}</button>`;
}

function dmHead(){
  const R = DM.run, Q = R.queue || [];
  const load = DM.load === 'running' ? 'Сейчас грузится и точная частотность: лимит общий.' : DM.load === 'waiting' ? 'Точная частотность ждёт нового дня.' : '';
  const q = Q.length ? `В очереди: ${Q.map(x => `${esc(x.label)} - готово ${num(x.total - x.left)} из ${dmPh(x.total)}`).join('; ')}. <button class="btn small" id="dmCancel">Отменить</button>` : '';
  const st = R.state === 'waiting' ? esc(R.msg) + ' Окно программы должно быть открыто.' : R.state === 'error' ? `<span class="err">${esc(R.msg)}</span>` : '';
  return `<section class="card dm-head"><h2>Спрос по Вордстату <span class="mut">через API Директа, бесплатно</span></h2>
    <p class="mut">Всё, что Вордстат знает о нише сверх частотности. Каждая фраза тратит тот же лимит, что и загрузка частотности: ${num(DM.limit)} фраз в сутки, сегодня отправлено ${num(DM.used)}. На кнопке видно, сколько фраз уйдёт; если лимита не хватит, остальное догрузится завтра само.</p>
    ${DM.has_token ? '' : '<p class="err">Ключ Директа не вставлен: Подключения → Яндекс Директ.</p>'}
    ${q || st || load ? `<p class="dm-run">${[q, st, esc(load)].filter(Boolean).join(' ')}</p>` : ''}<p class="err" id="dmErr"></p></section>`;
}

// подпись у цифр секции: Вордстат через Директ, регион и даты загрузки (пусто - ещё не загружалось)
const dmSrc = (at, region) => at ? `<p class="mut src-note">Откуда цифры: Вордстат через Директ, ${esc(region || DM.region)}, загружено ${esc(at)}.</p>` : '';

function dmBrand(){
  const B = DM.brand, city = B.city;
  const rows = B.sites.map(s => `<tr${s.own ? ' class="dm-own"' : ''}><td><b>${esc(s.host)}</b>${s.own ? ' <span class="pill bx-own">ваш сайт</span>' : ''}
      <input class="dm-names" data-site="${esc(s.host)}" value="${esc(s.names.join(', '))}" title="Как ищут: название по-русски и латиницей, через запятую. Проверьте написание: русское название из домена - догадка." aria-label="Названия ${esc(s.host)}"></td>
    ${city ? `<td class="num">${dmN(s.city)}</td>` : ''}<td class="num">${dmN(s.rf)}</td>
    <td class="mut dm-with">${s.rows.filter(r => r.with && r.with.length).map(r => r.with.slice(0, 4).map(w => `${esc(w[0])} <i>${num(w[1])}</i>`).join(', ')).join('; ')}</td></tr>`).join('');
  return `<section class="card"><h2>Узнаваемость: сколько ищут по названию</h2>
    <p class="mut">Сколько раз в месяц ищут каждую компанию по названию, вместе с любыми словами вокруг («газпрофсервис отзывы», «гигас адрес»). Чем больше, тем больше людей уже знают компанию и приходят не из рекламы. Названия можно поправить: русское название из домена программа угадывает на слух.</p>
    <div class="br-scroll"><table class="br-table dm-t"><tr><th>Сайт и названия</th>${city ? `<th>${esc(city)}</th>` : ''}<th>Россия</th><th>Что ищут вместе${city ? ` (${esc(city)})` : ''}</th></tr>${rows}</table></div>
    ${dmSrc(B.at, B.city ? B.city + ' и Россия' : 'Россия')}<div class="dm-go">${dmBtn('brand', 'Узнать узнаваемость', B.cost)}</div></section>`;
}

function dmLocal(){
  const L = DM.local;
  if (!L.city) return `<section class="card"><h2>Местный спрос</h2><p class="mut">Город семантики не задан: сравнивать не с чем.</p></section>`;
  const pct = x => x == null ? '<span class="mut">-</span>' : (x < 1 ? String(x).replace('.', ',') : num(Math.round(x))) + ' %';
  const KIND = {local: ['местный', 'bx-good', `Ищут в ${L.in} заметно чаще, чем обычно в нише: нужна страница под город, «в ${L.in}» в заголовке`], wide: ['по всей стране', 'mut', 'Ищут по всей стране: город в заголовке почти ничего не даст, важнее сама тема']};
  const rows = L.rows.map(r => `<tr><td>${esc(r.q)}${dmG(r.q, r.group)}</td><td class="num">${num(r.city)}</td><td class="num">${dmN(r.rf)}</td><td class="num">${pct(r.share)}</td>
    <td>${r.kind ? `<span class="${KIND[r.kind][1]}" title="${esc(KIND[r.kind][2])}">${KIND[r.kind][0]}</span>` : ''}</td></tr>`).join('');
  return `<section class="card"><h2>Местный спрос: ${esc(L.city)} и вся Россия</h2>
    <p class="mut">Самые востребованные в ${esc(L.in)} запросы ниши без названия города: сколько их ищут в городе и по всей России (фраза в кавычках). ${L.median ? `Обычно в этой нише на ${esc(L.city)} приходится около ${pct(L.median)} спроса России.` : ''} Запрос с долей заметно выше обычной - местный: под него нужна страница с городом в заголовке. Заметно ниже - ищут по всей стране.</p>
    ${L.rows.length ? `<div class="br-scroll"><table class="br-table dm-t"><tr><th>Запрос и группа</th><th>${esc(L.city)}</th><th>Россия</th><th>Доля города</th><th></th></tr>${rows}</table></div>`
      : '<p class="mut">Сначала загрузите точную частотность (кнопка «Загрузить частотность» вверху страницы): отсюда берутся самые востребованные запросы.</p>'}
    ${dmSrc([L.city_at && `${L.city} ${L.city_at}`, L.at && `Россия ${L.at}`].filter(Boolean).join(', '), `${L.city} и Россия`)}<div class="dm-go">${dmBtn('rf', 'Сравнить с Россией', L.cost)}</div></section>`;
}

const DM_MON = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const dmMon = m => DM_MON[+m.slice(5) - 1] + ' ' + m.slice(0, 4);
function dmSeason(){
  const S = DM.season;
  const intro = `<p class="mut">Вордстат через Директ показывает спрос только за последний месяц. Поэтому программа раз в месяц сама запоминает точную частоту ${num(30)} главных запросов (пока окно программы открыто, около 30 фраз из лимита в месяц). Через несколько месяцев здесь будет видно, когда в нише сезон: «зимой котлы ищут в 3 раза чаще».</p>`;
  if (!S.on) return `<section class="card"><h2>Своя сезонность</h2>${intro}<div class="dm-go">${dmBtn('season', 'Начать запоминать', S.start, 'Цифра этого месяца берётся из уже загруженной частотности бесплатно; чего нет - из лимита')}</div></section>`;
  const max = Math.max(...S.total, 1);
  const bars = S.months.length > 1 ? `<div class="dm-bars">${S.months.map((m, i) => `<div title="${dmMon(m)}: ${num(S.total[i])}"><i style="height:${Math.round(S.total[i] / max * 100)}%"></i><small>${dmMon(m)}</small></div>`).join('')}</div>` : '';
  const rows = S.rows.map(r => `<tr><td>${esc(r.q)}</td>${r.m.map(x => `<td class="num">${dmN(x)}</td>`).join('')}</tr>`).join('');
  return `<section class="card"><h2>Своя сезонность <span class="mut">${esc(S.region)}</span></h2>${intro}
    ${S.months.length < 2 ? `<p>Запомнено за ${S.months.map(dmMon).join(', ')}. График появится, когда будет хотя бы два месяца.</p>` : bars}
    <div class="br-scroll"><table class="br-table dm-t"><tr><th>Запрос</th>${S.months.map(m => `<th>${dmMon(m)}</th>`).join('')}</tr>
    <tr class="dm-own"><td><b>Все вместе</b></td>${S.total.map(x => `<td class="num"><b>${num(x)}</b></td>`).join('')}</tr>${rows}</table></div>
    ${dmSrc(S.months.length ? S.months.map(dmMon).join(', ') : '', S.region)}${S.cost ? `<div class="dm-go">${dmBtn('season', 'Записать этот месяц', S.cost)}</div>` : ''}</section>`;
}

function dmLevels(){
  const L = DM.levels;
  const intro = `<p class="mut">Метки не по общим таблицам («ВЧ - от 10 000 в месяц»), а по самой нише: в нише, где все запросы вместе ищут 300 раз в месяц, по таблицам всё было бы НЧ. ВЧ - самые востребованные запросы, которые вместе дают половину всего спроса ниши, СЧ - следующие, до 80 % спроса, НЧ - остальные. Бесплатно: считается по загруженной точной частоте. Метка видна и у числа в каждой группе.</p>`;
  if (!L) return `<section class="card"><h2>ВЧ, СЧ и НЧ для этой ниши</h2>${intro}<p class="mut">Нужна точная частотность хотя бы у 10 запросов: «Загрузить частотность» вверху страницы.</p></section>`;
  const tile = (n, t, s) => `<div class="stile"><b>${num(n)}</b><span>${t}${s ? `, ${s}` : ''}</span></div>`;
  return `<section class="card"><h2>ВЧ, СЧ и НЧ для этой ниши</h2>${intro}
    <div class="sem-tiles dm-tiles">${tile(L.n_hi, 'ВЧ', `от ${num(L.hi)} в месяц`)}${tile(L.n_mid, 'СЧ', `от ${num(L.mid)} до ${num(L.hi - 1)}`)}${tile(L.n_lo, 'НЧ', `меньше ${num(L.mid)}`)}${tile(L.n_zero, 'без спроса', 'точно 0')}</div>
    <p class="mut">Все запросы ниши вместе: ${num(L.total)} в месяц. Самые востребованные (ВЧ):</p>
    <ul class="dm-list">${L.top.map(x => `<li><span>${esc(x.q)}${dmG(x.q, x.group)}</span><b>${num(x.n)}</b></li>`).join('')}</ul>${dmSrc(L.at)}</section>`;
}

// новые запросы: дополнить группу / новые темы / статьи; кнопка - в «Разложить новые» (semsort.js)
function dmNew(V, key){
  const part = (t, a, hint, show) => a.length ? `<details class="dm-new"${show ? ' open' : ''}><summary><b>${t}</b> <span class="mut">${num(a.length)} · ${hint}</span></summary>
    <ul class="dm-list">${a.slice(0, 60).map(x => `<li><span>${esc(x.q)}${x.group && !x.group.startsWith('Не подошло') && !x.group.startsWith('Статьи') ? ` <span class="mut">→ ${esc(x.group)}</span>` : x.near ? ` <span class="mut">ближе всего к «${esc(x.near)}»</span>` : ''}</span><b>${num(x.n)}</b></li>`).join('')}</ul>
    ${a.length > 60 ? `<p class="mut">Ещё ${num(a.length - 60)} - в «Разложить новые».</p>` : ''}</details>` : '';
  const all = [...V.topics, ...V.add, ...V.articles];
  if (!all.length) return '';
  return part('Новые темы', V.topics, 'не подошли ни к одной группе: идеи новых разделов', true)
    + part('Дополнить группы', V.add, 'новые запросы для готовых групп', false)
    + part('Идеи статей', V.articles, 'вопросы', false)
    + `<div class="dm-go"><button class="btn small" data-sort="${key}" title="Вставить эти запросы на вкладке «Разложить новые», чтобы разложить по группам и скачать Excel">Разложить новые (${num(all.length)})</button>${V.dropped ? `<span class="mut">Отсеяно: ${num(V.dropped)} (чужие города, мусор, стоп-слова)</span>` : ''}</div>`;
}

function dmAlso(){
  const A = DM.also;
  return `<section class="card"><h2>Что ещё искали: соседние темы</h2>
    <p class="mut">Вордстат показывает, что ещё искали люди, которые искали запрос ниши: кто ищет котёл, ищет и дымоход. Отсюда идеи новых разделов и статей. Новая загрузка частотности собирает это сама, бесплатно; для уже загруженных запросов можно дозагрузить по ${num(40)} главным.</p>
    ${A.n ? `<p class="mut">Собрано по ${num(A.n)} ${plural(A.n, 'запросу', 'запросам', 'запросам')}. Уже собранные в семантике запросы не показаны.</p>` + (dmNew(A, 'also') || '<p class="mut">Ничего нового: всё уже есть в семантике.</p>') : ''}
    ${dmSrc(A.at)}<div class="dm-go">${dmBtn('also', 'Дозагрузить для главных запросов', A.cost)}</div></section>`;
}

function dmTree(){
  const T = DM.tree;
  return `<section class="card"><h2>Ёлочка: новые запросы из хвостов</h2>
    <p class="mut">По каждой главной фразе ниши Вордстат отдаёт до 200 запросов с ней («газовый котел бакси 24 квт»). Затем программа просит ещё раз, исключив самые частые слова (минус-слова «-купить -цена»), и Вордстат показывает то, что пряталось за ними. Новые запросы раскладываются по группам семантики. За одно нажатие - ${num(15)} главных фраз, по 2 фразы лимита на каждую.</p>
    ${T.roots.length ? `<p class="mut">Готово по ${num(T.roots.length)} ${plural(T.roots.length, 'фразе', 'фразам', 'фразам')}: ${T.roots.slice(0, 20).map(r => `${esc(r.q)} <i>${num(r.r1 + r.r2)}</i>`).join(', ')}. Найдено хвостов: ${num(T.found)}.</p>` + (dmNew(T, 'tree') || '<p class="mut">Ничего нового: всё уже есть в семантике.</p>') : ''}
    ${dmSrc(T.at)}<div class="dm-go">${dmBtn('tree', T.roots.length ? 'Ещё ёлочку' : 'Собрать ёлочку', T.cost, '', true)}</div></section>`;
}

function dmToSort(key){
  const V = DM[key];
  $('ssText').value = [...V.topics, ...V.add, ...V.articles].map(x => x.q + '\t' + x.n).join('\n');
  location.hash = '#sort';
}

function dmDraw(){
  $('dmView').innerHTML = dmHead() + dmBrand() + dmLocal() + dmSeason() + dmLevels() + dmAlso() + dmTree();
  $('dmView').querySelectorAll('[data-sort]').forEach(b => b.onclick = () => dmToSort(b.dataset.sort));
  $('dmView').querySelectorAll('[data-act]').forEach(b => b.onclick = () => dmPost({act: b.dataset.act}, b));
  $('dmView').querySelectorAll('.dm-names').forEach(i => i.onchange = () => dmPost({names: {site: i.dataset.site, text: i.value}}));
  const c = $('dmCancel'); if (c) c.onclick = () => dmPost({cancel: 1}, c);
  clearTimeout(dmTimer);
  if ((DM.run.queue || []).length) dmTimer = setTimeout(() => { if (dmLoaded === FOLDER && !$('dmView').hidden) dmFetch(); }, 5000);
}
