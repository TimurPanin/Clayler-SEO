// Страница «Семантика»: выбор сайта и сбор, сверху задачи по важности, ниже вкладки «Группы запросов»,
// «Запрос → страница», «Карта спроса», «Отсеяно», «Разложить новые» (page/semsort.js). Отдельные экраны (адрес после #): группа #g/N, «Страницы мешают друг другу» #cann,
// настоящие запросы #near, страницы-фильтры #flt, нейросети #geo, план статей #art.
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = n => (n || 0).toLocaleString('ru');
const host = u => { try { return new URL(u).host.replace(/^www\./, ''); } catch { return u; } };
const path = u => { try { const x = new URL(u); return decodeURI(x.pathname) + x.search; } catch { return u; } };
const plural = (n, a, b, c) => { n = Math.abs(n) % 100; const m = n % 10;
  return n > 10 && n < 20 ? c : m > 1 && m < 5 ? b : m === 1 ? a : c; };
// вид группы: подпись на метке, пояснение во вкладке. Слова приходят с сервера (semantics/labels.py, DATA.labels) -
// одни для окна, отчёта для клиента, Excel и Telegram; здесь - запасные, если сервер старый
let KIND = {page: ['Есть на сайте', 'страница под эти запросы на сайте есть, её продвигать'], create: ['Создать', 'спрос есть, а подходящей страницы на сайте нет'],
            absent: ['Решить, нужна ли', 'на сайте нет ни страницы, ни товаров: решить, нужна ли такая страница'], manual: ['Разобрать вручную', 'запросы не подошли ни к одной группе']};
const lc = s => s.charAt(0).toLowerCase() + s.slice(1);
// круглое число для примерного счёта: 9016 → 9000, 1460 → 1500 (как fmt.approx)
const approx = n => { n = Math.round(n || 0); if (Math.abs(n) < 100) return n; const k = 10 ** Math.max(1, String(Math.abs(n)).length - 2); return Math.round(n / k) * k; };
function setLabels(L){
  if (!L) return;
  KIND = L.kind;
  Object.keys(LAND).forEach(k => { if (L.status[k]) LAND[k][0] = L.status[k][0]; });
}
const PAGE_SIZE = 50;

let STOP = new Set(), PICK = new Set(), WORDS = [], fltShown = 30;   // стоп-слова: сохранённые и выбранные сейчас
const WSKIP = new Set('для на в и с по от до из под без или как что это при купить цена цены'.split(' '));   // и город сайта - semcards.js words()
const toks = q => q.split(/[^a-zа-яё0-9-]+/).filter(Boolean);
// другие формы того же запроса («группы безопасности» у «группа безопасности»): Вордстат считает их вместе
const formsTag = r => r[14] && r[14].length ? ` <span class="qforms" title="Тот же запрос в другой форме или с другим порядком слов. Вордстат считает их вместе, поэтому это одна строка. Если форма значит другое (одна страница или каталог), её можно вести на другую страницу.">также: ${r[14].map(esc).join(', ')}</span>` : '';
const hiddenRow = r => (STOP.size || PICK.size) && toks(r[0]).some(t => STOP.has(t) || PICK.has(t));
let dirFolder = '';
let REP = null, DATA = null, FOLDER = '', tab = 'all', intent = '', shown = PAGE_SIZE, wasRunning = false, LIST = [], prio = '';
// номер выбора сайта: ответ, пришедший после выбора другого сайта, не рисуется (иначе на mebel-primer.ru было видно
// семантику gasmaster, которая грузилась при открытии страницы)
let SITE_SEQ = 0;

function finished(g){ return g.checks.find(c => c.finished && !c.running) || null; }
function withSem(g){ return g.checks.find(c => c.has_semantics) || null; }
function when(s){ const m = /^(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d)/.exec(s || ''); if (!m) return '';
  return new Date(+m[1], m[2] - 1, +m[3]).toLocaleDateString('ru', {day: 'numeric', month: 'long'}) + ` в ${m[4]}:${m[5]}`; }

async function loadSites(){
  REP = await (await fetch('/api/reports')).json();
  const want = new URLSearchParams(location.search).get('f');
  const sites = REP.sites.filter(finished).concat(REP.new_sites || []);   // и проекты новых сайтов (newsite.py)
  $('semSite').innerHTML = sites.length ? sites.map(g => `<option value="${esc(g.key)}">${esc(siteName(g))}${withSem(g) ? '  ·  семантика собрана' : ''}</option>`).join('')
    : '<option value="">Нет готовых проверок</option>';
  const pre = want && sites.find(g => g.checks.some(c => c.folder === want));
  if (pre) $('semSite').value = pre.key;
  else { const s = sites.find(withSem); if (s) $('semSite').value = s.key; }
  await pickSite();
}

// куда вернуться после окошка «Подключения» на главной (side.js): этот же сайт и вкладка
window.backUrl = () => '/semantics' + (FOLDER ? '?f=' + encodeURIComponent(FOLDER) : '') + location.hash;

function curGroup(){ return REP.sites.concat(REP.new_sites || []).find(g => g.key === $('semSite').value); }
const siteName = g => g.new_site ? 'Новый сайт: ' + g.new_site.name : host(g.site);

async function pickSite(){
  const g = curGroup(), my = ++SITE_SEQ;
  $('semErr').textContent = '';
  DATA = null; FOLDER = '';   // от прошлого сайта ничего не остаётся: конкуренты по адресу, режим, данные
  $('semRivUrls').value = ''; $('semDeep').checked = false;
  if (!g) { $('semGo').disabled = true; $('semRivList').innerHTML = ''; $('semMeta').textContent = '';
    showEmpty('Сначала проверьте сайт на главной странице программы, потом здесь можно собрать для него семантику.'); return; }
  const last = finished(g), sem = withSem(g);
  $('semGo').textContent = sem ? 'Собрать заново' : 'Собрать';
  const others = REP.sites.filter(x => x.key !== g.key).map(x => [x, finished(x)]).filter(([, c]) => c);
  $('semRivList').innerHTML = others.length ? others.map(([x, c]) => `<label class="rchip" title="Проверка ${esc(when(c.finished))}"><input type="checkbox" value="${esc(c.folder)}"><span>${esc(host(x.site))}</span></label>`).join('')
    : '<span class="mut">Других проверенных сайтов нет: конкурента можно проверить на главной странице.</span>';
  rivCount(); loadFiles();
  if (window.semMasks) semMasks.load(g, last, sem);   // маски и стоп-слова клиента (semmask.js)
  document.querySelectorAll('.site-crumb').forEach(x => x.textContent = siteName(g));
  if (!sem) { DATA = null; $('semMeta').innerHTML = '<span>Семантика ещё не собрана</span>'; $('semOpts').open = true;
    showEmpty(`<b>Для ${esc(host(g.site))} семантика ещё не собрана.</b><br><span class="solo-only">Что просело после обновлений поиска, видно по группам запросов. Соберите семантику в «<a href="#tasks">Запросы и задачи</a>», потом возвращайтесь сюда.</span><span class="solo-not">Отметьте конкурентов, если нужно, и нажмите «Собрать». Это несколько минут: программа спросит подсказки Яндекса и Google по каждому разделу сайта.</span>`); return; }
  if (my === SITE_SEQ) await loadData(sem.folder, last && last.folder !== sem.folder ? last : null);
}

function rivCount(){
  const n = $('semRivList').querySelectorAll('input:checked').length;
  const MAX5 = 'Не больше 5 конкурентов за раз.';   // чужие сообщения (маски ждут подтверждения) не стираем
  if (n > 5) $('semErr').textContent = MAX5; else if ($('semErr').textContent === MAX5) $('semErr').textContent = '';
  $('semGo').disabled = n > 5 || !curGroup();
  const urls = $('semRivUrls').value.split(/[\s,;]+/).filter(Boolean).length;
  $('semOptsSum').textContent = '· ' + [n + urls ? `конкурентов: ${n + urls}` : 'без конкурентов', $('semDeep').checked ? 'подробно' : 'обычный сбор',
    FILES.length && `файлов с запросами: ${FILES.length}`].filter(Boolean).join(' · ');
}

// ---------- запросы из файлов (Вордстат, Key Collector, выгрузки Вебмастера и Search Console)
let FILES = [];
const siteHost = () => { const g = curGroup(); return g ? host(g.site) : ''; };
function drawFiles(){
  $('semFiles').innerHTML = FILES.map(f => `<div class="sem-file"><span><b>${esc(f.name)}</b> <span class="mut">${num(f.n)} ${plural(f.n, 'запрос', 'запроса', 'запросов')} · ${esc(f.label)} · ${esc(f.at)}</span></span>
    <button class="btn small" data-unfile="${esc(f.name)}">Убрать</button></div>`).join('');
  rivCount();
}
async function loadFiles(){
  const h = siteHost(); FILES = [];
  if (h) { const j = await fetch('/api/semantics_files?host=' + encodeURIComponent(h)).then(r => r.json()).catch(() => ({}));
    if (h !== siteHost()) return;   // пока ждали, выбрали другой сайт
    FILES = j.files || []; }
  drawFiles();
}
async function postFiles(body){
  const r = await fetch('/api/semantics_files', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.assign({host: siteHost()}, body))});
  const j = await r.json().catch(() => ({}));
  if (j.files) { FILES = j.files; drawFiles(); }
  return r.ok ? j : {error: j.error || 'Не получилось.'};
}
$('semFile').addEventListener('change', async e => {
  const list = [...e.target.files]; e.target.value = ''; if (!list.length) return;
  const msg = []; let redo = false;
  for (const f of list) {
    $('semFileMsg').textContent = `Читаю ${f.name}…`;
    const b64 = await new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1] || ''); r.onerror = bad; r.readAsDataURL(f); });
    const j = await postFiles({name: f.name, data: b64});
    redo = redo || (!j.error && j.added.kind !== 'bukvarix');   // Букварикс - вкладка «Видимость», собирать заново не нужно
    msg.push(j.error ? j.error : `${f.name}: ${num(j.added.n)} ${plural(j.added.n, 'запрос', 'запроса', 'запросов')} (${j.added.label})`);
  }
  const ok = redo;
  $('semFileMsg').textContent = msg.join('; ') + (ok ? (DATA ? '. Собираю семантику заново, чтобы учесть.' : '. Учтётся при сборе.') : '');
  if (ok && DATA && !$('semGo').disabled) start();
});
$('semFiles').addEventListener('click', async e => { const b = e.target.closest('[data-unfile]'); if (!b) return;
  await postFiles({remove: b.dataset.unfile}); $('semFileMsg').textContent = 'Убрано. Учтётся при следующем сборе («Собрать заново»).'; });

function showEmpty(html){ $('semView').hidden = true; dirFolder = ''; FOLDER = ''; if (window.semDirectOff) semDirectOff(); $('semEmpty').hidden = false; $('semEmpty').innerHTML = `<p>${html}</p>`;
  $('semXlsx').hidden = $('semTz').hidden = $('semFolder').hidden = true; }

async function loadData(folder, newer){
  const my = SITE_SEQ;
  const r = await fetch('/api/semantics?f=' + encodeURIComponent(folder));
  if (my !== SITE_SEQ) return;   // пока грузилось, выбрали другой сайт
  if (!r.ok) { showEmpty('Не получилось прочитать семантику. Соберите её заново.'); return; }
  const data = await r.json();
  if (my !== SITE_SEQ) return;
  DATA = data; FOLDER = folder; shown = PAGE_SIZE;
  setLabels(DATA.labels);
  // отметить конкурентов, с которыми собирали прошлый раз
  $('semRivList').querySelectorAll('input').forEach(i => {
    const g = REP.sites.find(x => x.checks.some(c => c.folder === i.value));
    i.checked = !!g && DATA.competitors.includes(host(g.site)); });
  $('semRivUrls').value = (DATA.light || []).join(', ');
  $('semDeep').checked = !!DATA.deep;
  rivCount();
  // спрос группы - по месту среди всех групп: верхняя треть - высокий
  const scores = DATA.groups.map(g => g.score).sort((a, b) => b - a);
  const hi = scores[Math.floor(scores.length / 3)] || 0, mid = scores[Math.floor(scores.length * 2 / 3)] || 0;
  DATA.groups.forEach((g, i) => { g.idx = i; g.level = g.score >= hi ? 3 : g.score >= mid ? 2 : 1; g.lname = g.name.toLowerCase(); });
  $('semEmpty').hidden = true; $('semView').hidden = false;
  overview(newer);
  realCard(); articlesCard(); filtersCard(); words(); geoCard(); cannPage();
  tasks();
  render(); landPage(); rivalsPage();
  route();
  if (window.semDec) semDec.load(newer);  // решения: галочки, смешанные группы, задачи разработчику (semdec.js)
  if (window.semMap) try { semMap(DATA); } catch (e) { console.error(e); }  // карта спроса - дополнение, сбой не мешает списку
  if (window.semDirect && FOLDER !== dirFolder) { dirFolder = FOLDER; semDirect(); }  // точная частотность из Директа (semdirect.js)
}
// откуда частотность в «Спросе»: Директ (Вордстат по городу) или добавленный файл
// ВЧ/СЧ/НЧ относительно самой ниши (semantics/demand.levels): ВЧ - запросы, которые вместе дают половину спроса ниши
const lvlOf = n => { const L = DATA && DATA.direct && DATA.direct.levels; return !L || !n ? '' : n >= L.hi ? 'ВЧ' : n >= L.mid ? 'СЧ' : 'НЧ'; };
const lvlTag = n => lvlOf(n) ? `<small class="qlvl l-${lvlOf(n)}">${lvlOf(n)}</small> ` : '';
const lvlTitle = n => lvlOf(n) ? `. ${lvlOf(n)} для этой ниши (ВЧ - от ${num(DATA.direct.levels.hi)}, СЧ - от ${num(DATA.direct.levels.mid)} в месяц)` : '';
const srcFiles = kind => (DATA.src_files || []).filter(f => f.kind === kind).map(f => `«${f.name}» (добавлен ${f.at})`).join(', ');
const freqSrc = () => DATA && DATA.direct ? `Вордстат через Директ, ${DATA.direct.region}, фраза в кавычках, ${DATA.direct.dates || DATA.direct.at}`
  : srcFiles('freq') ? 'из файла ' + srcFiles('freq') : 'из добавленного файла (Вордстат и т. п.)';
// Откуда цифры и от какого числа: одна подпись у чисел спроса и видимости на всех вкладках («Запрос → страница», группы,
// карта, бренды). Ключи: freq - частотность в месяц, sug - примерный спрос по подсказкам, real - показы и места,
// ya - видимость в Яндексе по Буквариксу. Нет данных - часть не пишется.
function srcNote(keys){
  const R = DATA.real || {}, Y = DATA.yandex, made = (DATA.made || '').slice(0, 10);
  const api = [R.wm === 'ok' && 'Яндекс Вебмастер', R.gsc === 'ok' && 'Google Search Console'].filter(Boolean);
  const P = {freq: DATA.groups.some(g => g.freq) ? 'спрос в месяц - ' + freqSrc() : '',
    sug: !DATA.groups.every(g => g.freq) ? `примерный спрос - подсказки Яндекса и Google, собраны ${made}` : '',
    real: [api.length && `показы и места - ${api.join(' и ')} за 4 недели до ${made}`,
           R.file === 'ok' && srcFiles('stats') && 'показы и места из файла ' + srcFiles('stats')].filter(Boolean).join('; '),
    ya: Y ? `«В Яндексе» - Букварикс, Яндекс ${Y.region}, загружено ${Y.at}` : ''};
  const t = keys.map(k => P[k]).filter(Boolean);
  return t.length ? `<p class="mut src-note">Откуда цифры: ${esc(t.join('; '))}.</p>` : '';
}

const realOk = () => { const R = DATA.real || {}; return R.wm === 'ok' || R.gsc === 'ok' || R.file === 'ok'; };
// почему нет настоящих запросов: не подключено, сайта нет в аккаунте или данных пока нет - это разные случаи
const realWhy = (name, st, who) => ({
  not_connected: `${name} не подключён (Подключения).`,
  no_access: `${name} подключён, но этого сайта в нём нет: нужен доступ от владельца.`,
  no_data: `${name} подключён и сайт в нём есть, но ${who} ещё не собрал по нему запросы (у нового или маленького сайта их может не быть).`,
  error: `${name} не ответил во время сбора - нажмите «Собрать заново» позже.`,
  no_link: `${name}: нет связи во время сбора, часто из-за VPN. Выключите VPN (или включите его для всех сайтов) и нажмите «Собрать заново».`,
  no_scope: `${name}: при входе в Google не отмечена галочка доступа к Search Console. Откройте «Подключения», нажмите «Подключить заново» у Google и отметьте галочку, потом «Собрать заново».`,
}[st] || (st === 'ok' ? '' : `${name}: запросы не загружались.`));
function droppedCount(){ return Object.values(DATA.dropped).reduce((s, l) => s + l.length, 0); }

function overview(newer){
  const k = {page: 0, create: 0, absent: 0, manual: 0}; DATA.groups.forEach(g => k[g.kind]++);
  const n = DATA.groups.length, nfix = DATA.groups.filter(g => g.a && g.a.problems.length).length, nd = droppedCount();
  $('semMeta').innerHTML = [`Собрано <b>${esc(DATA.made)}</b>`, `Город <b>${esc(DATA.city || 'вся Россия')}</b>`,
    `Конкуренты <b>${DATA.competitors.length ? esc(DATA.competitors.join(', ')) : 'не выбраны'}</b>`,
    `Режим <b>${DATA.deep ? 'подробный' : 'обычный'}</b>`,
    (DATA.wm || DATA.gsc) ? `Запросы из <b>${[DATA.wm && 'Вебмастера', DATA.gsc && 'Search Console'].filter(Boolean).join(' и ')}</b>` : ''
  ].filter(Boolean).map(x => `<span>${x}</span>`).join('');
  $('semXlsx').href = '/api/semdec/xlsx?f=' + encodeURIComponent(FOLDER);  // с учётом решений (semdec.py)
  $('semXlsx').hidden = false;
  $('cannXlsx').href = $('semXlsx').href;
  const ntz = DATA.groups.filter(g => g.kind === 'create' || (g.kind === 'page' && g.a && g.a.problems.length)).length;
  $('semTree').href = '/api/semdec/tree?f=' + encodeURIComponent(FOLDER);   // дерево сайта (semantics/tree.py)
  $('semTree').hidden = false;
  $('semFolder').hidden = false;   // папка проверки: там же Excel, ТЗ и дерево
  $('semStruct').hidden = !DATA.new_site;
  $('semRealHow').hidden = !!DATA.new_site;   // у нового сайта Вебмастера и Search Console нет   // новый сайт: структура для клиента (newsite.write_client)
  $('semStruct').href = '/r/' + encodeURIComponent(FOLDER) + '/' + encodeURIComponent('структура сайта.html');
  $('semTz').href = '/api/semantics_tz?f=' + encodeURIComponent(FOLDER);
  $('semTz').hidden = !ntz;
  $('semTz').textContent = `ТЗ копирайтеру · ${num(ntz)}`;
  // плитки
  const tile = (v, t, cls, pre = '', title = '') => `<div class="stile${cls ? ' ' + cls : ''}"${title ? ` title="${esc(title)}"` : ''}><b>${pre}${num(v)}</b><span>${t}</span></div>`;
  // без настоящих данных число запросов - примерное: часть подсказок может оказаться не про сайт (как в отчёте, fmt.approx)
  const rough = !realOk() && !DATA.groups.some(g => g.freq) && approx(DATA.total) !== DATA.total;
  $('semTiles').innerHTML = (rough ? tile(approx(DATA.total), `запросов в ${num(n)} ${plural(n, 'группе', 'группах', 'группах')}`, '', '≈ ',
      `Точно: ${num(DATA.total)}. Примерно, потому что спрос по подсказкам: часть запросов может оказаться не про сайт.`)
    : tile(DATA.total, `${plural(DATA.total, 'запрос', 'запроса', 'запросов')} в ${num(n)} ${plural(n, 'группе', 'группах', 'группах')}`))
    + (DATA.new_site ? '' : tile(k.page, `${plural(k.page, 'группа', 'группы', 'групп')}: ${lc(KIND.page[0])}`, 'good'))
    + tile(k.create, `${plural(k.create, 'группа', 'группы', 'групп')}: ${lc(KIND.create[0])}`, 'warn')
    + (DATA.new_site ? tile(k.absent, `${plural(k.absent, 'группа', 'группы', 'групп')}: ${lc(KIND.absent[0])}`, 'mut')
       : tile(nfix, `${plural(nfix, 'группа', 'группы', 'групп')}: ${lc(LAND.fix[0])}`, 'crit'))
    + tile(nd, `${plural(nd, 'запрос', 'запроса', 'запросов')} отсеяно`, 'mut');
  $('smapAt').textContent = DATA.made ? ', собраны ' + DATA.made.slice(0, 10) : '';
  $('cntGroups').textContent = num(n); $('cntMap').textContent = num(n); $('cntDropped').textContent = num(nd);
  // баннер: спрос примерный
  const R = DATA.real || {};
  $('semRealBanner').hidden = realOk() || DATA.groups.some(g => g.freq);  // частотность из файла - спрос уже не примерный
  $('semRealText').innerHTML = DATA.new_site ? 'Спрос <b>примерный</b>, по подсказкам поиска. Чтобы видеть частотность в месяц, добавьте файл Вордстата или Key Collector в «Конкуренты и режим сбора» и нажмите «Собрать заново».'
    : `Спрос <b>примерный</b>, по подсказкам поиска: нет настоящих показов и мест в поиске. ${realWhy('Вебмастер', R.wm, 'Яндекс')} ${realWhy('Search Console', R.gsc, 'Google')}`;
  $('semDist').innerHTML = ['page', 'create', 'absent', 'manual'].filter(x => k[x])
    .map(x => `<i class="d-${x}" style="flex:${k[x]}" title="${KIND[x][0]}: ${k[x]}"></i>`).join('');
  if (tab !== 'all' && !k[tab]) tab = 'all';
  $('semTabs').innerHTML = [['all', 'Все', n], ...['page', 'create', 'absent', 'manual'].filter(x => k[x]).map(x => [x, KIND[x][0], k[x]])]
    .map(([id, t, c]) => `<button role="tab" data-tab="${id}" class="fpill k-${id}${id === tab ? ' on' : ''}" title="${id === 'all' ? 'Все группы' : esc(KIND[id][1])}">${t} <small>${num(c)}</small></button>`).join('');
  $('semNewer').hidden = !newer;
  if (newer) $('semNewer').textContent = `Собрано по прошлой проверке. Есть проверка новее (${when(newer.finished)}): нажмите «Собрать заново».`;
  $('semFix').parentElement.querySelector('span').textContent = `С замечаниями · ${num(nfix)}`;
  $('semFix').parentElement.hidden = !nfix;
  drawDropped(nd);
}
function drawDropped(nd){
  nd = nd == null ? droppedCount() : nd;
  const reasons = Object.entries(DATA.dropped).sort((a, b) => b[1].length - a[1].length);
  $('semDroppedT').innerHTML = `Отсеяно ${num(nd)} ${plural(nd, 'запрос', 'запроса', 'запросов')} <span class="mut">чужие города, конкуренты, «скачать», не по теме</span>`;
  $('semDroppedList').innerHTML = nd ? reasons.map(([why, l]) => `<details class="sem-why"${why === FOREIGN ? ' id="semForeign"' : ''}><summary>${esc(why)} <span class="mut">${num(l.length)}</span></summary>${why === FOREIGN ? foreignHtml(l) : `<div class="qchips">${l.map(q => `<span>${esc(q)}</span>`).join('')}</div>`}</details>`).join('')
    : '<p class="mut">Ничего не отсеяно.</p>';
}

// «Отсеяно → слов нет на сайтах»: по словам, с кнопкой «Это про нас». Слово запоминается для сайта
// (маски, semantics/masks.set_ok), запросы с ним вернутся в группы при следующем «Собрать заново».
const FOREIGN = 'слов нет на сайтах';
function foreignHtml(l){
  const by = new Map();
  l.forEach(q => String((DATA.foreign || {})[q] || '').split(',').map(w => w.trim()).filter(Boolean)
    .forEach(w => { if (!by.has(w)) by.set(w, []); by.get(w).push(q); }));
  const ok = new Set(DATA.ok_words || []);
  const rows = [...by].sort((a, b) => b[1].length - a[1].length).map(([w, qs]) =>
    `<div class="fw-row"><button class="btn small${ok.has(w) ? '' : ' ghost'}" data-okw="${esc(w)}" title="${ok.has(w) ? 'Убрать из «про нас»' : 'Слово по теме сайта: запросы с ним вернутся в группы при следующем «Собрать заново»'}">${ok.has(w) ? '✓ про нас' : 'Это про нас'}</button>
      <b>${esc(w)}</b> <span class="mut">${num(qs.length)} ${plural(qs.length, 'запрос', 'запроса', 'запросов')}: ${qs.slice(0, 4).map(esc).join('; ')}${qs.length > 4 ? '…' : ''}</span></div>`).join('');
  return `<p class="mut">Этих слов нет ни на одной странице вашего сайта и конкурентов, поэтому запросы с ними похожи на «про другое». Если слово по теме (марка, которую вы продаёте, ваша услуга), нажмите «Это про нас» и соберите семантику заново.</p>${rows}`;
}
$('semDroppedList').addEventListener('click', async e => {
  const b = e.target.closest('[data-okw]'); if (!b || !DATA) return;
  const w = b.dataset.okw, on = (DATA.ok_words || []).includes(w);
  const r = await fetch('/api/semantics_ok', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({host: DATA.host, [on ? 'remove' : 'add']: [w]})});
  if (!r.ok) return;
  DATA.ok_words = (await r.json()).ok;
  const d = $('semForeign'), open = d && d.open;
  drawDropped();
  const d2 = $('semForeign'); if (d2 && open) d2.open = true;
});

// ---------- сбор
async function start(){
  const g = curGroup(); const last = g && finished(g); if (!last) return;
  if (window.semMasks && !(await semMasks.ready())) return;   // сначала маски: предложить, показать, подтвердить
  const rivals = [...$('semRivList').querySelectorAll('input:checked')].map(i => i.value);
  $('semErr').textContent = '';
  const r = await fetch('/api/semantics', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({folders: [last.folder, ...rivals], deep: $('semDeep').checked,
    hosts: $('semRivUrls').value.split(/[\s,;]+/).filter(Boolean)})});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { $('semErr').textContent = j.error || 'Не получилось запустить.'; return; }
  poll();
}

window.semStart = start; window.semPoll = () => poll();
window.semReload = async () => { const keep = $('semSite').value; await loadSites(); $('semSite').value = keep; await pickSite(); };
$('semStop').onclick = async () => { $('semStop').disabled = true; $('semStop').textContent = 'Останавливаю…'; await fetch('/api/stop', {method: 'POST'}); };
async function poll(){
  const s = await (await fetch('/api/status')).json().catch(() => null);
  if (!s) return;
  const mine = (s.site || '').startsWith('семантика');
  $('semRun').hidden = !s.running;
  if (!s.running) { $('semStop').disabled = false; $('semStop').textContent = 'Остановить'; }
  $('semStop').hidden = !mine;
  $('semGo').disabled = s.running;
  $('semGo').title = s.running && !mine ? 'Сейчас идёт проверка сайта' : '';
  if (s.running) {
    const line = [...s.log].reverse().find(l => l.trim()) || 'Запускаю…';
    const m = line.match(/подсказки: (\d+) из (\d+)/);
    $('semBar').style.width = m ? (m[1] / m[2] * 100).toFixed(0) + '%' : '5%';
    $('semStep').textContent = mine ? line.trim() : 'Сейчас идёт проверка сайта: семантику можно собрать, когда она закончится.';
    wasRunning = true; setTimeout(poll, 1500); return;
  }
  if (wasRunning) { wasRunning = false; const keep = NS_NEW || $('semSite').value; NS_NEW = ''; await loadSites(); $('semSite').value = keep; await pickSite();
    const err = [...s.log].reverse().find(l => /Traceback|Ошибка|Error/.test(l));
    if (err && mine) $('semErr').textContent = 'Не получилось: ' + err; }
}

// ---------- экраны страницы по адресу после #
// экраны со своим пунктом в меню слева (side.js): без шапки, плиток и вкладок Семантики, из выбора сайта - только сам сайт
const SOLO = ['upd'];
const soloMark = () => document.querySelector('main.sem').classList.toggle('sem-solo', SOLO.includes(decodeURIComponent(location.hash.slice(1)).split('/')[0]));
soloMark();
function route(){
  soloMark();
  if (!DATA) return;
  const h = decodeURIComponent(location.hash.slice(1)) || 'tasks';
  let [v, arg] = h.split('/');
  if (v === 'groups' && arg) {  // из задачи: сразу нужный фильтр
    $('semFix').checked = arg === 'fix'; tab = KIND[arg] ? arg : 'all'; $('semQ').value = ''; shown = PAGE_SIZE;
    $('semTabs').querySelectorAll('button').forEach(x => x.classList.toggle('on', x.dataset.tab === tab)); render();
    history.replaceState(null, '', '#groups');
  }
  if (v === 'pages' && arg) { lpSt = LAND[arg] || arg === 'other' ? arg : ''; lpShown = PAGE_SIZE; landPage(); history.replaceState(null, '', '#pages'); }
  if (v === 'g') { grpShown = 30; groupPage(+arg); v = 'group'; }
  if (!document.querySelector(`.sv[data-sv="${v}"]`)) v = 'tasks';
  document.querySelectorAll('.sv').forEach(x => x.hidden = x.dataset.sv !== v);
  const sub = !['tasks', 'pages', 'groups', 'map', 'dropped', 'sort', 'brands', 'bx', 'demand', 'upd'].includes(v);
  if (v === 'sort' && window.ssOpen) ssOpen();
  if (v === 'brands' && window.brOpen) brOpen();
  if (v === 'bx' && window.bxOpen) bxOpen();
  if (v === 'demand' && window.dmOpen) dmOpen();
  if (v === 'upd' && window.upOpen) upOpen();
  ['semTiles', 'semRealBanner'].forEach(id => $(id).classList.toggle('off', sub));
  document.querySelector('.sem-hero').classList.toggle('off', sub); $('semNewer').classList.toggle('off', sub);
  document.querySelector('.sem-tabs').hidden = sub; $('pick').hidden = sub;
  document.querySelectorAll('.sem-tabs a').forEach(a => a.classList.toggle('on', a.dataset.v === v));
  if (v === 'geo' && arg === 'faq') setTimeout(() => $('semFaq').scrollIntoView({block: 'start'}), 0);
  else if (sub) window.scrollTo(0, 0);
}
window.addEventListener('hashchange', route);

// ---------- события
$('semSite').onchange = () => { history.replaceState(null, '', '/semantics'); pickSite(); };
$('semRivList').addEventListener('change', rivCount);
$('semRivUrls').addEventListener('input', rivCount); $('semDeep').addEventListener('change', rivCount);
$('semGo').onclick = start;

// ---------- новый сайт: проект без своего сайта (POST /api/semantics_new, semantics/newsite.py)
let NS_NEW = '';
$('semFolder').onclick = async () => {   // проводник с папкой проверки (то же, что «Открыть папку с файлами» в «Отчётах»)
  if (!FOLDER) return;
  await fetch('/api/open_folder', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({folder: FOLDER})});
};
$('nsOpen').onclick = () => {
  const box = $('nsCard'); box.hidden = !box.hidden; if (box.hidden) return;
  const done = REP.sites.map(x => [x, finished(x)]).filter(([, c]) => c);
  $('nsRivList').innerHTML = done.length ? done.map(([x, c]) => `<label class="rchip" title="Проверка ${esc(when(c.finished))}"><input type="checkbox" value="${esc(c.folder)}"><span>${esc(host(x.site))}</span></label>`).join('')
    : '<span class="mut">Проверенных сайтов нет: впишите адреса конкурентов ниже.</span>';
  $('nsErr').textContent = ''; box.scrollIntoView({block: 'start', behavior: 'smooth'}); $('nsName').focus();
};
$('nsCancel').onclick = () => { $('nsCard').hidden = true; };
$('nsGo').onclick = async () => {
  const body = {name: $('nsName').value, words: $('nsWords').value, city: $('nsCity').value, domain: $('nsDomain').value,
    folders: [...$('nsRivList').querySelectorAll('input:checked')].map(i => i.value),
    hosts: $('nsRivUrls').value.split(/[\s,;]+/).filter(Boolean)};
  $('nsErr').textContent = '';
  if (!body.words.trim()) { $('nsErr').textContent = 'Напишите хотя бы одно слово темы: чем будет заниматься сайт.'; return; }
  const r = await fetch('/api/semantics_new', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { $('nsErr').textContent = j.error || 'Не получилось запустить.'; return; }
  NS_NEW = j.folder; $('nsCard').hidden = true; poll();
};
$('semTabs').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; tab = b.dataset.tab; shown = PAGE_SIZE;
  $('semTabs').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); render(); });
let qt; $('semQ').addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(() => { shown = PAGE_SIZE; render(); }, 150); });
$('semFix').addEventListener('change', () => { shown = PAGE_SIZE; render(); });
document.addEventListener('click', async e => { const b = e.target.closest('[data-copy]'); if (!b) return;
  e.preventDefault(); const was = b.textContent;
  try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = 'Скопировано'; } catch { b.textContent = 'Не вышло'; }
  setTimeout(() => { b.textContent = was; }, 1500); });
// карта спроса: «Показать в списке» открывает страницу группы
document.addEventListener('click', e => { const b = e.target.closest('#smapInfo [data-show]'); if (!b || !DATA) return;
  const g = DATA.groups.find(x => x.name === b.dataset.show); if (!g) return;
  e.stopPropagation(); e.preventDefault(); location.hash = '#g/' + g.idx; }, true);
$('semIntent').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; intent = b.dataset.v; shown = PAGE_SIZE;
  $('semIntent').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); render(); });
$('semMore').addEventListener('click', e => { if (e.target.id === 'semShowMore') { shown += PAGE_SIZE; render(); } });

// запуск - когда загружены и остальные части страницы (semtasks.js, semgroups.js, semcards.js, semdec.js…)
document.addEventListener('DOMContentLoaded', () => {
  fetch('/api/semantics_stop').then(r => r.json()).then(j => { STOP = new Set(j.words || []); }).catch(() => {})
    .then(loadSites).then(poll);
});
