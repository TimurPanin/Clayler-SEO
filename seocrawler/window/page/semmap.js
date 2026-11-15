// Карта семантики на странице «Семантика»: каждая группа запросов - шар. Размер - примерный спрос (по подсказкам
// поиска), цвет - есть ли под группу страница: зелёный - есть, жёлтый - есть, но слабая (замечания), красный - нет
// (товары есть или раздел есть у конкурента), серый кружок - нет ни страницы, ни товаров. Близкие группы
// («Радиаторы…») стоят кучкой и связаны линиями. Две страницы на одну группу (каннибализация) - красная пунктирная
// обводка. Кнопка «Есть у конкурента» подсвечивает группы, которые у конкурента закрыты, а у вас нет.
// Canvas без библиотек. semMap(DATA) вызывает semantics.js после загрузки семантики.
(function(){
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let S = null;  // состояние карты
const LABELS = 40;  // подписей на экране не больше: остальные - при наведении и после приближения

function family(name){
  const w = (name.toLowerCase().replace(/ё/g, 'е').match(/[a-zа-я0-9]+/g) || [''])[0];
  return w.length > 5 ? w.slice(0, 5) : w;  // «радиаторы», «радиатор» - одна семья
}

// упаковка кругов: каждый следующий - по спирали вокруг центра, пока не перестанет задевать уже поставленные
function pack(items, gap){
  const placed = [];
  items.forEach((it, n) => {
    if (!n){ it.x = 0; it.y = 0; placed.push(it); return; }
    const step = Math.max(1.5, Math.min(it.r * 0.5, 6));  // шаг по спирали - одинаковое расстояние, а не одинаковый угол
    for (let t = 0, rr = 1; ; t += step / rr){
      rr = 1 + t * step / (2 * Math.PI) * 2; const x = Math.cos(t) * rr, y = Math.sin(t) * rr;
      if (placed.every(p => (p.x - x) ** 2 + (p.y - y) ** 2 >= (p.r + it.r + gap) ** 2)){ it.x = x; it.y = y; break; }
    }
    placed.push(it);
  });
  return Math.max(...items.map(it => Math.hypot(it.x, it.y) + it.r));
}

function weak(g){ return g.kind === 'page' && g.a && g.a.problems && g.a.problems.length; }
function color(g, C){
  if (g.kind === 'page') return weak(g) ? C.warn : C.good;
  if (g.kind === 'create') return C.crit;
  return C.mut;
}

window.semMap = function(DATA){
  const box = document.getElementById('smapBox');
  if (!box) return;
  const groups = (DATA.groups || []).filter(g => g.kind !== 'manual');
  document.getElementById('semMap').hidden = !groups.length;
  if (!groups.length) return;
  const cann = new Map();  // группа → страницы, которые мешают друг другу
  (DATA.cannibal || []).forEach(c => c.pages.forEach(p => { if (p.group) cann.set(p.group, c); }));
  const mx = Math.max(1, ...groups.map(g => g.score || 0));
  const items = groups.map(g => ({g, r: 7 + 40 * Math.sqrt((g.score || 0) / mx), fam: family(g.name), cann: cann.get(g.name),
                                  rival: (g.rivals || []).length > 0 && g.kind !== 'page',
                                  near: (g.q || []).some(r => r[8] >= 11 && r[8] <= 20)}));
  const fams = new Map();
  items.forEach(it => { if (!fams.has(it.fam)) fams.set(it.fam, []); fams.get(it.fam).push(it); });
  const clusters = [...fams.values()].map(list => {
    list.sort((a, b) => b.r - a.r);
    const R = pack(list, 3);
    return {list, r: R, w: list.reduce((s, it) => s + (it.g.score || 0), 0)};
  }).sort((a, b) => b.r - a.r || b.w - a.w);  // крупные кучки в середину, мелкие заполняют промежутки
  pack(clusters, 14);
  clusters.forEach(c => c.list.forEach(it => { it.x += c.x; it.y += c.y; }));
  const cv = box.querySelector('canvas'), ctx = cv.getContext('2d'), tip = box.querySelector('.wtip');
  S = {items, clusters, zoom: 1, ox: 0, oy: 0, dpr: 1, hov: null, sel: null, rival: false, gaps: false, near: false, fitted: false, touched: false};
  const info = document.getElementById('smapInfo');
  const btns = document.getElementById('smapBar');
  const nRival = items.filter(it => it.rival).length, nRed = items.filter(it => it.g.kind === 'create').length;
  btns.querySelector('[data-a=rival]').hidden = !nRival;
  btns.querySelector('[data-a=rival]').textContent = `Есть у конкурента, нет у вас: ${nRival.toLocaleString('ru')}`;
  btns.querySelector('[data-a=gaps]').textContent = `Создать страницы: ${nRed.toLocaleString('ru')}`;
  btns.querySelector('[data-a=gaps]').disabled = !nRed;
  const nNear = items.filter(it => it.near).length;
  btns.querySelector('[data-a=near]').hidden = !nNear;
  btns.querySelector('[data-a=near]').textContent = `Почти в топе: ${nNear.toLocaleString('ru')}`;

  function fit(){
    const r = box.getBoundingClientRect(); if (!r.width) return; S.fitted = true;
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    items.forEach(it => { x0 = Math.min(x0, it.x - it.r); x1 = Math.max(x1, it.x + it.r); y0 = Math.min(y0, it.y - it.r); y1 = Math.max(y1, it.y + it.r); });
    S.zoom = Math.min((r.width - 24) / (x1 - x0), (r.height - 24) / (y1 - y0));
    S.ox = r.width / 2 - (x0 + x1) / 2 * S.zoom; S.oy = r.height / 2 - (y0 + y1) / 2 * S.zoom;
  }
  function on(it){
    if (S.rival) return it.rival;
    if (S.gaps) return it.g.kind === 'create';
    if (S.near) return it.near;
    return true;
  }
  function draw(){
    const r = box.getBoundingClientRect();
    if (!S.fitted) fit();
    S.dpr = window.devicePixelRatio || 1; cv.width = r.width * S.dpr; cv.height = r.height * S.dpr;
    const C = {good: css('--good'), warn: css('--warn'), crit: css('--crit'), mut: css('--mut'), tx: css('--tx'), bd: css('--bd'), acc: css('--acc')};
    const g = ctx, z = S.zoom, focus = S.rival || S.gaps || S.near;
    g.setTransform(S.dpr * z, 0, 0, S.dpr * z, S.dpr * S.ox, S.dpr * S.oy);
    // линии внутри семьи: от самой большой группы к остальным
    g.strokeStyle = C.mut; g.lineWidth = 1 / z; g.globalAlpha = focus ? 0.12 : 0.35; g.beginPath();
    clusters.forEach(c => { const h = c.list[0]; c.list.slice(1).forEach(it => { g.moveTo(h.x, h.y); g.lineTo(it.x, it.y); }); });
    g.stroke();
    items.forEach(it => {
      const hl = on(it); g.globalAlpha = focus && !hl ? 0.15 : 1;
      g.beginPath(); g.arc(it.x, it.y, it.r, 0, 2 * Math.PI);
      if (it.g.kind === 'absent'){ g.strokeStyle = C.mut; g.lineWidth = Math.max(1.2 / z, it.r * 0.12); g.stroke(); }
      else { g.fillStyle = color(it.g, C); g.fill(); }
      if (it.cann){ g.save(); g.setLineDash([4 / z, 3 / z]); g.strokeStyle = C.crit; g.lineWidth = 2.2 / z;
        g.beginPath(); g.arc(it.x, it.y, it.r + 3 / z, 0, 2 * Math.PI); g.stroke(); g.restore(); }
      if (it === S.hov || it === S.sel){ g.strokeStyle = C.tx; g.lineWidth = 2 / z; g.beginPath(); g.arc(it.x, it.y, it.r + 5 / z, 0, 2 * Math.PI); g.stroke(); }
    });
    // подписи: крупным шарам всегда, мелким - когда приблизили
    g.setTransform(S.dpr, 0, 0, S.dpr, 0, 0); g.textAlign = 'center'; g.textBaseline = 'middle'; g.globalAlpha = 1;
    const boxes = []; let shown = 0;
    items.slice().sort((a, b) => b.r - a.r).forEach(it => {
      const R = it.r * z; if (R < 14 || shown >= LABELS) return;
      if (S.rival || S.gaps || S.near) { if (!on(it)) return; }
      const x = S.ox + it.x * z, y = S.oy + it.y * z;
      if (x < -40 || y < -20 || x > r.width + 40 || y > r.height + 20) return;  // за краем окна - не считаем
      const fs = Math.min(13, Math.max(10, R / 2.5));
      g.font = `${R > 34 ? 600 : 400} ${fs}px system-ui,Segoe UI,sans-serif`;
      let t = it.g.name; const maxW = Math.max(R * 2.6, 70);
      while (g.measureText(t).width > maxW && t.length > 4) t = t.slice(0, -2);
      if (t !== it.g.name) t = t.replace(/\s*\S?$/, '') + '…';
      const w = g.measureText(t).width;
      if (boxes.some(b => Math.abs(b[0] - x) < (b[2] + w) / 2 + 4 && Math.abs(b[1] - y) < fs + 2)) return;
      boxes.push([x, y, w]); shown++;
      g.lineWidth = 3; g.strokeStyle = css('--card'); g.strokeText(t, x, y);
      g.fillStyle = it.g.kind === 'absent' ? C.mut : C.tx; g.fillText(t, x, y);
    });
  }
  S.draw = draw;
  function want(){ if (!S.pending){ S.pending = true; requestAnimationFrame(() => { S.pending = false; draw(); }); } }
  function pick(mx, my){
    const x = (mx - S.ox) / S.zoom, y = (my - S.oy) / S.zoom; let best = null;
    items.forEach(it => { if ((it.x - x) ** 2 + (it.y - y) ** 2 <= Math.max(it.r, 6 / S.zoom) ** 2) best = it; });
    return best;
  }
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const path = u => { try { const x = new URL(u); return decodeURI(x.pathname) + x.search; } catch { return u; } };
  function state(it){
    const g = it.g;
    const K = (DATA.labels || {}).kind || {page: ['Есть на сайте'], create: ['Создать'], absent: ['Решить, нужна ли']};
    const lc = s => s.charAt(0).toLowerCase() + s.slice(1);
    if (g.kind === 'page') return lc(K.page[0]) + (weak(g) ? ', но страница слабая' : '');
    if (g.kind === 'create') return lc(K.create[0]) + ': страницы нет' + (g.products ? ', а подходящие товары на сайте есть' : '');
    return lc(K.absent[0]) + ': нет ни страницы, ни товаров' + (it.rival ? ', а у конкурента есть' : '');
  }
  function describe(it, full){
    const g = it.g, q = (g.q || []).length;
    let h = `<b>${esc(g.name)}</b> · ${state(it)} · ${q.toLocaleString('ru')} ${q % 10 === 1 && q % 100 !== 11 ? 'запрос' : q % 10 > 1 && q % 10 < 5 && (q % 100 < 10 || q % 100 > 20) ? 'запроса' : 'запросов'}`;
    if (it.cann) h += ` · <b style="color:var(--crit)">две страницы мешают друг другу</b>`;
    if (it.near) h += ` · есть запросы на 11–20 месте`;
    if (!full) return h;
    h += `<br>${esc(g.todo)}`;
    if (g.page) h += ` · <a href="${esc(g.page)}" target="_blank">${esc(path(g.page))}</a>`;
    else if (g.near) h += ` · рядом: <a href="${esc(g.near)}" target="_blank">${esc(path(g.near))}</a>`;
    if (weak(g)) h += `<br><span class="mut">${g.a.problems.slice(0, 2).map(esc).join('; ')}</span>`;
    if (it.cann) h += `<br><span class="mut">${esc(it.cann.why)}: ${it.cann.pages.map(p => esc(path(p.url))).join(', ')}</span>`;
    if (q) h += `<br><span class="mut">Например: ${g.q.slice(0, 4).map(r => esc(r[0])).join(' · ')}</span>`;
    return h + ` <button class="btn small" data-show="${esc(g.name)}">Показать в списке</button>`;
  }
  let drag = null, moved = false;
  box.onpointerdown = e => { S.touched = true; drag = {x: e.clientX, y: e.clientY, ox: S.ox, oy: S.oy}; moved = false; box.setPointerCapture(e.pointerId); };
  box.onpointermove = e => {
    const r = box.getBoundingClientRect();
    if (drag){ const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      if (moved){ S.ox = drag.ox + dx; S.oy = drag.oy + dy; tip.style.display = 'none'; want(); return; } }
    const it = pick(e.clientX - r.left, e.clientY - r.top);
    if (it !== S.hov){ S.hov = it; want(); }
    if (it){ tip.innerHTML = describe(it, false); tip.style.display = 'block';
      const x = e.clientX - r.left, y = e.clientY - r.top; tip.style.left = Math.min(x + 14, r.width - 330) + 'px'; tip.style.top = (y + 14 > r.height - 70 ? y - 60 : y + 14) + 'px'; }
    else tip.style.display = 'none';
  };
  box.onpointerup = e => { const was = drag; drag = null; if (!was || moved) return;
    const r = box.getBoundingClientRect(); S.sel = pick(e.clientX - r.left, e.clientY - r.top);
    info.innerHTML = S.sel ? describe(S.sel, true) : 'Нажмите на шар - появятся запросы группы и что с ней сделать.'; want(); };
  box.onpointerleave = () => { tip.style.display = 'none'; if (S.hov){ S.hov = null; want(); } };
  box.onwheel = e => { e.preventDefault(); S.touched = true; const r = box.getBoundingClientRect(); zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.2 : 1 / 1.2); };
  function zoomAt(x, y, k){ const z = Math.max(0.05, Math.min(30, S.zoom * k)); S.ox = x - (x - S.ox) * z / S.zoom; S.oy = y - (y - S.oy) * z / S.zoom; S.zoom = z; want(); }
  btns.onclick = e => {
    const b = e.target.closest('button'); if (!b) return; const a = b.dataset.a, r = box.getBoundingClientRect();
    if (a === 'in') zoomAt(r.width / 2, r.height / 2, 1.5); else if (a === 'out') zoomAt(r.width / 2, r.height / 2, 1 / 1.5);
    else if (a === 'fit'){ fit(); want(); }
    else if (a === 'rival' || a === 'gaps' || a === 'near'){ const v = !S[a]; S.rival = S.gaps = S.near = false; S[a] = v;
      btns.querySelectorAll('[data-a=rival],[data-a=gaps],[data-a=near]').forEach(x => x.classList.toggle('on', S[x.dataset.a])); want(); }
  };
  info.onclick = e => { const b = e.target.closest('[data-show]'); if (!b) return;
    const q = document.getElementById('semQ'); q.value = b.dataset.show.toLowerCase(); q.dispatchEvent(new Event('input'));
    q.scrollIntoView({behavior: 'smooth', block: 'start'}); };
  info.innerHTML = 'Нажмите на шар - появятся запросы группы и что с ней сделать.';
  const det = document.getElementById('semMap');
  det.ontoggle = () => { if (det.open){ S.fitted = false; draw(); } };
  window.addEventListener('resize', () => { if (!S) return; if (!S.touched) S.fitted = false; S.draw(); });
  if (window.ResizeObserver && !box._ro){ box._ro = new ResizeObserver(() => { if (S && (!S.fitted || !S.touched)){ S.fitted = false; S.draw(); } }); box._ro.observe(box); }
  draw();
};
})();
