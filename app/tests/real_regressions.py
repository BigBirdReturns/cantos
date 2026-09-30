"""Real Run 3 browser gate. Reads Sol's packets through Open packet, never injects state.

python real_regressions.py --page PATH --packets ../sol/deliverables --out NEW_DIR
The flip assertions are intentionally strict: an ineligible H100 is a contract
failure, never a reason to weaken this gate or rewrite owner results in the view.
"""
from pathlib import Path
import argparse, functools, hashlib, http.server, json, threading, traceback, time
from playwright.sync_api import sync_playwright

p=argparse.ArgumentParser()
p.add_argument('--page',type=Path,required=True)
p.add_argument('--packets',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--browser-executable')
a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
checks,errors,blocked=[],[],[]
packets=[a.packets/'run3-decision.workspace.json',a.packets/'run3-decision.workspace.edition2.json']
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(a.page.resolve().parent)))
threading.Thread(target=server.serve_forever,daemon=True).start()
origin=f'http://127.0.0.1:{server.server_port}/'
def check(name,fn):
    try:
        result=fn()
        if result is False: raise AssertionError('Condition false')
        checks.append(dict(name=name,passed=True,detail=result))
    except Exception as e:
        checks.append(dict(name=name,passed=False,detail=str(e)))
    print(json.dumps(checks[-1]),flush=True)
def require(value,message):
    if not value: raise AssertionError(message)
    return True
try:
 with sync_playwright() as pw:
    opts={'headless':True}
    if a.browser_executable: opts['executable_path']=a.browser_executable
    browser=pw.chromium.launch(**opts)
    ctx=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    def route(r):
        if r.request.url.startswith(origin) or r.request.url.startswith('data:'): r.continue_()
        else: blocked.append(r.request.url);r.abort()
    ctx.route('**/*',route)
    page=ctx.new_page();page.set_default_timeout(120000)
    page.on('pageerror',lambda e:errors.append(str(e)))
    def wait(expr):
        # Playwright's string wait_for_function uses eval inside the page and
        # violates Cantos's unchanged CSP. CDP evaluate preserves that boundary.
        until=time.monotonic()+120
        while time.monotonic()<until:
            if page.evaluate(expr): return
            page.wait_for_timeout(25)
        raise AssertionError('Condition not reached: '+expr)
    def boot():
        page.goto(origin+a.page.name);wait('Boolean(window.CantosPreviewState) && !busy')
        # Cold load now opens the Run 3 decision; these checks start from the synthetic invoice example, so select it first.
        page.locator('[data-open-workspace="example"]').click();wait('document.getElementById("import-dialog").open')
        page.locator('#confirm-import').click();wait('!busy && !pendingImport && document.querySelectorAll(".task-cell").length===48')
    def open_packet(path):
        page.locator('#open-btn').click()
        page.locator('#packet-file').set_input_files(str(path.resolve()))
        wait('!busy')
        require(page.locator('#import-dialog').evaluate('e=>e.open'),page.locator('#notice').inner_text())
        page.locator('#confirm-import').click();wait('!busy && !pendingImport')
        require(page.evaluate("D.decisionClass(workspace)==='hardware'"),page.locator('#notice').inner_text())
        require(not page.locator('#notice').evaluate("e=>e.classList.contains('error')"),page.locator('#notice').inner_text())
    def row_data():
        return page.evaluate("viewState.calc.data.results.map(r=>({run:r.run_id,accepted:r.accepted,cost:r.cost_per_success,eligible:r.eligible,blockers:r.blockers}))")
    def price_values(expected):
        actual=page.locator('#comparison .comp-value').all_text_contents()
        return require(actual==expected,f'Expected {expected}, got {actual}')
    def h100_winner():
        title=page.locator('#winner').inner_text()
        return require('H100' in title,f'Expected H100 winner; got {title}. Owner results: {row_data()}')
    boot()
    original_ids=page.evaluate("[...document.querySelectorAll('[id]')].map(e=>e.id)")
    check('default task fixture remains intact',lambda:page.locator('.task-cell').count()==48)
    check('both real packets fit the 12 MB import boundary',lambda:all(x.exists() and x.stat().st_size<=12000000 for x in packets))
    check('Edition 01 imports through Open packet',lambda:open_packet(packets[0]))
    check('two real arms visible',lambda:require(page.locator('[data-arm="A/T0"]').count()==1 and page.locator('[data-arm="N/T0"]').count()==1,'Missing A/T0 or N/T0'))
    check('existing element ids survive hardware import',lambda:page.evaluate('(ids)=>ids.every(id=>document.getElementById(id))',original_ids))
    check('registered prices $0.74 and $1.20',lambda:price_values(['$0.74','$1.20']))
    check('accepted counts reconcile to retained records',lambda:require([r['accepted'] for r in row_data()]==[4336,4280],str(row_data())))
    check('MI300X is initial winner',lambda:'MI300X' in page.locator('#winner').inner_text())
    check('first-token percentiles present for both arms',lambda:page.locator('.hardware-percentiles b').count()==6)
    check('density replaces invoice tiles and retains all requests',lambda:page.locator('.task-cell').count()==0 and page.locator('canvas[aria-label*="8,622 requests"]').count()==2)
    check('real cards carry source date and scope stamps',lambda:all('24 Sep 2026' in t and 'RUN3-RESULTS.md' in t and 'not an invoice' in t for t in page.locator('.hardware-arm').all_text_contents()))
    def request_inspection():
        page.locator('.hardware-arm [data-inspect]').first.click()
        page.locator('[data-open-request]').click()
        require('Request request.' in page.locator('#inspector-title').inner_text(),'Retained request not opened')
        raw=json.loads(page.locator('#inspector-body').text_content())
        require('first_token_ms' in raw['task']['attempts'][0] and isinstance(raw['task']['attempts'][0]['correct'],bool),'Request measurements absent')
        page.keyboard.press('Escape')
    check('arm inspection reaches retained request measurements',request_inspection)
    def change_rate():
        rate=page.locator('[data-hardware-rate]').nth(1)
        rate.fill('2.49');page.locator('#apply-btn').click();wait('!busy')
        require(not page.evaluate('CantosPreviewState.current'),'Changed rate must make decision stale')
        require(page.locator('#history-count').inner_text()=='01','Earlier edition disappeared')
        page.locator('#recompute-btn').click();wait('!busy && CantosPreviewState.current')
        price_values(['$0.74','$0.68'])
        return row_data()
    check('rate change recomputes to $0.68 without changing retained counts',change_rate)
    check('requested $2.49 change flips decision to H100',h100_winner)
    check('scenario explicitly says no new model run',lambda:'no new model run' in page.locator('#outcome-diff').inner_text().lower())
    check('Edition 02 imports through Open packet',lambda:open_packet(packets[1]))
    check('two retained editions and supersedes line',lambda:page.locator('.edition').count()==2 and 'Supersedes Edition 01' in page.locator('.successor-line').inner_text())
    check('Edition 02 retains $0.74 and $0.68',lambda:price_values(['$0.74','$0.68']))
    check('Edition 02 winner is H100',h100_winner)
    for view in ['decision','evidence','architecture']:
        for width in [1440,390,320]:
            page.set_viewport_size({'width':width,'height':1000})
            page.locator(f'button.nav[data-view="{view}"]').click()
            page.evaluate("() => { window.scrollTo(0,0); for (const s of ['#workspace','.view']) document.querySelectorAll(s).forEach(e=>e.scrollTop=0); }")
            check(f'{view} no horizontal overflow {width}',lambda:page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            page.screenshot(path=str(a.out/f'{view}-{width}.png'),full_page=True)
    page.locator('button.nav[data-view="decision"]').click()
    def mobile_controls():
        page.locator('#mobile-scenario').click()
        require(page.locator('[data-first-token]').is_visible(),'Timing controls not visible')
        require(page.locator('#quote').evaluate('e=>e===document.activeElement'),'Hardware control did not receive focus')
        require(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Drawer overflow')
        page.screenshot(path=str(a.out/'scenario-320.png'),full_page=True)
        page.keyboard.press('Escape')
    check('hardware scenario drawer and focus at 320',mobile_controls)
    def task_reset():
        page.keyboard.press('Control+k');page.locator('#command-input').fill('Reset worked example');page.keyboard.press('Enter')
        page.locator('#confirm-reset').click();wait('!busy')
        return require(page.locator('.task-cell').count()==48 and page.locator('#grader').is_visible()==False and page.locator('.hardware-arm').count()==0,'Task reset did not recover original rendering')
    check('reset returns to the task fixture',task_reset)
    check('no runtime JavaScript errors',lambda:require(not errors,str(errors)))
    check('no external requests attempted',lambda:require(not blocked,str(blocked)))
    browser.close()
except Exception:
    errors.append(traceback.format_exc())
finally:
    server.shutdown()
report={'page_sha256':hashlib.sha256(a.page.read_bytes()).hexdigest(),'packets':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in packets if x.exists()},'checks':checks,'errors':errors,'blocked':blocked,'all_pass':bool(checks) and all(c['passed'] for c in checks) and not errors}
(a.out/'REAL.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['all_pass'] else 1)
