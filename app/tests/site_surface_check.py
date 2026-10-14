"""Check complete HTML inventory, reader routes, and the single qualification entry.

Historical source captures and pinned computation owners retain their original text.
Active presentation is edited through its template or component owner.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, re, subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
ROOT=Path(__file__).resolve().parents[2]
INVENTORY=ROOT/'app/site-surfaces.json'
GENERATED={'index.html':'app/source/index.template.html','app/Cantos.html':'app/source/index.template.html',
 'compute/index.html':'compute/template.html','compute/results.html':'compute/community/template.html',
 'compute/capacity/index.html':'compute/capacity/template.html',
 'clustermax-challenge/README.html':'clustermax-challenge/README.md',
 'clustermax-challenge/SUBMITTING.html':'clustermax-challenge/SUBMITTING.md'}
PINNED={'research-desk/app.html','compute/adapters/workload-report-v2.html','hot-aisle/index.html'}
def paths():
    output=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','*.html'],cwd=ROOT,encoding='utf-8')
    return sorted(set(output.splitlines()))
def role(path):
    if '/fixtures/' in path or path.startswith('evidence/'):return 'retained-source-or-fixture',None
    if '/raw/' in path:return 'retained-source-capture',None
    if path.startswith('compute/community/r/'):return 'generated-result-view','compute/community/cli.cjs'
    if path in GENERATED:return 'generated-current-page',GENERATED[path]
    if path in PINNED:return 'pinned-native-owner',path
    if any(p in path for p in ['/intake/','/retrospective/','/launch/','/research/round2/','/examples/','/data/demo/','/data/run3/']) or path=='hot-aisle/campaign/results/receipt-run3.html':return 'retained-study-or-example',None
    if 'template.html' in path or path.endswith('page.html'):return 'presentation-source',path
    return 'current-page',path
class HTML(HTMLParser):
    def __init__(self):super().__init__();self.skip=0;self.words=[];self.links=[];self.site_links=set();self.title=False;self.title_words=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ['script','style','svg']:self.skip+=1
        if tag=='title' and not self.skip:self.title=True
        if not self.skip and tag=='a' and 'href' in a:
            self.links.append(a['href'])
            if 'data-site-path' in a:self.site_links.add(a['href'])
    def handle_endtag(self,tag):
        if tag in ['script','style','svg'] and self.skip:self.skip-=1
        if tag=='title':self.title=False
    def handle_data(self,data):
        if not self.skip:
            self.words.append(data)
            if self.title:self.title_words.append(data)
def inventory():
    entries=[]
    for rel in paths():
        p=ROOT/rel;h=HTML();h.feed(p.read_text(encoding='utf-8'));r,owner=role(rel)
        entries.append({'path':rel,'role':r,'owner':owner,'title':' '.join(h.title_words).strip(),
                        'visible_characters':len(' '.join(h.words)),'linked_targets':len(h.links)})
    return {'scope':'Every tracked or candidate HTML surface, from document title through visible body; source snapshots and native identities are preserved.',
            'pages':entries,'counts':dict(collections.Counter(x['role'] for x in entries))}
def check():
    m=json.loads(INVENTORY.read_text(encoding='utf-8'))
    if {p['path'] for p in m['pages']}!=set(paths()):raise AssertionError('HTML inventory differs; classify the added or removed surface')
    if (ROOT/'index.html').read_bytes()!=(ROOT/'app/Cantos.html').read_bytes():raise AssertionError('Root overview differs from owner build')
    root=(ROOT/'index.html').read_text(encoding='utf-8');readme=(ROOT/'README.md').read_text(encoding='utf-8')
    for marker in ['AI workflow software for continuing work across engineers, models and infrastructure.','corpus/history.html']:
        if marker not in root or marker not in readme:raise AssertionError('Shared product/history entry missing: '+marker)
    history=json.loads((ROOT/'corpus/history/manifest.json').read_text(encoding='utf-8'))
    if format(history['total_rows'],',') not in readme:raise AssertionError('README historical population differs from its manifest')
    broken=[]
    for item in m['pages']:
        rel=item['path']
        if item['role'] not in ['current-page','generated-current-page']:continue
        h=HTML();h.feed((ROOT/rel).read_text(encoding='utf-8'))
        for href in h.links:
            u=urlsplit(href)
            if u.scheme or u.netloc or not u.path or u.path.startswith('/') or '{' in href:continue
            target=(ROOT if href in h.site_links else (ROOT/rel).parent)/unquote(u.path)
            if not target.exists():broken.append({'page':rel,'link':href})
    if broken:raise AssertionError('Missing current-page targets: '+json.dumps(broken))
    main=(ROOT/'.github/workflows/hot-aisle-ci.yml').read_text(encoding='utf-8')
    for child in ['shelf-ci.yml','clustermax-challenge-ci.yml']:
        text=(ROOT/'.github/workflows'/child).read_text(encoding='utf-8')
        if 'workflow_call:' not in text or re.search(r'^  (push|pull_request|workflow_dispatch):',text,re.M):raise AssertionError('Separate partial qualification trigger: '+child)
        if 'uses: ./.github/workflows/'+child not in main:raise AssertionError('Required component is absent from unified CI: '+child)
    for command in ['corpus/build_history.py --check','corpus/tests/browser_history.py','app/tests/site_surface_check.py']:
        if command not in main:raise AssertionError('Unified CI misses '+command)
    for rel in ['app/source/index.template.html','README.md','compute/chapek/README.md']:
        text=(ROOT/rel).read_text(encoding='utf-8')
        if any(phrase in text for phrase in ['not from a to-do list someone typed','The 28 September disposition is historical direction']):raise AssertionError('Internal reviewer instruction in current reader copy: '+rel)
    print(json.dumps({'status':'PASS','html_surfaces':len(m['pages']),'roles':m['counts'],'historical_rows':history['total_rows'],'qualification_entry':'hot-aisle-ci.yml','scope':'Full HTML inventory; current entry routes, owner parity, source population and unified CI coverage.'},indent=2))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--inventory',action='store_true');a=ap.parse_args()
    if a.inventory:INVENTORY.write_text(json.dumps(inventory(),indent=2)+'\n',encoding='utf-8')
    check()
