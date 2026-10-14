"""Exercise the delivered historical corpus through actual HTTP and browser controls."""
import argparse, functools, http.server, json, os, tempfile, threading
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=None);args=ap.parse_args()
OUT=args.out or Path(tempfile.mkdtemp(prefix='cantos-history-'));OUT.mkdir(parents=True,exist_ok=True)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f'http://127.0.0.1:{server.server_port}/corpus/history.html'
checks=[]
def check(name,ok):
    if not ok:raise AssertionError(name)
    checks.append(name)
def ready(page):page.wait_for_function('window.CantosHistoryState && window.CantosHistoryState.ready && !window.CantosHistoryState.busy',timeout=90000)
manifest=json.loads((ROOT/'corpus/history/manifest.json').read_text(encoding='utf-8'))
try:
 with sync_playwright() as p:
    options={'headless':True,'args':['--no-sandbox']}
    if os.environ.get('CHROMIUM_EXECUTABLE'):options['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
    browser=p.chromium.launch(**options);context=browser.new_context(viewport={'width':1366,'height':900},accept_downloads=True)
    page=context.new_page();errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url) if not r.url.startswith(('http://127.0.0.1:','blob:','data:','about:')) else None)
    page.goto(url);ready(page);state=page.evaluate('window.CantosHistoryState')
    check('full corpus total comes from source manifest',state['total']==manifest['total_rows'] and state['total']>100000)
    check('first page reads real source observations',state['displayed']==100 and state['loadedShards']==1)
    first=page.locator('#results-body tr').first.get_attribute('data-record-id')
    page.locator('#more-btn').click();ready(page)
    check('load more advances within same source shard without skipping rows',page.locator('#results-body tr').count()==200 and page.evaluate('window.CantosHistoryState.loadedShards')==1)
    ids=page.locator('#results-body tr').evaluate_all('(rows)=>rows.map(r=>r.dataset.recordId)')
    check('pagination preserves prior rows and unique identities',ids[0]==first and len(set(ids))==200)
    page.locator('.open-record').first.click();check('source details expose original source and revision',page.locator('#detail .source-link').count()==1 and 'Source row:' in page.locator('#detail-body').inner_text() and 'Retained source SHA-256:' in page.locator('#detail-body').inner_text())
    page.locator('#detail-close').click()
    for i in range(3):page.locator('.row-select').nth(i).check()
    check('selection maximum three is enforced',page.locator('.row-select').nth(3).is_disabled())
    page.locator('#compare-btn').click();check('comparison preserves three separate source contexts',page.locator('#detail .comparison section').count()==3)
    page.locator('#detail-close').click()
    with page.expect_download() as dl:page.locator('#export-btn').click()
    dest=OUT/'selection.json';dl.value.save_as(str(dest));selection=json.loads(dest.read_text(encoding='utf-8'))
    check('export retains actual rows and owning source identities',len(selection['rows'])==3 and all('context' in r and 'row' in r for r in selection['rows']) and selection['sources'][0]['raw_sha256'])
    for kind in ['issues','prices','models','traces','research','datasets']:
        page.locator('#kind-filter').select_option(kind);page.locator('#search-btn').click();ready(page)
        st=page.evaluate('window.CantosHistoryState');check(kind+' opens actual retained collection',st['displayed']>0 and st['lastError'] is None)
        check(kind+' resets selection',st['selected']==0)
    page.locator('#kind-filter').select_option('benchmarks');page.locator('#source-filter').select_option('mlperf--mlperf');page.locator('#hardware-filter').fill('H200');page.locator('#search-btn').click();ready(page)
    check('source and hardware filters select matching retained conditions',page.locator('#results-body tr').count()>0 and all('H200' in s.upper() for s in page.locator('#results-body tr td:nth-child(5)').all_text_contents()))
    page.locator('#hardware-filter').fill('THIS_HARDWARE_DOES_NOT_EXIST_042');page.locator('#search-btn').click();ready(page)
    check('empty filter creates no fabricated substitute',page.locator('#results-body tr').count()==0 and page.evaluate('window.CantosHistoryState.loadedShards')==0)
    page.locator('#hardware-filter').fill('');page.locator('#source-filter').select_option('');page.locator('#search-btn').click();ready(page)
    page.screenshot(path=str(OUT/'history-desktop.png'),full_page=False)
    mobile=browser.new_page(viewport={'width':390,'height':844});mobile.goto(url);ready(mobile)
    check('phone page does not overflow',mobile.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    check('phone table has its own scroll area',mobile.locator('.table-wrap').evaluate('e=>e.scrollWidth>=e.clientWidth'))
    mobile.screenshot(path=str(OUT/'history-phone.png'),full_page=False)
    check('no unintended external requests',not external);check('no runtime errors',not errors)
    browser.close()
 report={'status':'PASS','count':len(checks),'checks':checks,'corpus_rows':manifest['total_rows'],'source_files':len(manifest['sources']),'scope':'Delivered historical source projection; real HTTP, filtering, pagination, source inspection, comparison, export and responsive layout.'}
 (OUT/'HISTORY.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
finally:server.shutdown()
