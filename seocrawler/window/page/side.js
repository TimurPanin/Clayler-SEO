// Меню слева: одно на все страницы окна (главная, «Семантика», «Словарь»).
// Сверху переключатель «Техничка | Семантика»: у каждой «комнаты» своё меню, общее (журнал, подключения,
// настройки, поиск сайта Ctrl+K) видно в обеих. На главной (data-main) пункты - её экраны (data-view, их
// переключает app.js) и кнопки окошек (wChip, acChipY…), данные для точек и счётчиков берёт app.js.
// На других страницах пункты ведут на главную (/#queue, /#settings…), а данные side.js берёт сам.
(() => {
  const side = document.getElementById('side'); if (!side) return;
  const I = {
    home: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    watch: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3"/><circle cx="12" cy="12" r="5"/>',
    queue: '<path d="M4 6h11M4 12h11M4 18h7"/><path d="m17 15 4 3-4 3z"/>',
    tools: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>',
    sem: '<path d="M4 6h16M4 12h10M4 18h6"/>', dict: '<path d="M6 4h11a1 1 0 0 1 1 1v15H7.5A2.5 2.5 0 0 1 5 17.5V5a1 1 0 0 1 1-1z"/><path d="M5 17.5A2.5 2.5 0 0 1 7.5 15H18"/>',
    upd: '<path d="M3 17l5-5 4 4 8-8"/><path d="M15 8h5v5"/>',
    log: '<path d="M7 4h10a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M9 9h6M9 13h6M9 17h3"/>',
    brand: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    settings: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    clients: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    find: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
  };
  const MAIN = side.dataset.main === '1';
  const here = side.dataset.here || 'home';
  // экраны главной, которые не принадлежат ни одной комнате: на них меню остаётся той комнаты, откуда пришли
  const COMMON = ['log', 'brand', 'settings'];
  // пункт меню: на главной экран (data-view) или кнопка окошка (id), на других страницах - ссылка
  const svg = ic => `<svg viewBox="0 0 24 24" aria-hidden="true">${I[ic]}</svg>`;
  const item = (v, ic, t, o = {}) => {
    const extra = o.extra || '', also = o.also ? ` data-also="${o.also}"` : '';
    if (MAIN && o.btn) return `<button class="nav" id="${o.btn}" type="button" title="${o.title || ''}">${svg(ic)}${t}${extra}</button>`;
    if (MAIN && !o.href) return `<a class="nav" href="${v === 'home' ? '#' : '#' + v}" data-view="${v}"${also}>${svg(ic)}${t}${extra}</a>`;
    const href = o.href || (v === 'home' ? '/' : '/#' + v);
    return `<a class="nav" href="${href}" data-here="${v}"${also}>${svg(ic)}${t}${extra}</a>`;
  };
  side.innerHTML = `<div class="brand"><div class="brand-name">Clayler SEO</div><div class="brand-sub">Аудит и семантика сайтов</div><div class="brand-ver" id="appVer"></div></div>
  <div class="room" role="tablist" aria-label="Раздел программы">
    <a class="room-b" data-room="tech" href="/" role="tab">Техничка</a><a class="room-b" data-room="sem" href="/semantics" role="tab">Семантика</a></div>
  <button class="nav find" id="kFind" type="button" title="Найти сайт и открыть его отчёт или семантику">${svg('find')}Найти сайт<kbd>Ctrl+K</kbd></button>
  <nav class="nav-group" data-room="tech" aria-label="Техничка">
    ${item('home', 'home', 'Проверки и отчёты', {extra: '<span class="nav-run" id="navRun" hidden></span>'})}
    ${item('clients', 'clients', 'Клиенты')}
    ${item('watch', 'watch', 'Наблюдение', {btn: 'wChip', title: 'Проверка по расписанию и мониторинг сайтов', extra: '<span class="badge" id="wBadge" hidden></span>'})}
    ${item('queue', 'queue', 'Очередь сайтов', {extra: '<span class="badge" id="qBadge" hidden></span>'})}
    ${item('tools', 'tools', 'Инструменты', {also: 'search extract robot list reindex auth'})}
  </nav>
  <nav class="nav-group" data-room="sem" aria-label="Семантика">
    ${item('sem', 'sem', 'Запросы и задачи', {href: '/semantics#tasks'})}
    ${item('upd', 'upd', 'Обновления поиска', {href: '/semantics#upd'})}
    ${item('dict', 'dict', 'Словарь', {href: '/dictionary'})}
  </nav>
  <nav class="nav-group" aria-label="Общее">${item('log', 'log', 'Журнал')}</nav>
  <div class="side-foot"><div class="side-foot-t">Подключения</div>
    ${MAIN ? `<button class="conn ac-chip" id="acChipY" data-p="yandex" type="button" title="Яндекс Вебмастер и Метрика"><i class="dot"></i><span>Яндекс</span><small></small></button>
    <button class="conn ac-chip" id="acChipG" data-p="google" type="button" title="Google Search Console"><i class="dot"></i><span>Google</span><small></small></button>
    <button class="conn ac-chip" id="acChipD" data-p="direct" type="button" title="Яндекс Директ: точная частотность Вордстата"><i class="dot"></i><span>Директ</span><small></small></button>
    <button class="conn" id="tgChip" type="button" title="Сообщение в Telegram, когда проверка закончилась"><i class="dot"></i><span>Telegram</span><small></small></button>`
    : `<a class="conn" id="acChipY" href="/#yandex"><i class="dot"></i><span>Яндекс</span><small></small></a>
    <a class="conn" id="acChipG" href="/#google"><i class="dot"></i><span>Google</span><small></small></a>
    <a class="conn" id="acChipD" href="/#direct"><i class="dot"></i><span>Директ</span><small></small></a>
    <a class="conn" id="tgChip" href="/#telegram"><i class="dot"></i><span>Telegram</span><small></small></a>`}
    <details class="side-set" id="sideSet"><summary class="conn">${svg('gear')}<span>Настройки</span></summary>
      ${item('brand', 'brand', 'Ваши данные в аудите')}${item('settings', 'settings', 'Пороги и проверки')}</details>
    <div class="disk" id="disk"></div></div>`;
  const $ = id => document.getElementById(id);

  // ---- комната: на своих страницах - своя; на общих экранах главной - та, откуда пришли (запоминается)
  const ls = {get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} }};
  const ROOM_OF = {sem: 'sem', upd: 'sem', dict: 'sem'};
  const setRoom = r => {
    side.querySelectorAll('[data-room]').forEach(x => {
      if (x.classList.contains('room-b')) x.classList.toggle('on', x.dataset.room === r);
      else x.hidden = x.dataset.room !== r;
    });
  };
  // какой пункт подсвечен; на главной это делает app.js (showView), он же зовёт ClaylerSide.view
  const mark = v => {
    const r = COMMON.includes(v) ? (ls.get('claylerRoom') || 'tech') : (ROOM_OF[v] || 'tech');
    if (!COMMON.includes(v)) ls.set('claylerRoom', r);
    setRoom(r);
    if (!MAIN) side.querySelectorAll('.nav[data-here]').forEach(a => a.classList.toggle('on', a.dataset.here === v));
    if (['brand', 'settings'].includes(v)) $('sideSet').open = true;
  };
  window.ClaylerSide = {view: mark};
  const pageView = () => here === 'sem' && location.hash.slice(1).split('/')[0] === 'upd' ? 'upd' : here;
  if (!MAIN) { mark(pageView()); window.addEventListener('hashchange', () => mark(pageView())); }
  else setRoom(ls.get('claylerRoom') === 'sem' && COMMON.includes(location.hash.slice(1)) ? 'sem' : 'tech');
  // окошко главной (/#yandex, /#google, /#telegram, /#watch) с другой страницы: открывается прямо здесь, поверх
  // страницы - главная в прозрачной рамке показывает только окошко (app.js, ?embed=1), «Закрыть» убирает рамку.
  // Раньше «Подключения» из Семантики резко переносили в Техничку (22.10.2026)
  if (!MAIN) document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('a[href^="/#"]');
    const m = a && /^\/#(yandex|google|direct|telegram|watch)$/.exec(a.getAttribute('href'));
    if (!m || e.ctrlKey || e.shiftKey || e.metaKey) return;
    e.preventDefault(); e.stopPropagation();
    if (document.querySelector('iframe.embed-dlg')) return;
    const fr = document.createElement('iframe');
    fr.className = 'embed-dlg'; fr.title = a.textContent.trim() || 'Подключения'; fr.src = '/?embed=1#' + m[1];
    fr.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;border:0;z-index:2147483000;background:transparent;opacity:0;transition:opacity .18s';
    fr.addEventListener('load', () => { fr.style.opacity = '1'; });
    document.body.appendChild(fr);
  }, true);
  window.addEventListener('message', e => {
    if (e.origin !== location.origin || !e.data || e.data.claylerEmbed !== 'close') return;
    const fr = document.querySelector('iframe.embed-dlg'); if (!fr) return;
    fr.style.opacity = '0'; setTimeout(() => fr.remove(), 180);
    if (window.ClaylerSide && ClaylerSide.reload) ClaylerSide.reload();   // точки подключений - заново
  });
  // «Техничка» на главной - сразу её первый экран, без перезагрузки
  if (MAIN) side.querySelector('.room-b[data-room="tech"]').addEventListener('click', e => { e.preventDefault(); location.hash = ''; window.showView && window.showView('home'); });

  // ---- поиск сайта с любого экрана: Ctrl+K или «Найти сайт»
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const host = s => String(s || '').replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/$/, '');
  const dlg = document.createElement('dialog'); dlg.className = 'kdlg'; dlg.setAttribute('aria-label', 'Найти сайт');
  dlg.innerHTML = `<input type="search" id="kQ" placeholder="Начните вводить адрес: например, «лк»" autocomplete="off" aria-label="Адрес сайта">
    <div class="k-list" id="kList" role="listbox"></div><div class="k-hint">↑ ↓ выбрать · Enter - карточка сайта · Esc - закрыть</div>`;
  document.body.appendChild(dlg);
  let SITES = null, pos = 0, hits = [];
  const links = g => {
    const c = g.checks[0] || {}, r = '/r/' + encodeURIComponent(c.folder) + '/';
    const sem = g.sem_folder || (c.finished ? c.folder : '');
    return [['Карточка', '/?q=' + encodeURIComponent(host(g.site))],
      c.has_html ? ['Отчёт', r + 'отчёт.html', 1] : null,
      sem ? ['Семантика', '/semantics?f=' + encodeURIComponent(sem)] : null].filter(Boolean);
  };
  const draw = () => {
    const q = host($('kQ').value.trim().toLowerCase());
    hits = !SITES ? [] : SITES.filter(g => !q || host(g.site).toLowerCase().includes(q))
      .sort((a, b) => (host(b.site).toLowerCase().startsWith(q) - host(a.site).toLowerCase().startsWith(q)) || (b.fav - a.fav)).slice(0, 8);
    pos = Math.min(pos, Math.max(hits.length - 1, 0));
    $('kList').innerHTML = !SITES ? '<div class="k-empty">Загружаю список сайтов…</div>' : !hits.length ? '<div class="k-empty">Такого сайта нет среди проверенных</div>'
      : hits.map((g, i) => `<div class="k-row${i === pos ? ' on' : ''}" data-i="${i}" role="option"><span class="k-site">${g.fav ? '★ ' : ''}${esc(host(g.site))}</span>
        <span class="k-acts">${links(g).map(([t, u, blank]) => `<a href="${u}"${blank ? ' target="_blank"' : ''}>${t}</a>`).join('')}</span></div>`).join('');
  };
  const go = (u, blank) => {
    dlg.close();
    if (blank) { window.open(u, '_blank'); return; }
    // на главной карточка - просто фильтр списка, без перезагрузки
    const q = MAIN && u.startsWith('/?q=') ? decodeURIComponent(u.slice(4)) : null;
    if (q != null && document.getElementById('q')) { window.showView && window.showView('home'); const f = $('q'); f.value = q; f.dispatchEvent(new Event('input')); return; }
    location.href = u;
  };
  const open = () => {
    if (dlg.open) return;
    $('kQ').value = ''; pos = 0; draw(); dlg.showModal(); $('kQ').focus();
    if (!SITES) fetch('/api/reports').then(r => r.json()).then(R => { SITES = R.sites || []; draw(); }).catch(() => { SITES = []; draw(); });
  };
  $('kFind').onclick = open;
  document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K' || e.code === 'KeyK')) { e.preventDefault(); open(); } });
  $('kQ').addEventListener('input', () => { pos = 0; draw(); });
  $('kQ').addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); pos = (pos + (e.key === 'ArrowDown' ? 1 : -1) + hits.length) % Math.max(hits.length, 1); draw(); }
    if (e.key === 'Enter' && hits[pos]) { e.preventDefault(); const [, u, b] = links(hits[pos])[0]; go(u, b); }
  });
  $('kList').addEventListener('click', e => {
    const a = e.target.closest('a'); if (a) { e.preventDefault(); go(a.getAttribute('href'), a.target === '_blank'); return; }
    const row = e.target.closest('.k-row'); if (row) { const [, u, b] = links(hits[+row.dataset.i])[0]; go(u, b); }
  });
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });   // нажатие мимо окошка

  if (MAIN) return;   // на главной точки подключений, счётчики и версию заполняет app.js

  // ---- данные для меню на других страницах
  const get = u => fetch(u).then(r => r.json()).catch(() => null);
  const st = (el, cls, t) => { el.classList.remove('on', 'off', 'bad'); el.classList.add(cls); el.querySelector('small').textContent = t; };
  const conns = () => get('/api/accounts').then(A => A && [['yandex', 'acChipY'], ['google', 'acChipG']].forEach(([p, id]) => { const x = A[p]; if (!x) return;
    st($(id), x.connected && x.error ? 'bad' : x.connected ? 'on' : 'off', x.connected && x.error ? 'ошибка' : x.connected ? '' : 'нет'); }))
    .then(() => get('/api/direct')).then(D => { if (!D) return;   // как dirChip в app.js
      const c = !D.has_token ? 'off' : D.check && !D.check_ok ? 'bad' : 'on';
      st($('acChipD'), c, c === 'off' ? 'нет' : c === 'bad' ? 'ошибка' : ''); });
  conns(); window.ClaylerSide.reload = conns;
  get('/api/telegram').then(T => T && st($('tgChip'), !T.ready ? 'off' : T.online === false ? 'bad' : !T.enabled ? 'off' : 'on',
    !T.ready ? 'нет' : T.online === false ? 'нет связи' : !T.enabled ? 'выключен' : ''));
  get('/api/watch').then(W => { if (!W) return;
    const bad = W.sites.filter(s => s.monitor && s.mon && s.mon.ok === false).length, n = W.sites.filter(s => s.monitor || s.weekly).length;
    $('wBadge').hidden = !bad && !n; $('wBadge').textContent = bad || n; if (bad) $('wBadge').classList.add('bad'); });
  get('/api/version').then(V => { if (V) $('appVer').textContent = `Версия ${V.app} · Семантика ${V.semantics}`; });
  get('/api/reports').then(R => { if (!R || !R.sites.length) return;
    if (!SITES) SITES = R.sites;
    const b = R.sites.reduce((a, g) => a + g.checks.reduce((x, c) => x + (c.size || 0), 0), 0), n = R.sites.length;
    const sz = b >= 1e9 ? (b / 1e9).toFixed(1).replace('.', ',') + ' ГБ' : Math.round(b / 1e6) + ' МБ';
    $('disk').textContent = `На диске ${sz} · ${n} ${n % 10 === 1 && n % 100 !== 11 ? 'сайт' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'сайта' : 'сайтов'}`; });
  const run = () => get('/api/status').then(s => { if (!s) return;
    $('navRun').hidden = !s.running; $('navRun').textContent = s.running && s.overall != null ? Math.floor(s.overall) + '%' : ''; });
  run(); setInterval(run, 5000);
})();
