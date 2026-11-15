// Уведомления и «Журнал» на каждой странице окна (главная, «Семантика», «Словарь»).
// - Плашки справа внизу: «Отчёт готов», «Семантика собрана», ошибки простыми словами (window/events.py).
//   Окно свёрнуто или закрыто другой программой - ещё и уведомление Windows (если разрешено в колокольчике).
//   Звук играет сама программа, не страница: так его слышно и при свёрнутом окне.
// - Колокольчик рядом с названием программы: история уведомлений, звук вкл/выкл, уведомления Windows.
// - Нажатые кнопки и ошибки страницы уходят в «Журнал» (applog.py). Что введено в поля, не пишется никогда:
//   только название кнопки, раздел и сайт.
// Для других скриптов: window.claylerNotify({kind: 'ok'|'err'|'warn'|'info', title, text, todo}).
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const ss = {get: k => { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
              set: (k, v) => { try { sessionStorage.setItem(k, v); } catch (e) { /* без памяти вкладки */ } }};
  const ICON = {ok: '<path d="m5 12.5 4.5 4.5L19 7.5"/>', err: '<path d="M12 8v5M12 16.5h.01"/><circle cx="12" cy="12" r="9"/>',
    warn: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5h.01"/>'};
  const icon = k => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[k] || ICON.info}</svg>`;
  const KIND_RU = {ok: 'Готово', err: 'Ошибка', warn: 'Нужно ваше действие', info: 'Сообщение'};

  // ---------- плашки
  const box = document.createElement('div'); box.className = 'nt-stack'; box.setAttribute('aria-live', 'polite');
  document.body.appendChild(box);
  function body(e){
    return `<div class="nt-t">${esc(e.title)}</div>${e.text ? `<div class="nt-x">${esc(e.text)}</div>` : ''}`
      + (e.todo ? `<div class="nt-todo"><b>Что сделать:</b> ${esc(e.todo)}</div>` : '')
      + (e.detail ? `<details class="nt-more"><summary>Подробнее</summary><pre>${esc(e.detail)}</pre></details>` : '')
      + (e.link ? `<a class="nt-go" href="${esc(e.link)}"${e.link.startsWith('/r/') ? ' target="_blank"' : ''}>Открыть</a>` : '');
  }
  function toast(e){
    while (box.children.length >= 4) box.firstElementChild.remove();
    const t = document.createElement('div'); t.className = 'nt nt-' + (e.kind || 'info'); t.setAttribute('role', e.kind === 'err' ? 'alert' : 'status');
    t.innerHTML = `<span class="nt-ic">${icon(e.kind)}</span><div class="nt-b">${body(e)}</div><button class="nt-x-btn" type="button" aria-label="Закрыть">×</button>`;
    t.querySelector('.nt-x-btn').onclick = () => t.remove();
    box.appendChild(t);
    const ms = {ok: 9000, info: 7000, warn: 15000}[e.kind];   // ошибка висит, пока не закроют
    if (ms) { let tm = setTimeout(() => t.remove(), ms);
      t.onmouseenter = () => clearTimeout(tm); t.onmouseleave = () => { tm = setTimeout(() => t.remove(), 4000); }; }
    return t;
  }
  function osNote(e){   // окно свёрнуто или за другой программой - уведомление Windows
    if (!document.hidden || !('Notification' in window) || Notification.permission !== 'granted') return;
    try { const n = new Notification('Clayler SEO: ' + e.title, {body: [e.text, e.todo].filter(Boolean).join(' '), tag: String(e.id || Date.now())});
      n.onclick = () => { window.focus(); if (e.link) location.href = e.link; n.close(); }; } catch (x) { /* не поддерживается */ }
  }
  window.claylerNotify = e => { toast(e); osNote(e); log({kind: 'event', text: (KIND_RU[e.kind] || '') + ': ' + e.title + (e.text ? '. ' + e.text : '')}); };

  // ---------- колокольчик
  let ST = {items: [], seen: 0, sound: true, last: 0}, panel = null;
  const bell = document.createElement('button'); bell.type = 'button'; bell.className = 'nt-bell'; bell.title = 'Уведомления';
  bell.setAttribute('aria-label', 'Уведомления');
  bell.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/></svg><span class="nt-n" hidden></span>';
  const place = () => { const b = document.querySelector('.side .brand'); if (b && !b.contains(bell)) { b.classList.add('has-bell'); b.appendChild(bell); } };
  place(); if (!bell.isConnected) document.addEventListener('DOMContentLoaded', place);
  function badge(){
    const n = ST.items.filter(e => e.id > ST.seen && e.kind !== 'info').length, s = bell.querySelector('.nt-n');
    s.hidden = !n; s.textContent = n > 9 ? '9+' : n; s.classList.toggle('bad', ST.items.some(e => e.id > ST.seen && e.kind === 'err'));
  }
  const when = t => { const d = new Date(t.replace(' ', 'T')), now = new Date();
    return (d.toDateString() === now.toDateString() ? '' : d.toLocaleDateString('ru', {day: 'numeric', month: 'short'}) + ', ') + t.slice(11, 16); };
  function perm(){
    if (!('Notification' in window)) return '';
    if (Notification.permission === 'granted') return '<span class="mut">Уведомления Windows включены: придут, когда окно свёрнуто.</span>';
    if (Notification.permission === 'denied') return '<span class="mut">Уведомления Windows запрещены в браузере (значок замка слева от адреса).</span>';
    return '<button type="button" class="small" id="ntPerm">Включить уведомления Windows</button>';
  }
  function draw(){
    if (!panel) return;
    const items = ST.items.slice().reverse();
    panel.innerHTML = `<div class="nt-p-head"><b>Уведомления</b><button type="button" class="small ghost" id="ntClose" aria-label="Закрыть">×</button></div>
      <div class="nt-p-list">${items.length ? items.map(e => `<div class="nt-p-i nt-${e.kind}${e.id > ST.seen ? ' new' : ''}"><span class="nt-ic">${icon(e.kind)}</span>
        <div class="nt-b"><div class="nt-when">${esc(when(e.t))}</div>${body(e)}</div></div>`).join('') : '<p class="mut nt-empty">Пока ничего не было. Здесь появятся «Отчёт готов», «Семантика собрана» и ошибки.</p>'}</div>
      <div class="nt-p-foot"><label class="nt-snd"><input type="checkbox" id="ntSound"${ST.sound ? ' checked' : ''}> Звук на «готово» и «ошибку»</label>${perm()}
        <div class="nt-p-btns"><a class="btn small" href="/#log">Весь журнал</a>${items.length ? '<button type="button" class="small ghost" id="ntClear">Очистить</button>' : ''}</div></div>`;
    panel.querySelector('#ntClose').onclick = () => toggle(false);
    panel.querySelectorAll('a').forEach(a => a.addEventListener('click', () => toggle(false)));
    panel.querySelector('#ntSound').onchange = ev => post({sound: ev.target.checked});
    const pb = panel.querySelector('#ntPerm'); if (pb) pb.onclick = () => Notification.requestPermission().then(draw);
    const cb = panel.querySelector('#ntClear'); if (cb) cb.onclick = () => post({clear: true});
  }
  function toggle(on){
    if (on === undefined) on = !panel;
    if (!on) { if (panel) panel.remove(); panel = null; return; }
    panel = document.createElement('div'); panel.className = 'nt-panel'; panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', 'Уведомления');
    document.body.appendChild(panel); draw();
    if (ST.last > ST.seen) post({seen: ST.last});
  }
  bell.onclick = e => { e.stopPropagation(); toggle(); };
  document.addEventListener('click', e => { if (panel && !panel.contains(e.target) && e.target !== bell) toggle(false); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && panel) toggle(false); });
  function post(d){
    return fetch('/api/events', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(d)})
      .then(r => r.json()).then(j => { Object.assign(ST, j); badge(); draw(); }).catch(() => {});
  }

  // ---------- новые уведомления: раз в 3 секунды
  let fails = 0, down = null, first = true;
  const shown = new Set((ss.get('claylerShown') || '').split(',').filter(Boolean).map(Number));
  async function poll(){
    let j;
    try { j = await (await fetch('/api/events?after=' + (first ? 0 : ST.last))).json(); }
    catch (e) {
      if (++fails === 2 && !down) down = toast({kind: 'err', title: 'Программа не отвечает',
        todo: 'Проверьте, что чёрное окно программы открыто. Если его закрыли, запустите «Clayler SEO.bat» заново, это окно обновится само.'});
      return;
    }
    if (down) { down.remove(); down = null; }
    fails = 0;
    const fresh = first ? j.items : j.items.filter(e => e.id > ST.last);
    ST.items = (first ? [] : ST.items).concat(fresh).slice(-100);
    Object.assign(ST, {seen: j.seen, sound: j.sound, last: Math.max(ST.last, j.last)});
    // плашкой - только новое: с открытия страницы или за последние 20 секунд (пока переходили между страницами)
    const since = Date.now() - 20000;
    fresh.filter(e => e.id > ST.seen && !shown.has(e.id) && (!first || new Date(e.t.replace(' ', 'T')).getTime() > since))
      .forEach(e => { shown.add(e.id); toast(e); osNote(e); });
    ss.set('claylerShown', [...shown].slice(-50).join(','));
    first = false; badge(); if (fresh.length) draw();
  }
  poll(); setInterval(poll, 3000);

  // ---------- «Журнал»: нажатые кнопки, переключатели и ошибки страницы
  let queue = [], lastKey = '', lastAt = 0, pending = null;
  function log(it){ queue.push(it); if (queue.length > 40) flush(); }
  function flush(beacon){
    if (pending) { queue.push(pending.it); clearTimeout(pending.tm); pending = null; }
    if (!queue.length) return;
    const b = JSON.stringify({items: queue.splice(0)});
    if (beacon && navigator.sendBeacon) navigator.sendBeacon('/api/log', b);
    else fetch('/api/log', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: b}).catch(() => {});
  }
  setInterval(flush, 3000);
  addEventListener('pagehide', () => flush(true));
  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();
  const short = s => { s = clean(s); return s.length > 80 ? s.slice(0, 79) + '…' : s; };
  function where(el){
    const dlg = el.closest('dialog'); if (dlg) { const h = dlg.querySelector('h2,h3'); if (h) return clean(h.textContent); }
    const nav = document.querySelector('.side .nav.on');
    let s = nav ? clean([...nav.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ')) : document.title;
    const tab = document.querySelector('.tabs .on, [role=tab][aria-selected=true], .sem-tabs .on');
    if (tab && !tab.contains(el) && location.pathname !== '/') s += ' → ' + clean(tab.textContent);
    return s;
  }
  const hostOf = s => clean(s).replace(/^https?:\/\//, '').split(/[\/\s]/)[0].replace(/^www\./, '').split('_')[0];
  function siteOf(el){
    const d = el.closest('[data-f],[data-site],[data-u],[data-folder],[data-host]');
    if (d) return hostOf(d.dataset.f || d.dataset.site || d.dataset.u || d.dataset.folder || d.dataset.host);
    for (const id of ['semSite', 'srSite', 'riSite', 'lsSite']) {
      const s = document.getElementById(id);
      if (s && s.offsetParent && s.selectedOptions[0] && s.value) return hostOf(s.selectedOptions[0].textContent.split('·')[0].replace(/^Новый сайт: /, ''));
    }
    const f = new URLSearchParams(location.search).get('f'); return f ? hostOf(f) : '';
  }
  function label(el){
    const t = el.getAttribute('aria-label') || clean(el.innerText || el.textContent) || el.title || el.value && el.type === 'button' && el.value || el.id;
    return short(t);
  }
  document.addEventListener('click', e => {
    const el = e.target.closest('button, a, summary, [role=button], [role=tab]');
    if (!el || el === bell || el.closest('.nt-panel, .nt-stack')) return;
    const name = label(el); if (!name) return;
    const key = name + where(el); if (key === lastKey && Date.now() - lastAt < 800) return;
    lastKey = key; lastAt = Date.now();
    const it = {kind: 'action', text: (el.tagName === 'SUMMARY' ? (el.parentElement.open ? 'Свёрнут блок ' : 'Развёрнут блок ') : 'Нажата кнопка ') + `«${name}» (${where(el)})`, site: siteOf(el)};
    if (pending) { queue.push(pending.it); clearTimeout(pending.tm); }
    pending = {it, tm: setTimeout(() => { if (pending) { queue.push(pending.it); pending = null; } }, 1500)};
  }, true);
  document.addEventListener('change', e => {
    const el = e.target; if (!el.matches('input[type=checkbox], input[type=radio], select')) return;
    if (el.closest('.nt-panel')) return;
    const lab = el.labels && el.labels[0] ? short(el.labels[0].innerText) : short(el.getAttribute('aria-label') || el.title || el.id);
    const text = el.tagName === 'SELECT' ? `«${lab}»: выбрано «${short(el.selectedOptions[0] ? el.selectedOptions[0].textContent : '')}»`
      : el.type === 'radio' ? `Выбрано «${lab}»` : `${el.checked ? 'Включено' : 'Выключено'} «${lab}»`;
    log({kind: 'action', text: text + ` (${where(el)})`, site: siteOf(el)});
  }, true);
  // действие отправило запрос в программу - сайт берём из запроса, если у кнопки его не было
  const ofetch = window.fetch.bind(window);
  window.fetch = (u, o) => {
    if (pending && o && o.method === 'POST' && typeof o.body === 'string' && !String(u).includes('/api/log') && !String(u).includes('/api/events')) {
      try { const d = JSON.parse(o.body), v = d.folder || d.f || d.host || d.site || d.url || (d.folders || d.sites || [])[0];
        if (!pending.it.site && typeof v === 'string') pending.it.site = hostOf(v); } catch (x) { /* не JSON */ }
    }
    return ofetch(u, o);
  };
  addEventListener('error', e => {
    if (!e.message || /ResizeObserver/.test(e.message)) return;
    log({kind: 'error', text: 'Ошибка на странице окна: ' + e.message, detail: `${e.filename || ''}:${e.lineno || ''}:${e.colno || ''}`});
  });
  addEventListener('unhandledrejection', e => {
    const m = String(e.reason && (e.reason.stack || e.reason.message) || e.reason || '');
    if (!m || /Failed to fetch|NetworkError|AbortError/.test(m)) return;   // программа закрыта - об этом плашка «не отвечает»
    log({kind: 'error', text: 'Ошибка на странице окна: ' + m.split('\n')[0], detail: m});
  });
})();
