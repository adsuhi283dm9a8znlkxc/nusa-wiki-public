/* Reading features for the static Vector edition. No analytics or server API calls. */
(()=>{'use strict';
const root=document.documentElement;
let searchData;
const getIndex=()=>searchData||(searchData=fetch('assets/search-index.json').then(r=>{if(!r.ok)throw Error('Search unavailable');return r.json()}));
function preference(name,value){
 const prefix={text:'vector-feature-custom-font-size-clientpref-',width:'vector-feature-limited-width-clientpref-',color:'skin-theme-clientpref-'}[name];
 [...root.classList].filter(c=>c.startsWith(prefix)).forEach(c=>root.classList.remove(c));
 root.classList.add(prefix+value);
 try{localStorage.setItem('static-wiki-'+name,value)}catch(e){}
}
for(const name of ['text','width','color']){try{const value=localStorage.getItem('static-wiki-'+name);if(value)preference(name,value)}catch(e){}}
const appearance=document.querySelector('#vector-appearance');
if(appearance){
 appearance.innerHTML='<div class="vector-pinnable-header"><div class="vector-pinnable-header-label">Appearance</div></div><fieldset><legend>Text</legend><label><input type="radio" name="static-text" value="0"> Small</label><br><label><input type="radio" name="static-text" value="1" checked> Standard</label><br><label><input type="radio" name="static-text" value="2"> Large</label></fieldset><fieldset><legend>Width</legend><label><input type="radio" name="static-width" value="1" checked> Standard</label><br><label><input type="radio" name="static-width" value="0"> Wide</label></fieldset><fieldset><legend>Color</legend><label><input type="radio" name="static-color" value="day" checked> Light</label><br><label><input type="radio" name="static-color" value="night"> Dark</label></fieldset>';
 appearance.querySelectorAll('input').forEach(input=>{const name=input.name.replace('static-','');try{if(localStorage.getItem('static-wiki-'+name)===input.value)input.checked=true}catch(e){}input.addEventListener('change',()=>preference(name,input.value))});
}
// MediaWiki renders menu checkboxes; preserve their accessible native behavior.
document.querySelectorAll('.vector-toc-collapse-button,.vector-toc-toggle').forEach(button=>button.addEventListener('click',()=>{
 const item=button.closest('li');const list=item&&item.querySelector('ul');if(list){const expanded=!item.classList.contains('vector-toc-list-item-expanded');item.classList.toggle('vector-toc-list-item-expanded',expanded);list.hidden=!expanded;button.setAttribute('aria-expanded',String(expanded))}
}));
const toc=document.querySelector('#vector-toc');const tocHome=toc&&toc.parentElement;
const mobileToc=document.querySelector('#vector-page-titlebar-toc-checkbox');
if(toc&&mobileToc){mobileToc.addEventListener('change',()=>{const popup=mobileToc.closest('.vector-dropdown').querySelector('.vector-dropdown-content');if(mobileToc.checked&&popup)popup.append(toc);else tocHome.append(toc)});toc.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{if(mobileToc.checked){mobileToc.checked=false;tocHome.append(toc)}}))}
document.querySelectorAll('.vector-pinnable-header-toggle-button').forEach(button=>button.addEventListener('click',()=>{
 const panel=button.closest('#vector-toc,#vector-main-menu,#vector-appearance');if(!panel)return;
 const inner=[...panel.children].filter(el=>!el.classList.contains('vector-pinnable-header'));
 const hide=!inner.every(el=>el.hidden);inner.forEach(el=>el.hidden=hide);button.textContent=hide?'show':'hide';
}));
document.querySelectorAll('.mw-collapsible').forEach(box=>{
 const content=box.querySelector('.mw-collapsible-content');if(!content)return;
 const button=document.createElement('button');button.className='mw-collapsible-toggle';button.textContent='hide';button.type='button';button.setAttribute('aria-expanded','true');
 button.addEventListener('click',()=>{content.hidden=!content.hidden;button.textContent=content.hidden?'show':'hide';button.setAttribute('aria-expanded',String(!content.hidden))});box.prepend(button);
});
const results=document.querySelector('#static-search-results');
if(results){
 const query=new URLSearchParams(location.search).get('q')||'';
 document.querySelectorAll('input[name=q]').forEach(el=>el.value=query);
 const status=document.createElement('p');status.textContent=query?'Searching…':'Use the search box to find a wiki page.';results.append(status);
 if(query)getIndex().then(index=>{
 const terms=query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
 const hits=index.map(p=>({...p,score:terms.reduce((score,t)=>score+(p.title.toLocaleLowerCase().includes(t)?10:0),0)})).filter(p=>terms.every(t=>(p.title+' '+p.text).toLocaleLowerCase().includes(t))).sort((a,b)=>b.score-a.score).slice(0,100);
 status.textContent=hits.length+' results for “'+query+'”';
 for(const hit of hits){const box=document.createElement('div');box.className='static-search-item';const a=document.createElement('a');a.href=hit.url;a.textContent=hit.title;const h=document.createElement('h3');h.append(a);const excerpt=document.createElement('p');const start=Math.max(0,hit.text.toLocaleLowerCase().indexOf(terms[0])-70);excerpt.textContent=hit.text.slice(start,start+260)+'…';box.append(h,excerpt);results.append(box)}
 }).catch(()=>status.textContent='Search could not load. Please try again.');
}
let timer,preview;
function clearPreview(){clearTimeout(timer);if(preview){preview.remove();preview=null}}
document.querySelectorAll('.mw-parser-output a[href^="page-"]').forEach(link=>{
 link.addEventListener('mouseenter',()=>{timer=setTimeout(async()=>{const index=await getIndex();const page=index.find(p=>p.url===link.getAttribute('href').split('#')[0]);if(!page||!link.matches(':hover'))return;clearPreview();preview=document.createElement('div');preview.className='static-preview';const title=document.createElement('strong');title.textContent=page.title;const text=document.createElement('span');text.textContent=page.text.slice(0,240)+'…';preview.append(title,text);document.body.append(preview);const rect=link.getBoundingClientRect();preview.style.left=Math.max(8,Math.min(rect.left,innerWidth-350))+'px';preview.style.top=Math.max(8,Math.min(rect.bottom+8,innerHeight-preview.offsetHeight-8))+'px'},450)});
 link.addEventListener('mouseleave',clearPreview);link.addEventListener('focusout',clearPreview);
});
window.addEventListener('scroll',clearPreview,{passive:true});
})();
