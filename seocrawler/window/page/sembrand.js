// Вкладка «Бренды» на странице «Семантика»: какие бренды ищут, есть ли страница бренда и товары, есть ли у конкурентов,
// таблица «бренд × категория» и как пишут бренды. Сервер: semantics/brands.py (/api/semdec/brands).
// Общие $, esc, num, plural, host, path, FOLDER, lc - из semantics.js.
let BR = null, brLoaded = '', brFlt = '', brKind = '', brShown = 50, brMxShown = 30;
const BR_CLS = {have: 'good', filter: 'acc', create: 'warn', rival: 'mut', low: 'mut', decide: 'mut'};

function brOpen(){
  catLoad();
  if (brLoaded === FOLDER && BR) return;
  brLoaded = FOLDER; BR = null; brKind = ''; $('brView').hidden = true; $('brWait').hidden = false;
  $('brWait').textContent = 'Ищу бренды в запросах, на сайте и у конкурентов…';
  fetch('/api/semdec/brands?f=' + encodeURIComponent(FOLDER)).then(r => r.json()).then(j => {
    if (brLoaded !== FOLDER) return;
    BR = j; $('cntBrands').textContent = num(j.brands.length);
    if (!j.brands.length) { $('brWait').textContent = 'Брендов в запросах и на сайте не нашлось. Если вы продаёте бренды, добавьте их на странице «Словарь», вид «Бренды».'; return; }
    $('brWait').hidden = true; $('brView').hidden = false; brDraw();
  }).catch(() => { $('brWait').textContent = 'Не получилось собрать бренды. Обновите страницу.'; });
}

const brDem = d => BR.freq ? `${num(d)} в месяц` : `спрос ${num(d)}`;
const brPill = st => `<span class="pill br-${BR_CLS[st] || 'mut'}">${esc((BR.labels.brand[st] || BR.labels.cell[st] || ''))}</span>`;

function brDraw(){
  const B = BR.brands, c = BR.count || {}, L = BR.labels.brand;
  const tile = (v, t, cls) => `<div class="stile${cls ? ' ' + cls : ''}"><b>${num(v)}</b><span>${t}</span></div>`;
  const pb = n => plural(n, 'бренд', 'бренда', 'брендов');
  const K = BR.kinds || {}, KN = BR.kind_names || {};
  $('brSrc').innerHTML = srcNote([BR.freq ? 'freq' : 'sug']);
  $('brMxSrc').textContent = BR.freq ? 'в месяц, ' + freqSrc() : `примерно, по подсказкам Яндекса и Google, собраны ${(DATA.made || '').slice(0, 10)}`;
  $('brTiles').innerHTML = tile(B.length, `${pb(B.length)} ищут или есть на сайте`)
    + [['have', 'good'], ['create', 'warn'], ['decide', 'mut']].filter(([k]) => c[k]).map(([k, cls]) => tile(c[k], `${pb(c[k])}: ${lc(L[k])}`, cls)).join('')
    + (K.for ? tile(K.for, `${plural(K.for, 'марка', 'марки', 'марок')}, для которых товары (раздел марок на сайте)`, '') : '')
    + (K.parts ? tile(K.parts, `${plural(K.parts, 'бренд', 'бренда', 'брендов')} комплектующих и материалов (логотипы на сайте)`, '') : '');
  const pills = [['', 'Все', B.length], ...['have', 'create', 'decide'].map(k => [k, L[k], c[k] || 0])];
  // марки, для которых товары («Запчасти для Audi»), и производители товаров - отдельно, если на сайте есть оба вида
  const kinds = K.for || K.parts ? [['for', 'Марки', K.for || 0], ['maker', 'Производители', K.maker || 0], ['parts', 'Комплектующие', K.parts || 0], ['-', 'Не понятно', B.length - (K.for || 0) - (K.maker || 0) - (K.parts || 0)]].filter(p => p[2]) : [];
  $('brFlt').innerHTML = pills.filter(p => !p[0] || p[2]).map(p => `<button class="fpill${p[0] === brFlt ? ' on' : ''}" data-k="${p[0]}">${esc(p[1])} <small>${num(p[2])}</small></button>`).join('')
    + (kinds.length ? '<span class="br-sep"></span>' + kinds.map(p => `<button class="fpill${p[0] === brKind ? ' on' : ''}" data-kind="${p[0]}" title="${esc(KN[p[0]] || 'Ни в разделе марок, ни в товарах сайта: бренд только из запросов или словаря')}">${esc(p[1])} <small>${num(p[2])}</small></button>`).join('') : '');
  brList(); brMatrix(); brForms();
}

function brList(){
  const q = $('brQ').value.trim().toLowerCase();
  const L = BR.brands.filter(b => (!brFlt || b.st === brFlt) && (!brKind || (b.kind || '-') === brKind) && (!q || b.name.toLowerCase().includes(q) || b.forms.some(f => f[0].includes(q))));
  $('brList').innerHTML = L.slice(0, brShown).map(b => {
    const forms = b.forms.filter(f => f[0] !== b.name.toLowerCase()).slice(0, 4).map(f => esc(f[0]) + (f[2] ? ` <i>(${esc(f[2])})</i>` : '')).join(', ');
    const rv = b.rivals.map(h => b.rp[h] ? `<a href="${esc(b.rp[h])}" target="_blank">${esc(h)}</a>` : esc(h)).join(', ');
    const kind = (b.kind && BR.kind_names ? ` <span class="mut" title="${esc(BR.kind_names[b.kind])}">· ${({for: 'марка', maker: 'производитель', parts: 'комплектующие'})[b.kind]}</span>` : '')
      + (b.logo ? ` <a class="mut" href="${esc(b.logo)}" target="_blank" title="Логотип или название в блоке брендов на этой странице сайта">· логотип на сайте</a>` : '');
    const models = (b.models || []).length ? `<div class="mut" title="Слова после бренда в запросах: модели и серии${b.sm ? `. На сайте моделей: ${num(b.sm)}` : ''}">Модели: ${b.models.map(m => `${esc(m[0])} ${num(m[1])}`).join(', ')}</div>` : '';
    return `<div class="br-row"><div><b>${esc(b.name)}</b>${kind}${b.user ? ' <span class="mut" title="Из словаря «Бренды»">· словарь</span>' : ''}${forms ? `<div class="mut">${forms}</div>` : ''}${models}</div>
      <div>${b.d ? brDem(b.d) : '-'}<div class="mut">${num(b.n)} ${plural(b.n, 'запрос', 'запроса', 'запросов')}</div></div>
      <div>${b.page ? `<a class="mono gurl" href="${esc(b.page)}" target="_blank" title="${esc(b.page)}">${esc(path(b.page))}</a>` : '<span class="mut">нет</span>'}</div>
      <div>${rv || '<span class="mut">нет</span>'}</div>
      <div>${b.products === null ? '<span class="mut" title="На сайте нет разметки товаров">?</span>' : num(b.products)}</div>
      <div>${brPill(b.st)}${b.q.length ? `<div class="mut">${esc(b.q.slice(0, 2).join(', '))}</div>` : ''}</div></div>`; }).join('')
    || '<p class="mut sem-none">Ничего не нашлось.</p>';
  $('brMore').innerHTML = L.length > brShown ? `<button class="btn small" id="brMoreB">Показать ещё ${num(Math.min(L.length - brShown, 100))}</button>` : '';
}

function brMatrix(){
  const cats = ['', ...BR.cats.slice(0, BR.cats_shown)], Lc = BR.labels.cell;
  const rows = BR.brands.filter(b => Object.keys(b.cats).length).slice(0, brMxShown);
  $('brLeg').innerHTML = ['have', 'filter', 'create', 'rival', 'low'].map(k => `<span class="br-${BR_CLS[k]}"><i></i>${esc(lc(Lc[k]))}</span>`).join('');
  const head = `<tr><th>Бренд</th>${cats.map(k => `<th>${esc(k || BR.alone)}</th>`).join('')}</tr>`;
  const body = rows.map(b => `<tr><th>${esc(b.name)}</th>${cats.map(k => { const c = b.cats[k];
    if (!c) return '<td></td>';
    const [n, d, st, url, q, rv] = c;
    const tip = `${b.name} · ${k || BR.alone}: ${Lc[st]}. ${num(n)} ${plural(n, 'запрос', 'запроса', 'запросов')}: ${q.join(', ')}${rv.length ? '. Есть у ' + rv.join(', ') : ''}${url ? '. Страница: ' + path(url) : ''}`;
    const v = d ? num(d) : num(n);
    return `<td class="br-${BR_CLS[st]}" title="${esc(tip)}">${url ? `<a href="${esc(url)}" target="_blank">${v}</a>` : v}</td>`; }).join('')}</tr>`).join('');
  $('brTable').innerHTML = `<thead>${head}</thead><tbody>${body}</tbody>`;
  const all = BR.brands.filter(b => Object.keys(b.cats).length).length;
  $('brMxMore').innerHTML = all > brMxShown ? `<button class="btn small" id="brMxB">Показать все ${num(all)}</button> <span class="mut">Все бренды и категории - в Excel, лист «Бренды по категориям».</span>`
    : '<span class="mut">Все категории - в Excel, лист «Бренды по категориям».</span>';
}

function brForms(){
  const L = BR.brands.filter(b => b.forms.length > 1).slice(0, 60);
  $('brForms').innerHTML = L.map(b => `<div><b>${esc(b.name)}</b> <span class="mut">${b.forms.map(f => `${esc(f[0])} ${num(f[1])}${f[2] ? ` (${esc(f[2])})` : ''}`).join(' · ')}</span></div>`).join('')
    || '<p class="mut">Все бренды пишут одинаково.</p>';
}

$('brFlt').addEventListener('click', e => {
  const k = e.target.closest('[data-kind]');
  if (k) { brKind = brKind === k.dataset.kind ? '' : k.dataset.kind; brShown = 50; brDraw(); return; }
  const b = e.target.closest('[data-k]'); if (!b) return; brFlt = b.dataset.k; brShown = 50; brDraw(); });
$('brQ').addEventListener('input', () => { brShown = 50; brList(); });
$('brMore').addEventListener('click', e => { if (e.target.id === 'brMoreB') { brShown += 100; brList(); } });
$('brTable').parentNode.addEventListener('fs-open', () => { if (brMxShown < 1e9) { brMxShown = 1e9; brMatrix(); } });
$('brMxMore').addEventListener('click', e => { if (e.target.id === 'brMxB') { brMxShown = 1e9; brMatrix(); } });
$('brDict').addEventListener('click', () => { brLoaded = ''; });

// Общая таблица «Бренды и прочие» (catalog.py): открыть Excel, подключить Google-таблицу через скрипт таблицы
let CAT = null;
function catLoad(){
  fetch('/api/catalog').then(r => r.json()).then(j => { CAT = j; catDraw(); }).catch(() => {});
}
function catDraw(){
  const g = CAT.google || {};
  $('catScript').value = CAT.script || '';
  $('catOpen').disabled = !CAT.exists;
  $('catGstate').innerHTML = g.url
    ? (g.error ? `Google-таблица: <span class="bad">${esc(g.error)}</span>`
       : `Google-таблица подключена${g.sheet ? ` - <a href="${esc(g.sheet)}" target="_blank">открыть</a>` : ''}${g.at ? `, отправлено ${esc(g.at.slice(8, 10) + '.' + g.at.slice(5, 7) + '.' + g.at.slice(0, 4) + ' ' + g.at.slice(11, 16))}` : ''}`)
    : '';
  $('catPush').hidden = !g.url;
  $('catOff').hidden = !g.url;
  $('catGset').textContent = g.url ? 'Настройка Google' : 'Подключить Google-таблицу';
  if (g.url && !$('catUrl').value) $('catUrl').value = g.url;
}
function catPost(body, wait){
  $('catMsg').textContent = wait || '';
  return fetch('/api/catalog', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
    .then(r => r.json()).then(j => { $('catMsg').textContent = j.error || ''; catLoad(); return !j.error; })
    .catch(() => { $('catMsg').textContent = 'Программа не ответила. Обновите страницу.'; });
}
$('catOpen').addEventListener('click', () => catPost({do: 'open'}));
$('catGset').addEventListener('click', () => { $('catSteps').hidden = !$('catSteps').hidden; });
$('catCopy').addEventListener('click', () => {
  navigator.clipboard.writeText($('catScript').value).then(() => { $('catMsg').textContent = 'Скрипт скопирован.'; },
    () => { $('catScript').select(); document.execCommand('copy'); $('catMsg').textContent = 'Скрипт скопирован.'; });
});
$('catSave').addEventListener('click', () => catPost({do: 'connect', url: $('catUrl').value}, 'Отправляю таблицу в Google…')
  .then(ok => { if (ok) { $('catSteps').hidden = true; $('catMsg').textContent = 'Готово: таблица отправлена, дальше программа будет обновлять её сама.'; } }));
$('catPush').addEventListener('click', () => catPost({do: 'push'}, 'Отправляю таблицу в Google…')
  .then(ok => { if (ok) $('catMsg').textContent = 'Отправлено.'; }));
$('catOff').addEventListener('click', () => { $('catUrl').value = ''; catPost({do: 'off'}); });
