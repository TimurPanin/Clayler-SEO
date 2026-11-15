// Страница «Семантика»: точная частотность Вордстата через API Директа (direct.py). Кнопка «Загрузить частотность»,
// полоса «готово N из M» и сколько дней осталось, лента последних фраз (по подсказкам - точно), группы цветом
// (точные цифры есть / частично / ждут), «самое интересное»: пустышки и неожиданно крупные запросы.
(function(){
  let timer = null, lastDone = -1, open = false, openFor = '', allGroups = false, off = false;
  // «Как идёт загрузка» свёрнуто, пока человек сам не развернул на этом сайте (запоминается по сайту)
  const OPEN_KEY = 'semDirectOpen', site = f => (f || '').split('_')[0];
  const openSaved = f => { try { return !!JSON.parse(localStorage.getItem(OPEN_KEY) || '{}')[site(f)]; } catch (e) { return false; } };
  const openSave = (f, on) => { try { const d = JSON.parse(localStorage.getItem(OPEN_KEY) || '{}'); if (on) d[site(f)] = 1; else delete d[site(f)];
    localStorage.setItem(OPEN_KEY, JSON.stringify(d)); } catch (e) { /* без памяти браузера - просто свёрнуто */ } };
  document.addEventListener('click', e => { const s = e.target.closest && e.target.closest('#semDirect .dmore > summary');
    if (s && FOLDER) { const f = FOLDER; setTimeout(() => { const d = box().querySelector('.dmore'); if (d) { open = d.open; openSave(f, d.open); } }, 0); } });
  const TOP = 20;
  const box = () => $('semDirect');
  const LV = ['', 'низкий', 'средний', 'высокий'];
  const day = n => `${num(n)} ${plural(n, 'день', 'дня', 'дней')}`;
  function feedRow(x){
    return `<li><span>${esc(x.q)}</span><span class="mut">по подсказкам ${LV[x.level]} спрос</span><b>точно ${num(x.freq)}${x.broad != null ? ` <span class="mut" title="Без кавычек: фраза со всеми хвостами">с хвостами ${num(x.broad)}</span>` : ''}</b></li>`;
  }
  function groupsHtml(G){
    return (allGroups ? G : G.slice(0, TOP)).map(g => {
      const cls = g.done >= g.n ? 'full' : g.done ? 'part' : 'wait';
      return `<span class="dg ${cls}" title="${esc(g.name)}: точная частота у ${num(g.done)} из ${num(g.n)} ${plural(g.n, 'запроса', 'запросов', 'запросов')}${g.freq ? `, ${num(g.freq)} в месяц` : ''}">${esc(g.name)}${g.done ? ` <small>${num(g.freq)}</small>` : ''}</span>`;
    }).join('');
  }
  function detail(P){
    if (!P || !P.done) return '';
    const full = P.groups.filter(g => g.done >= g.n).length, part = P.groups.filter(g => g.done && g.done < g.n).length;
    const list = (a, empty) => a.length ? `<ul class="dfeed">${a.map(feedRow).join('')}</ul>` : `<p class="mut">${empty}</p>`;
    return `<details class="dmore"${open ? ' open' : ''}><summary>Как идёт загрузка</summary>
      <div class="dcols"><div><div class="f-label">Последние фразы</div>${list(P.feed, '')}</div>
      <div><div class="f-label">Самое интересное</div>
        <p class="mut">Пустышки: по подсказкам спрос высокий, а ищут почти никто, даже с хвостами (проверено без кавычек).${P.empty_wait ? ` Ещё ${num(P.empty_wait)} ${plural(P.empty_wait, 'кандидат проверяю', 'кандидата проверяю', 'кандидатов проверяю')} по ходу загрузки.` : ''}</p>${list(P.empty, 'Пока не нашлось.')}
        ${(P.city_small || []).length ? `<p class="mut">В регионе «${esc(P.region)}» почти не ищут, но по России ищут - это не пустышки, просто мало в городе:</p>${list(P.city_small, '')}` : ''}
        <p class="mut">Неожиданно крупные: по подсказкам спрос низкий или средний, а точно ищут много. Запросы из одного слова не берутся: это часто другое значение слова.</p>${list(P.big, 'Пока не нашлось.')}</div></div>
      <div class="f-label">Группы: <span class="dg full">все цифры</span> ${num(full)} · <span class="dg part">часть</span> ${num(part)} · <span class="dg wait">ждут</span> ${num(P.groups.length - full - part)}</div>
      <p class="mut">Сначала самые востребованные. Число на плашке - сколько раз в месяц ищут запросы группы (сумма точных частот).</p>
      <div class="dgroups">${groupsHtml(P.groups)}</div>
      ${P.groups.length > TOP ? `<button class="btn small" id="dirAllG">${allGroups ? 'Только первые ' + TOP : 'Показать все ' + num(P.groups.length)}</button>` : ''}</details>`;
  }
  async function poll(){
    if (off || !FOLDER || !box()) return;
    const f = FOLDER;
    let D; try { D = await (await fetch('/api/direct?f=' + encodeURIComponent(f))).json(); } catch (e) { return; }
    if (off || f !== FOLDER) return;   // пока ждали ответ, выбрали другой сайт
    const J = D.job || {}, P = D.progress;
    if (!D.has_token) { box().hidden = true; return; }
    box().hidden = false;
    if (openFor !== f) { openFor = f; open = openSaved(f); }   // другой сайт - как запомнено для него
    else { const old = box().querySelector('.dmore'); if (old) open = old.open; }
    const busy = J.state === 'running' || J.state === 'waiting';
    const st = J.state === 'running' ? 'Загружаю…'
      : J.state === 'waiting' ? esc(J.msg || 'Лимит Яндекса на сегодня исчерпан, продолжу завтра.') + ' Окно программы должно быть открыто.'
      : J.state === 'done' || J.state === 'stopped' ? esc(J.msg)
      : J.state === 'error' ? `<span class="err">${esc(J.msg)}</span>` : '';
    const pct = P && P.total ? Math.round(P.done / P.total * 100) : 0;
    box().innerHTML = `<div class="dhead"><div><b>Точная частотность</b> <span class="mut">Вордстат через Директ, ${esc((P && P.region) || 'вся Россия')}, фраза в кавычках</span></div>
      <button class="btn small${busy ? '' : ' primary'}" id="dirGo">${busy ? 'Остановить' : P && P.done ? 'Догрузить частотность' : 'Загрузить частотность'}</button></div>
      ${P ? `<div class="pbar dbar"><i style="width:${pct}%"></i></div>
      <div class="mut">Готово ${num(P.done)} из ${num(P.total)} ${plural(P.total, 'фразы', 'фраз', 'фраз')} (${pct}%)${P.done < P.total ? (P.fast ? (busy ? ', загружаю' : ', загружу') + ' прогнозом Директа: по 100 фраз, без суточного лимита' : `, осталось примерно ${day(P.days)} по ${num(D.limit)} в день`) : ''}. Сегодня отправлено ${num(D.used)} из ${num(D.limit)}.</div>
      ${P.sieved ? `<div class="mut">Из готовых ${num(P.sieved)} ${plural(P.sieved, 'фраза отсеяна', 'фразы отсеяны', 'фраз отсеяно')} сразу: Директ отвечает, что показов нет (это точно 0), суточный лимит на них не тратится.</div>` : ''}` : ''}
      ${st ? `<div class="mut"${J.detail ? ` title="${esc(J.detail)}"` : ''}>${st}</div>` : ''}${(J.next || []).length ? `<div class="mut">${(J.next || []).includes(FOLDER) ? 'Этот сайт стоит в очереди частотности (выбран в «Отчётах»), загрузится после текущего. ' : ''}Ждут частотность после текущего: ${num(J.next.length)} ${plural(J.next.length, 'сайт', 'сайта', 'сайтов')}.</div>` : ''}${detail(P)}`;
    const ag = $('dirAllG'); if (ag) ag.onclick = () => { allGroups = !allGroups; poll(); };
    $('dirGo').onclick = async () => {
      $('dirGo').disabled = true;
      const r = await fetch('/api/direct/' + (busy ? 'stop' : 'start'), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({f: FOLDER})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) $('semErr').textContent = j.error || 'Не получилось.';
      poll();
    };
    // каждые 100 фраз и в конце - перечитать семантику, чтобы «Спрос» обновился
    const done = P ? P.done : 0;
    if (lastDone >= 0 && (done - lastDone >= 100 || (!busy && done !== lastDone))) { lastDone = done; loadData(FOLDER); }
    if (lastDone < 0) lastDone = done;
    clearTimeout(timer);
    timer = setTimeout(poll, J.state === 'running' ? 5000 : 60000);
  }
  window.semDirect = () => { lastDone = -1; off = false; poll(); };
  // у выбранного сайта семантики нет: не показывать частотность прошлого сайта
  window.semDirectOff = () => { off = true; clearTimeout(timer); if (box()) { box().hidden = true; box().innerHTML = ''; } };
})();
