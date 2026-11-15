// Вкладка «Видимость» на странице «Семантика»: по каким запросам сайт и конкуренты видны в Яндексе (Букварикс),
// разложено по группам семантики. Сервер: window/sembx.py (/api/sembx), semantics/bukvarix.py.
// Общие $, esc, num, plural, path, FOLDER - из semantics.js.
let BX = null, bxLoaded = '', bxFlt = '', bxShown = 40;

function bxOpen(){
  if (bxLoaded === FOLDER && BX) return;
  bxLoaded = FOLDER; BX = null; $('bxView').hidden = true; $('bxWait').hidden = false;
  $('bxWait').textContent = 'Смотрю, что уже загружено из Букварикса…';
  fetch('/api/sembx?f=' + encodeURIComponent(FOLDER)).then(r => r.json()).then(j => {
    if (bxLoaded !== FOLDER) return;
    if (j.error) { $('bxWait').textContent = j.error; return; }
    BX = j; $('bxWait').hidden = true; $('bxView').hidden = false; bxForm(); bxDraw();
  }).catch(() => { $('bxWait').textContent = 'Не получилось открыть. Обновите страницу.'; });
}

const bxQ = n => plural(n, 'запрос', 'запроса', 'запросов');
const bxPos = p => p >= 99 ? 'есть' : `${num(p)} место`;

function bxForm(){
  const sel = $('bxRegion');
  if (!sel.options.length) sel.innerHTML = BX.regions.map(([c, n]) => `<option value="${c}">Яндекс, ${esc(n)}</option>`).join('');
  sel.value = BX.region;
  const have = BX.domains.map(d => d.domain);
  $('bxDoms').value = [BX.own || DATA.host, ...(BX.competitors || []), ...have].filter((x, i, a) => x && a.indexOf(x) === i).join('\n');
  $('bxNote').textContent = BX.note;
  $('bxLoaded').innerHTML = BX.domains.length ? BX.domains.map(d => `<div class="bx-dom"><b>${esc(d.domain)}</b>${d.own ? ' <span class="pill bx-own">ваш сайт</span>' : ''}
    <span>${num(d.n)} ${bxQ(d.n)}, в первой десятке ${num(d.top10)}</span>
    <span class="mut">Яндекс, ${esc(d.region_name)} · ${esc(d.at)} · ${esc(d.src)}</span>
    <button class="btn small" data-rm="${esc(d.domain)}">убрать</button></div>`).join('')
    : '<p class="mut">Пока ничего не загружено.</p>';
}

function bxDraw(){
  const t = BX.total || {}, G = BX.groups, N = BX.names || {};
  const tile = (v, s, cls) => `<div class="stile${cls ? ' ' + cls : ''}"><b>${num(v)}</b><span>${s}</span></div>`;
  const Q = BX.quick || {rows: [], groups: []};
  $('bxTiles').innerHTML = (!BX.domains.length ? '' : tile(t.mine, `${bxQ(t.mine)}: ваш сайт виден в Яндексе`, 'good')
    + tile(t.top10, 'из них в первой десятке') + (t.rivals ? tile(t.miss, `${bxQ(t.miss)} есть у конкурентов, а у вас нет`, 'warn') : '')
    + (t.dropped ? tile(t.dropped, 'отсеяно: чужие города, фирмы, мусор', 'mut') : ''))
    + (Q.ads && Q.ads.money ? tile(bxRub(Q.ads.money), `в месяц стоили бы в рекламе Яндекса ${num(Q.ads.visitors)} ${plural(Q.ads.visitors, 'посетитель', 'посетителя', 'посетителей')}, которых вы уже получаете из поиска (оценка, смотрите «В рекламе»)`, 'good') : '')
    + (Q.rows.length ? tile(Q.gain, `${plural(Q.gain, 'посетителя', 'посетителей', 'посетителей')} в месяц недополучаете по ${num(Q.rows.length)} ${plural(Q.rows.length, 'запросу', 'запросам', 'запросам')} с 4-15 мест (оценка, смотрите «Быстрые победы»)`, 'warn') : '');
  $('bxRes').hidden = !BX.domains.length && !Q.rows.length;
  $('bxXlsx').href = '/api/semdec/xlsx?f=' + encodeURIComponent(FOLDER);
  if ($('bxRes').hidden) return;
  if (!G.length && Q.rows.length) bxFlt = 'quick';
  const A = Q.ads || {rows: [], left: 0};
  $('bxAds').hidden = !A.left;
  $('bxAds').textContent = A.rows.length ? `Досчитать стоимость в рекламе (${num(A.left)})` : 'Посчитать стоимость в рекламе';
  const n = k => k === 'quick' ? Q.groups.length : k === 'ads' ? A.rows.length : k === 'miss' ? G.filter(g => !g.special && g.miss.length).length : k === 'mine' ? G.filter(g => !g.special && g.mine.length).length
    : k === 'special' ? G.filter(g => g.special).length : k === 'drop' ? BX.dropped.length : G.length;
  const pills = [['', 'Все группы'], ['quick', 'Быстрые победы'], ['ads', 'В рекламе'], ['miss', 'Чего у вас нет'], ['mine', 'Где вы видны'], ['special', `${N.articles}, не подошло`], ['drop', 'Отсеяно']];
  $('bxFlt').innerHTML = pills.filter(p => !p[0] || n(p[0])).map(p => `<button class="fpill${p[0] === bxFlt ? ' on' : ''}" data-k="${p[0]}">${esc(p[1])} <small>${num(n(p[0]))}</small></button>`).join('');
  bxList();
}

// откуда цифры во «Видимости»: Букварикс по каждому сайту со своей датой, места по Вебмастеру и частота по городу -
// с датой сбора семантики и загрузки частотности (srcNote, freqSrc - из semantics.js)
function bxSrc(quick){
  const d = BX.domains.map(x => `${x.domain} - Яндекс ${x.region_name}, ${x.at}`).join(', ');
  const t = [d && `места и «!частотность» по всей России - Букварикс (${d})`,
    (quick ? BX.quick.rows.some(r => r.psrc === 'Вебмастер') : BX.groups.some(g => g.mine.some(r => r.wm)))
      && `«Вебмастер» - среднее место по Яндекс Вебмастеру на ${(DATA.made || '').slice(0, 10)}`,
    quick && DATA.direct && 'частота по городу - ' + freqSrc()].filter(Boolean);
  return `<p class="mut src-note">Откуда цифры: ${esc(t.join('; '))}.</p>`;
}

function bxRow(r, mine){
  const riv = Object.entries(r.rivals).map(([h, p]) => `${esc(h)}${p < 99 ? ' <i>' + num(p) + ' место</i>' : ''}`).join(', ');
  const d = r.exact || r.freq;
  return `<div class="bx-q"><span>${esc(r.q)}</span>
    <span class="bx-num" title="«!Частотность» по всей стране в месяц (Букварикс)">${d ? num(d) : ''}</span>
    <span>${mine ? `<b>${bxPos(r.mine)}</b>${r.wm ? ` <span class="mut" title="Среднее место по Яндекс Вебмастеру - свежее">· Вебмастер ${num(r.wm)}</span>` : ''}` : ''}${riv ? `<span class="mut">${mine ? ' · ' : ''}${riv}</span>` : ''}</span></div>`;
}

const bxFsrc = {city: 'в месяц по городу (Вордстат)', calc: 'примерно в месяц по городу: частота Букварикса по России, пересчитанная на город',
  ru: 'в месяц по всей России (Букварикс): для одного города будет меньше'};

const bxRub = v => num(v >= 1000 ? Math.round(v / 100) * 100 : v) + ' ₽';

function bxAdsList(q){
  const A = BX.quick.ads, L = A.rows.filter(r => !q || r.q.includes(q) || r.group.toLowerCase().includes(q));
  $('bxList').innerHTML = `<p class="mut bx-qnote">${esc(A.note)} Цены - прогноз Директа${A.at ? ' от ' + esc(A.at) : ''}.${A.ru ? ` Для ${num(A.ru)} ${plural(A.ru, 'запроса', 'запросов', 'запросов')} частота по всей России, для города сумма будет меньше.` : ''}${A.left ? ` Ещё ${num(A.left)} ${plural(A.left, 'запрос', 'запроса', 'запросов')} без цены: нажмите «Досчитать».` : ''}</p>`
    + (L.slice(0, bxShown * 5).map(r => `<div class="bx-q bx-ad"><span>${esc(r.q)} <span class="mut">· ${esc(r.group)}</span></span>
      <span class="bx-num" title="${esc(bxFsrc[r.fsrc])}">${num(r.freq)}${r.fsrc === 'ru' ? ' <small>РФ</small>' : ''}</span>
      <span><b>${num(r.pos)} место</b> <span class="mut">· около ${num(r.now)} ${plural(r.now, 'посетителя', 'посетителей', 'посетителей')} в месяц × ${num(r.cpc)} ₽ за клик</span> <span class="bx-good">= ${bxRub(r.money)}</span></span></div>`).join('')
      || '<p class="mut sem-none">Ничего не нашлось.</p>');
  $('bxMore').innerHTML = L.length > bxShown * 5 ? `<button class="btn small" id="bxMoreB">Показать ещё ${num(Math.min(L.length - bxShown * 5, 100))}</button>` : '';
}

function bxQuick(q){
  const Q = BX.quick, more = bxShown;
  const L = Q.groups.filter(g => !q || g.name.toLowerCase().includes(q) || g.rows.some(r => r.q.includes(q)));
  const warn = [Q.calc ? `Для ${num(Q.calc)} ${plural(Q.calc, 'запроса', 'запросов', 'запросов')} частоты по городу нет, она пересчитана из частоты по России (доля города примерно ${String(Math.round(Q.ratio * 1000) / 10).replace('.', ',')} %).` : '',
    Q.ru && Q.region !== 'Россия' ? `Для ${num(Q.ru)} ${plural(Q.ru, 'запроса', 'запросов', 'запросов')} частота по всей России, для города посетителей будет меньше. Точнее посчитает «Загрузить частотность» (Директ).` : ''].filter(Boolean).join(' ');
  $('bxList').innerHTML = `<p class="mut bx-qnote">Запросы, где ваш сайт на 4-15 месте, у группы уже есть страница и запрос ищут не меньше 10 раз в месяц. Подтянуть эти страницы в первую тройку обычно проще и быстрее всего. «Недополучаете» - сколько посетителей в месяц прибавится, если страница поднимется на 3-е место. ${esc(Q.note)}${warn ? ' ' + esc(warn) : ''}</p>${bxSrc(true)}`
    + (L.slice(0, more).map(g => {
      const name = g.idx !== null && g.idx !== undefined ? `<a href="#g/${g.idx}">${esc(g.name)}</a>` : esc(g.name);
      return `<details class="bx-g"${q || L.length === 1 ? ' open' : ''}><summary><b>${name}</b>${g.page ? ` <a class="mono gurl" href="${esc(g.page)}" target="_blank">${esc(path(g.page))}</a>` : ''}
        <div class="bx-sum"><span class="bx-warn">недополучаете примерно ${num(g.gain)} ${plural(g.gain, 'посетителя', 'посетителей', 'посетителей')} в месяц</span>${g.gmoney ? `<span class="mut">в рекламе такие посетители стоили бы ${bxRub(g.gmoney)} в месяц</span>` : ''}<span class="mut">${num(g.rows.length)} ${bxQ(g.rows.length)} на 4-15 местах</span></div></summary>
        ${g.rows.map(r => `<div class="bx-q"><span>${esc(r.q)}</span>
          <span class="bx-num" title="${esc(bxFsrc[r.fsrc])}">${r.fsrc === 'calc' ? '≈' : ''}${num(r.freq)}${r.fsrc === 'ru' ? ' <small>РФ</small>' : ''}</span>
          <span><b>${num(r.pos)} место</b> <span class="mut">(${esc(r.psrc)}) · сейчас около ${num(r.now)} в месяц</span> <span class="bx-warn">· +${num(r.gain)}</span>${r.gmoney ? ` <span class="mut">(≈ ${bxRub(r.gmoney)} в рекламе)</span>` : ''}</span></div>`).join('')}</details>`; }).join('')
      || '<p class="mut sem-none">Ничего не нашлось.</p>');
  $('bxMore').innerHTML = L.length > more ? `<button class="btn small" id="bxMoreB">Показать ещё ${num(Math.min(L.length - more, 100))}</button>` : '';
}

function bxList(){
  const q = $('bxQ').value.trim().toLowerCase();
  if (bxFlt === 'quick') return bxQuick(q);
  if (bxFlt === 'ads') return bxAdsList(q);
  if (bxFlt === 'drop') {
    const L = BX.dropped.filter(r => !q || r.q.includes(q) || r.why.includes(q));
    $('bxList').innerHTML = L.slice(0, bxShown * 10).map(r => `<div class="bx-q"><span>${esc(r.q)}</span><span class="bx-num">${r.freq ? num(r.freq) : ''}</span><span class="mut">${esc(r.why)}${r.mine ? ' · ваш сайт: ' + bxPos(r.mine) : ''}${Object.keys(r.rivals).length ? ' · ' + esc(Object.keys(r.rivals).join(', ')) : ''}</span></div>`).join('')
      || '<p class="mut sem-none">Ничего не нашлось.</p>';
    $('bxMore').innerHTML = ''; return;
  }
  const L = BX.groups.filter(g => (bxFlt === 'miss' ? !g.special && g.miss.length : bxFlt === 'mine' ? !g.special && g.mine.length
    : bxFlt === 'special' ? g.special : true) && (!q || g.name.toLowerCase().includes(q) || g.mine.concat(g.miss).some(r => r.q.includes(q))));
  $('bxList').innerHTML = (L.length ? bxSrc(false) : '') + L.slice(0, bxShown).map(g => {
    const kind = g.kind && BX.kinds[g.kind] ? `<span class="pill">${esc(BX.kinds[g.kind])}</span>` : '';
    const name = g.idx !== null && g.idx !== undefined ? `<a href="#g/${g.idx}">${esc(g.name)}</a>` : esc(g.name);
    const head = `<b>${name}</b> ${kind}${g.page ? ` <a class="mono gurl" href="${esc(g.page)}" target="_blank">${esc(path(g.page))}</a>` : ''}
      <div class="bx-sum">${g.mine.length ? `<span class="bx-good">виден по ${num(g.mine.length)} ${plural(g.mine.length, 'запросу', 'запросам', 'запросам')}${g.top10 ? `, в десятке ${num(g.top10)}` : ''}</span>` : '<span class="mut">ваш сайт не виден</span>'}
      ${g.miss.length ? `<span class="bx-warn">${g.special ? '' : 'нет у вас: '}${num(g.miss.length)} ${bxQ(g.miss.length)}${g.demand ? `, ${num(g.demand)} в месяц` : ''}</span>` : ''}</div>`;
    const open = !!q || L.length === 1;
    return `<details class="bx-g"${open ? ' open' : ''}><summary>${head}</summary>
      ${g.miss.length ? `<h4>${g.special ? 'Запросы конкурентов' : 'Есть у конкурентов, нет у вас'}</h4>${g.miss.map(r => bxRow(r, false)).join('')}` : ''}
      ${g.mine.length ? `<h4>Ваш сайт виден</h4>${g.mine.map(r => bxRow(r, true)).join('')}` : ''}</details>`; }).join('')
    || '<p class="mut sem-none">Ничего не нашлось.</p>';
  $('bxMore').innerHTML = L.length > bxShown ? `<button class="btn small" id="bxMoreB">Показать ещё ${num(Math.min(L.length - bxShown, 100))}</button>` : '';
}

async function bxPost(body, btn, busy){
  $('bxErr').textContent = ''; $('bxMsg').textContent = '';
  const old = btn && btn.textContent; if (btn) { btn.disabled = true; btn.textContent = busy; }
  try {
    const r = await fetch('/api/sembx', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.assign({f: FOLDER}, body))});
    const j = await r.json();
    if (!r.ok) { $('bxErr').textContent = j.error || 'Не получилось.'; return; }
    BX = j; bxForm(); bxDraw(); if (j.msg) $('bxMsg').textContent = (body.ads ? 'Посчитано: ' : 'Загружено: ') + j.msg + '.';
  } catch { $('bxErr').textContent = 'Программа не ответила. Она запущена?'; }
  finally { if (btn) { btn.disabled = false; btn.textContent = old; } }
}

$('bxAds').onclick = () => bxPost({ads: 1}, $('bxAds'), 'Считаю в Директе…');
$('bxGo').onclick = () => {
  const doms = $('bxDoms').value.split(/[\s,]+/).map(x => x.trim()).filter(Boolean);
  if (!doms.length) { $('bxErr').textContent = 'Впишите адреса сайтов.'; return; }
  bxPost({fetch: doms, region: $('bxRegion').value}, $('bxGo'), 'Загружаю…');
};
$('bxFile').addEventListener('change', async e => {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  const data = await new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1] || ''); r.onerror = bad; r.readAsDataURL(f); });
  bxPost({name: f.name, data}, null, '');
});
$('bxLoaded').addEventListener('click', e => { const b = e.target.closest('[data-rm]'); if (b) bxPost({remove: b.dataset.rm}, b, '…'); });
$('bxFlt').addEventListener('click', e => { const b = e.target.closest('[data-k]'); if (!b) return; bxFlt = b.dataset.k; bxShown = 40; bxDraw(); });
$('bxQ').addEventListener('input', () => { bxShown = 40; bxList(); });
$('bxMore').addEventListener('click', e => { if (e.target.id === 'bxMoreB') { bxShown += 100; bxList(); } });
