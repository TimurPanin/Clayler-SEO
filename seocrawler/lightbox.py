"""Снимок крупно поверх страницы: нажали на снимок в отчёте (телефон, ошибка с рамкой, кнопка покупки) - он
открывается во весь экран, закрывается нажатием в любом месте или клавишей Esc. Без библиотек, работает офлайн
(в отчёте для клиента снимки внутри файла). Срабатывает на любой <img> внутри <figure>."""

CSS = """figure img{cursor:zoom-in}
#lbx{position:fixed;inset:0;z-index:1000;background:rgba(8,10,16,.88);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:16px;box-sizing:border-box;cursor:zoom-out}
#lbx[hidden]{display:none}
#lbx img{max-width:100%;max-height:calc(100vh - 80px);object-fit:contain;border-radius:8px;box-shadow:0 10px 40px rgba(0,0,0,.5);background:#fff}
#lbx p{margin:0;max-width:900px;color:#e9edf5;font-size:14px;line-height:1.45;text-align:center;overflow-wrap:anywhere;white-space:pre-line}
#lbx b.x{position:fixed;top:10px;right:16px;color:#fff;font-size:32px;line-height:1;font-weight:400}
@media print{#lbx{display:none}}"""

JS = """(function(){var box=document.createElement('div');box.id='lbx';box.hidden=true;
box.setAttribute('role','dialog');box.setAttribute('aria-label','Снимок крупно');
box.innerHTML='<b class="x" aria-hidden="true">×</b><img alt=""><p></p>';document.body.appendChild(box);
var big=box.querySelector('img'),cap=box.querySelector('p');
function close(){box.hidden=true;big.removeAttribute('src');document.body.style.overflow=''}
document.addEventListener('click',function(e){var t=e.target;
if(!box.hidden){close();return}
if(t.tagName!=='IMG'||!t.closest('figure'))return;
e.preventDefault();big.src=t.currentSrc||t.src;var c=t.closest('figure').querySelector('figcaption');
cap.textContent=c?c.innerText:'';cap.hidden=!c;box.hidden=false;document.body.style.overflow='hidden'});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!box.hidden)close()});})();"""
