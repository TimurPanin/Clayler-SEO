// Страница «Словарь»: дерево тем слева, справа - правила темы по видам (синонимы, единицы, опечатки, омонимы, бренды,
// мусорные слова), поиск по всем темам, «Ждут подтверждения» (пары с сайтов) и «Сайты и их темы».
// Сервер: window/dictview.py (/api/dict…), логика: semantics/dictionary.py.
(() => {
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const num = n => String(n || 0).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
const plural = (n, a, b, c) => { n = Math.abs(n) % 100; const m = n % 10; return n > 10 && n < 20 ? c : m > 1 && m < 5 ? b : m === 1 ? a : c; };
let V = null, SEL = 'common', KIND = 'syn', OPEN = {common: true}, PAIRS = {}, SHUT = {};

async function api(body){
  const r = await fetch('/api/dict', body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : undefined);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || 'Не получилось.');
  return j;
}
function msg(text, bad){ const m = $('dcMsg'); m.hidden = !text; m.textContent = text || ''; m.classList.toggle('err', !!bad);
  if (text && !bad) setTimeout(() => { if (m.textContent === text) m.hidden = true; }, 4000); }
async function act(body, ok){
  try { V = await api(body); if (V.msg) msg(V.msg); else if (ok) msg(ok); draw(); return true; }
  catch (e) { msg(e.message, true); return false; }
}

const N = id => V.nodes.find(n => n.id === id);
const kids = id => V.nodes.filter(n => n.parent === id);
const chainOf = id => { const out = []; let n = N(id); while (n) { out.unshift(n); n = n.parent ? N(n.parent) : null; } return out; };
const pathOf = id => chainOf(id).map(n => n.name).join(' → ');
const rules = (id, k) => ((V.rules[id] || {})[k] || []);
const count = id => V.kinds.reduce((s, k) => s + rules(id, k.id).filter(r => !r.off).length, 0);
const kindName = k => (V.kinds.find(x => x.id === k) || {}).name || k;

// ---------- дерево тем
// у каждой ниши свой цвет; подтема - цвета своей ниши
const HUES = ['#8e9cff', '#4fbf8a', '#e5a54b', '#e07fb0', '#5fc3d6', '#c79a6b', '#a98bff', '#9ccc65', '#ff8f80', '#7aa7ff', '#d4c25a', '#6fd0a8'];
function dot(id){ const ch = chainOf(id); if (ch.length < 2) return '<i class="dc-dot" style="background:var(--mut2)"></i>';
  const i = V.nodes.filter(n => n.parent === 'common').findIndex(n => n.id === ch[1].id); return `<i class="dc-dot" style="background:${HUES[(i + HUES.length) % HUES.length]}"></i>`; }
function tree(){
  const row = (n, d) => {
    const ch = kids(n.id), open = OPEN[n.id] || SEL === n.id || chainOf(SEL).some(x => x.id === n.id);
    return `<button class="dc-node dc-d${d}${SEL === n.id ? ' on' : ''}" data-node="${esc(n.id)}"><i class="dc-tw" aria-hidden="true">${ch.length ? (open ? '▾' : '▸') : ''}</i>${dot(n.id)}<span>${esc(n.name)}${n.builtin ? '' : '<small class="dc-own">своя</small>'}</span><small class="dc-n">${num(count(n.id))}</small></button>`
      + (open ? ch.map(c => row(c, d + 1)).join('') : '');
  };
  $('dcTree').innerHTML = row(N('common'), 1);
  // ждут ответа: найденные при сборе семантики (сервер считает сам) или открытые здесь
  const pend = V.sites.reduce((s, x) => { const p = PAIRS[x.folder]; return s + (p && p.suggest ? p.suggest.length : (x.pairs || 0)); }, 0);
  $('dcQueueN').textContent = pend ? num(pend) : '';
  $('dcSitesN').textContent = num(V.sites.length);
  $('dcQueue').classList.toggle('on', SEL === '#queue'); $('dcSites').classList.toggle('on', SEL === '#sites');
}
$('dcTree').addEventListener('click', e => { const b = e.target.closest('[data-node]'); if (!b) return;
  const id = b.dataset.node;
  if (SEL === id && kids(id).length) OPEN[id] = !OPEN[id]; else { SEL = id; OPEN[id] = true; }
  $('dcQ').value = ''; go(); });
$('dcQueue').onclick = () => { SEL = '#queue'; $('dcQ').value = ''; go(); };
$('dcSites').onclick = () => { SEL = '#sites'; $('dcQ').value = ''; go(); };
$('dcAddNiche').onclick = () => addNode('common');
async function addNode(parent){
  const name = prompt(parent === 'common' ? 'Название ниши, например «Окна и двери»:' : `Подтема в «${N(parent).name}», например «Котлы»:`);
  if (!name || !name.trim()) return;
  const before = new Set(V.nodes.map(n => n.id));
  if (await act({act: 'node_add', name, parent}, 'Тема добавлена.')) {
    const nw = V.nodes.find(n => !before.has(n.id)); if (nw) { SEL = nw.id; OPEN[parent] = true; go(); } }
}
function go(){ location.hash = SEL === 'common' && KIND === 'syn' ? '' : SEL.startsWith('#') ? SEL.slice(1) : `${SEL}/${KIND}`; draw(); }

// ---------- строка правила
function words(t, k){
  if (k === 'brand') { const [a, b] = t.split('='); return `<b>${esc(a.trim())}</b>${b ? '<span class="dc-eq">=</span>' + b.split(',').filter(x => x.trim()).map(x => `<i>${esc(x.trim())}</i>`).join('') : ''}`; }
  if (k === 'homonym') { const [a, b] = t.split('='); return `<b>${esc(a.trim())}</b>${b ? '<span class="dc-eq">:</span>' + b.split('|').map(x => `<i>${esc(x.trim())}</i>`).join('<span class="dc-eq">или</span>') : ''}`; }
  if (k === 'junk') return `<b>${esc(t)}</b>`;
  const p = t.replace(/^#\s*/, '').split('=').map(x => x.trim()).filter(Boolean);
  return `<b>${esc(p[0] || t)}</b>${p.slice(1).map(x => `<i>${esc(x)}</i>`).join('')}`;
}
function meta(r, id){
  const bits = [];
  if (r.off) bits.push('выключено («#» в начале)');
  if (r.src) bits.push(esc(r.src) + (r.at ? ', ' + esc(r.at) : ''));
  if (!r.off) bits.push(r.hits ? `<span class="hit">сработало в ${num(r.hits)} ${plural(r.hits, 'запросе', 'запросах', 'запросах')}</span>` : 'пока не встречалось в семантиках сайтов');
  if (id) bits.push(esc(pathOf(id)));
  return bits.join(' · ');
}
function rowHtml(r, id, k, ro){
  return `<div class="dc-row${r.off ? ' off' : ''}" data-id="${esc(id)}" data-k="${esc(k)}" data-t="${esc(r.t)}">
    <div class="dc-t"><div class="dc-w">${words(r.t, k)}</div><div class="dc-meta">${meta(r, ro ? id : '')}</div></div>
    ${ro ? '' : `<div class="dc-ra"><button data-a="edit" title="Изменить" aria-label="Изменить">✎</button><button data-a="move" title="Перенести в другую тему" aria-label="Перенести в другую тему">⇄</button><button data-a="del" title="Удалить" aria-label="Удалить">×</button></div>`}</div>`;
}

// ---------- тема
function nodeView(){
  const n = N(SEL); if (!n) { SEL = 'common'; return nodeView(); }
  const kinds = V.kinds.map(k => `<button data-k="${k.id}"${k.id === KIND ? ' class="on"' : ''}>${esc(k.name)}<small>${num(rules(n.id, k.id).filter(r => !r.off).length)}</small></button>`).join('');
  const sites = V.sites.filter(s => s.node === n.id);
  const kind = V.kinds.find(k => k.id === KIND);
  const list = rules(n.id, KIND);
  const edited = n.builtin && (n.edited.includes(KIND) || (n.id === 'common' && (KIND === 'syn' || KIND === 'brand')));
  const up = chainOf(n.id).slice(0, -1);
  const inh = up.map(p => rules(p.id, KIND).filter(r => !r.off).map(r => rowHtml(r, p.id, KIND, true)).join('')).join('');
  const inhN = up.reduce((s, p) => s + rules(p.id, KIND).filter(r => !r.off).length, 0);
  const ph = {syn: 'водонагреватель = бойлер', unit: 'м2 = кв м = квадратных метров', typo: 'котел = rjntk = кател', homonym: 'сто = автосервис | 100', brand: 'Samsung = самсунг, самсунк', junk: 'майнкрафт'}[KIND];
  $('dcMain').innerHTML = `<div class="dc-head"><h2>${dot(n.id)}${esc(n.name)}</h2><div class="dc-acts">
      ${n.depth < V.depth ? `<button class="btn small" data-na="sub">+ Подтема</button>` : ''}
      ${n.builtin ? '' : '<button class="btn small" data-na="ren">Переименовать</button><button class="btn small" data-na="delnode">Удалить тему</button>'}</div></div>
    <div class="dc-path">${n.id === 'common' ? 'Действует на всех сайтах' : esc(pathOf(n.id))}${n.id !== 'common' && kids(n.id).length ? ' · подтемы: ' + kids(n.id).map(c => esc(c.name)).join(', ') : ''}</div>
    <div class="dc-sites">${n.id === 'common' ? '' : sites.length ? 'Сайты этой темы: ' + sites.map(s => `<span class="dc-chip dc-host">${esc(s.host)}${s.own ? '' : ' <small class="mut2">сама</small>'}</span>`).join('') : 'Сайтов этой темы пока нет: тему сайта можно выбрать в «Сайты и их темы».'}</div>
    <div class="seg dc-kinds" role="tablist">${kinds}</div>
    <p class="mut dc-hint">${esc(kind.hint)}</p>
    <div class="dc-add"><input type="text" id="dcLine" placeholder="${esc(ph)}" aria-label="Новая строка"><button class="btn primary" id="dcAdd">Добавить</button></div>
    <div id="dcList">${list.map(r => rowHtml(r, n.id, KIND)).join('') || '<p class="dc-empty">В этой теме пока нет строк этого вида.</p>'}</div>
    ${edited && list.length && !(n.id === 'common' && KIND === 'junk') ? '<p class="mut"><button class="btn small" data-na="reset">Вернуть как было в программе</button></p>' : ''}
    ${inhN ? `<details class="dc-inh"><summary>Действуют и здесь, из темы выше: ${num(inhN)} ${plural(inhN, 'строка', 'строки', 'строк')}</summary>${inh}</details>` : ''}`;
}
$('dcMain').addEventListener('click', async e => {
  const k = e.target.closest('.dc-kinds [data-k]'); if (k) { KIND = k.dataset.k; go(); return; }
  const na = e.target.closest('[data-na]');
  if (na) {
    const a = na.dataset.na;
    if (a === 'sub') addNode(SEL);
    if (a === 'ren') { const name = prompt('Новое название темы:', N(SEL).name); if (name && name.trim()) act({act: 'node_rename', node: SEL, name}, 'Переименовано.'); }
    if (a === 'delnode' && confirm(`Удалить тему «${N(SEL).name}»? Её строки, подтемы и сайты перейдут в «${N(N(SEL).parent).name}».`)) {
      const p = N(SEL).parent; if (await act({act: 'node_delete', node: SEL}, 'Тема удалена.')) { SEL = p; go(); } }
    if (a === 'reset' && confirm('Вернуть строки этого вида в теме как было в программе? Ваши правки здесь пропадут.')) act({act: 'reset', node: SEL, kind: KIND}, 'Как было в программе.');
    return;
  }
  if (e.target.id === 'dcAdd') { const line = $('dcLine').value.trim(); if (line && await act({act: 'add', node: SEL, kind: KIND, line}, 'Добавлено.')) $('dcLine').focus(); return; }
  const b = e.target.closest('.dc-ra [data-a]'), row = e.target.closest('.dc-row');
  if (b && row) {
    const {id, k, t} = row.dataset, a = b.dataset.a;
    if (a === 'del' && confirm(`Удалить «${t}»?`)) act({act: 'remove', node: id, kind: k, line: t}, 'Удалено.');
    if (a === 'edit' || a === 'move') {
      row.querySelector('.dc-edit') && row.querySelector('.dc-edit').remove();
      const box = document.createElement('div'); box.className = 'dc-edit';
      box.innerHTML = a === 'edit' ? `<input type="text" value="${esc(t)}" aria-label="Строка"><button class="btn small primary" data-e="save">Сохранить</button><button class="btn small" data-e="x">Отмена</button>`
        : `<select aria-label="Тема">${V.nodes.filter(n => n.id !== id).map(n => `<option value="${esc(n.id)}">${esc(pathOf(n.id))}</option>`).join('')}</select><button class="btn small primary" data-e="move">Перенести</button><button class="btn small" data-e="x">Отмена</button>`;
      row.querySelector('.dc-t').appendChild(box); const f = box.querySelector('input,select'); f.focus();
    }
    return;
  }
  const ed = e.target.closest('[data-e]');
  if (ed && row) {
    const {id, k, t} = row.dataset, box = ed.closest('.dc-edit');
    if (ed.dataset.e === 'x') box.remove();
    if (ed.dataset.e === 'save') act({act: 'edit', node: id, kind: k, old: t, line: box.querySelector('input').value}, 'Сохранено.');
    if (ed.dataset.e === 'move') act({act: 'move', node: id, kind: k, line: t, to: box.querySelector('select').value}, 'Перенесено.');
  }
});
$('dcMain').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  if (e.target.id === 'dcLine') $('dcAdd').click();
  const box = e.target.closest('.dc-edit'); if (box) { e.preventDefault(); box.querySelector('.primary').click(); }
});

// ---------- поиск во всех темах
function searchView(q){
  q = q.toLowerCase().replace(/ё/g, 'е');
  const out = [];
  for (const n of V.nodes) for (const k of V.kinds) for (const r of rules(n.id, k.id))
    if (r.t.toLowerCase().replace(/ё/g, 'е').includes(q)) out.push(`<div class="dc-res-path">${esc(kindName(k.id))}</div>` + rowHtml(r, n.id, k.id, true));
  $('dcMain').innerHTML = `<div class="dc-head"><h2>Найдено: ${num(out.length)}</h2></div>` + (out.join('') || '<p class="dc-empty">Ни в одной теме нет такого слова.</p>');
}
let qt; $('dcQ').addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(draw, 150); });

// ---------- сайты и их темы
function nodeOptions(sel){   // по дереву: ниша, под ней её подтемы с отступом
  const walk = id => kids(id).map(n => `<option value="${esc(n.id)}"${n.id === sel ? ' selected' : ''}>${n.depth > 2 ? '   — ' : ''}${esc(n.name)}</option>` + walk(n.id)).join('');
  return walk('common');
}
function sitesView(){
  $('dcMain').innerHTML = `<div class="dc-head"><h2>Сайты и их темы</h2></div>
    <p class="mut">Тема определяется сама по запросам семантики сайта. Если выбрать подтему («Котлы»), сайт возьмёт её правила, правила ниши и «Общего».</p>
    ${V.sites.map(s => `<div class="dc-site"><div><b>${esc(s.host)}</b><small>${num(s.queries)} ${plural(s.queries, 'запрос', 'запроса', 'запросов')} в семантике</small></div>
      <select data-host="${esc(s.host)}" aria-label="Тема сайта ${esc(s.host)}"><option value="auto"${s.own ? '' : ' selected'}>Сама по запросам${s.auto ? ` (${esc(N(s.auto).name)})` : ' (не определилась)'}</option>
      ${nodeOptions(s.own ? s.node : '')}<option value=""${s.own && s.node === 'common' ? ' selected' : ''}>Только «Общий»</option></select></div>`).join('')
      || '<p class="dc-empty">Семантика ещё не собрана ни для одного сайта.</p>'}`;
}
$('dcMain').addEventListener('change', e => { const s = e.target.closest('select[data-host]'); if (s) act({act: 'site', host: s.dataset.host, node: s.value}, 'Тема сайта сохранена.'); });

// ---------- ждут подтверждения: пары «похоже на синонимы» с сайтов
function queueView(){
  // пары, найденные при сборе семантики (в том числе очередью сайтов), открываются сами, без «Показать пары»
  V.sites.forEach(s => { if (!PAIRS[s.folder] && s.pairs) loadPairs(s.folder, true); });
  const order = V.sites.slice().sort((a, b) => (b.pairs || 0) - (a.pairs || 0));
  $('dcMain').innerHTML = `<div class="dc-head"><h2>Ждут подтверждения</h2></div>
    <p class="mut">Программа находит в семантике сайта слова, с которыми ищут одно и то же. Часто это разные вещи одного ряда («газовый» и «электрический») - тогда «Нет», и пара больше не появится. «Да, это одно» - пара попадёт в выбранную тему. Галочками можно ответить на много пар сразу.</p>
    ${order.map(s => { const P = PAIRS[s.folder];
      return `<div class="dc-qsite" data-f="${esc(s.folder)}"><div class="dc-head"><h3><span class="dc-host">${esc(s.host)}</span> <span class="dc-topic">${dot(s.node)}${esc(s.node === 'common' ? 'Общий' : pathOf(s.node).replace('Общий → ', ''))}</span></h3>
        ${!P ? '<button class="btn small" data-q="load">Показать пары</button>' : P === 'wait' ? '' : `<button class="btn small" data-q="fold" aria-expanded="${!SHUT[s.folder]}">${SHUT[s.folder] ? 'Показать' : 'Скрыть'} пары${P.suggest ? ` <small class="dc-n">${num(P.suggest.length)}</small>` : ''}</button>`}</div>
        ${P === 'wait' ? '<p class="mut">Ищу пары…</p>' : SHUT[s.folder] ? '' : P && P.error ? `<p class="err">${esc(P.error)}</p>` : P ? ((P.suggest.length ? batchBar() : '') + P.suggest.map((p, i) => pairHtml(p, i, s)).join('') || '<p class="dc-empty">Новых пар нет.</p>') : ''}</div>`; }).join('')
      || '<p class="dc-empty">Семантика ещё не собрана ни для одного сайта.</p>'}`;
}
const reEsc = t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function hl(q, a, b){   // слова пары в примере - своими цветами
  let h = esc(q);
  [[a, 'dc-ma'], [b, 'dc-mb']].forEach(([w, c]) => { h = h.replace(new RegExp(`(^|[^а-яёa-z0-9])(${reEsc(esc(w))})(?=$|[^а-яёa-z0-9])`, 'gi'), `$1<mark class="${c}">$2</mark>`); });
  return h;
}
const tag = (t, c) => ` <span class="dc-tag ${c || ''}">${esc(t)}</span>`;
const batchBar = () => `<div class="dc-batch"><label><input type="checkbox" data-q="all"> Отметить все</label>
  <button class="btn small primary" data-q="yes_many" disabled>Да для отмеченных</button><button class="btn small" data-q="no_many" disabled>Нет для отмеченных</button></div>`;
function pairHtml(p, i, s){
  return `<div class="dc-pair" data-i="${i}"><input type="checkbox" class="dc-chk" aria-label="Отметить пару ${esc(p.a)} = ${esc(p.b)}"><div class="dc-pt"><b class="dc-pa">${esc(p.a)}</b> <span class="mut">=</span> <b class="dc-pb2">${esc(p.b)}</b>${p.why ? tag(p.why, 'good') : ''}${p.short ? tag('короткое слово, проверьте', 'warn') : ''}${p.homonym ? tag('разный смысл: ' + p.homonym, 'warn') : ''}
    <small>${p.ex.map(e => `«${hl(e[0], p.a, p.b)}» и «${hl(e[1], p.a, p.b)}»`).join('<br>')}${p.n > p.ex.length ? `<br>и ещё ${num(p.n - p.ex.length)}` : ''}</small>${p.quote ? `<small class="dc-quote">На сайте: ${esc(p.quote)}</small>` : ''}</div>
    <div class="dc-pb"><select aria-label="В какую тему">${nodeOptions(p.node || s.node)}<option value="common"${(p.node || s.node) === 'common' ? ' selected' : ''}>Общий</option></select>
    <button class="btn small primary" data-q="yes">Да, это одно</button><button class="btn small" data-q="no">Нет</button></div></div>`;
}
async function loadPairs(f, quiet){
  PAIRS[f] = 'wait'; if (!quiet) draw();
  try { const r = await fetch('/api/dict/suggest?f=' + encodeURIComponent(f)); const j = await r.json(); PAIRS[f] = r.ok ? j : {error: j.error || 'Не получилось.'}; }
  catch { PAIRS[f] = {error: 'Программа не ответила.'}; }
  draw();
}
$('dcMain').addEventListener('click', async e => {
  const b = e.target.closest('[data-q]'); if (!b) return;
  const box = b.closest('.dc-qsite'), f = box.dataset.f;
  if (b.dataset.q === 'load') return loadPairs(f);
  if (b.dataset.q === 'fold') { SHUT[f] = !SHUT[f]; draw(); return; }
  if (b.dataset.q === 'all') return;
  if (b.dataset.q === 'yes_many' || b.dataset.q === 'no_many') {
    const rows = [...box.querySelectorAll('.dc-pair')].filter(r => r.querySelector('.dc-chk').checked);
    const pairs = rows.map(r => { const p = PAIRS[f].suggest[+r.dataset.i]; return {a: p.a, b: p.b, node: r.querySelector('select').value}; });
    if (!pairs.length) return;
    box.querySelectorAll('button,select,input').forEach(x => { x.disabled = true; });
    try {
      const r = await fetch('/api/dict', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({act: b.dataset.q, f, pairs})});
      const j = await r.json(); if (!r.ok) throw new Error(j.error || 'Не получилось.');
      PAIRS[f] = j; V = await api();
      msg(b.dataset.q === 'yes_many' ? `Добавлено в словарь: ${num(pairs.length)}.` : `Больше не предложу: ${num(pairs.length)}.`); draw();
    } catch (err) { msg(err.message, true); box.querySelectorAll('button,select,input').forEach(x => { x.disabled = false; }); }
    return;
  }
  const row = b.closest('.dc-pair'), p = PAIRS[f].suggest[+row.dataset.i];
  row.querySelectorAll('button,select').forEach(x => { x.disabled = true; });
  try {
    const r = await fetch('/api/dict', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({act: b.dataset.q, f, a: p.a, b: p.b, node: row.querySelector('select').value})});
    const j = await r.json(); if (!r.ok) throw new Error(j.error || 'Не получилось.');
    PAIRS[f] = j; V = await api(); msg(b.dataset.q === 'yes' ? 'Добавлено в словарь.' : 'Больше не предложу.'); draw();
  } catch (err) { msg(err.message, true); row.querySelectorAll('button,select').forEach(x => { x.disabled = false; }); }
});

$('dcMain').addEventListener('change', e => {   // галочки пар: «Отметить все» и кнопки пачкой
  const box = e.target.closest('.dc-qsite'); if (!box || !e.target.matches('.dc-chk, [data-q="all"]')) return;
  if (e.target.dataset.q === 'all') box.querySelectorAll('.dc-chk').forEach(c => { c.checked = e.target.checked; });
  const n = box.querySelectorAll('.dc-chk:checked').length;
  box.querySelectorAll('[data-q="yes_many"], [data-q="no_many"]').forEach(x => { x.disabled = !n;
    x.textContent = (x.dataset.q === 'yes_many' ? 'Да' : 'Нет') + ' для отмеченных' + (n ? ` (${n})` : ''); });
});

// ---------- из файла
$('dcImport').addEventListener('change', async e => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  let data; try { data = JSON.parse(await f.text()); } catch { msg('Это не файл словаря: не получилось прочитать.', true); return; }
  act({act: 'import', data});
});

function draw(){
  if (!V) return;
  tree();
  const q = $('dcQ').value.trim();
  if (q) return searchView(q);
  if (SEL === '#queue') return queueView();
  if (SEL === '#sites') return sitesView();
  nodeView();
}
function fromHash(){
  const h = decodeURIComponent(location.hash.slice(1));
  if (!h) return;
  if (h === 'queue' || h === 'sites') { SEL = '#' + h; return; }
  const [a, b] = h.split('/');
  if (V.kinds.some(k => k.id === a)) { KIND = a; return; }
  if (N(a)) SEL = a;
  if (b && V.kinds.some(k => k.id === b)) KIND = b;
}
api().then(j => { V = j; fromHash(); draw(); }).catch(e => { $('dcMain').innerHTML = `<p class="err">${esc(e.message)}</p>`; });
})();
