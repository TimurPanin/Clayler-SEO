"""«Паутинка» в отчёте: живая схема внутренних ссылок (данные — analyze/web.py, summary["web"]).
Canvas и JavaScript без библиотек и без интернета: работает и в отчёте для клиента, открытом у него с диска.
Приближение колесом или кнопками, перетаскивание, нажатие на точку — её ссылки и данные страницы,
кнопки подсвечивают ошибки, сирот и тупики, нажатие на раздел в списке — его страницы."""
import html
import json

from .fmt import num as _num, plural as _plural

PALETTE = ["#3b5bdb", "#0ca678", "#e8590c", "#ae3ec9", "#1098ad", "#f08c00", "#d6336c", "#5c940d", "#7048e8",
           "#a61e4d", "#2b8a3e", "#1c7ed6"]

CSS = """
.web{padding:0;overflow:hidden}.web .wtop{padding:14px 16px 0}.web .wtop p{margin:0 0 8px;font-size:14px}
.wbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:4px 16px 10px}
.wbar button{font:inherit;font-size:13px;padding:4px 10px;border:1px solid var(--bd);border-radius:999px;background:var(--card);color:var(--tx);cursor:pointer}
.wbar button.on{border-color:var(--acc);background:var(--acc);color:#fff}.wbar button:disabled{opacity:.45;cursor:default}
.wbar .sp{flex:1}.wbar i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:0}
.wcv{position:relative;height:620px;background:var(--bg);border-top:1px solid var(--bd);border-bottom:1px solid var(--bd);touch-action:none;cursor:grab}
.wcv.drag{cursor:grabbing}.wcv canvas{display:block;width:100%;height:100%}
.wtip{position:absolute;pointer-events:none;background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:6px 9px;font-size:12px;max-width:340px;overflow-wrap:anywhere;box-shadow:0 2px 10px rgba(0,0,0,.12);display:none}
.winfo{padding:10px 16px;font-size:13px;min-height:42px;overflow-wrap:anywhere}.winfo b{font-weight:600}
.wsecs{padding:0 16px 14px;font-size:13px}.wsecs table{width:100%}.wsecs td,.wsecs th{padding:4px 6px}
.wsecs tr.pick{cursor:pointer}.wsecs tr.pick:hover td{background:var(--bg)}.wsecs tr.on td{background:var(--bg);font-weight:600}
.wsecs .lo{color:var(--warn)}.wsecs i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}
@media (max-width:640px){.wcv{height:440px}}
@media print{.wbar,.wcv,.winfo{display:none}}
"""

JS = r"""
(function(){
const W = JSON.parse(document.getElementById('webdata').textContent);
const box = document.getElementById('wcv'), cv = box.querySelector('canvas'), ctx = cv.getContext('2d');
const tip = box.querySelector('.wtip'), info = document.getElementById('winfo');
const N = W.nodes.length, PAL = W.palette;
const F_CRIT = 1, F_WARN = 2, F_ORPHAN = 4, F_DEAD = 8, F_ERR = 16, F_HOME = 32;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const node = W.nodes.map(a => ({p: a[0], par: a[1], d: a[2], s: a[3], f: a[4], inn: a[5], out: a[6], hid: a[7], pr: a[8] || 0, kids: [], x: 0, y: 0}));
// ---- раскладка: главная в центре, кольца по переходам, ветки — секторами по размеру
const roots = [], loose = [];
node.forEach((v, i) => { if (v.par >= 0) node[v.par].kids.push(i); else if (v.f & F_HOME) roots.push(i); else loose.push(i); });
const key = i => node[i].s * 1e6 + i;
node.forEach(v => v.kids.sort((a, b) => key(a) - key(b)));
const size = new Float64Array(N);
const order = []; (function walk(){ const st = roots.slice(); while (st.length){ const i = st.pop(); order.push(i); node[i].kids.forEach(k => st.push(k)); } })();
for (let k = order.length - 1; k >= 0; k--){ const i = order[k]; size[i] = 1 + Math.log2(1 + node[i].hid) + node[i].kids.reduce((a, c) => a + size[c], 0); }
const RING = 120; let maxD = 1;
function place(i, a0, a1, j){
  const v = node[i], a = (a0 + a1) / 2;
  const r = v.d * RING + (v.d > 1 ? (j % 3) * RING * 0.24 : 0);
  v.x = Math.cos(a) * r; v.y = Math.sin(a) * r; v.a = a; maxD = Math.max(maxD, v.d);
  let t = a0; const tot = v.kids.reduce((s, c) => s + size[c], 0) || 1;
  v.kids.forEach((c, n) => { const w = (a1 - a0) * size[c] / tot; place(c, t, t + w, n); t += w; });
}
(function(){ // рекурсия place() не глубже числа переходов от главной
  let t = -Math.PI / 2; const tot = roots.reduce((s, c) => s + size[c], 0) || 1;
  roots.forEach(c => { const w = 2 * Math.PI * size[c] / tot; place(c, t, t + w, 0); t += w; });
})();
// сироты и страницы без пути от главной — кучкой справа
const R0 = (maxD + 0.9) * RING + RING * 0.5, cols = Math.max(1, Math.ceil(Math.sqrt(loose.length / 2)));
loose.sort((a, b) => key(a) - key(b)).forEach((i, n) => { node[i].x = R0 + (n % cols) * 14; node[i].y = -Math.floor(n / cols) * 14 + Math.floor(loose.length / cols) * 7; });
// подписи разделов: средний угол страниц раздела у внешнего кольца
const secLab = W.sections.map(() => ({sx: 0, sy: 0, n: 0}));
node.forEach(v => { if (v.d >= 1 && v.s > 0 && !(v.f & F_ORPHAN) && v.par >= 0){ const L = secLab[v.s]; L.sx += Math.cos(v.a); L.sy += Math.sin(v.a); L.n++; } });
// ---- сетка для поиска точки под мышью
const CELL = 24, grid = new Map();
node.forEach((v, i) => { const k = Math.floor(v.x / CELL) + ',' + Math.floor(v.y / CELL); (grid.get(k) || grid.set(k, []).get(k)).push(i); });
// ссылки без сквозных блоков: цель получает ссылки с 5% страниц и больше — это меню, подвал, «популярное»
const EC = [];
for (let k = 0; k < W.edges.length; k += 2) if (node[W.edges[k + 1]].inn < (W.block_min || 1e12)) EC.push(W.edges[k], W.edges[k + 1]);
// вид «По разделам»: шар на раздел по кругу в порядке их секторов, главная и отдельные страницы в центре
const SB = W.sections.map((x, j) => ({j, n: x.pages || 0, crit: x.crit || 0, a: Math.atan2(secLab[j].sy, secLab[j].sx), x: 0, y: 0, r: 0}));
(function(){
  const mx = Math.max(1, ...SB.map(b => b.n)), ring = SB.filter(b => b.j > 0 && b.n).sort((p, q) => p.a - q.a);
  SB.forEach(b => { b.r = b.n ? 14 + 56 * Math.sqrt(b.n / mx) : 0; });
  const R = Math.max(190, ring.reduce((t, b) => t + 2 * b.r + 56, 0) / (2 * Math.PI));
  const tot = ring.reduce((t, b) => t + 2 * b.r + 56, 0) || 1; let acc = 0;  // каждому шару дуга по его размеру
  ring.forEach(b => { const a = -Math.PI / 2 + 2 * Math.PI * (acc + b.r + 28) / tot; acc += 2 * b.r + 56; b.x = Math.cos(a) * R; b.y = Math.sin(a) * R; });
})();
function secLinks(){
  const L = W[clean ? 'sec_links' : 'sec_links_all'] || {}, m = {};
  Object.keys(L).forEach(k => { const [a, b] = k.split('-').map(Number), key = Math.min(a, b) + '-' + Math.max(a, b); m[key] = (m[key] || 0) + L[k]; });
  return m;
}
const adj = Array.from({length: N}, () => []);
for (let k = 0; k < W.edges.length; k += 2){ adj[W.edges[k]].push(W.edges[k + 1]); adj[W.edges[k + 1]].push(W.edges[k]); }
// ---- вид
let fitted = false, zoom = 1, ox = 0, oy = 0, dpr = 1, mode = 'err', hl = '', sec = -1, sel = -1, hov = -1, clean = true, warn = false, view = 'pages', pending = false;
function fit(){
  const r = box.getBoundingClientRect(); if (!r.width || !r.height) return; fitted = true; let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  const pts = view === 'secs' ? SB.filter(b => b.n).map(b => [b.x, b.y, b.r + 60]) : node.filter(v => sec < 0 || v.s === sec).map(v => [v.x, v.y, 0]);
  if (!pts.length) return;
  pts.forEach(([x, y, r]) => { x0 = Math.min(x0, x - r); x1 = Math.max(x1, x + r); y0 = Math.min(y0, y - r); y1 = Math.max(y1, y + r); });
  zoom = Math.min(r.width / (x1 - x0 + 80), r.height / (y1 - y0 + 80)); ox = r.width / 2 - (x0 + x1) / 2 * zoom; oy = r.height / 2 - (y0 + y1) / 2 * zoom;
}
function resize(){ if (!fitted) fit(); const r = box.getBoundingClientRect(); dpr = window.devicePixelRatio || 1; cv.width = r.width * dpr; cv.height = r.height * dpr; draw(); }
function want(){ if (!pending){ pending = true; requestAnimationFrame(() => { pending = false; draw(); }); } }
function match(v, i){
  if (sec >= 0 && v.s !== sec) return false;
  if (hl === 'err') return !!(v.f & F_CRIT); if (hl === 'orph') return !!(v.f & F_ORPHAN); if (hl === 'dead') return !!(v.f & F_DEAD);
  return true;
}
function color(v, C){
  if (mode === 'sec') return v.s > 0 ? PAL[(v.s - 1) % PAL.length] : C.mut;
  if (v.f & F_CRIT) return C.crit; if (warn && v.f & F_WARN) return C.warn; return C.good;
}
function draw(){
  const C = {crit: css('--crit'), warn: css('--warn'), good: css('--good'), mut: css('--mut'), acc: css('--acc'), tx: css('--tx'), bd: css('--bd'), bg: css('--bg')};
  const g = ctx; g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height);
  g.setTransform(dpr * zoom, 0, 0, dpr * zoom, dpr * ox, dpr * oy);
  const lw = 1 / zoom, focus = hl || sec >= 0;
  if (view === 'secs'){ drawSecs(g, C); return; }
  // кольца
  g.strokeStyle = C.bd; g.lineWidth = lw; g.globalAlpha = 0.7;
  for (let d = 1; d <= maxD; d++){ g.beginPath(); g.arc(0, 0, d * RING, 0, 2 * Math.PI); g.stroke(); }
  // ссылки между страницами (кроме меню)
  const E = clean ? EC : W.edges;
  if (E.length){
    g.strokeStyle = C.acc; g.globalAlpha = focus || sel >= 0 ? 0.03 : Math.min(0.25, 9 / Math.sqrt(E.length)); g.beginPath();
    for (let k = 0; k < E.length; k += 2){ const a = node[E[k]], b = node[E[k + 1]]; g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); }
    g.stroke();
  }
  // ветки: откуда на страницу ведёт путь от главной
  g.globalAlpha = focus || sel >= 0 ? 0.12 : 0.35; g.strokeStyle = C.mut; g.beginPath();
  node.forEach(v => { if (v.par >= 0){ const p = node[v.par]; g.moveTo(p.x, p.y); g.lineTo(v.x, v.y); } }); g.stroke();
  if (sel >= 0){ // ссылки выбранной страницы
    const v = node[sel]; g.globalAlpha = 0.9; g.strokeStyle = C.acc; g.lineWidth = 1.6 * lw; g.beginPath();
    adj[sel].forEach(j => { g.moveTo(v.x, v.y); g.lineTo(node[j].x, node[j].y); });
    if (v.par >= 0){ g.moveTo(v.x, v.y); g.lineTo(node[v.par].x, node[v.par].y); }
    v.kids.forEach(j => { g.moveTo(v.x, v.y); g.lineTo(node[j].x, node[j].y); }); g.stroke(); g.lineWidth = lw;
  }
  // точки
  const s = Math.max(0.6, Math.min(2.4, Math.sqrt(zoom) * 1.2)) / zoom;
  for (let i = 0; i < N; i++){
    const v = node[i], on = match(v, i), r = (v.f & F_HOME ? 7 : 1.8 + v.pr / 100 * 3.2 + Math.min(4, Math.log2(1 + v.hid) * 0.7) + (on && focus ? 1.2 : 0)) * s;
    g.globalAlpha = focus && !on ? 0.12 : 1;
    if (v.f & F_ORPHAN){ g.strokeStyle = color(v, C); g.lineWidth = 1.6 * s; g.beginPath(); g.arc(v.x, v.y, r, 0, 2 * Math.PI); g.stroke(); continue; }
    g.fillStyle = v.f & F_HOME ? C.acc : color(v, C); g.beginPath(); g.arc(v.x, v.y, r, 0, 2 * Math.PI); g.fill();
    if (v.f & F_DEAD){ g.strokeStyle = C.tx; g.lineWidth = 1.2 * s; g.stroke(); }
  }
  g.globalAlpha = 1; g.lineWidth = lw;
  [sel, hov].forEach(i => { if (i >= 0){ const v = node[i]; g.strokeStyle = C.tx; g.lineWidth = 2 / zoom; g.beginPath(); g.arc(v.x, v.y, 8 / zoom + 2 * s, 0, 2 * Math.PI); g.stroke(); } });
  // подписи разделов и кучки сирот
  g.setTransform(dpr, 0, 0, dpr, 0, 0); g.font = '12px system-ui,Segoe UI,sans-serif'; g.textBaseline = 'middle';
  const R = (maxD + 0.35) * RING;
  const boxes = []; // подписи не налезают друг на друга: крупные разделы первыми, мелкие пропускаются
  secLab.map((L, j) => [L, j]).sort((p, q) => q[0].n - p[0].n).forEach(([L, j]) => {
    if (!L.n || j === 0 || (sec >= 0 && j !== sec)) return; const a = Math.atan2(L.sy, L.sx);
    const x = ox + Math.cos(a) * R * zoom, y = oy + Math.sin(a) * R * zoom, n = W.sections[j].name, t = n.length > 28 ? n.slice(0, 27) + '…' : n;
    const al = Math.cos(a) < -0.2 ? 'right' : Math.cos(a) > 0.2 ? 'left' : 'center', tw = g.measureText(t).width;
    const x0 = al === 'right' ? x - tw : al === 'center' ? x - tw / 2 : x;
    if (boxes.some(b => x0 < b[0] + b[2] + 6 && b[0] < x0 + tw + 6 && Math.abs(b[1] - y) < 15)) return;
    boxes.push([x0, y, tw]); g.textAlign = al;
    g.fillStyle = mode === 'sec' ? PAL[(j - 1) % PAL.length] : C.mut; g.fillText(t, x, y);
  });
  if (loose.length){ g.textAlign = 'left'; g.fillStyle = C.mut; const v = node[loose[0]];
    g.fillText(W.lbl_loose, ox + R0 * zoom, oy + (Math.max(...loose.map(i => node[i].y)) + 16) * zoom); }
}
function drawSecs(g, C){
  const links = secLinks(), mx = Math.max(1, ...Object.values(links)), lw = 1 / zoom;
  g.strokeStyle = C.acc; g.lineCap = 'round';
  Object.keys(links).forEach(k => { const [a, b] = k.split('-').map(Number), A = SB[a], B = SB[b]; if (!A.n || !B.n) return;
    const on = sec < 0 || a === sec || b === sec;
    g.globalAlpha = on ? 0.25 + 0.45 * links[k] / mx : 0.05; g.lineWidth = Math.max(lw, 1.5 + 16 * Math.sqrt(links[k] / mx));
    g.beginPath(); g.moveTo(A.x, A.y); g.lineTo(B.x, B.y); g.stroke(); });
  g.lineWidth = lw;
  SB.forEach(b => { if (!b.n) return; const share = b.crit / b.n;
    g.globalAlpha = sec >= 0 && b.j !== sec ? 0.25 : 1;
    g.fillStyle = mode === 'sec' ? (b.j > 0 ? PAL[(b.j - 1) % PAL.length] : C.mut) : share >= 0.3 ? C.crit : share >= 0.1 ? C.warn : C.good;
    g.beginPath(); g.arc(b.x, b.y, b.r, 0, 2 * Math.PI); g.fill();
    if (b.j === hov || b.j === sec){ g.strokeStyle = C.tx; g.lineWidth = 2 * lw; g.stroke(); g.lineWidth = lw; } });
  g.globalAlpha = 1; g.setTransform(dpr, 0, 0, dpr, 0, 0); g.textAlign = 'center'; g.textBaseline = 'top';
  SB.forEach(b => { if (!b.n) return; const nm = W.sections[b.j].name, t = nm.length > 26 ? nm.slice(0, 25) + '…' : nm;
    const x = ox + b.x * zoom, y = oy + (b.y + b.r) * zoom + 4;
    g.font = '600 12px system-ui,Segoe UI,sans-serif'; g.fillStyle = C.tx; g.fillText(t, x, y);
    g.font = '11px system-ui,Segoe UI,sans-serif'; g.fillStyle = C.mut; g.fillText(b.n.toLocaleString('ru') + ' стр.', x, y + 15); });
}
function pickSec(mx, my){
  const x = (mx - ox) / zoom, y = (my - oy) / zoom;
  let best = -1; SB.forEach(b => { if (b.n && (b.x - x) ** 2 + (b.y - y) ** 2 <= Math.max(b.r, 8 / zoom) ** 2) best = b.j; });
  return best;
}
function describeSec(j){
  const b = SB[j], L = W[clean ? 'sec_links' : 'sec_links_all'] || {}; let into = 0, out = 0;
  Object.keys(L).forEach(k => { const [a, c] = k.split('-').map(Number); if (c === j) into += L[k]; if (a === j) out += L[k]; });
  return `<b>${esc(W.sections[j].name)}</b> · ${b.n.toLocaleString('ru')} ${plural(b.n, 'страница', 'страницы', 'страниц')}`
    + (b.crit ? ` · с ошибками: ${b.crit.toLocaleString('ru')}` : '') + ` · ссылок из других разделов: ${into.toLocaleString('ru')}, в другие: ${out.toLocaleString('ru')}`;
}
function pick(mx, my){
  const x = (mx - ox) / zoom, y = (my - oy) / zoom, rr = Math.max(6, 10 / zoom); let best = -1, bd = rr * rr;
  const cx = Math.floor(x / CELL), cy = Math.floor(y / CELL), k = Math.ceil(rr / CELL);
  for (let a = cx - k; a <= cx + k; a++) for (let b = cy - k; b <= cy + k; b++) (grid.get(a + ',' + b) || []).forEach(i => {
    const v = node[i], d = (v.x - x) ** 2 + (v.y - y) ** 2; if (d < bd){ bd = d; best = i; } });
  return best;
}
const esc = t => String(t).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const plural = (n, a, b, c) => { const m = n % 100, k = n % 10; return m > 10 && m < 20 ? c : k === 1 ? a : k > 1 && k < 5 ? b : c; };
function flagsText(v){
  const t = [];
  if (v.f & F_ERR) t.push('<b style="color:var(--crit)">не открывается</b>'); else if (v.f & F_CRIT) t.push('<b style="color:var(--crit)">есть критичные проблемы</b>'); else if (v.f & F_WARN) t.push('<b style="color:var(--warn)">есть предупреждения</b>');
  if (v.f & F_ORPHAN) t.push('<b>сирота</b>: есть в sitemap, ссылок на неё нет');
  if (v.f & F_DEAD) t.push('<b>тупик</b>: со страницы нет ни одной ссылки');
  return t.join(' · ');
}
function describe(i, full){
  const v = node[i], url = v.p.startsWith('http') ? v.p : W.prefix + v.p;
  const parts = [full ? `<a href="${esc(url)}" target="_blank">${esc(url)}</a>` : `<b>${esc(v.p)}</b>`];
  if (v.d >= 0) parts.push(v.d ? `${v.d} ${plural(v.d, 'переход', 'перехода', 'переходов')} от главной` : 'главная');
  else if (!(v.f & F_ORPHAN)) parts.push('по ссылкам от главной не дойти');
  parts.push(`ссылок на неё: ${v.inn}`, `с неё: ${v.out}`);
  if (v.s > 0) parts.push('раздел «' + esc(W.sections[v.s].name) + '»');
  if (v.hid) parts.push(`под ней на схеме скрыто ещё ${v.hid} ${plural(v.hid, 'страница', 'страницы', 'страниц')}`);
  const f = flagsText(v); if (f) parts.push(f);
  return parts.join(' · ');
}
// ---- мышь и пальцы
let drag = null, moved = false;
box.addEventListener('pointerdown', e => { drag = {x: e.clientX, y: e.clientY, ox, oy}; moved = false; box.setPointerCapture(e.pointerId); });
box.addEventListener('pointermove', e => {
  const r = box.getBoundingClientRect();
  if (drag){ const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3){ moved = true; box.classList.add('drag'); }
    if (moved){ ox = drag.ox + dx; oy = drag.oy + dy; tip.style.display = 'none'; want(); return; } }
  const i = view === 'secs' ? pickSec(e.clientX - r.left, e.clientY - r.top) : pick(e.clientX - r.left, e.clientY - r.top);
  if (i !== hov){ hov = i; want(); }
  if (i >= 0){ tip.innerHTML = view === 'secs' ? describeSec(i) + '<br><span style="color:var(--mut)">нажмите, чтобы раскрыть в страницы</span>' : describe(i, false); tip.style.display = 'block';
    const x = e.clientX - r.left, y = e.clientY - r.top; tip.style.left = Math.min(x + 14, r.width - 350) + 'px'; tip.style.top = (y + 14 > r.height - 80 ? y - 70 : y + 14) + 'px'; }
  else tip.style.display = 'none';
});
box.addEventListener('pointerup', e => {
  box.classList.remove('drag'); const was = drag; drag = null; if (!was || moved) return;
  const r = box.getBoundingClientRect();
  if (view === 'secs'){ const j = pickSec(e.clientX - r.left, e.clientY - r.top); if (j < 0) return;
    info.innerHTML = describeSec(j); setView('pages'); setSec(j); fit(); want(); return; }
  sel = pick(e.clientX - r.left, e.clientY - r.top);
  info.innerHTML = sel >= 0 ? describe(sel, true) : W.lbl_hint; want();
});
box.addEventListener('pointerleave', () => { tip.style.display = 'none'; if (hov >= 0){ hov = -1; want(); } });
box.addEventListener('wheel', e => { e.preventDefault(); const r = box.getBoundingClientRect(); zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.2 : 1 / 1.2); }, {passive: false});
function zoomAt(x, y, k){ const z = Math.max(0.02, Math.min(40, zoom * k)); ox = x - (x - ox) * z / zoom; oy = y - (y - oy) * z / zoom; zoom = z; want(); }
// ---- кнопки
const bar = document.getElementById('wbar');
bar.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return; const a = b.dataset.a, r = box.getBoundingClientRect();
  if (a === 'in') zoomAt(r.width / 2, r.height / 2, 1.5); else if (a === 'out') zoomAt(r.width / 2, r.height / 2, 1 / 1.5);
  else if (a === 'fit'){ fit(); want(); }
  else if (a === 'clean'){ clean = !clean; b.classList.toggle('on', clean); want(); }
  else if (a === 'warn'){ warn = !warn; b.classList.toggle('on', warn); want(); }
  else if (a === 'view'){ setView(view === 'secs' ? 'pages' : 'secs'); fit(); want(); }
  else if (a === 'mode'){ mode = mode === 'err' ? 'sec' : 'err'; b.classList.toggle('on', mode === 'sec'); want(); }
  else { hl = hl === a ? '' : a; bar.querySelectorAll('[data-h]').forEach(x => x.classList.toggle('on', x.dataset.a === hl)); want(); }
});
function setView(v){ view = v; hov = -1; sel = -1; bar.querySelector('[data-a=view]').classList.toggle('on', v === 'secs');
  bar.querySelectorAll('[data-h]').forEach(x => { x.disabled = v === 'secs' || x.dataset.n === '0'; }); }
function setSec(j){ sec = j; document.querySelectorAll('#wsecs tr.pick').forEach(x => x.classList.toggle('on', +x.dataset.s === sec)); }
document.querySelectorAll('#wsecs tr.pick').forEach(tr => tr.addEventListener('click', () => {
  const j = +tr.dataset.s; setSec(sec === j ? -1 : j); want();
}));
window.addEventListener('resize', resize);
if (window.ResizeObserver) new ResizeObserver(() => { if (!fitted) resize(); }).observe(box);
const det = box.closest('details'); if (det) det.addEventListener('toggle', () => { if (det.open){ fit(); resize(); } });
fit(); resize();
})();
"""


def html_block(summary, client=False):
    w = summary.get("web")
    if not w or not w.get("nodes"):
        return ""
    e = html.escape
    secs = w["sections"]
    total, shown = w["total"], w["shown"]
    big = (f'<p class="mut">Сайт большой, поэтому на схеме {_num(shown)} самых важных страниц из {_num(total)}: '
           f'все с ошибками, сироты, тупики и главные по ссылкам. Остальные спрятаны под точкой, от которой к ним '
           f'идёт ветка (такая точка крупнее).</p>' if shown < total else "")
    menu = (f' Ссылки из меню и подвала не нарисованы: они ведут на {_num(w["menu"])} '
            f'{_plural(w["menu"], "страницу", "страницы", "страниц")} с каждой страницы и закрыли бы всё сплошным пятном.'
            if w.get("menu") else "")
    rows = []
    for j, s in enumerate(secs):
        if not s["pages"]:
            continue
        low = s["pages"] >= 5 and s["from_other"] <= 2 and j > 0
        weak = round(100 * s["weak"] / s["pages"]) if s["pages"] else 0
        dot = PALETTE[(j - 1) % len(PALETTE)] if j > 0 else "var(--mut)"
        rows.append(f'<tr class="pick" data-s="{j}"><td><i style="background:{dot}"></i>{e(s["name"])}</td>'
                    f'<td>{_num(s["pages"])}</td>'
                    f'<td{" class=lo" if low else ""}>{_num(s["from_other"])}{" - мало" if low else ""}</td>'
                    f'<td{" class=lo" if weak >= 30 and s["pages"] >= 5 else ""}>{weak}%</td></tr>')
    data = dict(w, palette=PALETTE, lbl_loose="Сироты и страницы без пути от главной",
                lbl_hint="Нажмите на точку - появятся её ссылки и данные страницы.")
    data.pop("sections")
    data["sections"] = [{"name": s["name"], "pages": s["pages"], "crit": s.get("crit", 0)} for s in secs]
    js_data = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    def btn(a, label, n, color):
        return (f'<button data-a="{a}" data-h="1" data-n="{n}"{" disabled" if not n else ""}><i style="background:{color}"></i>'
                f'{label}: {_num(n)}</button>')
    loose_note = (" Справа отдельно висят страницы, до которых по ссылкам от главной не дойти"
                  + (" (сироты обведены кружком)" if w.get("orphans") else "") + "." if w.get("orphans") or w.get("unreached") else "")
    return f"""<h2 class="sec">Паутинка: как страницы связаны ссылками</h2>
<style>{CSS}</style>
<div class="card web"><div class="wtop">
<p>Каждая точка - страница сайта, линия - ссылка между страницами. Главная в центре, дальше кольцами: чем дальше от
центра, тем больше переходов от главной. Чем крупнее точка, тем больше у страницы силы ссылок. Красные точки -
страницы с ошибками, остальные зелёные (жёлтым предупреждения покажет кнопка «Предупреждения»).{loose_note} Тупики
обведены тёмной каймой: с них никуда не уйти.{menu} Кнопка «Без меню и подвала» (включена) прячет и другие
сквозные блоки вроде «популярное»: остаются ссылки из текста и карточек, то есть настоящие связи между страницами.
«По разделам» показывает каждый раздел одним шаром, а толщина линии - сколько ссылок идёт из раздела в раздел.</p>
<p class="mut">Колесо мыши или кнопки «+» и «−» приближают, схему можно двигать мышью, нажатие на точку покажет её ссылки.</p>
{big}</div>
<div class="wbar" id="wbar">{btn("err", "С ошибками", w.get("crit", 0), "var(--crit)")}
{btn("orph", "Сироты", w.get("orphans", 0), "var(--note)")}{btn("dead", "Тупики", w.get("dead", 0), "var(--tx)")}
<button data-a="warn" title="Показать жёлтым страницы с предупреждениями">Предупреждения</button>
<button data-a="mode">Цвет по разделам</button>
<button data-a="clean" class="on" title="Не рисовать ссылки, которые стоят почти на каждой странице: меню, подвал, блоки «популярное». Остаются ссылки из текста и карточек">Без меню и подвала</button>
<button data-a="view" title="Каждый раздел - один шар, толщина линии - сколько ссылок идёт из раздела в раздел">По разделам</button>
<span class="sp"></span><button data-a="out" title="Отдалить">−</button><button data-a="in" title="Приблизить">+</button>
<button data-a="fit">Вся схема</button></div>
<div class="wcv" id="wcv"><canvas></canvas><div class="wtip"></div></div>
<div class="winfo" id="winfo">Нажмите на точку - появятся её ссылки и данные страницы.</div>
<div class="wsecs" id="wsecs"><table><thead><tr><th>Раздел (нажмите, чтобы выделить)</th><th>Страниц</th>
<th title="Сколько страниц из других разделов ссылаются на этот раздел (вместе с меню). Мало - раздел почти не связан с остальным сайтом">Ссылок из других разделов</th>
<th title="Доля страниц раздела, на которые ведёт одна ссылка или ни одной">Слабо связаны</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<noscript><p class="winfo">Схема рисуется скриптом: откройте отчёт в обычном браузере.</p></noscript>
</div>
<script type="application/json" id="webdata">{js_data}</script>
<script>{JS}</script>"""
