#!/usr/bin/env python3
"""The Chapek seat page (edition 5) as a reader meets it: served over HTTP, the first screen states what the
next operator inherits, the quick test under Server, save, next step, reload, saved copy reopened offline from
disk, import, start over, phone layout. Requires test-only Playwright and Chromium."""
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
STORAGE_KEY='cantos.chapek.seat.v5'
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
    state=page.evaluate('window.CantosSeatState')
    check('ready on a fresh open',page.locator('#notice').inner_text().startswith('Ready. The recommendation in use is version '))
    check('author and contact in the header','Jonathan Sandhu' in page.locator('header').inner_text() and 'bigbirdreturns@proton.me' in page.locator('header').inner_text())
    check('first screen states the recommendation state',page.locator('#i-state').inner_text() in ('WRITTEN BEFORE YOUR CHANGE','DRAFT') and page.locator('#i-text').inner_text().strip()!='')
    check('first screen lists what changed',page.locator('#changes li').count()>=1)
    check('first screen summarises native runs',page.locator('#performed-summary tr').count()==state['runs']+1 and state['runs']>=1)
    check('first screen lists open items',page.locator('#open li').count()==state['open'] and state['open']>=1)
    check('first screen shows the next command','next.py' in page.locator('#next-cmd').inner_text())
    check('the quick test is not on the first screen',page.locator('#seat #quick').count()==0)
    page.screenshot(path=str(OUT/'laptop-first.png'))
    page.locator('nav [data-tab=performed]').click()
    check('work performed lists every retained procedure',page.locator('#procedures .proc').count()==state['procedures'] and state['procedures']>=1)
    check('run 3 source is checkout-relative','"source": "hot-aisle/campaign/results/run3-scored-a-t0"' in page.locator('#procedures').inner_text())
    page.locator('nav [data-tab=allocation]').click()
    lead=page.locator('#server-lead').inner_text()
    check('server lead follows the numbers in use','USD' in lead and 'read ' in lead)
    page.locator('#q-name').fill(NAME);page.locator('#q-volume').fill('20000')
    out=page.locator('#q-out').inner_text()
    per=page.evaluate("(()=>{const w=document.getElementById('capacity-frame').contentWindow,a=C.latest(C.state(ws),'allocation-scenario'),x=w.JSON.parse(JSON.stringify(JSON.parse(a.data.capacity_packet.body_json).input));x.productiveHours=x.committedHours;x.acceptedPerProductiveHour=20000/x.committedHours;return w.Capacity.evaluate(x).cost_per_1000_accepted/1000;})()")
    fmt=lambda v:('${:,.2f}'.format(v) if v>=0.1 else '$'+format(v,'.3g'))
    check('price per result appears as he types, priced by the engine',out.startswith(fmt(per)+' per checked result'))
    check('more work on the same server lowers the price',fmt(per/4) in out)
    before=page.evaluate('window.CantosSeatState.allocationRevision')
    page.locator('#q-save').click();page.wait_for_function('window.CantosSeatState.opportunityRevision===2&&window.CantosSeatState.allocationRevision==='+str(before+1)+'&&'+READY)
    check('saved prospect follows across tabs',page.locator('#strip').inner_text().startswith(NAME) and fmt(per)+' per result' in page.locator('#strip').inner_text())
    check('saved in the browser',page.locator('#storage').inner_text()=='Saved in this browser')
    nxt=page.locator('#quick [data-next]');check('next step offered',nxt.is_visible() and nxt.inner_text().startswith('Next: what is still open for '+NAME))
    nxt.click();check('next lands on the prospect',page.locator('#decision').is_visible() and page.locator('#customer').input_value()==NAME)
    check('open questions name the prospect',page.locator('#unknowns').inner_text().startswith('Still open for '+NAME))
    page.locator('nav [data-tab=seat]').click()
    check('first screen reflects the saved prospect',any(NAME in t for t in page.locator('#open li').all_inner_texts()))
    page.reload(wait_until='load');page.wait_for_function(READY)
    check('reload reopens the work',page.locator('#notice').inner_text().startswith('Your work from this browser is open ('+NAME+')'))
    record=page.evaluate('window.CantosSeatState.packetHash')
    with page.expect_download() as d:page.locator('#copy-top').click()
    copy=OUT/'copy.html';d.value.save_as(str(copy))
    offline=browser.new_context(viewport={'width':1366,'height':640},offline=True);fresh=watch(offline.new_page())
    fresh.goto(copy.as_uri(),wait_until='load');fresh.wait_for_function(READY)
    check('saved copy reopens offline from disk with the work',fresh.locator('#notice').inner_text().startswith('Opened with the work saved in this copy ('+NAME+')') and fresh.evaluate('window.CantosSeatState.packetHash')==record)
    check('saved copy carries the first screen','next.py' in fresh.locator('#next-cmd').inner_text() and fresh.locator('#performed-summary tr').count()==state['runs']+1)
    # Replacing work must also replace the quick form, or its old values can overwrite the import.
    page.locator('nav [data-tab=allocation]').click()
    page.locator('#q-name').fill('Prospect A');page.locator('#q-volume').fill('15.000')
    per15=page.evaluate("(()=>{const w=document.getElementById('capacity-frame').contentWindow,a=C.latest(C.state(ws),'allocation-scenario'),x=w.JSON.parse(JSON.stringify(JSON.parse(a.data.capacity_packet.body_json).input));x.productiveHours=x.committedHours;x.acceptedPerProductiveHour=15000/x.committedHours;return w.Capacity.evaluate(x).cost_per_1000_accepted/1000;})()")
    check('European grouping prices 15000 results',page.locator('#q-line').inner_text().startswith('= 15,000 results a month') and page.locator('#q-out').inner_text().startswith(fmt(per15)+' per checked result'))
    page.locator('#q-save').click();page.wait_for_function("()=>window.CantosSeatState.prospect==='Prospect A'&&!busy&&"+READY)
    page.locator('nav [data-tab=history]').click();page.locator('#history details').first.evaluate('d=>d.open=true')
    packet_a=page.locator('#packet-view').text_content();hash_a=page.evaluate('window.CantosSeatState.packetHash')
    page.locator('nav [data-tab=allocation]').click()
    page.locator('#q-name').fill('Prospect B');page.locator('#q-volume').fill('20000')
    page.locator('#q-save').click();page.wait_for_function("()=>window.CantosSeatState.prospect==='Prospect B'&&!busy&&"+READY)
    page.locator('#file').set_input_files({'name':'prospect-a.json','mimeType':'application/json','buffer':packet_a.encode('utf-8')})
    page.wait_for_function("()=>window.CantosSeatState.prospect==='Prospect A'&&!busy&&"+READY)
    check('import restores prospect and volume in the quick form',page.locator('#q-name').input_value()=='Prospect A' and page.locator('#q-volume').input_value()=='15,000' and page.locator('#q-unit').input_value()=='month')
    check('imported quick price agrees with the saved prospect',page.locator('#q-out').inner_text().startswith(fmt(per15)+' per checked result') and page.locator('#strip').inner_text().startswith('Prospect A') and '15,000 results a month' in page.locator('#strip').inner_text())
    page.locator('#q-save').click();page.wait_for_function("()=>!busy&&document.getElementById('notice').textContent.startsWith('Nothing new to save:')")
    check('resaving imported work cannot restore the previous prospect',page.evaluate('window.CantosSeatState.packetHash')==hash_a)
    # Instrument throughput is a separate assumption; it cannot rewrite the prospect's volume.
    page.locator('#q-volume').fill('25000')
    allocation_revision=page.evaluate('window.CantosSeatState.allocationRevision')
    page.frame_locator('#capacity-frame').locator('#rate').fill('1000')
    page.wait_for_function("()=>!document.getElementById('bind').disabled")
    page.locator('#bind').click();page.wait_for_function('()=>window.CantosSeatState.allocationRevision==='+str(allocation_revision+1)+'&&!busy&&'+READY)
    check('server changes preserve unsaved quick input',page.locator('#q-volume').input_value()=='25000')
    check('server throughput leaves saved prospect volume intact','15,000 results a month' in page.locator('#strip').inner_text())
    page.reload(wait_until='load');page.wait_for_function(READY)
    page.locator('nav [data-tab=allocation]').click()
    check('saved prospect volume survives server changes and reload',page.locator('#q-name').input_value()=='Prospect A' and page.locator('#q-volume').input_value()=='15,000')
    page.locator('nav [data-tab=history]').click();page.locator('#history details').first.evaluate('d=>d.open=true')
    with page.expect_navigation():page.locator('#start-over').click()
    page.wait_for_function("document.getElementById('notice').textContent.startsWith('Ready.')&&"+READY)
    check('start over returns to the starting point',page.evaluate("localStorage.getItem('"+STORAGE_KEY+"')") is None)
    page.set_viewport_size({'width':390,'height':844});page.reload(wait_until='load');page.wait_for_function(READY);page.screenshot(path=str(OUT/'phone-first.png'))
    check('phone: every tab within the screen width',page.evaluate("[...document.querySelectorAll('nav [data-tab]')].every(x=>{const r=x.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})"))
    for t in ['seat','decision','allocation','performed','work','evidence','history']:
        page.evaluate(f"document.querySelector('nav [data-tab={t}]').click()")
        check(f'phone: no sideways scroll on {t}',page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
    check('no external requests',not external)
    check('no JavaScript runtime errors',not errors)
    browser.close()
server.shutdown()
report={'status':'PASS','checks':checks,'count':len(checks),'scope':'Reader journey over local HTTP and an offline saved copy. Not customer validation or hosted deployment.','external_requests':external,'runtime_errors':errors}
(OUT/'browser-results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
