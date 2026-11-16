"""Страница из отчёта с обведённой проблемой: в отчёт.html, открытом из окна, клик по адресу страницы
в строке проблемы открывает копию этой страницы, где красной рамкой обведено то, о чём строка: ссылка на казино,
битая ссылка на мессенджер, картинка без alt, заголовок и т. п. Что искать - остальные ячейки той же строки
(адреса ищутся в href/src, текст - в тексте страницы).

Копия - HTML сайта, загруженный программой, с <base> на настоящий адрес (картинки, стили и скрипты грузятся
с сайта) и нашим скриптом подсветки. Открывается на отдельном адресе show.localhost: у скриптов чужой страницы
другой «сайт», чем у окна программы, и они не могут нажимать кнопки окна (server.py отдаёт show.localhost
только эту страницу, а действия окна принимает только с его собственного адреса). Адреса окна и локальной сети
копия не открывает (closed): скрипт копии может сам запросить /api/show и прочитать ответ."""
import html
import ipaddress
import json
import os
import re
import socket
import threading
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from ..fetcher import Fetcher, UA_PRESETS
from ..parser import detect_encoding

HOST = "show.localhost"
MAX_FIND = 12

MARK_JS = r"""(function(){
var SHOT=__SHOT__, KEY=__KEY__, DET=__DET__, F=__FIND__, REAL=__URL__, CODE=__CODE__, FOCUS=__FOCUS__, LINES=__LINES__, TITLE=__TITLE__, META=__META__, done=false, tries=0, ERR=[], subsOff=false;
try{var u=new URL(REAL);history.replaceState(null,'',location.origin+u.pathname+u.search+u.hash)}catch(e){}
// ошибки JavaScript страницы при загрузке - для панели «Что в коде» (наш скрипт первый в <head>, видит все)
function errPush(s){if(ERR.length<30&&s)ERR.push(String(s).slice(0,300));var c=document.getElementById('clayler-code-js');if(c)fillJs(c)}
addEventListener('error',function(e){if(e instanceof ErrorEvent)errPush(e.message+(e.filename?' ('+e.filename.split('?')[0]+':'+e.lineno+')':''))},true);
addEventListener('unhandledrejection',function(e){var r=e.reason;errPush('Promise: '+(r&&r.message||r))});
try{var ce=console.error;console.error=function(){errPush('console.error: '+[].map.call(arguments,function(a){return a&&a.message||String(a)}).join(' '));return ce.apply(console,arguments)}}catch(e){}
// адрес для сравнения: параметры по порядку (программа хранит адреса так), без «/» в конце
function abs(v){try{var x=new URL(v,REAL);x.searchParams.sort();return x.href.replace(/\/+$/,'')}catch(e){return v}}
// кривой адрес («https://Собрали показательные кейсы…» - ошибка на сайте): браузер его не разберёт, а программа
// хранит строчными и с «/» в конце - сравниваем без регистра, кодировки и хвостовых «/» и «.»
function loose(v){try{v=decodeURIComponent(v)}catch(e){}
  var m=/^([a-z]+:\/\/[^\/?#]*)(.*)$/i.exec(v);return (m?m[1].toLowerCase()+m[2]:v).replace(/[\/.\s]+$/,'')}
function urlish(s){return /^(https?:|tg:|whatsapp:|viber:|mailto:|tel:|\/\/|\/)/i.test(s)}
var ATTR=['href','src','data-src','data-lazy-src','data-original','action','poster'];
function byUrl(s){
  // проблема про картинку (img_…): только картинки - иначе адрес «картинки» https://site.ru/ (пустой src) обводил
  // логотип и «Главная» в крошках (dom-primer.ru 01.11.2026)
  var want=abs(s), out=[], sel=/^img_/.test(KEY||'')?'img,source,picture':'a,img,source,iframe,video,audio,form,picture,link,script';
  document.querySelectorAll(sel).forEach(function(el){
    if(el.closest('#clayler-show'))return;   // своя плашка («Открыть настоящую страницу» ведёт на тот же адрес)
    for(var i=0;i<ATTR.length;i++){var v=el.getAttribute(ATTR[i]);
      if(v&&(v===s||abs(v)===want||loose(v)===loose(s))){out.push(el);return}}
    var ss=el.getAttribute('srcset')||el.getAttribute('data-srcset');
    if(ss&&ss.split(',').some(function(p){var x=p.trim().split(/\s+/)[0];return x&&abs(x)===want}))out.push(el);
  });
  return out.map(function(el){return el.tagName==='SOURCE'&&el.parentElement?el.parentElement:el});
}
function norm(t){return t.replace(/\s+/g,' ').trim().toLowerCase()}
function byText(s){
  // телефон в отчёте приведён к виду +79297322722, на сайте - «+7 (929) 732-27-22»: сравниваем цифры
  var dig=s.replace(/\D/g,'');
  if(/^\+?[\d\s()-]{10,}$/.test(s)&&dig.length>=10&&dig.length<=12){
    var tail=dig.slice(-10),hits=[].filter.call(document.querySelectorAll('a[href^="tel:"]'),function(a){
      return a.getAttribute('href').replace(/\D/g,'').slice(-10)===tail});
    if(!hits.length){var tw=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null),tn;
      while((tn=tw.nextNode())&&hits.length<5){var pe=tn.parentElement;
        if(pe&&!/^(SCRIPT|STYLE)$/.test(pe.tagName)&&!pe.closest('#clayler-show')&&tn.data.replace(/\D/g,'').indexOf(tail)>=0)hits.push(pe)}}
    if(hits.length)return hits.slice(0,5);
  }
  var want=norm(s.replace(/…$/,'')).slice(0,80), out=[];
  if(want.length<4||/^[\d\s%.,:+-]+$/.test(want))return out;
  var w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null),n;
  while((n=w.nextNode())&&out.length<10){
    var p=n.parentElement;if(!p||/^(SCRIPT|STYLE|NOSCRIPT)$/.test(p.tagName)||p.closest('#clayler-show'))continue;
    if(norm(n.data).indexOf(want)>=0)out.push(p);
  }
  if(!out.length){  // текст разбит на несколько тегов: самый маленький элемент, где он есть целиком
    // только небольшие элементы: textContent больших блоков на тяжёлой странице (Tilda, 5 МБ) считается минутами
    var all=document.body.querySelectorAll('*'),best=null;
    for(var i=all.length-1;i>=0;i--){var el=all[i];
      if(el.childElementCount>20||el.id==='clayler-show')continue;
      var t=el.textContent||'';if(t.length>want.length*4+300)continue;
      if(norm(t).indexOf(want)>=0){best=el;break}}  // с конца: вложенный раньше внешнего
    if(best)out.push(best);
  }
  return out.slice(0,5);
}
function reveal(el){  // спрятанное стилем (взлом прячет ссылки) показываем, чтобы рамку было видно
  var hid=false;
  for(var e=el;e&&e!==document.body;e=e.parentElement){var c=getComputedStyle(e);
    if(c.display==='none'){e.style.setProperty('display','block','important');hid=true}
    if(c.visibility==='hidden'){e.style.setProperty('visibility','visible','important');hid=true}
    if(c.position==='absolute'||c.position==='fixed'){var r=e.getBoundingClientRect();
      if(r.right<0||r.bottom<0||r.left>innerWidth+2000){e.style.setProperty('position','static','important');hid=true}}
  }
  if(parseFloat(getComputedStyle(el).fontSize)<2){el.style.setProperty('font-size','14px','important');hid=true}
  return hid;
}
// Рамка там, где элемент ВИДНО (05.11.2026): раньше обводили сам элемент (outline), а у ссылки-обёртки вокруг
// карточки товара (<a> строчная, внутри блоки) своя рамка нулевой высоты - «обведено: 1», а рамки нет (dom-primer.ru,
// битая ссылка на странице каталога). Теперь - по содержимому: текст по самим словам, обёртка - по тому, что внутри,
// картинка и поле - по себе. Рамка - отдельный слой поверх страницы и переставляется сама при изменении ширины
// окна и разметки (иначе съезжала, когда окно сужали или открывали инструменты разработчика)
var FRAMES=[];
function rectOf(el){var own=el.getBoundingClientRect(),r=null;
  if(el.firstChild&&!/^(IMG|IFRAME|VIDEO|INPUT|SELECT|TEXTAREA|PICTURE|svg)$/i.test(el.tagName)){
    try{var rg=document.createRange();rg.selectNodeContents(el);r=rg.getBoundingClientRect()}catch(e){}}
  if(!r||r.width<2||r.height<2)return own;
  if(own.width>=2&&own.height>=2){   // по словам, но не шире самого элемента: спрятанное подменю или текст для
    var L=Math.max(r.left,own.left),T=Math.max(r.top,own.top),R=Math.min(r.right,own.right),B=Math.min(r.bottom,own.bottom);
    return R-L>=2&&B-T>=2?{left:L,top:T,width:R-L,height:B-T}:own}   // экранного диктора (left:-9999px) не растянут рамку
  // обёртка без своей высоты: по видимым детям, без спрятанных и унесённых за экран
  var L2=1e9,T2=1e9,R2=-1e9,B2=-1e9,n=0;
  [].slice.call(el.querySelectorAll('*'),0,200).forEach(function(c){var q=c.getBoundingClientRect();
    if(q.width<2||q.height<2||q.right<0||q.left>document.documentElement.scrollWidth)return;
    var st=getComputedStyle(c);if(st.visibility==='hidden'||+st.opacity===0)return;
    L2=Math.min(L2,q.left);T2=Math.min(T2,q.top);R2=Math.max(R2,q.right);B2=Math.max(B2,q.bottom);n++});
  return n?{left:L2,top:T2,width:R2-L2,height:B2-T2}:r}
function place(f){var r=rectOf(f.el),x=r.left+scrollX,y=r.top+scrollY,s=f.box.style;
  // элемент без размера (битая картинка без alt): рамка 20×20 на его месте - видно, где он стоит; совсем не виден
  // (внутри закрытого меню, display:none) - рамки нет, а не рамка в углу страницы (ревью 05.11.2026)
  var off=!f.el.isConnected||!f.el.getClientRects().length,w=Math.max(r.width,12),h=Math.max(r.height,12);s.display=off?'none':'block';
  s.left=(x-4)+'px';s.top=(y-4)+'px';s.width=(w+8)+'px';s.height=(h+8)+'px';
  if(f.tag){f.tag.style.display=off?'none':'block';f.tag.style.left=Math.max(0,x-4)+'px';f.tag.style.top=Math.max(0,y-27)+'px'}}
function placeAll(){FRAMES.forEach(place)}
function frame(el,label){
  var b=document.createElement('div');b.setAttribute('data-clayler','1');
  b.setAttribute('style','position:absolute;z-index:2147483646;pointer-events:none;box-sizing:border-box;border:3px solid #e00;'+
    'border-radius:4px;box-shadow:0 0 0 6px rgba(230,0,0,.25)');
  document.documentElement.appendChild(b);var f={el:el,box:b,tag:null};
  if(label){var t=document.createElement('div');t.setAttribute('data-clayler','1');t.textContent=label;
    t.setAttribute('style','position:absolute;z-index:2147483647;pointer-events:none;background:#e00;color:#fff;'+
      'font:600 13px/1.5 Arial,sans-serif;padding:1px 7px;border-radius:4px;white-space:nowrap');
    document.documentElement.appendChild(t);f.tag=t}
  FRAMES.push(f);place(f);
  if(FRAMES.length===1){addEventListener('resize',placeAll);
    try{new ResizeObserver(placeAll).observe(document.body)}catch(e){}
    setInterval(placeAll,700)}   // карусели, подгрузка картинок и шрифтов двигают страницу без изменения её размера
  return f}
window.__claylerFrames=FRAMES;   // для автотеста: что обведено и где рамка
function mark(){
  try{mark1()}catch(e){done=true;var b=document.getElementById('clayler-show-msg');
    if(b)b.textContent='Не получилось найти: '+String(e).slice(0,120)}
}
// «Тошнота»: самые частые слова из отчёта («сайта - 93, страницы - 80») - подсветить каждое на странице своим цветом
function markWords(){
  var items=[];F.join(', ').replace(/([A-Za-zА-Яа-яЁё-]{3,})\s*[-–]\s*(\d+)/g,function(_m,w,n){items.push([w.toLowerCase(),+n])});
  if(!items.length)F.join(', ').split(/\s*,\s*/).forEach(function(w){if(/^[A-Za-zА-Яа-яЁё-]{3,}$/.test(w))items.push([w.toLowerCase(),0])});
  if(!items.length)return false;
  var colors=['#ffd34d','#9be7ff','#c6f6a8','#ffb3c7','#e2c6ff'],stems=items.slice(0,5).map(function(it){
    var w=it[0];return w.length>6?w.slice(0,-2):w.length>4?w.slice(0,-1):w});
  var rx=new RegExp('(?<![\\p{L}])('+stems.join('|')+')\\p{L}*','giu');   // в слове только буквы и «-»
  var cnt=stems.map(function(){return 0}),nodes=[],tw=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null),n;
  while((n=tw.nextNode())){var pe=n.parentElement;
    if(pe&&!/^(SCRIPT|STYLE|NOSCRIPT|TEXTAREA)$/.test(pe.tagName)&&!pe.closest('#clayler-show')&&rx.test(n.data))nodes.push(n);rx.lastIndex=0}
  nodes.forEach(function(t){var frag=document.createDocumentFragment(),last=0,txt=t.data,m;rx.lastIndex=0;
    while((m=rx.exec(txt))){var k=stems.findIndex(function(x){return m[1].toLowerCase()===x.toLowerCase()});
      frag.appendChild(document.createTextNode(txt.slice(last,m.index)));
      var mk=document.createElement('mark');mk.textContent=m[0];mk.setAttribute('style','background:'+colors[k]+' !important;color:#000 !important');
      frag.appendChild(mk);cnt[k]++;last=m.index+m[0].length}
    frag.appendChild(document.createTextNode(txt.slice(last)));t.parentNode.replaceChild(frag,t)});
  var first=document.querySelector('mark[style*="background"]');if(first)first.scrollIntoView({block:'center'});
  var b=document.getElementById('clayler-show-msg');
  if(b)b.innerHTML='Подсвечены самые частые слова: '+items.slice(0,5).map(function(it,i){return '<span style="background:'+colors[i]+
    ';color:#000;padding:0 3px">'+esc(it[0])+'</span> - '+(it[1]?it[1]+' раз в тексте, ':'')+'на странице с меню и подвалом - '+cnt[i]}).join('; ')+
    '. Замените часть повторов синонимами или уберите.';
  return true;
}
// «Нет H2»: обвести блоки своего текста страницы (где много текста и нет подзаголовков)
function markText(){
  var blocks=[].filter.call(document.body.querySelectorAll('p,li,div,td,section,article'),function(el){
    if(el.closest('#clayler-show,nav,header,footer'))return false;
    var own=[].reduce.call(el.childNodes,function(a,c){return a+(c.nodeType===3?c.data.trim().length:0)},0);
    return own>=150&&el.getBoundingClientRect().width>0});
  blocks=blocks.filter(function(el){return !blocks.some(function(o){return o!==el&&o.contains(el)})}).slice(0,12);
  blocks.forEach(function(el){el.style.setProperty('outline','3px solid #e00','important');el.style.setProperty('outline-offset','2px','important')});
  if(blocks[0])blocks[0].scrollIntoView({block:'center'});
  var h2=document.querySelectorAll('h2').length,b=document.getElementById('clayler-show-msg');
  if(b)b.textContent='Обведены блоки текста ('+blocks.length+'). Подзаголовков H2 на странице: '+h2+
    '. Разбейте текст подзаголовками H2 по темам - так его легче читать, а поисковику проще понять, о чём каждая часть.';
  return blocks.length>0;
}
// Подсветить сами куски текста (а не весь элемент): остатки шаблона «#Classic#», слово со смешанными буквами.
// subs - [[текст, {номера букв, которые выделить красным}]]. Возвращает число подсвеченных.
function markSubs(subs){
  var n=0,first=null,nodes=[],tw=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null),t;
  while((t=tw.nextNode())){var pe=t.parentElement;
    if(pe&&!/^(SCRIPT|STYLE|NOSCRIPT|TEXTAREA)$/.test(pe.tagName)&&!pe.closest('#clayler-show'))nodes.push(t)}
  nodes.forEach(function(t){
    var txt=t.data,low=txt.toLowerCase(),hits=[],same=low.length===txt.length;
    if(!same)low=txt;   // «İ» в нижнем регистре - две буквы: места в low и txt разъедутся - ищем как есть
    subs.forEach(function(s){var w=same?s[0].toLowerCase():s[0],i=low.indexOf(w);
      while(w&&i>=0&&n+hits.length<50){hits.push([i,i+w.length,s[1]]);i=low.indexOf(w,i+w.length)}});
    if(!hits.length)return;
    hits.sort(function(a,b){return a[0]-b[0]});
    var frag=document.createDocumentFragment(),last=0;
    hits.forEach(function(h){if(h[0]<last)return;
      frag.appendChild(document.createTextNode(txt.slice(last,h[0])));
      var mk=document.createElement('mark');
      mk.setAttribute('style','background:#ffd34d !important;color:#000 !important;outline:2px solid #e00 !important;outline-offset:1px');
      var piece=txt.slice(h[0],h[1]);
      for(var k=0;k<piece.length;k++){
        if(h[2]&&h[2][k]){var b=document.createElement('b');b.textContent=piece[k];
          b.setAttribute('style','color:#e00 !important;text-decoration:underline !important');mk.appendChild(b)}
        else mk.appendChild(document.createTextNode(piece[k]))}
      frag.appendChild(mk);reveal(mk);first=first||mk;n++;last=h[1]});
    frag.appendChild(document.createTextNode(txt.slice(last)));t.parentNode.replaceChild(frag,t)});
  if(first)first.scrollIntoView({block:'center'});
  return n;
}
// Что подсветить кусками: остатки шаблона - всё, что в «…» в строке отчёта; смешанные буквы - слово «[C]eramicplus»
// (в скобках - чужие буквы). [] - подсвечивать обычным способом
function subsFor(){
  var out=[];
  if(/^buy_junk/.test(KEY||''))F.forEach(function(s){(s.match(/«([^«»]{2,80})»/g)||[]).forEach(function(q){
    q=q.slice(1,-1);if(!out.some(function(o){return o[0]===q}))out.push([q,null])})});
  if(/^mixed_letters/.test(KEY||''))F.forEach(function(s){
    var m=/^(\S*\[[^\]]+\]\S*)\s*\(/.exec(s)||/^(\S*\[[^\]]+\]\S*)$/.exec(s);if(!m)return;
    var word='',odd={};m[1].replace(/\[([^\]]+)\]|([^\[\]])/g,function(_a,x,y){
      if(x){for(var k=0;k<x.length;k++)odd[word.length+k]=true;word+=x}else word+=y;return ''});
    if(word.length>=2)out.push([word,odd])});
  return out;
}
// Формы (согласие на обработку данных): нужная форма - по её названию из строки отчёта («Оставить заявку») или та,
// где просят телефон или почту; поиск по сайту не обводим (dom-primer.ru 01.11.2026 обвело два поля поиска)
function pickForms(){
  var names=F.map(function(s){return norm(s.replace(/[«»"]/g,''))}).filter(function(s){return s.length>=4&&!/^(на странице|в виджете)/.test(s)});
  var all=[].filter.call(document.querySelectorAll('form'),function(f){return !f.closest('#clayler-show')});
  var byName=all.filter(function(f){var t=norm(f.textContent||'')+' '+[].map.call(f.querySelectorAll('input[type=submit],button'),
    function(b){return norm(b.value||b.textContent||'')}).join(' ');return names.some(function(n){return t.indexOf(n)>=0})});
  if(byName.length)return byName;
  return all.filter(function(f){return f.querySelector('input[type=tel],input[type=email],input[name*=phone i],input[name*=tel i],input[name*=mail i],textarea')});
}
function mark1(){
  if(done)return;
  // куски не нашлись за 6 попыток - дальше обычный поиск, без возврата к кускам: иначе счётчик попыток сбрасывался по
  // кругу и копия искала вечно, «Не нашёл на странице» не появлялось (проверка кода 04.11.2026)
  var subs=subsOff?[]:subsFor();
  if(subs.length){var n=markSubs(subs);
    if(n){done=true;var bm=document.getElementById('clayler-show-msg');
      if(bm)bm.textContent='Подсвечено: '+n+' ('+subs.map(function(s){return '«'+s[0]+'»'}).slice(0,3).join(', ')+
        (/^mixed_letters/.test(KEY||'')?'; чужие буквы - красным с подчёркиванием':'')+').';
      return}
    if(++tries<6){setTimeout(mark,[300,800,1500,3000,6000][tries-1]);return}
    tries=0;subsOff=true}
  if(FOCUS==='words'&&markWords()){done=true;return}
  if(FOCUS==='shot'){done=true;var r=SHOT([KEY,innerWidth]),b=document.getElementById('clayler-show-msg');
    if(b)b.textContent=r.n?('Обведено красным: '+r.n+(r.note?' ('+r.note+')':'')+'.'):'На этой копии такого не нашлось - снимок в отчёте сделан при проверке.';
    if(r.top!==null)scrollTo(0,Math.max(0,r.top-120));return}
  if(FOCUS==='text'&&markText()){done=true;return}
  // проблема про H1 - обводим сами заголовки (текст в отчёте у нескольких H1 склеен « | » и на странице не найдётся)
  if(FOCUS==='h1'&&document.querySelector('h1'))F=['<h1>'];
  if(FOCUS==='forms'){var fs=pickForms();if(fs.length){F=['<form>'];window.__forms=fs}}   // в отчёте у формы - надпись кнопки, её может не быть
  if(!F.length&&LINES&&LINES.ids&&LINES.ids.length){   // одинаковые id: обводим элементы, которые видно
    var els=[];LINES.ids.forEach(function(i){[].forEach.call(document.querySelectorAll('#'+CSS.escape(String(i))),
      function(el){if(el.getBoundingClientRect().width>0)els.push(el)})});
    if(els.length){F=['<ids>'];window.__ids=els}}
  if(!F.length){done=true;var m=document.getElementById('clayler-show-msg');
    if(m)m.textContent=KEY==='mobile_diff'?'Сравните с соседней версией: что отличается - в строке отчёта сверху.'
      :'Проблема в коде страницы, на самой странице её не видно - смотрите «Что в коде».';return}
  var found=[],miss=[],urls=F.filter(urlish),texts=F.filter(function(s){return !urlish(s)&&!/^<(h1|ids|form)>$/.test(s)});
  if(F[0]==='<h1>')found=[].slice.call(document.querySelectorAll('h1'));
  if(F[0]==='<ids>')found=window.__ids.slice(0,30);
  if(F[0]==='<form>')found=window.__forms.slice(0,10);
  urls.forEach(function(s){var r=byUrl(s);if(r.length)found=found.concat(r);else miss.push(s)});
  // текст - только из первой ячейки, которая нашлась: иначе название, подпись и описание карточки обводятся все
  if(!found.length)texts.some(function(s){found=byText(s);return found.length>0});
  found=found.filter(function(el,i){return found.indexOf(el)===i&&!found.some(function(o){return o!==el&&el.contains(o)})});
  if(!found.length&&++tries<6){setTimeout(mark,[300,800,1500,3000,6000][tries-1]);return}
  done=true;var hidden=0;
  found.slice(0,30).forEach(function(el){
    if(reveal(el))hidden++;
    if(el.tagName!=='LINK'&&el.tagName!=='SCRIPT')frame(el);
  });
  var first=found.filter(function(el){return el.tagName!=='LINK'&&el.tagName!=='SCRIPT'})[0];
  var fr=FRAMES.filter(function(f){return f.el===first})[0];   // к рамке, а не к элементу: у обёртки своей высоты нет
  if(fr&&fr.box.style.display!=='none')fr.box.scrollIntoView({block:'center'});else if(first)first.scrollIntoView({block:'center'});
  var b=document.getElementById('clayler-show-msg');
  var unseen=FRAMES.filter(function(f){return f.box.style.display==='none'}).length;
  if(b)b.textContent=found.length?('Обведено красным: '+found.length+(hidden?' (из них спрятано на сайте и показано здесь: '+hidden+')':'')+
    (unseen?'; не видно на странице (в закрытом меню или блоке): '+unseen:'')+'.')
    :('Не нашёл на странице: '+F.slice(0,3).join(', ')+'. Возможно, это в коде страницы (title, описание), появляется после действий посетителя или уже исправлено.');
}
function banner(){
  var d=document.createElement('div');d.id='clayler-show';
  d.setAttribute('style','position:fixed;z-index:2147483647;right:12px;bottom:12px;max-width:min(560px,calc(100vw - 24px));background:#fff;color:#111;'+
    'font:13px/1.4 Arial,sans-serif;border:2px solid #e00;border-radius:8px;padding:8px 12px;box-shadow:0 4px 16px rgba(0,0,0,.25)');
  // в рамке «телефон / компьютер» название и строка отчёта - уже сверху страницы, здесь коротко
  var inner=window!==window.top;
  d.innerHTML='<b>Clayler SEO</b> · копия страницы'+(TITLE&&!inner?'<div style="margin:2px 0;font-weight:bold">Проблема: '+esc(TITLE)+'</div>'+
    (DET?'<div style="color:#555;margin-bottom:2px">'+esc(DET)+'</div>':''):' ')+
    '<span id="clayler-show-msg">ищу…</span> '+
    '<a style="color:#06c" target="_top"></a> <a style="color:#06c;cursor:pointer;margin-left:6px">Что в коде ▸</a>'+
    ' <a style="color:#666;cursor:pointer;margin-left:6px">скрыть</a><div id="clayler-code" hidden></div>';
  var a=d.querySelectorAll('a');a[0].href=REAL;a[0].textContent='Открыть настоящую страницу';
  a[1].onclick=function(){toggleCode()};
  a[2].onclick=function(){d.remove()};
  document.body.appendChild(d);
  if(FOCUS&&!/^(words|text|forms|shot)$/.test(FOCUS))toggleCode();   // для слов, текста и форм код не нужен   // проблема в коде страницы (title, description, canonical…) - панель сразу открыта
}
// «Что в коде»: то, чего не видно на странице, - из HTML, который получает поисковик (без JavaScript),
// поле проблемы обведено красным; ниже - ошибки JavaScript этой копии при загрузке
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function fillJs(c){c.innerHTML=ERR.length?ERR.map(function(e){return '<div style="color:#b00">'+esc(e)+'</div>'}).join(''):'<span style="color:#080">ошибок нет</span>'}
// Качество существующего (05.11.2026): длина сейчас, оценка из последней проверки сайта (длинный, короткий, такой же
// у N страниц - заголовки.csv) и готовый вариант с кнопкой «Скопировать»
var QPFX={title:'title:',description:'описание:',h1:'h1:'};
function quality(key,vals){
  if(!QPFX[key])return '';var out='';
  if(vals.length&&key!=='h1')out+='<div style="color:#888">'+Array.from(vals[0]).length+' симв.</div>';
  ((META&&META.what)||[]).forEach(function(w){if(w.toLowerCase().indexOf(QPFX[key])===0&&!/: нет /.test(w))
    out+='<div style="color:#b00">'+esc(w.slice(QPFX[key].length).trim())+(META.when?' <span style="color:#888">(проверка '+esc(META.when)+')</span>':'')+'</div>'});
  if(META&&META[key])out+='<div style="margin-top:3px;color:#060">Предлагаю: '+esc(META[key])+
    ' <a data-copy="'+esc(META[key])+'" style="color:#06c;cursor:pointer;white-space:nowrap">Скопировать</a></div>';
  return out}
function copyText(a){var s=a.getAttribute('data-copy');
  function ok(){a.textContent='Скопировано';setTimeout(function(){a.textContent='Скопировать'},1500)}
  function old(){var x=document.createElement('textarea');x.value=s;x.setAttribute('data-clayler','1');
    x.style.cssText='position:fixed;left:-9999px';document.body.appendChild(x);x.select();
    try{document.execCommand('copy');ok()}catch(e){a.textContent='Не вышло'}x.remove()}
  if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(s).then(ok,old);else old()}
function toggleCode(){
  var p=document.getElementById('clayler-code');if(!p)return;
  if(!p.hidden){p.hidden=true;return}
  var rows=CODE.map(function(r){var key=r[0],name=r[1],vals=r[2],hit=key===FOCUS;
    var need=key==='title'||key==='description'||key==='h1';   // без остального страница обходится
    var v=vals.length?vals.map(function(x){return '<div'+(/\((пусто|нет)\)$/.test(x)?' style="color:#b00"':'')+'>'+esc(x)+'</div>'}).join(''):'<span style="color:'+(need?'#b00':'#888')+'">нет</span>';
    if(vals.length>1&&(key==='title'||key==='description'||key==='canonical'||key==='h1'))v+='<div style="color:#b00">'+vals.length+' шт.</div>';
    v+=quality(key,vals);
    return '<tr style="'+(hit?'outline:3px solid #e00;outline-offset:-2px;':'')+'"><td style="padding:3px 8px 3px 0;color:#555;vertical-align:top;white-space:nowrap">'+
      esc(name)+'</td><td style="padding:3px 0;word-break:break-word">'+v+'</td></tr>'});
  var code=LINES&&LINES.title?'<div style="margin:2px 0 8px;padding:6px;border:3px solid #e00;border-radius:4px">'+
    '<div style="margin-bottom:4px">'+esc(LINES.title)+'</div>'+(LINES.lines||[]).map(function(l){
      return '<div style="font:12px Consolas,monospace;white-space:pre-wrap;word-break:break-all;'+(l[2]?'background:#fdd;':'color:#555;')+
        '"><span style="color:#888;display:inline-block;min-width:44px">'+l[0]+'</span>'+esc(l[1])+'</div>'}).join('')+'</div>':'';
  p.innerHTML='<div style="margin-top:8px;max-height:50vh;overflow:auto;border-top:1px solid #ddd;padding-top:6px">'+code+
    '<div style="color:#555;margin-bottom:4px">Как в HTML от сервера (так видит поисковик без JavaScript)</div>'+
    '<table style="border-collapse:collapse;font:13px Arial">'+rows.join('')+'</table>'+
    '<div style="color:#555;margin:8px 0 4px">Ошибки JavaScript при загрузке этой копии (на сайте могут быть не все: копия открыта с другого адреса)</div>'+
    '<div id="clayler-code-js"></div></div>';
  fillJs(document.getElementById('clayler-code-js'));p.hidden=false;
  p.querySelectorAll('a[data-copy]').forEach(function(a){a.onclick=function(){copyText(a)}});
  var hit=p.querySelector('tr[style*="outline"]');if(hit)hit.scrollIntoView({block:'nearest'});
}
// ищем после загрузки и первых скриптов сайта: конструкторы (Tilda и др.) сначала прячут блоки, потом рисуют
var started=false;function start(){if(started)return;started=true;setTimeout(mark,800)}
function go(){if(!document.body)return setTimeout(go,100);banner();
  if(document.readyState==='complete')start();else{addEventListener('load',start);setTimeout(start,5000)}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go();
})();"""


def _find_list(raw):
    try:
        got = json.loads(raw or "[]")
    except ValueError:
        got = [raw]
    if isinstance(got, str):
        got = [got]
    out = []
    for s in got if isinstance(got, list) else []:
        s = str(s).strip()
        if s and s != "-" and s not in out:
            out.append(s[:500])
    return out[:MAX_FIND]


def closed(url, own_port=0):
    """Почему адрес не открываем, или "". Этот компьютер (окно программы с отчётами и кнопками, другие программы) и
    локальная сеть недоступны. Имя проверяется отдельно от загрузки: подмену адреса между ними (DNS rebinding)
    это не ловит - для неё нужен сайт злоумышленника, который пользователь сам откроет из отчёта."""
    sp = urlsplit(url)
    if sp.scheme not in ("http", "https") or not sp.hostname:
        return "нужен адрес, начинающийся с http:// или https://"
    try:
        port = sp.port or (443 if sp.scheme == "https" else 80)
        ips = {ipaddress.ip_address(a[4][0].split("%")[0]) for a in socket.getaddrinfo(sp.hostname, port)}
    except (OSError, ValueError):
        return ""   # адрес не нашёлся - это скажет загрузка
    for ip in ips:
        if ip.is_loopback or ip.is_unspecified:
            # на этом компьютере могут работать и другие программы (базы, панели) - их скрипт копии тоже прочитал бы;
            # автотест поднимает свой сайт на 127.0.0.1 и разрешает это переменной
            if port == own_port or 8900 <= port <= 8930 or os.environ.get("CLAYLER_SHOW_LOCAL") != "1":
                return "адреса этого компьютера не открываются"
        elif ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return "адреса локальной сети не открываются"
    return ""


_RECENT, _RECENT_LOCK, RECENT_SEC = {}, threading.Lock(), 60


def _page(url, own_port=0, ua="chrome"):
    """(конечный адрес, HTML, "") или (адрес, None, текст ошибки). Удачный ответ помнится минуту: «компьютер и телефон
    рядом» (frames) скачивает обе версии для сравнения ссылок, а потом их же открывают обе копии (inner=1) - раньше
    это были 4 запроса к сайту клиента вместо 2."""
    key, now = (url, own_port, ua), time.time()
    with _RECENT_LOCK:
        hit = _RECENT.get(key)
        if hit and now - hit[0] < RECENT_SEC:
            return hit[1]
    out = _load_page(url, own_port, ua)
    if out[1] is not None:
        with _RECENT_LOCK:
            for k in [k for k, v in _RECENT.items() if now - v[0] >= RECENT_SEC]:
                del _RECENT[k]
            _RECENT[key] = (now, out)
    return out


def _load_page(url, own_port=0, ua="chrome"):
    f = Fetcher(UA_PRESETS.get(ua) or UA_PRESETS["chrome"])
    try:
        for _ in range(6):
            why = closed(url, own_port)   # и после каждого перенаправления
            if why:
                return url, None, why
            r = f.fetch(url)
            if r.error or not (300 <= r.status < 400) or not r.location:
                break
            url = urljoin(url, r.location)
    finally:
        f.close()
    if r.error or not r.body:
        return url, None, f"страница не открылась: {r.error or r.status}"
    if not r.is_html:
        return url, None, f"это не HTML-страница ({r.content_type or 'тип не указан'})"
    ct = r.headers.get("content-type", "")
    return url, r.body.decode(detect_encoding(r.body, ct)[0], "replace"), ""


def _error_page(url, why):
    link = f'<br><br><a href="{html.escape(url)}">Открыть настоящую страницу</a>' if url.startswith("http") else ""
    return (f'<!doctype html><meta charset="utf-8"><title>Не открылась</title><body style="font:15px Arial;'
            f'padding:24px">Не получилось показать страницу с подсветкой: {html.escape(why)}.{link}</body>')


# проблема отчёта (id строки в отчёт.html) → поле панели «Что в коде», которое обвести
FOCUS = [(re.compile(r"mixed_letters_meta"), "open"),
         (re.compile(r"^text_(nausea|water)"), "words"),   # частые слова - подсветить каждое
         (re.compile(r"^h2_missing"), "text"),   # текст без подзаголовков - обвести блоки текста
         (re.compile(r"^buy_(no_consent|consent_form|consent_nobox)"), "forms"),   # формы - обводим их на странице   # слово в title или description - панель открыта, без обводки
         (re.compile(r"title"), "title"), (re.compile(r"^desc|js_desc|tmpl_meta"), "description"),
         (re.compile(r"canon"), "canonical"), (re.compile(r"h1"), "h1"), (re.compile(r"noindex|robots_meta"), "robots"),
         (re.compile(r"^og_"), "og"), (re.compile(r"hreflang"), "hreflang"), (re.compile(r"lang"), "lang"),
         (re.compile(r"viewport"), "viewport"), (re.compile(r"keywords"), "keywords"),
         (re.compile(r"schema"), "schema")]


def code_rows(doc):
    """[(поле, подпись, [значения])] из HTML страницы - для панели «Что в коде»."""
    from ..parser import parse_html
    p = parse_html(doc.encode("utf-8"), "text/html; charset=utf-8")
    og = p.get("og") or {}
    return [("title", "Title", p.get("titles") or []), ("description", "Description", p.get("descriptions") or []),
            ("canonical", "Canonical", p.get("canonicals") or []),
            ("robots", "Meta robots", [f"{n}: {c}" for n, c in p.get("robots") or []]),
            ("h1", "H1", p.get("h1") or []), ("lang", "Язык (lang)", [p["lang"]] if p.get("lang") else []),
            ("viewport", "Viewport", [p["viewport"]] if p.get("viewport") else []),
            ("hreflang", "Hreflang", [" → ".join(map(str, h)) if isinstance(h, (list, tuple)) else str(h)
                                      for h in (p.get("hreflang") or [])][:20]),
            # главные поля Open Graph - всегда строкой: пустое и отсутствующее видно («(пусто)», «(нет)» - красным)
            ("og", "Open Graph", [f"og:{k}: {og.get('og:' + k, og.get(k)) or '(пусто)'}"
                                  if ("og:" + k) in og or k in og else f"og:{k}: (нет)"
                                  for k in ("title", "description", "image", "url")]
             + [f"{k}: {v}" for k, v in og.items() if k.replace("og:", "") not in ("title", "description", "image", "url")][:8]),
            ("keywords", "Keywords", [p["keywords"]] if p.get("keywords") else []),
            ("schema", "Разметка Schema.org", list(p.get("schema_types") or []))]


class _Where(HTMLParser):
    """Где в коде то, о чём проблема, - по тем же правилам, что parser.py (там проблема и найдена): тег, который
    закрыл <head> раньше времени, повторы id, лишние <html>/<head>/<body>. Позиции - (строка, столбец)."""
    HEAD_OK = {"html", "head", "title", "meta", "link", "script", "style", "base", "noscript", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.head_phase, self.in_noscript, self.seen_head, self.head_closed = True, 0, False, False
        self.head_break = None          # (тег, строка, столбец)
        self.ids, self.roots = {}, {}   # id → [(строка, столбец)], html/head/body → [(строка, столбец)]

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        pos = self.getpos()
        if a.get("id"):
            self.ids.setdefault(a["id"], []).append(pos)
        if tag in ("html", "head", "body"):
            self.roots.setdefault(tag, []).append(pos)
        if tag == "head":
            self.seen_head = True
        if self.head_phase and not self.in_noscript:
            if tag == "body":
                self.head_phase = False
            elif tag not in self.HEAD_OK:
                self.head_phase = False
                if self.seen_head and not self.head_closed and not self.head_break:
                    self.head_break = (tag, *pos)
        if tag == "noscript":
            self.in_noscript += 1

    def handle_endtag(self, tag):
        if tag == "noscript" and self.in_noscript:
            self.in_noscript -= 1
        if tag == "head":
            self.head_closed = True


def _snip(src, line, col, width=220):
    """Строка кода line (с 1) вокруг столбца col: у сжатого HTML строки бывают на тысячи знаков."""
    s = src[line - 1] if 0 < line <= len(src) else ""
    if len(s) <= width:
        return s.strip()
    lo = max(0, col - 60)
    return ("…" if lo else "") + s[lo:lo + width].strip() + "…"


def code_lines(doc, key):
    """Для проблем, которых не видно на странице: {подпись, строки кода с номерами, id для обводки}."""
    key = key or ""
    if not re.search(r"head_invalid|head_broken|html_multi|dup_ids", key):
        return {}
    w = _Where()
    try:
        w.feed(doc)
        w.close()
    except Exception:
        pass
    src = doc.split("\n")
    if "html_multi" in key:
        many = [(t, ps) for t, ps in w.roots.items() if len(ps) > 1]
        if not many:
            return {"title": "В HTML от сервера повторов <html>, <head>, <body> нет", "lines": []}
        return {"title": "Повторяются теги: " + ", ".join(f"<{t}> ×{len(ps)}" for t, ps in many)
                         + ". Лишние - убрать (обычно их вставляет виджет или кусок кода, скопированный целиком).",
                "lines": [(ln, _snip(src, ln, col), True) for _t, ps in many for ln, col in ps[:6]]}
    if "dup_ids" in key:
        dup = sorted(((i, ps) for i, ps in w.ids.items() if len(ps) > 1), key=lambda x: -len(x[1]))[:8]
        if not dup:
            return {"title": "В HTML от сервера одинаковых id нет: их добавляет скрипт", "lines": []}
        return {"title": "Одинаковые id (у каждого должен быть свой): " + ", ".join(
                    f"«{i}» ×{len(ps)}" for i, ps in dup) + ". Ниже - теги с ними и номера строк (Ctrl+U).",
                "lines": [(ln, _snip(src, ln, col), True) for _i, ps in dup for ln, col in ps[:3]],
                "ids": [i for i, _ in dup]}
    # head_invalid, head_broken: тег, после которого браузер считает, что начался <body>
    if not w.head_break:
        return {"title": "В HTML от сервера <head> не обрывается: лишний тег добавляет скрипт при загрузке страницы",
                "lines": []}
    tag, ln, col = w.head_break
    lines = [(k, _snip(src, k, col if k == ln else 0), k == ln) for k in range(max(1, ln - 2), min(len(src), ln + 2) + 1)]
    return {"title": f"Тег <{tag}> в <head> - строка {ln} кода этой страницы (Ctrl+U, затем Ctrl+F). С него браузер считает, что начался "
                     f"<body>: всё, что ниже (canonical, meta robots, стили), уже не в <head>", "lines": lines}


_SUGGEST = {}   # путь к заголовки.csv → (время изменения, {адрес: строка}); у dom-primer.ru 57 тыс. строк - читаем один раз


def suggest_row(url):
    """Оценка и готовые варианты страницы из последней проверки сайта (заголовки.csv, analyze/checks/meta_suggest):
    {"when", "what": [«title: длинный (72 симв.)»…], "title", "description", "h1"} или {}. Для панели «Что в коде»
: кроме «нет» видно и качество существующего, и готовый вариант с кнопкой «Скопировать»."""
    import csv
    import glob
    from . import REPORTS
    sp = urlsplit(url)
    host = (sp.hostname or "").lower()
    if not host:
        return {}
    want = {url.rstrip("/"), url.rstrip("/") + "/"}
    names = {host, host[4:] if host.startswith("www.") else "www." + host}
    if sp.port:   # папка сайта с портом - «127.0.0.1_8787_<дата>»
        names = {f"{n}_{sp.port}" for n in names}
    # только последняя проверка сайта, даже если в ней заголовки.csv нет (suggest_out удаляет файл, когда менять
    # нечего): иначе показалась бы оценка старой проверки для уже исправленных title (ревью)
    folders = sorted((f for n in names for f in glob.glob(os.path.join(REPORTS, glob.escape(n) + "_20*"))
                      if os.path.isfile(os.path.join(f, "crawl.db"))), key=lambda f: os.path.basename(f)[-19:], reverse=True)
    for f in folders[:1]:
        path = os.path.join(f, "заголовки.csv")
        try:
            mt = os.path.getmtime(path)
            got = _SUGGEST.get(path)
            if not got or got[0] != mt:
                with open(path, encoding="utf-8-sig", newline="") as fh:
                    rows = csv.reader(fh, delimiter=";")
                    head = next(rows)
                    got = (mt, {r[0]: dict(zip(head, r)) for r in rows if r})
                if len(_SUGGEST) >= 3:
                    _SUGGEST.clear()
                _SUGGEST[path] = got
        except (OSError, StopIteration, csv.Error):
            continue
        row = next((got[1][u] for u in want if u in got[1]), None)
        if not row:
            return {}
        m = re.search(r"_(\d{4})-(\d\d)-(\d\d)_", os.path.basename(f))
        out = {"when": f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else "",
               "what": [s.strip() for s in (row.get("Что не так") or "").split(";") if s.strip()]}
        for k, col, now in (("title", "Предлагаю title", "Title сейчас"),
                            ("description", "Предлагаю description", "Description сейчас"),
                            ("h1", "Предлагаю H1", "H1 сейчас")):
            v = (row.get(col) or "").strip()
            if v and v != (row.get(now) or "").strip():
                out[k] = v
        return out
    return {}


def render(url, find_raw, own_port=0, key="", title="", ua="chrome", det="", shot=False):
    """HTML копии страницы с подсветкой. url - адрес страницы сайта, find_raw - JSON-список того, что обвести,
    own_port - порт окна программы (его страницы не открываем), key - проблема из отчёта (какое поле кода обвести)."""
    url, doc, err = _page(url or "", own_port, ua)
    if doc is None:
        return _error_page(url, err)
    try:
        code = code_rows(doc)
        lines = code_lines(doc, key)   # строки кода с номерами - для того, чего не видно на странице
    except Exception:   # панель - дополнение, копия страницы важнее
        code, lines = [], {}
    try:
        meta = suggest_row(url)
    except Exception:
        meta = {}
    focus = next((f for rx, f in FOCUS if rx.search(key or "")), "") or ("lines" if lines else "")
    m = re.search(r"<base\b[^>]*\bhref\s*=\s*[\"']?([^\"'\s>]+)", doc, re.I)
    base = urljoin(url, html.unescape(m.group(1))) if m else url
    doc = re.sub(r"<base\b[^>]*>", "", doc, flags=re.I)
    # своя политика безопасности страницы запретила бы наш скрипт; на копии она не нужна
    doc = re.sub(r"<meta\b[^>]*http-equiv\s*=\s*[\"']?content-security-policy[^>]*>", "", doc, flags=re.I)
    # одной подстановкой: «__FOCUS__» в title страницы не должен подставиться второй раз и сломать скрипт
    from ..problem_shots import KINDS, MARK_JS as SHOT_JS
    use_shot = key in KINDS and (shot or (KINDS[key][0] == "mobile" and not _find_list(find_raw)))
    if use_shot:
        focus = "shot"
    vals = {"__FIND__": _find_list(find_raw), "__URL__": url, "__CODE__": code, "__FOCUS__": focus, "__LINES__": lines,
            "__TITLE__": (title or "")[:200], "__KEY__": key or "", "__DET__": (det or "")[:400], "__META__": meta}
    shot_js = "(" + (SHOT_JS if use_shot else "function(){return {n:0,top:null}}") + ")"   # код, а не данные
    js = re.sub(r"__(?:FIND|URL|CODE|FOCUS|LINES|TITLE|KEY|DET|SHOT|META)__",
                lambda m: shot_js if m.group(0) == "__SHOT__" else json.dumps(vals[m.group(0)], ensure_ascii=False),
                MARK_JS).replace("</", "<\\/")
    head = f'<base href="{html.escape(base)}"><script>{js}</script>'
    m = re.search(r"<head\b[^>]*>", doc, re.I)
    if m:
        return doc[:m.end()] + head + doc[m.end():]
    m = re.search(r"<html\b[^>]*>", doc, re.I)
    at = m.end() if m else 0
    return doc[:at] + "<head>" + head + "</head>" + doc[at:]


PHONE_W = 390   # ширина экрана телефона в копии (как в снимках телефона)


def _own_links(doc, url, final):
    """{путь?параметры: адрес} ссылок на свой сайт. Свой - сайт проверки и сайт, куда привело (у телефона бывает
    m.site.ru): у отдельной мобильной версии ссылки на m.site.ru/catalog/ - это те же разделы, что site.ru/catalog/."""
    from ..parser import parse_html
    from .. import urls as U

    def bare(u):
        h = (urlsplit(u).hostname or "").removeprefix("www.")
        return h.removeprefix("m.") if h.startswith("m.") else h
    own = {bare(url), bare(final)}
    out = {}
    for lk in parse_html(doc.encode("utf-8"), "text/html; charset=utf-8").get("links") or []:
        n = U.normalize(lk.get("href") or "", final)
        if lk.get("kind") == "a" and n and bare(n) in own:
            sp = urlsplit(n)
            out.setdefault(sp.path.rstrip("/") + ("?" + sp.query if sp.query else ""), n)
    return out


def frames(url, find_raw, own_port, key, title, both, det=""):
    """Копия «как на телефоне» (ширина 390 px, User-Agent телефона) или «компьютер и телефон рядом» (mobile_diff):
    в копии компьютера обведены ссылки, которых нет у телефона, в копии телефона - которых нет у компьютера."""
    from urllib.parse import urlencode
    if closed(url or "", own_port):
        return _error_page(url or "", closed(url or "", own_port))
    base = {"url": url, "key": key, "t": title, "inner": "1"}
    note = ""
    src_pc = src_ph = ""
    if both:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(2) as ex:   # обе версии сразу, а не по очереди
            (u1, pc, _e1), (u2, ph, _e2) = ex.map(lambda ua: _page(url, own_port, ua), ("chrome", "phone"))
        a, b = (_own_links(pc, url, u1) if pc else {}), (_own_links(ph, url, u2) if ph else {})
        only_pc, only_ph = [a[k] for k in a.keys() - b.keys()], [b[k] for k in b.keys() - a.keys()]
        shown = lambda n: f"{n}" + (" (обведены первые 12)" if n > 12 else "")  # noqa: E731
        note = (f"Ссылок на свой сайт: у компьютера {len(a)}, у телефона {len(b)}"
                + (f" (телефон открывает {urlsplit(u2).hostname})" if pc and ph and urlsplit(u1).hostname != urlsplit(u2).hostname else "")
                + f". Обведены те, что есть только в одной версии: только у компьютера - {shown(len(only_pc))}, "
                  f"только у телефона - {shown(len(only_ph))}.")
        src_pc = "/api/show?" + urlencode(dict(base, find=json.dumps(only_pc[:12])))
        src_ph = "/api/show?" + urlencode(dict(base, find=json.dumps(only_ph[:12]), ua="phone"))
    else:
        src_ph = "/api/show?" + urlencode(dict(base, find=find_raw or "[]", ua="phone"))
    e = html.escape
    pc_frame = (f'<div class="f"><div class="h">Компьютер</div><iframe src="{e(src_pc)}" style="width:100%"></iframe></div>'
                if both else "")
    return (f'<!doctype html><meta charset="utf-8"><title>{e(title or "Копия страницы")}</title>'
            '<style>body{margin:0;font:14px Arial,sans-serif;background:#eef0f3;color:#111}'
            '.top{padding:10px 16px;background:#fff;border-bottom:2px solid #e00}.w{display:flex;gap:16px;padding:12px;'
            'align-items:flex-start}.f{flex:1;min-width:0}.f.p{flex:0 0 auto}.h{font-weight:bold;margin:0 0 6px}'
            'iframe{height:calc(100vh - 140px);border:1px solid #ccc;background:#fff;border-radius:6px}</style>'
            f'<div class="top"><b>Clayler SEO</b> · {e("Проблема: " + title) if title else "копия страницы"}'
            + (f'<div style="color:#555">Строка отчёта - {e(det)}</div>' if det else "") +
            f'{e(note) if note else "Так страницу видит телефон (ширина " + str(PHONE_W) + " px, браузер телефона)."} '
            f'<a href="{e(url)}" target="_top">Открыть настоящую страницу</a></div>'
            f'<div class="w">{pc_frame}<div class="f p"><div class="h">Телефон</div>'
            f'<iframe src="{e(src_ph)}" style="width:{PHONE_W}px"></iframe></div></div>')
