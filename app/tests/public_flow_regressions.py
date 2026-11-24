"""Public Open Compute flow: real decisions, saved-state isolation and offline packet replay.

Run from the checkout with Python + Playwright. Optional --base-url exercises an
already served exact candidate without transferring the checkout.
"""
from pathlib import Path
import argparse, functools, hashlib, http.server, json, threading, time, traceback
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--base-url')
parser.add_argument('--browser-executable')
args=parser.parse_args()
args.out.mkdir(parents=True,exist_ok=False)
server=None
if args.base_url:
    origin=args.base_url.rstrip('/')+'/'
else:
    root=Path(__file__).resolve().parents[2]
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(root)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}/'
checks=[];errors=[];blocked=[]
def require(value,message):
    if not value:raise AssertionError(message)
    return True
def check(name,fn):
    try:
        detail=fn()
        require(detail is not False,'Condition false')
        checks.append({'name':name,'passed':True,'detail':detail})
    except Exception as exc:
        checks.append({'name':name,'passed':False,'detail':str(exc)})
        raise
    finally:print(json.dumps(checks[-1]),flush=True)
def wait(frame,expr):
    limit=time.monotonic()+120
    while time.monotonic()<limit:
        if frame.evaluate(expr):return
        time.sleep(.04)
    raise AssertionError('Condition not reached: '+expr)
source_hash=hashlib.sha256(urlopen(origin+'app/Cantos.html',timeout=30).read()).hexdigest()
try:
 with sync_playwright() as pw:
    opts={'headless':True}
    if args.browser_executable:opts['executable_path']=args.browser_executable
    browser=pw.chromium.launch(**opts)
    ctx=browser.new_context(viewport={'width':1920,'height':1080},reduced_motion='reduce',accept_downloads=True)
    def route(r):
        if r.request.url.startswith(origin) or r.request.url.startswith(('blob:','data:')):r.continue_()
        else:blocked.append(r.request.url);r.abort()
    ctx.route('**/*',route)
    page=ctx.new_page()
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_default_timeout(30000)
    page.goto(origin+'public/open-compute/',wait_until='domcontentloaded')
    frame=page.frame_locator('#decision-app')
    child=page.locator('#decision-app').element_handle().content_frame()
    wait(child,'Boolean(window.CantosPreviewState) && !busy')
    wait(page,'Boolean(window.CantosGuideState)')
    check('public entry directly opens verified Run 3',lambda:require(child.evaluate("CantosPreviewState.decisionClass==='hardware' && !document.getElementById('decision-view').hidden"),'Run 3 decision absent'))
    check('original accepted counts and list-price results',lambda:require(child.evaluate("JSON.stringify(viewState.calc.data.results.map(r=>r.accepted))==='[4336,4280]'") and frame.locator('.comp-value').all_text_contents()==['$0.74','$1.20'],'Original result changed'))
    baseline_hash=child.evaluate('viewState.reports[0].snapshot_hash')
    original_saved=child.evaluate("()=>{const x=document.getElementById('run3-packet').textContent;localStorage.setItem('cantos.research-preview.v0.1',x);return x}")
    page.locator('[data-step="evidence"]').click()
    wait(child,"document.getElementById('inspector').open")
    check('guide reaches native acceptance contract',lambda:require('1000' in frame.locator('#inspector-body').text_content() and '60000' in frame.locator('#inspector-body').text_content(),'Policy limits absent'))
    page.locator('#guide-request').click()
    wait(child,"document.getElementById('inspector-title').textContent.startsWith('Request ')")
    check('guide reaches retained request measurements',lambda:require(child.evaluate("(()=>{const r=JSON.parse(document.getElementById('inspector-body').textContent);return typeof r.task.attempts[0].correct==='boolean'&&'first_token_ms' in r.task.attempts[0]})()"),'Retained request grade/timing absent'))
    page.locator('[data-step="change"]').click()
    wait(child,"!document.getElementById('inspector').open && document.activeElement===document.querySelector('[data-hardware-rate=\"n-t0\"]')")
    frame.locator('[data-hardware-rate="n-t0"]').fill('2.49')
    frame.locator('#apply-btn').click()
    wait(child,'!busy && !CantosPreviewState.current')
    check('Apply marks prior decision stale and blocks retention',lambda:require(frame.locator('#current-state').inner_text()=='STALE' and frame.locator('#freeze-btn').is_disabled() and frame.locator('.comp-value').all_text_contents()==['$0.74','$1.20'],'Stale gate or retained prior result missing'))
    frame.locator('#recompute-btn').click()
    wait(child,'!busy && CantosPreviewState.current')
    check('explicit recompute reverses the price decision with unchanged counts',lambda:require(frame.locator('.comp-value').all_text_contents()==['$0.74','$0.68'] and 'H100' in frame.locator('#winner').inner_text() and child.evaluate("JSON.stringify(viewState.calc.data.results.map(r=>r.accepted))==='[4336,4280]'"),'Native reversal or evidence count failed'))
    page.locator('[data-step="retain"]').click()
    wait(child,"document.activeElement===document.getElementById('reviewer')")
    frame.locator('#reviewer').fill('Public flow regression')
    frame.locator('#rationale').fill('H100 list-price scenario at $2.49/h over unchanged Run 3 evidence.')
    frame.locator('#review-btn').click()
    wait(child,'!busy && viewState.review.ready')
    frame.locator('#freeze-btn').click()
    wait(child,'!busy && CantosPreviewState.reportCount===2')
    check('successor keeps original retained snapshot',lambda:require(child.evaluate('viewState.reports[0].snapshot_hash')==baseline_hash and frame.locator('.edition').count()==2,'Earlier edition altered'))
    with page.expect_download() as download:
        frame.locator('#export-btn').click()
    exported=args.out/'exported-workspace.json'
    download.value.save_as(exported)
    require(exported.stat().st_size<=12000000,'Export exceeds own import boundary')
    exported_hash=json.loads(exported.read_text())['sha256']
    frame.locator('#save-btn').click()
    wait(child,'!busy')
    check('guided Save commits the exact packet before acknowledging success',lambda:require(child.evaluate("(async()=>{const saved=await guidedRecord('get');return saved && JSON.parse(saved).sha256===CantosPreviewState.packetHash && persist})()") and frame.locator('#notice').inner_text()=='Workspace saved on this device.','Saved packet or success acknowledgement missing'))
    check('guided Save preserves ordinary Cantos saved work',lambda:require(child.evaluate("localStorage.getItem('cantos.research-preview.v0.1')")==original_saved,'Ordinary saved copy was overwritten'))
    page.reload(wait_until='domcontentloaded')
    child=page.locator('#decision-app').element_handle().content_frame()
    frame=page.frame_locator('#decision-app')
    wait(child,'Boolean(window.CantosPreviewState) && !busy')
    check('guided reload restores saved successor',lambda:require(child.evaluate('CantosPreviewState.reportCount===2') and child.evaluate('CantosPreviewState.packetHash')==exported_hash,'Guided reload lost saved successor'))
    page.locator('#workbench').scroll_into_view_if_needed()
    page.screenshot(path=str(args.out/'desktop-guided.png'))
    fresh=ctx.new_page();fresh.set_default_timeout(30000)
    fresh.goto(origin+'app/Cantos.html?workspace=run3&presentation=1&fresh=1',wait_until='domcontentloaded')
    wait(fresh,'Boolean(window.CantosPreviewState) && !busy')
    check('explicit fresh route opens baseline in memory',lambda:require(fresh.evaluate('CantosPreviewState.reportCount===1'),'Fresh route failed to open baseline'))
    page.reload(wait_until='domcontentloaded')
    child=page.locator('#decision-app').element_handle().content_frame()
    wait(child,'Boolean(window.CantosPreviewState) && !busy')
    check('fresh route preserves saved guided successor',lambda:require(child.evaluate('CantosPreviewState.packetHash')==exported_hash,'Fresh route changed saved guided work'))
    ctx.set_offline(True)
    fresh.locator('#packet-file').set_input_files(str(exported.resolve()))
    wait(fresh,"document.getElementById('import-dialog').open")
    fresh.locator('#confirm-import').click()
    wait(fresh,'!busy && !pendingImport && CantosPreviewState.reportCount===2')
    time.sleep(.5)
    check('export reopens offline through native verification and retains both editions',lambda:require(fresh.evaluate('CantosPreviewState.packetHash')==exported_hash and fresh.evaluate('viewState.reports[0].snapshot_hash')==baseline_hash,'Offline restored packet differs'))
    ctx.set_offline(False)
    mobile=ctx.new_page();mobile.set_default_timeout(30000)
    mobile.set_viewport_size({'width':390,'height':844})
    mobile.goto(origin+'public/open-compute/',wait_until='domcontentloaded')
    mchild=mobile.locator('#decision-app').element_handle().content_frame()
    wait(mchild,'Boolean(window.CantosPreviewState) && !busy')
    check('public and embedded mobile layout have no horizontal overflow',lambda:require(mobile.evaluate('document.documentElement.scrollWidth<=innerWidth') and mchild.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Horizontal overflow'))
    mobile.locator('[data-step="change"]').click()
    wait(mchild,"document.activeElement===document.querySelector('[data-hardware-rate=\"n-t0\"]')")
    mobile.wait_for_timeout(100)
    mobile_apply=mobile.frame_locator('#decision-app').locator('#apply-btn').bounding_box()
    check('mobile guide brings native scenario and Apply into the viewport',lambda:require(mobile_apply and mobile_apply['y']>=0 and mobile_apply['y']+mobile_apply['height']<=844,'Mobile Apply remains outside the viewport'))
    mobile.screenshot(path=str(args.out/'mobile-controls.png'),full_page=True)
    denied=browser.new_context(viewport={'width':1280,'height':900},reduced_motion='reduce')
    denied.add_init_script("Object.defineProperty(window,'indexedDB',{value:{open(){throw new DOMException('Blocked for regression','SecurityError')}}})")
    denied_page=denied.new_page();denied_page.set_default_timeout(30000)
    denied_page.goto(origin+'public/open-compute/',wait_until='domcontentloaded')
    denied_child=denied_page.locator('#decision-app').element_handle().content_frame()
    wait(denied_child,'Boolean(window.CantosPreviewState) && !busy')
    wait(denied_page,'Boolean(window.CantosGuideState)')
    check('storage denial opens verified Run 3 in memory with explicit notice',lambda:require(denied_child.evaluate("CantosPreviewState.decisionClass==='hardware' && CantosPreviewState.reportCount===1 && !persist") and 'could not be read' in denied_page.locator('#guide-detail').inner_text(),'Storage-denied baseline fallback or notice failed'))
    denied.close()
    check('no runtime JavaScript errors or external requests',lambda:require(not errors and not blocked,str({'errors':errors,'blocked':blocked})))
    browser.close()
except Exception:
    errors.append(traceback.format_exc())
    try:
        page.screenshot(path=str(args.out/'failure.png'),full_page=True)
        errors.append(json.dumps({'notice':child.locator('#notice').inner_text(),'current':child.evaluate('window.CantosPreviewState'),'dialog':child.evaluate("document.getElementById('inspector').open")}))
    except Exception:pass
finally:
    if server:server.shutdown()
report={'app_sha256':source_hash,'origin':origin,'checks':checks,'errors':errors,'blocked':blocked,'all_pass':bool(checks) and all(c['passed'] for c in checks) and not errors}
(args.out/'PUBLIC-FLOW.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
raise SystemExit(0 if report['all_pass'] else 1)
