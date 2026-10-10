#!/usr/bin/env python3
"""The Chapek seat page as a reader meets it: served over HTTP, quick test, save, next step, reload,
saved copy reopened offline from disk, start over, phone layout. Requires test-only Playwright and Chromium."""
import functools,http.server,json,os,sys,tempfile,threading
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(tempfile.mkdtemp(prefix='chapek-browser-'))
OUT.mkdir(parents=True,exist_ok=True)
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
URL=f'http://127.0.0.1:{server.server_port}/index.html'
READY="window.CantosSeatState&&window.CantosSeatState.frameSynced===window.CantosSeatState.allocationSha"
NAME='Krauss Maschinenbau'
checks=[]
def check(name,condition):
    if not condition:raise AssertionError(name)
    checks.append(name)
with sync_playwright() as p:
    options={'headless':True,'args':['--no-sandbox']}
    if os.environ.get('CHROMIUM_EXECUTABLE'):options['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
    browser=p.chromium.launch(**options)
    context=browser.new_context(viewport={'width':1366,'height':640},accept_downloads=True)
    errors=[];external=[]
    def watch(pg):
        pg.on('pageerror',lambda e:errors.append(str(e)))
        pg.on('request',lambda r:external.append(r.url) if not r.url.startswith(('http://127.0.0.1:','file:','data:','blob:','about:')) else None)
        pg.on('dialog',lambda d:d.accept())
        return pg
    page=watch(context.new_page())
    page.goto(URL,wait_until='load');page.wait_for_function(READY)
    check('ready on a fresh open',page.locator('#notice').inner_text()=='Ready. Try it with one prospect below.')
    check('author and contact in the header','Jonathan Sandhu' in page.locator('header').inner_text() and 'bigbirdreturns@proton.me' in page.locator('header').inner_text())
    check('quick test on the first laptop screen',page.locator('#q-volume').bounding_box()['y']+page.locator('#q-volume').bounding_box()['height']<=640)
    page.screenshot(path=str(OUT/'laptop-first.png'))
    page.locator('#q-name').fill(NAME);page.locator('#q-volume').fill('20000')
    check('price per result appears as he types',page.locator('#q-out').inner_text().startswith('$1.84 per checked result'))
    check('more work on the same server lowers the price','$0.46' in page.locator('#q-out').inner_text())
    page.locator('#q-save').click();page.wait_for_function("window.CantosSeatState.opportunityRevision===2&&window.CantosSeatState.allocationRevision===2&&"+READY)
    check('saved prospect follows across tabs',page.locator('#strip').inner_text().startswith(NAME) and '$1.84 per result' in page.locator('#strip').inner_text())
    check('saved in the browser',page.locator('#storage').inner_text()=='Saved in this browser')
    nxt=page.locator('#quick [data-next]');check('next step offered',nxt.is_visible() and nxt.inner_text().startswith('Next: what is still open for '+NAME))
    nxt.click();check('next lands on the prospect',page.locator('#decision').is_visible() and page.locator('#customer').input_value()==NAME)
    check('open questions name the prospect',page.locator('#unknowns').inner_text().startswith('Still open for '+NAME))
    page.reload(wait_until='load');page.wait_for_function(READY)
    check('reload reopens the work',page.locator('#notice').inner_text().startswith('Your work from this browser is open ('+NAME+')'))
    record=page.evaluate('window.CantosSeatState.packetHash')
    with page.expect_download() as d:page.locator('#copy-top').click()
    copy=OUT/'copy.html';d.value.save_as(str(copy))
    offline=browser.new_context(viewport={'width':1366,'height':640},offline=True);fresh=watch(offline.new_page())
    fresh.goto(copy.as_uri(),wait_until='load');fresh.wait_for_function(READY)
    check('saved copy reopens offline from disk with the work',fresh.locator('#notice').inner_text().startswith('Opened with the work saved in this copy ('+NAME+')') and fresh.evaluate('window.CantosSeatState.packetHash')==record)
    page.locator('nav [data-tab=history]').click();page.locator('#history details').first.evaluate('d=>d.open=true')
    with page.expect_navigation():page.locator('#start-over').click()
    page.wait_for_function("document.getElementById('notice').textContent.startsWith('Ready.')&&"+READY)
    check('start over returns to the starting point',page.evaluate("localStorage.getItem('cantos.chapek.seat.v3')") is None)
    page.set_viewport_size({'width':390,'height':844});page.reload(wait_until='load');page.wait_for_function(READY);page.screenshot(path=str(OUT/'phone-first.png'))
    check('phone: every tab within the screen width',page.evaluate("[...document.querySelectorAll('nav [data-tab]')].every(x=>{const r=x.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})"))
    check('phone: quick test on the first screen',page.locator('#q-volume').bounding_box()['y']+page.locator('#q-volume').bounding_box()['height']<=844)
    for t in ['seat','decision','allocation','work','evidence','history']:
        page.evaluate(f"document.querySelector('nav [data-tab={t}]').click()")
        check(f'phone: no sideways scroll on {t}',page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
    check('no external requests',not external)
    check('no JavaScript runtime errors',not errors)
    browser.close()
server.shutdown()
report={'status':'PASS','checks':checks,'count':len(checks),'scope':'Reader journey over local HTTP and an offline saved copy. Not customer validation or hosted deployment.','external_requests':external,'runtime_errors':errors}
(OUT/'browser-results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
