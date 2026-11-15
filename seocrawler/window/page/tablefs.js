// Кнопка «На весь экран» у больших таблиц: окно (/page/tablefs.js) и отчёты (report.py, дерево сайта -
// вставляются в страницу через seocrawler/tablefs.py). Таблица переносится в слой на весь экран, первая строка и первый
// столбец закреплены, выход - Esc или «Закрыть». Обёртки: .br-scroll, .tw, [data-fs]. Кнопка появляется, если таблица
// не влезает по ширине или в ней больше 12 строк. Перед открытием на обёртку уходит событие «fs-open».
(function(){
if (window.__tableFs) return; window.__tableFs = 1;
const SEL = '.br-scroll,.tw,[data-fs]';
const st = document.createElement('style');
st.textContent = `.fs-bar{display:flex;justify-content:flex-end;margin:6px 0 2px}
.fs-btn{font:inherit;font-size:13px;line-height:1.2;padding:4px 10px;border-radius:7px;border:1px solid rgba(128,128,128,.4);background:transparent;color:inherit;cursor:pointer;opacity:.85}
.fs-btn:hover{opacity:1;border-color:rgba(128,128,128,.8)}
.fs-ov{position:fixed;inset:0;z-index:2147483000;display:flex;flex-direction:column;background:var(--fsbg);color:var(--fstx)}
.fs-top{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid rgba(128,128,128,.3)}
.fs-top b{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:16px}
.fs-top span{font-size:13px;opacity:.65}
.fs-ov>.fs-in{flex:1 1 auto;min-height:0;max-height:none!important;height:auto!important;overflow:auto!important;margin:0!important;padding:0 16px 16px}
.fs-ov table{width:auto}
.fs-ov thead th,.fs-ov thead td{position:sticky;top:0;z-index:2;background:var(--fsbg)}
.fs-ov tr>:first-child{position:sticky;left:0;z-index:1;background:var(--fsbg)}
.fs-ov thead tr>:first-child{z-index:3}
body.fs-lock{overflow:hidden}`;
document.head.appendChild(st);

const bgOf = el => { for (let e = el; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor;
  if (c && c !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(c)) return c; } return '#fff'; };
const titleOf = el => { if (el.dataset.fs) return el.dataset.fs; const box = el.closest('section,details,.card,.sec,article') || document.body;
  const h = box.querySelector('h2,h3,summary'); if (!h) return 'Таблица';
  const c = (h.querySelector('.it') || h).cloneNode(true); c.querySelectorAll('.mut,small,button,.cat,.cnt').forEach(e => e.remove());
  return c.textContent.replace(/\s+/g, ' ').trim().slice(0, 140) || 'Таблица'; };
const big = el => { if (el.hasAttribute('data-fs')) return true; const t = el.querySelector('table');
  return !!t && (el.scrollWidth > el.clientWidth + 4 || t.rows.length > 12); };

let cur = null;
function open(el){
  if (cur) close();
  el.dispatchEvent(new CustomEvent('fs-open', {bubbles: true}));
  const ov = document.createElement('div'), mark = document.createComment('fs');
  ov.className = 'fs-ov'; ov.setAttribute('role', 'dialog'); ov.setAttribute('aria-modal', 'true');
  ov.style.setProperty('--fsbg', bgOf(el)); ov.style.setProperty('--fstx', getComputedStyle(el).color);
  const top = document.createElement('div'); top.className = 'fs-top';
  const b = document.createElement('b'); b.textContent = titleOf(el);
  const hint = document.createElement('span'); hint.textContent = 'Esc - выйти';
  const x = document.createElement('button'); x.type = 'button'; x.className = 'fs-btn'; x.textContent = 'Закрыть';
  x.onclick = close; top.append(b, hint, x);
  el.parentNode.insertBefore(mark, el); el.classList.add('fs-in'); ov.append(top, el);
  document.body.appendChild(ov); document.body.classList.add('fs-lock'); x.focus();
  cur = {el, ov, mark};
}
function close(){
  if (!cur) return; const {el, ov, mark} = cur; cur = null;
  el.classList.remove('fs-in'); mark.parentNode.insertBefore(el, mark); mark.remove(); ov.remove();
  document.body.classList.remove('fs-lock');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape' && cur) { e.preventDefault(); e.stopPropagation(); close(); } }, true);

function scan(){
  document.querySelectorAll(SEL).forEach(el => {
    if (el.closest('.fs-ov')) return;
    const prev = el.previousElementSibling, has = prev && prev.classList.contains('fs-bar');
    const need = el.offsetParent !== null && big(el);
    if (need && !has) {
      const bar = document.createElement('div'); bar.className = 'fs-bar';
      const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'fs-btn';
      btn.textContent = '⛶ На весь экран'; btn.title = 'Открыть таблицу на весь экран, выход - Esc';
      btn.onclick = () => open(el); bar.appendChild(btn); el.parentNode.insertBefore(bar, el);
    } else if (has && prev.hidden !== !need) prev.hidden = !need;
  });
}
let t = 0; const later = () => { clearTimeout(t); t = setTimeout(scan, 150); };
new MutationObserver(later).observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'open']});
addEventListener('resize', later); document.addEventListener('toggle', later, true); scan();
})();
