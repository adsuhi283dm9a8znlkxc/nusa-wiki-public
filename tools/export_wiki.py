"""Export rendered MediaWiki pages and their assets, never its database or sources."""
import concurrent.futures
import hashlib
import io
import ipaddress
import json
import re
import shutil
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from PIL import Image
import fitz

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'docs'
LOCAL = ROOT / '.local'
BASE = 'http://localhost:8081/'
ASSETS = SITE / 'assets'
lock = threading.RLock()
asset_map = {}
redactions = []
bad_path = re.compile(r'(?i)(?:(?<![\w])[a-z]:[\\/](?!/)(?:[^\s<>"\'|\]\[{}]+)|file:[/][/][A-Za-z0-9][^\s<>"\']*|/(?:home|Users)/[^\s<>"\']+)')

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent':'nUSA-static-export/1.0'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read(), r.headers.get_content_type()

def api(**params):
    return json.loads(fetch(BASE+'api.php?'+urllib.parse.urlencode(dict(params,format='json')))[0])

def local_url(url):
    p=urllib.parse.urlsplit(urllib.parse.urljoin(BASE,url))
    if p.hostname in ('localhost','127.0.0.1'): return True
    try: return ipaddress.ip_address(p.hostname).is_private
    except ValueError: return False

def canonical(url):
    p=urllib.parse.urlsplit(urllib.parse.urljoin(BASE,url))
    return urllib.parse.urlunsplit(('http','localhost:8081',p.path,p.query,''))

def scrub(text, label):
    def replace(m):
        redactions.append({'file':label,'kind':'computer-path','value':m.group(0)})
        return '[local archive]'
    text=bad_path.sub(replace,text)
    text=re.sub(r'(?i)(?:source-archive|research)[/\\][^\s<>"\'|]+','[archived source]',text)
    private_name=json.loads((ROOT/'.local/privacy.json').read_text(encoding='utf-8'))['redactions'][-1]['term']
    text=re.sub('Dork'+private_name,'[name withheld]',text,flags=re.I)
    return re.sub(private_name,'J.',text,flags=re.I)

def asset(url):
    url=canonical(url)
    with lock:
        if url in asset_map: return asset_map[url]
        raw,mime=fetch(url)
        ext={'text/css':'.css','application/javascript':'.js','text/javascript':'.js','image/png':'.png','image/jpeg':'.jpg','image/svg+xml':'.svg','application/pdf':'.pdf','image/gif':'.gif','image/webp':'.webp','font/woff2':'.woff2','font/woff':'.woff','application/font-woff':'.woff'}.get(mime)
        if not ext:
            ext=Path(urllib.parse.urlsplit(url).path).suffix.lower()
        if ext not in {'.css','.png','.jpg','.jpeg','.svg','.pdf','.gif','.webp','.woff','.woff2','.ttf','.ico'}:
            raise ValueError('Unapproved asset type: '+mime+' '+url)
        name=hashlib.sha256(url.encode()).hexdigest()[:24]+ext
        asset_map[url]='assets/'+name
        if ext=='.css':
            css=raw.decode('utf-8')
            def cssurl(m):
                value=m.group(1).strip(' \t\r\n\"\'')
                if value.startswith(('data:','#')): return m.group(0)
                target=urllib.parse.urljoin(url,value)
                if not local_url(target): raise ValueError('External CSS asset '+target)
                return 'url('+Path(asset(target)).name+')'
            css=re.sub(r'url\(([^)]+)\)',cssurl,css)
            css=re.sub(r'/\*#?\s*sourceMappingURL=.*?\*/','',css)
            raw=scrub(css,name).encode()
        elif ext in ('.png','.jpg','.jpeg','.webp'):
            im=Image.open(io.BytesIO(raw)); out=io.BytesIO()
            im.save(out,format={'PNG':'PNG','JPEG':'JPEG','WEBP':'WEBP'}[im.format],**({'quality':95} if im.format in ('JPEG','WEBP') else {}))
            raw=out.getvalue()
        elif ext=='.pdf':
            doc=fitz.open(stream=raw,filetype='pdf')
            for i,page in enumerate(doc):
                if bad_path.search(page.get_text()):
                    raise ValueError('Computer path in PDF content, requires review: '+name+' page '+str(i+1))
                for link in page.get_links():
                    if link.get('kind') in (fitz.LINK_LAUNCH,fitz.LINK_GOTOR) or bad_path.search(link.get('uri','')):
                        page.delete_link(link)
            doc.set_metadata({}); doc.del_xml_metadata()
            raw=doc.tobytes(garbage=4,deflate=True); doc.close()
        elif ext=='.svg':
            xml=raw.decode('utf-8')
            if re.search(r'<script|\bon\w+\s*=',xml,re.I): raise ValueError('Executable SVG '+name)
            raw=scrub(xml,name).encode()
        (ASSETS/name).write_bytes(raw)
        return 'assets/'+name

def title_key(s): return s.replace('_',' ').strip()

def main():
    global SITE, ASSETS
    # Build privately first; never carry old assets into a new published export.
    published=ROOT/'docs'; staging=LOCAL/'export-staging'; previous=LOCAL/'previous-export'
    for folder in (staging,previous):
        if folder.resolve().parent != LOCAL.resolve(): raise ValueError('Unsafe export directory')
    if staging.exists(): shutil.rmtree(staging)
    (staging/'assets').mkdir(parents=True)
    for filename in ('static.css','static.js'):
        shutil.copy2(published/'assets'/filename,staging/'assets'/filename)
    SITE=staging; ASSETS=staging/'assets'
    ASSETS.mkdir(parents=True,exist_ok=True); LOCAL.mkdir(exist_ok=True)
    ns=api(action='query',meta='siteinfo',siprop='namespaces')['query']['namespaces']
    pages=[]
    for n in ns.values():
        if n['id']<0: continue
        p=dict(action='query',list='allpages',apnamespace=n['id'],aplimit='max')
        while True:
            r=api(**p); pages.extend(r['query']['allpages'])
            if 'continue' not in r: break
            p.update(r['continue'])
    files={title_key(p['title']):('index.html' if p['title']=='Main Page' else 'page-'+str(p['pageid'])+'.html') for p in pages}
    index=[]
    def export(p):
        title=p['title']; name=files[title_key(title)]
        html=fetch(BASE+'index.php?'+urllib.parse.urlencode({'title':title}))[0].decode('utf-8')
        soup=BeautifulSoup(html,'html.parser')
        for el in soup.select('script, .printfooter, meta[property^="og:"], link[rel="EditURI"], link[rel="search"], link[rel="alternate"], meta[property="mw:pageId"], #p-personal, #p-vector-user-menu-preferences, #p-vector-user-menu-userpage, #p-vector-user-menu-notifications, #p-vector-user-menu-overflow, #vector-user-links-dropdown, #p-views, #p-cactions, #p-tb, #vector-page-tools-dropdown, #vector-page-tools-pinned-container'):
            el.decompose()
        for comment in soup.find_all(string=lambda x:isinstance(x,Comment)): comment.extract()
        for el in soup.select('[href]'):
            href=el['href']
            if href.startswith('#'): continue
            if href.startswith(('file:','javascript:')):
                el.attrs.pop('href',None); continue
            if not local_url(href):
                el['href']=scrub(href,name); continue
            u=urllib.parse.urlsplit(urllib.parse.urljoin(BASE,href)); q=urllib.parse.parse_qs(u.query)
            if el.name=='link' and ('stylesheet' in el.get('rel',[]) or 'icon' in el.get('rel',[])):
                el['href']=asset(href); continue
            t=q.get('title',[None])[0]
            if t is None and u.path.startswith('/index.php/'):
                t=urllib.parse.unquote(u.path[len('/index.php/'):])
            if t is None and u.path.startswith('/wiki/'):
                t=urllib.parse.unquote(u.path[len('/wiki/'):])
            if t is None and u.path in ('/','/index.php'): t='Main Page'
            if u.path.startswith(('/images/','/resources/','/skins/')):
                el['href']=asset(href); continue
            target=files.get(title_key(t or ''))
            if title_key(t or '')=='Special:AllPages': target='all-pages.html'
            if target and not any(k in q for k in ('action','diff','oldid')):
                el['href']=target+('#'+u.fragment if u.fragment else '')
                el.attrs.pop('data-mw',None)
            else:
                el.attrs.pop('href',None); el['aria-disabled']='true'; el['title']='Unavailable in the static edition'
        for el in soup.select('[src]'):
            if local_url(el['src']): el['src']=asset(el['src'])
        for el in soup.select('[srcset]'):
            items=[]
            for item in el['srcset'].split(','):
                parts=item.strip().split()
                if not parts: continue
                if local_url(parts[0]): parts[0]=asset(parts[0])
                items.append(' '.join(parts))
            el['srcset']=', '.join(items)
        for el in soup.find_all(True):
            for key in list(el.attrs):
                if key.startswith('on') or key in ('data-mw','data-parsoid'): del el.attrs[key]
        for form in soup.select('form'):
            form['action']='search.html'; form['method']='get'
            for hidden in form.select('input[type="hidden"]'): hidden.decompose()
            for inp in form.select('input[type="search"], input[name="search"]'): inp['name']='q'
        for toggle in soup.select('.search-toggle'):
            toggle['href']='search.html'; toggle.attrs.pop('aria-disabled',None);toggle['title']='Search nUSA Wiki'
        # Keep Vector's rendered class settings, without server-dependent startup code.
        classes=soup.html.get('class',[])
        soup.html['class']=[('client-js' if c=='client-nojs' else c) for c in classes]
        for div in soup.select('.mw-collapsible'): div['class']=[c for c in div.get('class',[]) if c!='mw-collapsed']
        footer=soup.select_one('#footer-info')
        if footer:
            li=soup.new_tag('li'); li.string='Static edition — browsing and search available; editing remains on the source wiki.'; footer.append(li)
        extra=soup.new_tag('link',rel='stylesheet',href='assets/static.css'); soup.head.append(extra)
        js=soup.new_tag('script',src='assets/static.js',defer=''); soup.body.append(js)
        content=soup.select_one('.mw-parser-output')
        text=content.get_text(' ',strip=True) if content else title
        rendered=scrub(str(soup),name)
        (SITE/name).write_text(rendered,encoding='utf-8')
        with lock: index.append({'title':title,'url':name,'text':scrub(text,name)[:35000]})
        return name
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i,name in enumerate(pool.map(export,pages),1):
            if i%25==0: print('Rendered',i,'/',len(pages),flush=True)
    # Include all registered uploads, even when an original is only linked from its file page.
    params=dict(action='query',list='allimages',ailimit='max',aiprop='url')
    while True:
        result=api(**params)
        for item in result['query']['allimages']: asset(item['url'])
        if 'continue' not in result: break
        params.update(result['continue'])
    index.sort(key=lambda x:x['title'])
    (ASSETS/'search-index.json').write_text(json.dumps(index,ensure_ascii=False),encoding='utf-8')
    template=BeautifulSoup((SITE/'index.html').read_text(encoding='utf-8'),'html.parser')
    template.title.string='Search — nUSA Wiki'
    template.select_one('#firstHeading').string='Search'
    main=template.select_one('#mw-content-text'); main.clear()
    form=template.new_tag('form',action='search.html',method='get')
    inp=template.new_tag('input',type='search',name='q',placeholder='Search nUSA Wiki')
    inp['aria-label']='Search nUSA Wiki';button=template.new_tag('button',type='submit');button.string='Search';form.append(inp);form.append(button);main.append(form)
    div=template.new_tag('div',id='static-search-results'); main.append(div)
    (SITE/'search.html').write_text(str(template),encoding='utf-8')
    template.title.string='All pages — nUSA Wiki'
    template.select_one('#firstHeading').string='All pages'
    main=template.select_one('#mw-content-text'); main.clear()
    ul=template.new_tag('ul')
    for item in index:
        li=template.new_tag('li'); a=template.new_tag('a',href=item['url']); a.string=item['title'];li.append(a);ul.append(li)
    main.append(ul)
    (SITE/'all-pages.html').write_text(str(template),encoding='utf-8')
    (SITE/'404.html').write_text('<!doctype html><meta charset="utf-8"><title>Page unavailable</title><h1>Page unavailable</h1><p>This page is not in the static wiki.</p><a href="index.html">Main Page</a>',encoding='utf-8')
    (SITE/'.nojekyll').write_text('')
    report={'pages':len(pages),'asset_count':len(asset_map),'asset_map':asset_map,'redactions':redactions,'files':files}
    (LOCAL/'export-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    if previous.exists(): shutil.rmtree(previous)
    published.rename(previous)
    try: staging.rename(published)
    except Exception:
        previous.rename(published)
        raise
    print('Export finished:',len(pages),'pages;',len(asset_map),'assets;',len(redactions),'path redactions',flush=True)

if __name__=='__main__': main()
