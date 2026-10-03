"""Fail closed on unexpected tracked files, private paths, secrets, or broken assets."""
import argparse
import base64
import hashlib
import ipaddress
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ALLOWED_ROOT={'.gitignore','README.md','requirements.txt','Export Wiki.cmd','Publish Wiki.cmd'}
ALLOWED_TOOLS={'tools/export_wiki.py','tools/security_check.py','tools/publish.ps1','tools/export.ps1'}
ALLOWED_HOOKS={'.githooks/pre-commit','.githooks/pre-push'}
SITE_EXT={'.html','.css','.js','.json','.png','.jpg','.jpeg','.svg','.pdf','.gif','.webp','.woff','.woff2','.ttf','.ico'}
TEXT_EXT={'.html','.css','.js','.json','.svg','.md','.txt','.py','.ps1','.cmd'}
PATH_PATTERN=re.compile(r'(?i)(?:(?<![\w])[a-z]:[\\/](?!/)[^\s<>"\'|\]\[{}]+|file:[/][/][A-Za-z0-9][^\s<>"\']*|/(?:home|Users)/[A-Za-z0-9_.-]+/|\\\\[A-Za-z0-9_.-]+\\)')
SECRET_PATTERN=re.compile(r'(?i)(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
PRIVATE_HOST=re.compile(r'(?i)(?:https?:)?//(?:localhost|127\.0\.0\.1|0\.0\.0\.0|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?=[:/\s"\'])')
privacy=json.loads((ROOT/'.local/privacy.json').read_text(encoding='utf-8'))
PRIVATE_TERMS=[rule['term'] for rule in privacy['redactions']]
if not PRIVATE_TERMS or any(not isinstance(term,str) or not term for term in PRIVATE_TERMS):
    raise ValueError('Configure private redaction terms in .local/privacy.json before checking.')
PRIVATE_MARKERS={value.casefold() for term in PRIVATE_TERMS for value in (term,term.encode().hex(),base64.b64encode(term.encode()).decode())}
ARCHIVE_PATH=re.compile(r'(?i)(?:source-archive|research)[/\\][A-Za-z0-9_.-]+')

def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--staged',action='store_true'); parser.add_argument('--ref'); parser.add_argument('--working',action='store_true'); args=parser.parse_args()
    if args.staged:
        names=git('ls-files','-z').decode().split('\0')
        get=lambda name:git('show',':'+name)
    elif args.ref:
        names=git('ls-tree','-r','--name-only','-z',args.ref).decode().split('\0')
        get=lambda name:git('show',args.ref+':'+name)
    else:
        names=[p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and not any(part in {'.git','.local','__pycache__'} for part in p.relative_to(ROOT).parts) and p.name!='AGENTS.md']
        get=lambda name:(ROOT/name).read_bytes()
    names=sorted(n for n in names if n); errors=[]; inventory=[]; site={}
    for name in names:
        allowed=name in ALLOWED_ROOT|ALLOWED_TOOLS|ALLOWED_HOOKS or (name.startswith('docs/') and (Path(name).suffix in SITE_EXT or name=='docs/.nojekyll'))
        if not allowed: errors.append({'file':name,'reason':'not in publication allowlist'});continue
        raw=get(name); inventory.append({'file':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        if len(raw)>100*1024**2: errors.append({'file':name,'reason':'exceeds regular Git file limit'})
        if name.startswith('docs/'): site[name]=raw
        if Path(name).suffix in TEXT_EXT:
            text=raw.decode('utf-8',errors='replace')
            variants=[text,urllib.parse.unquote(urllib.parse.unquote(text)),text.replace('\\\\','\\'),text.replace('\\u005c','\\').replace('\\u002f','/')]
            if any(PATH_PATTERN.search(v) for v in variants): errors.append({'file':name,'reason':'computer file path'})
            if any(marker in v.casefold() for v in variants for marker in PRIVATE_MARKERS): errors.append({'file':name,'reason':'private term or encoded private term'})
            if name.startswith('docs/') and ARCHIVE_PATH.search(text): errors.append({'file':name,'reason':'private archive path'})
            if SECRET_PATTERN.search(text): errors.append({'file':name,'reason':'credential or private key'})
            if name.startswith('docs/') and PRIVATE_HOST.search(text): errors.append({'file':name,'reason':'private network or local-server URL'})
            if name.endswith('.map'): errors.append({'file':name,'reason':'source map'})
        if name.startswith('docs/') and Path(name).suffix in {'.png','.jpg','.jpeg','.webp'}:
            from PIL import Image
            import io
            im=Image.open(io.BytesIO(raw))
            if im.getexif() or any(k in im.info for k in ('exif','xmp','XML:com.adobe.xmp','Comment','comment','Description','Author','Software')):
                errors.append({'file':name,'reason':'image metadata not stripped'})
        if name.endswith('.pdf'):
            import fitz
            doc=fitz.open(stream=raw,filetype='pdf')
            if any(doc.metadata.get(k) for k in ('title','author','subject','keywords','creator','producer','creationDate','modDate')) or doc.get_xml_metadata() or doc.embfile_count():
                errors.append({'file':name,'reason':'PDF metadata or attachment'})
            for p in doc:
                if PATH_PATTERN.search(p.get_text()) or any(marker in p.get_text().casefold() for marker in PRIVATE_MARKERS): errors.append({'file':name,'reason':'private term or computer path in PDF text'})
                for link in p.get_links():
                    if link.get('kind') in (fitz.LINK_LAUNCH,fitz.LINK_GOTOR) or PATH_PATTERN.search(link.get('uri','')):
                        errors.append({'file':name,'reason':'local PDF link'})
    from bs4 import BeautifulSoup
    def check_url(file,url):
        if url.startswith(('#','data:','mailto:','https://','http://','//')): return
        parts=urllib.parse.urlsplit(url)
        if parts.scheme: errors.append({'file':file,'reason':'unsupported link scheme'});return
        if not parts.path: return
        # The exported site uses relative links so it works below the project URL.
        if parts.path.startswith('/'):
            errors.append({'file':file,'reason':'root-relative link'});return
        from posixpath import normpath,join,dirname
        target=normpath(join(dirname(file),urllib.parse.unquote(parts.path)))
        if target not in site: errors.append({'file':file,'reason':'missing asset/page','target':target})
    for name,raw in site.items():
        if name.endswith('.html'):
            soup=BeautifulSoup(raw,'html.parser')
            for el in soup.select('[href], [src], [srcset]'):
                for attr in ('href','src'):
                    if el.get(attr): check_url(name,el[attr])
                if el.get('srcset'):
                    for item in el['srcset'].split(','): check_url(name,item.strip().split()[0])
            for el in soup.select('script'):
                if el.get('src')!='assets/static.js' or el.string: errors.append({'file':name,'reason':'unapproved script'})
            for el in soup.find_all(True):
                if any(k.startswith('on') for k in el.attrs): errors.append({'file':name,'reason':'inline event script'})
        elif name.endswith('.css'):
            for url in re.findall(r'url\(([^)]+)\)',raw.decode('utf-8')): check_url(name,url.strip(' \t\r\n\"\''))
    site_bytes=sum(map(len,site.values()))
    if site_bytes>=1_000_000_000: errors.append({'reason':'site exceeds conservative 1 GB Pages limit'})
    if 'docs/index.html' not in site or 'docs/assets/search-index.json' not in site: errors.append({'reason':'missing required entry files'})
    report={'passed':not errors,'files':len(inventory),'site_bytes':site_bytes,'html_pages':sum(n.endswith('.html') for n in site),'errors':errors,'inventory':inventory}
    (ROOT/'.local').mkdir(exist_ok=True)
    (ROOT/'.local/security-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='inventory'},indent=2))
    return 0 if not errors else 1

if __name__=='__main__': sys.exit(main())
