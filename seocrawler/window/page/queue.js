// «Очередь сайтов» (seocrawler/site_queue.py): список сайтов проверяется по одному, сам.
// Пользуется общим из app.js: $, esc, plural, host, fmtTime, VIEW_LOAD.
(() => {
  let Q = null, timer = null, filter = 'all';
  const STATE = {wait: 'ждёт', run: 'идёт', done: 'готово', fail: 'пропущен'};
  const SEM = {wait: 'ждёт', run: 'собирается', done: 'собрана', fail: 'не собрана'};
  const about = s => { s = Math.max(60, Math.round(s / 300) * 300); const h = Math.floor(s / 3600), m = Math.round(s % 3600 / 60);
    return h ? `${h} ч` + (m ? ` ${m} мин` : '') : `${m} мин`; };
  const post = async (act, body) => {
    const r = await fetch('/api/queue/' + act, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || 'Не получилось');
    return j;
  };
  const act = async (a, body) => {
    $('qErr').textContent = '';
    try { const j = await post(a, body); await load(); return j; } catch (e) { $('qErr').textContent = e.message; }
  };
  const when = t => { const d = new Date(t * 1000), p = x => String(x).padStart(2, '0');
    return `${p(d.getDate())}.${p(d.getMonth() + 1)} в ${p(d.getHours())}:${p(d.getMinutes())}`; };
  const num = n => n == null ? '' : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

  function badge(){
    const b = $('qBadge'); if (!b || !Q) return;
    const left = Q.counts.wait + Q.counts.run;
    b.hidden = !left; b.textContent = left;
  }

  function render(){
    if (!Q) return;
    const c = Q.counts, left = c.wait + c.run, all = Q.items.length;
    const cur = Q.items.find(i => i.state === 'run' || i.sem === 'run');
    let st;
    if (!all) st = 'Очередь пуста. Вставьте сайты ниже или загрузите готовый список.';
    else if (cur) st = `<b>Идёт: ${cur.kind === 'sem' || cur.sem === 'run' ? 'семантика ' : ''}${esc(host(cur.url))}</b>` + (Q.paused ? ' · после него очередь встанет на паузу' : '');
    else if (Q.paused && (c.wait || c.sem_wait)) st = '<b>На паузе</b>';
    else if (Q.other_job && (c.wait || c.sem_wait)) st = '<b>Ждёт:</b> идёт другая проверка, очередь продолжится после неё';
    else if (c.wait || c.sem_wait) st = '<b>Запускаю следующий сайт…</b>';
    else st = '<b>Очередь закончилась</b>';
    if (all) st += `<br><span class="mut">Осталось ${left} ${plural(left, 'сайт', 'сайта', 'сайтов')} из ${all}` +
      ` · готово ${c.done}` + (c.fail ? ` · пропущено ${c.fail}` : '') + '</span>';
    const E = Q.eta;
    if ((left || c.sem_wait) && E && E.seconds)   // по уже проверенным сайтам: секунд на страницу и сколько страниц набирают
      st += `<br><span class="mut" title="Оценка по ${E.sites} ${plural(E.sites, 'проверенному сайту', 'проверенным сайтам', 'проверенным сайтам')}: сайт при лимите ${num(Q.pages)} набирает в среднем ${num(Math.round(E.share * Q.pages))} страниц и идёт около ${esc(about(E.per_site))}. Пропущенные сайты и семантика тоже учтены.">Осталось примерно ${esc(about(E.seconds))}</span>`;
    else if (left && !E) st += '<br><span class="mut2">Сколько осталось, станет видно после первого проверенного сайта.</span>';
    $('qState').innerHTML = st;
    $('qStart').hidden = !(Q.paused && (c.wait || c.sem_wait));
    $('qStart').textContent = c.done || c.fail ? 'Продолжить' : 'Запустить';
    $('qPause').hidden = Q.paused || !left;
    $('qStop').hidden = $('qSkip').hidden = !cur;
    if (document.activeElement !== $('qPages')) $('qPages').value = Q.pages;
    $('qSem').checked = !!Q.sem_after;
    $('qLists').innerHTML = (Q.lists || []).map(l =>
      `<button class="ghost q-list" data-file="${esc(l.file)}" title="Добавить в очередь ${l.count} ${plural(l.count, 'сайт', 'сайта', 'сайтов')} из файла «очередь\\${esc(l.file)}»">Загрузить «${esc(l.name)}»</button>`).join('');
    const F = {all: 'Все', wait: 'Ждут', done: 'Готово', fail: 'Пропущены'};
    $('qFilter').innerHTML = all ? Object.entries(F).map(([k, t]) => {
      const n = k === 'all' ? all : k === 'wait' ? left : c[k];
      return `<button class="ghost small${filter === k ? ' on' : ''}" data-f="${k}">${t} ${n}</button>`; }).join('') : '';
    const rows = Q.items.map((i, n) => [i, n + 1]).filter(([i]) => filter === 'all' || (filter === 'wait' ? (i.state === 'wait' || i.state === 'run') : i.state === filter));
    $('qRows').innerHTML = rows.map(([i, n]) => {
      const site = `<b>${esc(host(i.url))}</b>` + (i.kind === 'sem' ? ' <span class="q-kind" title="Сбор семантики готовой проверки, без новой проверки сайта">семантика</span>' : '') + (i.big ? ' <span class="tag warn" title="Очень большой сайт: проверится только до лимита страниц">очень большой</span>' : '') +
        (i.note ? `<div class="mut2 q-note">${esc(i.note)}</div>` : '');
      let state = `<span class="q-st ${i.state}">${STATE[i.state] || i.state}</span>`;
      if (i.finished && (i.state === 'done' || i.state === 'fail'))   // когда закончился и сколько шёл
        state += ` <span class="mut2">${when(i.finished)}${i.took ? ', за ' + esc(fmtTime(i.took)) : ''}</span>`;
      if (i.reason) state += `<div class="mut2 q-note">${esc(i.reason)}</div>`;
      if (i.sem) state += `<span class="q-sem ${i.sem}">Семантика ${SEM[i.sem] || i.sem}${i.sem_took ? ', за ' + esc(fmtTime(i.sem_took)) : ''}${i.sem_queries ? `, ${num(i.sem_queries)} ${plural(i.sem_queries, 'запрос', 'запроса', 'запросов')}` : ''}${i.sem_reason ? ': ' + esc(i.sem_reason) : ''}</span>`;
      if (i.kind === 'sem' && i.state === 'done' && i.sem_queries) state += `<span class="q-sem done">${num(i.sem_queries)} ${plural(i.sem_queries, 'запрос', 'запроса', 'запросов')}</span>`;
      const k = i.kind ? ` data-k="${esc(i.kind)}"` : '';
      const pages = i.state === 'done' || i.state === 'fail' ? num(i.pages) : (i.limit && i.state === 'wait' ? 'до ' + num(i.limit) : '');
      const semDone = i.sem === 'done' || (i.kind === 'sem' && i.state === 'done');
      const btns = i.state === 'run' || i.sem === 'run' ? '' :
        (i.folder && i.kind !== 'sem' && (i.state === 'done' || i.state === 'fail') ? `<a class="btn small" href="/r/${encodeURIComponent(i.folder)}/отчёт.html" target="_blank">Отчёт</a>` : '') +
        (semDone && i.folder ? `<a class="btn small" href="/semantics?f=${encodeURIComponent(i.folder)}" target="_blank">Семантика</a>` : '') +
        (i.state === 'done' && i.kind !== 'sem' && i.folder && (!i.sem || i.sem === 'fail') ? `<button class="ghost small" data-a="sem_retry" data-u="${esc(i.url)}" title="Быстрый сбор семантики: главная и разделы, без Вордстата">Собрать семантику</button>` : '') +
        (i.state === 'fail' || i.state === 'done' ? `<button class="ghost small" data-a="retry" data-u="${esc(i.url)}"${k}>Ещё раз</button>` : '') +
        (i.state === 'wait' ? `<button class="ghost small" data-a="up" data-u="${esc(i.url)}"${k}>Следующим</button>` : '') +
        `<button class="ghost small" data-a="remove" data-u="${esc(i.url)}"${k} title="Убрать из очереди">✕</button>`;
      return `<tr class="${i.state}"><td class="mut2">${n}</td><td>${site}</td><td>${state}</td><td class="num">${pages}</td><td class="q-btns">${btns}</td></tr>`;
    }).join('') || (all ? '<tr><td colspan="5" class="mut">Здесь пусто.</td></tr>' : '');
    $('qTable').hidden = !all;
    $('qClearAll').hidden = !all;
    hist();
    badge();
  }

  // прошлые очереди: когда, сколько сайтов, страниц и времени, по каждому сайту
  let histKey = '';
  function hist(){
    const H = Q.history || [];
    $('qHist').hidden = !H.length;
    const key = JSON.stringify(H.map(r => [r.began, r.ended, r.items.length]));
    if (key === histKey) return;   // не перерисовывать раскрытое каждые 4 секунды
    histKey = key;
    $('qHistN').textContent = H.length ? `(${H.length})` : '';
    $('qHistBody').innerHTML = H.map((r, n) => `<details${n ? '' : ' open'}><summary class="q-run"><b>${esc(when(r.began))}</b>${r.ended ? ' - ' + esc(when(r.ended)) : ''}
      <span class="mut2">· готово ${r.done}${r.fail ? `, пропущено ${r.fail}` : ''}${r.sem ? `, семантика ${r.sem}` : ''} · ${num(r.pages)} стр. · ${esc(fmtTime(r.took))}</span></summary>
      <div class="tw"><table><thead><tr><th>Сайт</th><th>Итог</th><th class="num">Страниц</th><th class="num">Время</th><th class="num">с на стр.</th></tr></thead><tbody>${
      r.items.slice().sort((a, b) => (a.finished || 0) - (b.finished || 0)).map(x => `<tr><td>${esc(host(x.url))}${x.kind === 'sem' ? ' <span class="q-kind">семантика</span>' : ''}</td>
        <td><span class="q-st ${x.state}">${STATE[x.state] || x.state}</span>${x.sem ? ` <span class="q-sem ${x.sem}">семантика ${SEM[x.sem] || x.sem}${x.sem_took ? ', ' + esc(fmtTime(x.sem_took)) : ''}</span>` : ''}${x.reason ? `<div class="mut2 q-note">${esc(x.reason)}</div>` : ''}</td>
        <td class="num">${x.kind === 'sem' ? (x.sem_queries ? num(x.sem_queries) + ' запр.' : '') : num(x.pages)}${x.pages_limit && x.kind !== 'sem' && x.pages != null ? ` <span class="mut2">из ${num(x.pages_limit)}</span>` : ''}</td>
        <td class="num">${x.took ? esc(fmtTime(x.took)) : ''}</td>
        <td class="num">${x.kind !== 'sem' && x.took && x.pages ? String(Math.round(x.took / x.pages * 10) / 10).replace('.', ',') : ''}</td></tr>`).join('')}</tbody></table></div></details>`).join('');
  }

  async function load(){
    try { Q = await (await fetch('/api/queue')).json(); } catch (e) { return; }
    render();
  }
  function loop(){
    clearTimeout(timer);
    load().finally(() => { timer = setTimeout(loop, document.querySelector('.view[data-view="queue"]').hidden ? 30000 : 4000); });
  }

  $('qStart').onclick = () => act('start');
  $('qPause').onclick = () => act('pause');
  $('qSkip').onclick = () => { if (confirm('Пропустить текущий сайт и перейти к следующему? Отчёт по нему соберётся по тому, что успели проверить.')) act('skip'); };
  $('qStop').onclick = () => { if (confirm('Остановить текущий сайт? Отчёт по нему соберётся по тому, что успели проверить, очередь встанет на паузу. При продолжении этот сайт пойдёт с того же места.')) act('stop'); };
  $('qPages').onchange = () => act('pages', {pages: +$('qPages').value});
  $('qSem').onchange = () => act('sem_after', {on: $('qSem').checked});
  $('qAdd').onclick = async () => {
    const j = await act('add', {text: $('qText').value, pages: +$('qPages').value});
    if (j) { $('qText').value = ''; if (!j.added) $('qErr').textContent = 'Эти сайты уже стоят в очереди.'; }
  };
  $('qLists').onclick = async e => {
    const b = e.target.closest('[data-file]'); if (!b) return;
    const j = await act('add_list', {file: b.dataset.file, pages: +$('qPages').value});
    if (j && !j.added) $('qErr').textContent = 'Все сайты из этого списка уже стоят в очереди.';
  };
  $('qFilter').onclick = e => { const b = e.target.closest('[data-f]'); if (b) { filter = b.dataset.f; render(); } };
  $('qRows').onclick = e => { const b = e.target.closest('[data-a]'); if (b) act(b.dataset.a, {url: b.dataset.u, kind: b.dataset.k || ''}); };
  $('qClearAll').onclick = () => { if (confirm('Убрать из очереди все сайты? Готовые отчёты останутся в списке отчётов.')) act('clear_all'); };

  VIEW_LOAD.queue = loop;
  loop();
})();
