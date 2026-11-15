// Маски семантики и стоп-слова клиента (semantics/masks.py) на странице «Семантика», блок «Маски и стоп-слова».
// Маски программа предлагает по проверке (отдельной программой, окно не ждёт): главная и меню, разделы, подразделы
// и карточки. Человек правит текст, выключает лишнее, добавляет свои и подтверждает - тогда сбор идёт только по ним.
(function(){
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = n => (n || 0).toLocaleString('ru');
  const plural = (n, a, b, c) => { n = Math.abs(n) % 100; const m = n % 10; return n > 10 && n < 20 ? c : m > 1 && m < 5 ? b : m === 1 ? a : c; };
  const LV = {1: 'Главная и меню', 2: 'Разделы', 3: 'Подразделы и карточки'};
  const LV_HINT = {1: 'тема главной и разделы, на которые ссылается почти каждая страница: ядро сайта',
    2: 'разделы каталога и услуг', 3: 'подразделы глубже и карточки товаров: в основном модели и хвосты, включайте по выбору'};
  const SHOW = 150;
  let MK = null, HOST = '', LAST = '', SEMF = '', FIND = '', ALL = {}, timer = 0;

  function sum(){
    if (!MK || !MK.masks.length) return 'маски ещё не предложены';
    const on = MK.masks.filter(m => m.on).length;
    return `· включено ${num(on)} из ${num(MK.masks.length)}` + (MK.confirmed ? ', подтверждены' : ', не подтверждены')
      + (MK.stop.length ? ` · стоп-слов ${num(MK.stop.length)}` : '');
  }
  function row(m, i){
    return `<div class="mk-row${m.on ? '' : ' off'}" data-i="${i}">
      <input type="checkbox" data-f="on"${m.on ? ' checked' : ''} title="Собирать по этой маске">
      <input type="text" data-f="t" value="${esc(m.t)}" title="Как маску ищут в поиске: её можно поправить">
      <select data-f="lv" title="Уровень">${[1, 2, 3].map(l => `<option value="${l}"${m.lv === l ? ' selected' : ''}>${l}</option>`).join('')}</select>
      <span class="mk-src">${esc(m.src)}${m.new ? ' <b class="mk-new">новая</b>' : ''}${m.note ? ` · <span class="mk-note">${esc(m.note)}</span>` : ''}${m.url ? ` <a href="${esc(m.url)}" target="_blank" title="${esc(m.name)}">↗</a>` : ''}</span>
      ${m.src === 'своя' ? '<button class="btn small" data-f="del" title="Убрать свою маску">×</button>' : '<span></span>'}</div>`;
  }
  function draw(){
    const body = $('mkBody'); if (!body) return;
    $('mkSum').textContent = sum();
    if (!MK) { body.innerHTML = '<p class="mut">Загружаю…</p>'; return; }
    if (!MK.masks.length) {
      body.innerHTML = `<p class="hint">Маски - фразы, по которым программа собирает подсказки Яндекса и Google. Программа предложит их по проверке сайта: главная и меню, разделы, подразделы и карточки. Вы поправите лишнее и подтвердите, и сбор пойдёт только по ним: так не тратятся запросы на служебные страницы и хвосты.</p>
        <div><button class="btn primary" id="mkPropose">Предложить маски</button> <span class="mut" id="mkMsg"></span></div>` + stopHtml();
      return;
    }
    const f = FIND.toLowerCase(), est = MK.masks.filter(m => m.on).length * 4;
    let h = (MK.stale ? `<div class="mk-stale">${MK.stale_rules ? 'Программа стала точнее выбирать разделы, а эти маски сделаны по старым правилам.' : 'Есть проверка сайта новее, чем маски.'} <button class="btn small" id="mkPropose">Обновить маски</button> <span class="mut">Ваши правки сохранятся, новые разделы придут отметкой «новая».</span></div>` : '')
      + `<p class="hint">Сбор идёт только по включённым маскам${MK.confirmed ? ` (подтверждены ${esc(MK.at)})` : ''}. По каждой - около 4 запросов подсказок, всего около ${num(est)}. Текст маски можно поправить, уровень - поменять. Запрос, который подошёл к подразделу, к разделу выше уже не относится, и Вордстат проверяет каждую фразу один раз: сначала главная и меню, потом разделы, потом остальное.</p>
      <div class="mk-tools"><input type="search" id="mkFind" placeholder="Найти маску" value="${esc(FIND)}" autocomplete="off">
      <input type="text" id="mkAddT" placeholder="Своя маска, например: ремонт газовых котлов" autocomplete="off">
      <select id="mkAddL">${[1, 2, 3].map(l => `<option value="${l}"${l === 2 ? ' selected' : ''}>${l}: ${LV[l]}</option>`).join('')}</select>
      <button class="btn small" id="mkAdd">Добавить</button> <span class="mut" id="mkMsg"></span></div>`;
    for (const lv of [1, 2, 3]) {
      const items = MK.masks.map((m, i) => [m, i]).filter(([m]) => m.lv === lv);
      if (!items.length) continue;
      const vis = items.filter(([m]) => !f || m.t.includes(f) || (m.name || '').toLowerCase().includes(f));
      const on = items.filter(([m]) => m.on).length, lim = ALL[lv] || f ? vis.length : SHOW;
      h += `<details class="mk-lv"${lv < 3 || f ? ' open' : ''}><summary><b>Уровень ${lv}. ${LV[lv]}</b> <span class="mut">включено ${num(on)} из ${num(items.length)} · ${LV_HINT[lv]}</span>
        ${lv === 2 && !on && items.length > 300 ? '<span class="mk-note">сайт большой: сначала соберите ядро (уровень 1), потом включите этот уровень и нажмите «Собрать по маскам» ещё раз - уже собранное не повторится</span>' : ''}</summary>
        <label class="mk-all"><input type="checkbox" data-lv="${lv}"${on === items.length ? ' checked' : ''}${on && on < items.length ? ' data-part="1"' : ''}> собирать весь уровень</label>
        <div class="mk-list">${vis.slice(0, lim).map(([m, i]) => row(m, i)).join('')}</div>
        ${vis.length > lim ? `<button class="btn small" data-more="${lv}">Показать все ${num(vis.length)}</button>` : ''}</details>`;
    }
    h += stopHtml()
      + `<div class="mk-go"><button class="btn primary" id="mkOk">${MK.confirmed ? 'Собрать по маскам' : 'Подтвердить маски и собрать'}</button>
        ${MK.confirmed ? '<button class="btn" id="mkUn" title="Собирать как раньше: по всем разделам, которые программа нашла сама">Не использовать маски</button>' : ''}</div>`;
    body.innerHTML = h;
    body.querySelectorAll('input[data-part]').forEach(x => x.indeterminate = true);
  }
  function stopHtml(){
    const ok = new Set(MK && MK.ok || []);
    const C = (MK && MK.candidates || []).filter(w => !MK.stop.includes(w) && !ok.has(w));
    return `<div class="mk-stop"><div class="f-label">Стоп-слова этого клиента</div>
      <p class="hint">Запросы с ними уходят в «Отсеяно» сразу, без нового сбора, и Вордстат на них не тратится. Слово от 5 букв ловит и другие формы («аренда» - «аренду»), фраза - целиком. Чужие города, «бесплатно», «своими руками», «б/у», «скачать» и названия конкурентов отсеиваются всегда.</p>
      <textarea id="mkStop" rows="3" placeholder="оптом, аренда, чертеж">${esc((MK && MK.stop || []).join(', '))}</textarea>
      ${C.length ? `<div class="mut mk-cand">Этих слов нет на страницах сайтов, а в запросах встречаются. Чужое слово - «в стоп-слова»,
        слово про вас («топ», «раскрутка») - «про нас», и запросы с ним вернутся в группы при следующем сборе:
        ${C.map(w => `<span class="mk-cw"><b>${esc(w)}</b> <button class="rchip-b" data-stop="${esc(w)}" title="Запросы с «${esc(w)}» уйдут в «Отсеяно»">в стоп-слова</button><button class="rchip-b" data-okc="${esc(w)}" title="Слово по теме сайта: запросы с ним вернутся в группы при следующем «Собрать заново»">про нас</button></span>`).join(' ')}</div>` : ''}
      ${(MK && MK.ok || []).length ? `<div class="mut mk-cand">Про нас: ${MK.ok.map(w => `<button class="rchip-b" data-okx="${esc(w)}" title="Убрать из «про нас»">✓ ${esc(w)}</button>`).join(' ')}</div>` : ''}
      <span class="mut" id="mkStopMsg"></span></div>`;
  }
  async function post(body){
    const r = await fetch('/api/semantics_masks', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.assign({host: HOST, f: LAST}, body))});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || 'Не получилось сохранить.');
    const cand = MK && MK.candidates; MK = j; if (!MK.candidates.length && cand) MK.candidates = cand;
    return j;
  }
  const slim = () => MK.masks.map(m => ({k: m.k, t: m.t, lv: m.lv, on: m.on}));
  function saveSoon(){ clearTimeout(timer); timer = setTimeout(() => post({masks: slim()}).then(() => { $('mkSum').textContent = sum(); }).catch(e => { const x = $('mkMsg'); if (x) x.textContent = e.message; }), 600); }

  async function load(g, last, sem){
    HOST = g && !g.new_site ? new URL(g.site).host.replace(/^www\./, '') : '';
    LAST = last ? last.folder : ''; SEMF = sem ? sem.folder : ''; FIND = ''; ALL = {};
    $('mkBox').hidden = !HOST;
    if (!HOST) { MK = null; return; }
    // свёрнут, пока человек сам не развернул на этом сайте (запоминается по сайту)
    // свёрнут, если только не ждёт подтверждения после «Собрать заново» (ASK) - тогда развёрнут и с подсказкой
    $('mkBox').open = openSaved(HOST) || ASK === HOST;
    MK = null; draw();
    const h = HOST, q = new URLSearchParams({host: HOST, f: LAST, s: SEMF});
    const mk = await fetch('/api/semantics_masks?' + q).then(r => r.json()).catch(() => null);
    if (h !== HOST) return;   // пока грузилось, выбрали другой сайт
    MK = mk;
    draw();
    if (ASK === HOST && MK && MK.masks.length && !MK.confirmed) {   // маски предложены по «Собрать заново»: сбор ждёт подтверждения
      const x = $('mkMsg'); if (x) x.textContent = 'Маски предложены. Проверьте их и нажмите «Подтвердить маски и собрать» внизу списка - тогда начнётся сбор.';
      const e = $('semErr'); if (e) e.textContent = 'Семантика ещё не собирается: сначала подтвердите маски (блок «Маски и стоп-слова» ниже).';
    }
  }
  let ASK = '';   // сайт, где «Собрать заново» ждёт подтверждения масок
  const OPEN_KEY = 'semMasksOpen';
  function openSaved(h){
    try { return !!(JSON.parse(localStorage.getItem(OPEN_KEY) || '{}')[h]); } catch (e) { return false; }
  }
  function openSave(h, on){
    try { const d = JSON.parse(localStorage.getItem(OPEN_KEY) || '{}'); if (on) d[h] = 1; else delete d[h];
      localStorage.setItem(OPEN_KEY, JSON.stringify(d)); } catch (e) { /* без памяти браузера - просто свёрнут */ }
  }
  // запоминается только то, что человек сделал сам: щелчок по заголовку блока
  document.addEventListener('click', e => {
    const s = e.target.closest && e.target.closest('#mkBox > summary');
    if (s && HOST) { const h = HOST; setTimeout(() => openSave(h, $('mkBox').open), 0); }
  });
  async function propose(){
    const r = await fetch('/api/semantics_masks_propose', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({folder: LAST})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { const x = $('mkMsg'); if (x) x.textContent = j.error || 'Не получилось запустить.'; return false; }
    $('mkBox').open = true; ASK = HOST;
    if (window.semPoll) window.semPoll();
    return true;
  }
  // перед сбором: маски есть и подтверждены - собрать; нет или устарели - сначала предложить и показать
  async function ready(){
    if (!HOST || !MK) return true;
    if (MK.masks.length && !MK.stale && MK.confirmed) return true;
    $('mkBox').open = true; ASK = HOST;
    const e = $('semErr'); if (e) e.textContent = 'Семантика ещё не собирается: сначала подтвердите маски (блок «Маски и стоп-слова» ниже).';
    if (window.claylerNotify) window.claylerNotify({kind: 'warn', title: 'Семантика ещё не собирается: ' + HOST,   // плашка (page/notify.js)
      text: MK.masks.length && !MK.stale ? 'Сначала подтвердите маски: блок «Маски и стоп-слова».' : 'Сначала программа предложит маски, потом их нужно подтвердить.'});
    if (!MK.masks.length || MK.stale) { await propose(); return false; }
    $('mkBox').scrollIntoView({block: 'start', behavior: 'smooth'});
    const x = $('mkMsg'); if (x) x.textContent = 'Проверьте маски и нажмите «Подтвердить маски и собрать» внизу списка.';
    return false;
  }

  document.addEventListener('click', async e => {
    const t = e.target;
    if (!t.closest || !t.closest('#mkBox')) return;
    if (t.id === 'mkPropose') { t.disabled = true; await propose(); return; }
    if (t.dataset.more) { ALL[t.dataset.more] = true; draw(); return; }
    if (t.dataset.f === 'del') { MK.masks.splice(+t.closest('.mk-row').dataset.i, 1); draw(); saveSoon(); return; }
    if (t.dataset.stop) { const ta = $('mkStop'); ta.value = (ta.value.trim() ? ta.value.trim().replace(/,$/, '') + ', ' : '') + t.dataset.stop; t.closest('.mk-cw').remove(); saveStop(); return; }
    if (t.dataset.okc || t.dataset.okx) {   // «про нас»: слово запоминается для сайта (masks.set_ok), как в «Отсеяно»
      const w = t.dataset.okc || t.dataset.okx;
      const r = await fetch('/api/semantics_ok', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({host: HOST, [t.dataset.okc ? 'add' : 'remove']: [w]})});
      if (r.ok) { MK.ok = (await r.json()).ok; draw(); }
      return;
    }
    if (t.id === 'mkAdd') {
      const v = $('mkAddT').value.trim().toLowerCase(); if (!v) return;
      if (MK.masks.some(m => m.t === v)) { $('mkMsg').textContent = 'Такая маска уже есть.'; return; }
      MK.masks.push({k: '', t: v, lv: +$('mkAddL').value, on: true, src: 'своя', name: v, url: ''});
      try { await post({masks: slim()}); } catch (err) { $('mkMsg').textContent = err.message; }
      draw(); return;
    }
    if (t.id === 'mkOk') {
      t.disabled = true;
      try { await post({masks: slim(), stop: stopList(), confirmed: true}); } catch (err) { $('mkMsg').textContent = err.message; t.disabled = false; return; }
      ASK = ''; const e = $('semErr'); if (e) e.textContent = '';
      draw(); if (window.semStart) window.semStart(); return;
    }
    if (t.id === 'mkUn') { await post({confirmed: false}); draw(); }
  });
  document.addEventListener('change', e => {
    const t = e.target; if (!t.closest || !t.closest('#mkBox')) return;
    if (t.dataset.lv) {   // весь уровень
      MK.masks.forEach(m => { if (m.lv === +t.dataset.lv) m.on = t.checked; }); draw(); saveSoon(); return;
    }
    const rw = t.closest('.mk-row');
    if (rw) {
      const m = MK.masks[+rw.dataset.i];
      if (t.dataset.f === 'on') { m.on = t.checked; rw.classList.toggle('off', !m.on); }
      if (t.dataset.f === 't') m.t = t.value.trim().toLowerCase() || m.t;
      if (t.dataset.f === 'lv') { m.lv = +t.value; draw(); }
      $('mkSum').textContent = sum(); saveSoon(); return;
    }
    if (t.id === 'mkStop') saveStop();
  });
  document.addEventListener('input', e => { if (e.target.id === 'mkFind') { FIND = e.target.value; const p = e.target.selectionStart; draw(); const x = $('mkFind'); x.focus(); x.setSelectionRange(p, p); } });
  const stopList = () => ($('mkStop') ? $('mkStop').value : '').split(/[,;\n]+/).map(s => s.trim().toLowerCase()).filter(Boolean);
  async function saveStop(){
    try { await post({stop: stopList()}); $('mkSum').textContent = sum();
      if (window.semReload) await window.semReload();   // запросы со стоп-словами - сразу в «Отсеяно»
      const x = $('mkStopMsg'); if (x) x.textContent = 'Сохранено: запросы с этими словами ушли в «Отсеяно».'; }
    catch (err) { $('mkStopMsg').textContent = err.message; }
  }
  window.semMasks = {load, ready};
})();
