// Вкладка «Разложить новые» на странице «Семантика»: новые запросы по готовым группам и словари.
// Сервер: window/semsort.py (/api/semsort…). Общие $, esc, num, plural, FOLDER - из semantics.js.
let SS = null, ssFlt = '', ssShown = 100, SSD = null, ssKind = 'info', ssLoaded = '';
const SS_HOW = {'уверенно': 'ok', 'похоже': 'ok', 'спорно': 'warn', 'уже в группе': 'mut'};
const SS_HINT = {
  info: 'Запрос с таким словом или фразой - вопрос: ему нужна статья, а не страница товара. Слова сравниваются точно, поэтому пишите нужные формы («инструкция», «инструкции»). Если в запросе есть «купить», «цена», «заказать», маркер не считается.',
  gallery: 'Запрос с таким словом ищет фото и примеры работ: ему нужна галерея или портфолио.',
  synonyms: 'Слова одной строки через «=» считаются одним словом: «айфон = iphone», «стиралка = стиральная машина». Формы слова («айфоны») подходят сами.',
  ignore: 'Эти слова не учитываются, когда запрос сравнивается с группами: они говорят о покупке, а не о товаре. Запросы с ними не убираются.',
  axes: 'Признаки для карты признаков в «Дереве сайта»: строка «Признак: слово, слово», например «Цвет: белый, черный». Формы слова подходят сами. Что не нашлось здесь: латиница - бренд, «для …» - назначение, «6 квт», «80 литров» - размер и мощность, остальное - тип.',
  brands: 'Бренды для вкладки «Бренды»: строка «Название = как ещё пишут, через запятую», например «Samsung = самсунг, самсунк». По звучанию (Baxi = бакси) и с «х» вместо «x» (бахи) программа узнаёт сама, сюда - то, что звучит иначе.'};

function ssOpen(){
  if (ssLoaded !== FOLDER) { ssLoaded = FOLDER; SS = null; $('ssRes').hidden = true;
    fetch('/api/semsort?f=' + encodeURIComponent(FOLDER)).then(r => r.json()).then(j => { if (j.summary) { SS = j; ssDraw(); } }).catch(() => {}); }
  synLoad();
  if (!SSD) fetch('/api/semsort/dicts').then(r => r.json()).then(j => { SSD = j.dicts; ssDict(); }).catch(() => {});
}

const ssB64 = f => new Promise((ok, bad) => { const r = new FileReader();
  r.onload = () => ok(String(r.result).split(',')[1] || ''); r.onerror = bad; r.readAsDataURL(f); });
let ssFileObj = null, ssGFileObj = null;
$('ssFile').addEventListener('change', e => { ssFileObj = e.target.files[0] || null; e.target.value = '';
  $('ssFileName').textContent = ssFileObj ? ssFileObj.name + ' ' : ''; if (ssFileObj) $('ssFileName').insertAdjacentHTML('beforeend', '<button class="btn small" id="ssFileX">убрать</button>'); });
$('ssFileName').addEventListener('click', e => { if (e.target.id === 'ssFileX') { ssFileObj = null; $('ssFileName').textContent = ''; } });
$('ssGFile').addEventListener('change', e => { ssGFileObj = e.target.files[0] || null; e.target.value = '';
  $('ssGName').textContent = ssGFileObj ? ssGFileObj.name : ''; });
document.querySelectorAll('input[name=ssSrc]').forEach(x => x.addEventListener('change', () => {
  $('ssGBtn').hidden = document.querySelector('input[name=ssSrc]:checked').value !== 'file'; }));

$('ssGo').onclick = async () => {
  $('ssErr').textContent = '';
  const body = {f: FOLDER, text: $('ssText').value};
  if (ssFileObj) { body.name = ssFileObj.name; body.data = await ssB64(ssFileObj); }
  if (document.querySelector('input[name=ssSrc]:checked').value === 'file') {
    if (!ssGFileObj) { $('ssErr').textContent = 'Выберите файл с группами.'; return; }
    body.gname = ssGFileObj.name; body.gdata = await ssB64(ssGFileObj); }
  if (!body.text.trim() && !body.data) { $('ssErr').textContent = 'Вставьте запросы или добавьте файл.'; return; }
  $('ssGo').disabled = true; $('ssGo').textContent = 'Раскладываю…';
  try {
    const r = await fetch('/api/semsort', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const j = await r.json();
    if (!r.ok) { $('ssErr').textContent = j.error || 'Не получилось.'; return; }
    SS = j; ssFlt = ''; ssShown = 100; ssDraw(); $('ssRes').scrollIntoView({block: 'start', behavior: 'smooth'});
  } catch { $('ssErr').textContent = 'Программа не ответила. Она запущена?'; }
  finally { $('ssGo').disabled = false; $('ssGo').textContent = 'Разложить'; }
};

function ssKindOf(r){
  const n = SS.names;
  return r.group === n.articles ? 'art' : r.group === n.gallery ? 'gal' : r.group === n.none ? 'none'
    : r.how === 'уже в группе' ? 'have' : r.how === 'спорно' ? 'doubt' : 'ok';
}
function ssDraw(){
  const s = SS.summary; $('ssRes').hidden = false;
  $('ssT').textContent = `Разложено ${num(s.total)} ${plural(s.total, 'запрос', 'запроса', 'запросов')}`;
  $('ssXlsx').href = '/api/semsort/xlsx?f=' + encodeURIComponent(FOLDER);
  const pills = [['', 'Все', s.total], ['ok', 'В группах', s.groups - s.doubt], ['doubt', 'Спорно', s.doubt],
    ['art', 'Статьи', s.articles], ['gal', 'Галерея', s.gallery], ['none', 'Не подошло', s.none], ['have', 'Уже были', s.have]];
  $('ssFlt').innerHTML = pills.filter(p => !p[0] || p[2]).map(p => `<button class="fpill${p[0] === ssFlt ? ' on' : ''}" data-k="${p[0]}">${p[1]} <small>${num(p[2])}</small></button>`).join('')
    + `<span class="mut ss-src">${esc(SS.made)}, ${esc(SS.source || '')}</span>`;
  const q = $('ssQ').value.trim().toLowerCase();
  const rows = SS.rows.filter(r => (!ssFlt || ssKindOf(r) === ssFlt) && (!q || r.q.includes(q) || r.group.toLowerCase().includes(q) || (r.topic || '').toLowerCase().includes(q)));
  $('ssList').innerHTML = rows.slice(0, ssShown).map(r => {
    const k = ssKindOf(r);
    const grp = k === 'art' || k === 'gal' ? `${esc(r.group)}${r.topic ? `<small>тема: ${esc(r.topic)}</small>` : ''}`
      : k === 'none' ? `<span class="mut">${esc(r.group)}</span>${r.alt ? `<small>ближе всего: ${esc(r.alt)}</small>` : ''}`
      : `${esc(r.group)}${r.alt ? `<small>или «${esc(r.alt)}»</small>` : ''}`;
    const why = r.why ? `<small>общие слова: ${esc(r.why)}</small>` : '';
    return `<div class="ss-row"><span>${esc(r.q)}${r.freq ? ` <small class="mut2">${num(r.freq)}</small>` : ''}</span><span>${grp}</span><span class="ss-how ${SS_HOW[r.how] || ''}">${esc(r.how)}${why}</span></div>`;
  }).join('') || '<p class="mut sem-none">Ничего не нашлось.</p>';
  const rest = rows.length - Math.min(ssShown, rows.length);
  $('ssMore').innerHTML = (rest ? `Показано ${num(ssShown)} из ${num(rows.length)}. <button class="btn small" id="ssAll">Показать ещё</button>` : '')
    + (SS.more ? ` Ещё ${num(SS.more)} - в Excel.` : '');
}
$('ssFlt').addEventListener('click', e => { const b = e.target.closest('[data-k]'); if (!b) return; ssFlt = b.dataset.k; ssShown = 100; ssDraw(); });
let ssQt; $('ssQ').addEventListener('input', () => { clearTimeout(ssQt); ssQt = setTimeout(() => { if (SS) { ssShown = 100; ssDraw(); } }, 150); });
$('ssMore').addEventListener('click', e => { if (e.target.id === 'ssAll') { ssShown += 500; ssDraw(); } });

// ---------- словари
function ssDict(){
  $('ssKinds').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.k === ssKind));
  $('ssKHint').textContent = SS_HINT[ssKind];
  $('ssDict').value = (SSD[ssKind] || []).join('\n'); $('ssDSave').disabled = true; $('ssDMsg').textContent = '';
}
$('ssKinds').addEventListener('click', e => { const b = e.target.closest('[data-k]'); if (!b || !SSD) return;
  if (!$('ssDSave').disabled && !confirm('Изменения в этом словаре не сохранены. Перейти без сохранения?')) return;
  ssKind = b.dataset.k; ssDict(); });
$('ssDict').addEventListener('input', () => { $('ssDSave').disabled = false; $('ssDMsg').textContent = ''; });
async function ssDictPost(body, msg){
  const r = await fetch('/api/semsort/dicts', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const j = await r.json(); if (!r.ok) { $('ssDMsg').textContent = j.error || 'Не получилось.'; return; }
  SSD = j.dicts; ssDict(); $('ssDMsg').textContent = msg;
}
$('ssDSave').onclick = () => ssDictPost({kind: ssKind, lines: $('ssDict').value}, 'Сохранено. Нажмите «Разложить» ещё раз, чтобы учесть.');
$('ssDReset').onclick = () => { if (confirm('Вернуть этот словарь как было в программе? Ваши правки в нём пропадут.'))
  ssDictPost({kind: ssKind, reset: true}, 'Словарь как было в программе.'); };

// ---------- синонимы этого сайта (window/semsort.py /api/semsort/syn, semantics/synonyms.py)
let SYN = null, synFor = '';
function synLoad(force){
  if (!force && synFor === FOLDER) return;
  synFor = FOLDER; SYN = null; $('synList').innerHTML = '<p class="mut">Ищу пары…</p>';
  fetch('/api/semsort/syn?f=' + encodeURIComponent(FOLDER)).then(r => r.json()).then(j => {
    if (j.error) { $('synCard').hidden = true; return; } $('synCard').hidden = false; SYN = j; synDraw(); })
    .catch(() => { synFor = ''; $('synList').innerHTML = '<p class="err">Программа не ответила. Откройте вкладку ещё раз.</p>'; });
}
function synDraw(){
  const j = SYN, name = id => (j.niches.find(n => n.id === id) || {}).name || 'только «Общий»';
  $('synNiche').innerHTML = `<option value="auto">Сама по запросам${j.auto ? ` (${esc(name(j.auto))})` : ''}</option>`
    + j.niches.map(n => `<option value="${esc(n.id)}">${esc(n.name)}</option>`).join('') + '<option value="">Только «Общий»</option>';
  $('synNiche').value = j.own ? j.niche : 'auto';
  $('synAuto').textContent = j.own ? '' : j.auto ? `запросов со словами ниши: ${Math.round(j.share * 100)} %` : 'ниша не определилась: работает только «Общий»';
  const m = j.moved.length;
  $('synMoved').innerHTML = m ? `Синонимы уже в одной группе: перенесено ${num(m)} ${plural(m, 'запрос', 'запроса', 'запросов')}, например «${esc(j.moved[0][0])}» из «${esc(j.moved[0][1])}» в «${esc(j.moved[0][2])}».` : '';
  $('synN').textContent = j.suggest.length ? num(j.suggest.length) : '';
  $('synList').innerHTML = j.suggest.map((p, i) => `<div class="syn-row" data-i="${i}">
    <div class="syn-pair"><b>${esc(p.a)}</b> <span class="mut">=</span> <b>${esc(p.b)}</b>${p.why ? ` <span class="syn-why">${esc(p.why)}</span>` : ''}${p.short ? ' <span class="syn-why warn">короткое слово, проверьте</span>' : ''}${p.homonym ? ` <span class="syn-why warn" title="Омоним из словаря">разный смысл: ${esc(p.homonym)}</span>` : ''}
      <small>${p.ex.map(e => `«${esc(e[0])}» и «${esc(e[1])}»`).join('<br>')}${p.n > p.ex.length ? `<br>и ещё ${num(p.n - p.ex.length)}` : ''}</small>${p.quote ? `<small class="dc-quote">На сайте: ${esc(p.quote)}</small>` : ''}</div>
    <div class="syn-btns"><button class="btn small primary" data-syn="yes">Да, это одно</button><button class="btn small" data-syn="no">Нет</button></div></div>`).join('')
    || '<p class="mut">Новых пар не нашлось.</p>';
  $('synDN').textContent = `: тема этого сайта - «${j.path}», в ней ${num(j.lines.length)} ${plural(j.lines.length, 'строка', 'строки', 'строк')} синонимов`;
  $('synDictLink').href = '/dictionary#' + encodeURIComponent(j.niche || 'common');
}
async function synReload(){ const y = window.scrollY; await loadData(FOLDER); window.scrollTo(0, y); }
async function synPost(body){
  const r = await fetch('/api/semsort/syn', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.assign({f: FOLDER}, body))});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { alert(j.error || 'Не получилось.'); return false; }
  SYN = j; synDraw();
  return true;
}
$('synList').addEventListener('click', async e => {
  const b = e.target.closest('[data-syn]'); if (!b) return;
  const row = b.closest('.syn-row'), p = SYN.suggest[+row.dataset.i];
  row.querySelectorAll('button').forEach(x => { x.disabled = true; });
  // «да» меняет группы: перечитать семантику, чтобы группы на странице были с переносами
  if (await synPost({act: b.dataset.syn, a: p.a, b: p.b}) && b.dataset.syn === 'yes' && window.loadData) synReload();
});
$('synNiche').addEventListener('change', async () => {
  if (await synPost({act: 'niche', niche: $('synNiche').value}) && window.loadData) synReload(); });
