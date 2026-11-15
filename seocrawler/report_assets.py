"""Неизменные стили и скрипт отчёт.html: вынесены из report.html_report, чтобы шаблон страницы читался."""
REPORT_CSS = """:root{--bg:#f7f6f3;--card:#fff;--tx:#1f1e1c;--mut:#6b6a66;--bd:#e4e2dc;--crit:#c0392b;--warn:#d9730d;--note:#b08d00;
--good:#2f855a;--acc:#3b5bdb;--bar:#c9d3f5}
@media (prefers-color-scheme:dark){:root{--bg:#181817;--card:#222220;--tx:#ecebe7;--mut:#a3a19b;--bd:#3a3936;
--crit:#ef6f5e;--warn:#f0973c;--note:#e3c84a;--good:#58c08a;--acc:#8ea6ff;--bar:#3b4675}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:24px;margin:0 0 4px;font-weight:600}.sub{color:var(--mut);margin:0 0 20px;word-break:break-all}
h2.sec{font-size:18px;font-weight:600;margin:28px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:12px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 16px}
.card b.big{display:block;font-size:26px;font-weight:600}.card span{color:var(--mut);font-size:13px}
.hero{display:grid;grid-template-columns:minmax(200px,260px) 1fr;gap:16px;align-items:start}
.hero .num{font-size:44px;font-weight:600;line-height:1.1}.good .num{color:var(--good)}.mid .num{color:var(--warn)}.bad .num{color:var(--crit)}
.hero p{margin:0 0 8px}.mut{color:var(--mut)}
.split{display:flex;height:10px;border-radius:5px;overflow:hidden;margin:10px 0 6px;background:var(--bg)}
.split i{display:block;height:100%}.leg{font-size:13px;color:var(--mut)}.leg i{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 4px 0 10px}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-bottom:12px}
.card h3{margin:0 0 10px;font-size:15px;font-weight:600}
.bar{display:grid;grid-template-columns:140px 1fr 56px;gap:8px;align-items:center;font-size:13px;margin:4px 0}
.bt{background:var(--bg);border-radius:4px;height:12px;overflow:hidden}.bt span{display:block;height:100%;background:var(--bar)}
.bn{text-align:right;color:var(--mut)}
.dpx{margin:-4px 0 10px;font-size:13px}.dpv{margin:10px 0 0;font-size:13px}
details.dp summary{cursor:pointer;list-style:none}details.dp summary::-webkit-details-marker{display:none}
details.dp summary:hover .bl{color:var(--acc)}details.dp[open] .bl{font-weight:600}
.dp.far .bt span{background:var(--warn)}.dp.vfar .bt span{background:var(--crit)}
.dp.far .bl,.dp.vfar .bl{text-decoration:underline dotted;text-underline-offset:3px}
details.dp ol{margin:4px 0 10px;padding-left:22px;font-size:13px;max-height:260px;overflow:auto;overflow-wrap:anywhere}
details.dp p{margin:0 0 10px;font-size:13px}
.sev-h{font-size:18px;margin:28px 0 2px;font-weight:600}.sev-h span{color:var(--mut);font-weight:400}
.sev-h.crit{color:var(--crit)}.sev-h.warn{color:var(--warn)}.sev-h.note{color:var(--note)}
.sev-intro{margin:0 0 10px;color:var(--mut)}
.issue{background:var(--card);border:1px solid var(--bd);border-radius:10px;margin:8px 0}.issue.crit{border-left:4px solid var(--crit)}.issue.warn{border-left:4px solid var(--warn)}.issue.note{border-left:4px solid var(--note)}.sev-legend{color:var(--mut);font-size:13px;margin:0 0 6px}.sev-legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 4px 0 10px}
.issue summary{cursor:pointer;padding:12px 14px;display:flex;gap:10px;align-items:center;list-style:none}
.issue summary::-webkit-details-marker{display:none}
.issue summary::after{content:"›";color:var(--mut);font-size:18px;transition:transform .15s}.issue[open] summary::after{transform:rotate(90deg)}
.dot{width:9px;height:9px;border-radius:50%;flex:none}.crit .dot{background:var(--crit)}.warn .dot{background:var(--warn)}.note .dot{background:var(--note)}
.cat{color:var(--mut);font-size:12px;min-width:96px}.it{flex:1}.cnt{font-weight:600;font-variant-numeric:tabular-nums}
.lbl{margin:0 14px 10px;font-size:13px;color:var(--mut)}.lbl[hidden]{display:none}.lbl select{font:inherit;padding:2px 6px}.lbl-tag{font-size:12px;border:1px solid var(--bd);border-radius:20px;padding:0 8px;margin-left:6px;color:var(--mut);white-space:nowrap}
.expl{margin:0 14px 12px;padding:10px 12px;background:var(--bg);border-radius:8px}.expl p{margin:0 0 6px}.expl p:last-child{margin:0}
.expl b{font-weight:600}
.more{margin:8px 14px 14px;color:var(--mut);font-size:13px}
.tw{overflow-x:auto;margin:0 14px}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd);vertical-align:top}
th{color:var(--mut);font-weight:500;white-space:nowrap}td{word-break:break-word;max-width:520px}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
code{background:var(--bg);padding:1px 5px;border-radius:4px}
#f{width:100%;padding:10px 12px;border:1px solid var(--bd);border-radius:8px;background:var(--card);color:var(--tx);font:inherit;margin:8px 0}
.warnbox,.infobox{background:var(--card);border:1px solid var(--warn);border-radius:10px;padding:12px 14px;margin:0 0 12px}
.infobox{border-color:var(--bd)}
ol.first{margin:6px 0 0;padding-left:22px}ol.first li{margin:3px 0}
footer{color:var(--mut);font-size:13px;margin-top:30px}"""

REPORT_CSS_INTRO = """.intro p{margin:0 0 6px}.intro p:last-child{margin:0}h1 .mut{font-weight:400}"""

REPORT_CSS_TAIL = (
    ".rg{border-collapse:collapse;width:100%;font-size:14px}"
    ".rg th,.rg td{text-align:left;padding:6px;border-bottom:1px solid var(--bd,#ddd);vertical-align:top}"
    ".rg td{overflow-wrap:anywhere}\n"
    ".rg b.ok{color:var(--good)}.rg b.warn{color:var(--warn)}.rg b.crit{color:var(--crit)}"
    ".rg tr.sub td{font-size:13px}.rg tr.sub td:first-child{padding-left:18px}\n"
    "@media (max-width:640px){.cat{display:none}.hero{grid-template-columns:1fr}"
    ".bar{grid-template-columns:96px 1fr 44px}}")


REPORT_JS = """document.getElementById('f').addEventListener('input',e=>{const q=e.target.value.toLowerCase().trim();
document.querySelectorAll('.issue').forEach(d=>{d.style.display=!q||d.dataset.text.includes(q)?'':'none'})});
// отчёт.html#page=<адрес>&issues=<ключи>: открыли из живой паутины в окне - показать только проблемы этой страницы
(function(){const h=new URLSearchParams(location.hash.slice(1)),url=h.get('page');if(!url)return;
const keys=(h.get('issues')||'').split(',').filter(Boolean),box=document.getElementById('pagef'),all=[...document.querySelectorAll('.issue')];
const has=d=>[...d.querySelectorAll('td')].some(td=>td.textContent===url||[...td.querySelectorAll('a')].some(a=>a.getAttribute('href')===url));
const mine=all.filter(d=>keys.includes(d.id)||has(d));
all.forEach(d=>{const on=mine.includes(d);d.style.display=on?'':'none';d.open=on&&mine.length<=5;
d.querySelectorAll('tr').forEach(tr=>{if(on&&[...tr.querySelectorAll('td')].some(td=>td.textContent===url))tr.style.background='rgba(255,196,0,.18)'})});
const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener';a.textContent=url;
box.textContent=mine.length?'Проблемы страницы ':'У страницы ';box.appendChild(a);
box.append(mine.length?': '+mine.length+'. ':' в этом отчёте проблем не найдено. ');
const b=document.createElement('a');b.href='#';b.textContent='Показать все проблемы';
b.onclick=e=>{e.preventDefault();box.hidden=true;all.forEach(d=>{d.style.display='';d.open=false});history.replaceState(null,'',location.pathname)};
box.appendChild(b);box.hidden=false;box.scrollIntoView({block:'start'})})();"""
