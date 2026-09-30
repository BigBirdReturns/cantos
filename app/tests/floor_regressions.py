"""Cantos interaction floor. Loopback only; no installs or external requests.

python floor_regressions.py --page Cantos.html --packets PATH --out NEW_DIR
--packets is accepted for parity with browser_regressions.py; that gate owns
packet validation. This suite deliberately reports all failures, not just first.
"""
from pathlib import Path
import argparse, functools, hashlib, http.server, json, threading, traceback, time
from playwright.sync_api import sync_playwright

p = argparse.ArgumentParser()
p.add_argument('--page', type=Path, required=True)
p.add_argument('--packets', type=Path)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--browser-executable')
p.add_argument('--allow-missing-stamps', action='store_true', help='Only for isolated interaction patch on v0.3; floor integration must omit this')
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
checks, errors, requests, blocked = [], [], [], []
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(a.page.resolve().parent)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_port}/{a.page.name}'

def check(name, fn):
    try:
        detail = fn()
        if detail is False: raise AssertionError('Condition false')
        checks.append(dict(name=name, passed=True, detail=detail))
    except Exception as e:
        checks.append(dict(name=name, passed=False, detail=str(e)))

try:
 with sync_playwright() as pw:
    opts = dict(headless=True)
    if a.browser_executable: opts['executable_path'] = a.browser_executable
    browser = pw.chromium.launch(**opts)
    ctx = browser.new_context(viewport=dict(width=1440,height=1000))
    def route(r):
        if r.request.url.startswith(f'http://127.0.0.1:{server.server_port}/') or r.request.url.startswith('data:'): r.continue_()
        else: blocked.append(r.request.url); r.abort()
    ctx.route('**/*', route)
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: requests.append(r.url) if not r.url.startswith('data:') else None)
    def wait(expression):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if page.evaluate(expression): return
            page.wait_for_timeout(15)
        raise AssertionError('Condition not reached: '+expression)
    def boot(width=1440, motion='no-preference', select_example_first=True):
        page.emulate_media(reduced_motion=motion)
        page.set_viewport_size(dict(width=width,height=1000))
        page.goto(url)
        wait('Boolean(window.CantosPreviewState) && !busy')
        if select_example_first:
            # Cold load now opens the Run 3 decision; these checks were written against the synthetic invoice example, so select it first.
            page.locator('[data-open-workspace="example"]').click();wait('document.getElementById("import-dialog").open')
            page.locator('#confirm-import').click();wait('!busy && !pendingImport && document.querySelectorAll(".task-cell").length===48')
            page.wait_for_timeout(900)  # let the swap's view transition settle so timing-sensitive checks see the same page as a fresh load
    def palette(query=''):
        page.keyboard.press('Control+k')
        page.locator('#command-input').fill(query)
        page.wait_for_timeout(80)  # dialog 'toggle' (aria-expanded) is dispatched as a queued task; let it land before reading ARIA
    def palette_aria():
        boot(); palette('invoice')
        return page.evaluate("""() => { const i=document.querySelector('#command-input'), active=document.getElementById(i.getAttribute('aria-activedescendant')); return i.getAttribute('role')==='combobox' && i.getAttribute('aria-controls')==='command-list' && i.getAttribute('aria-expanded')==='true' && active?.getAttribute('aria-selected')==='true'; }""")
    check('palette combobox exposes active option', palette_aria)
    def tab_enter():
        boot(); palette('Go to')
        page.keyboard.press('Tab'); page.keyboard.press('Tab')
        focus=page.evaluate('document.activeElement.id')
        page.keyboard.press('Enter')
        # If rows are tabbable, focused evidence row must execute. A proper
        # active-descendant combobox keeps Tab in the dialog's sole input.
        if focus=='command-input': return page.locator('#decision-view').is_visible() and not page.locator('#command-palette').evaluate('(d)=>d.open')
        return page.locator('#evidence-view').is_visible()
    check('palette Tab and Enter do not execute a different focused command', tab_enter)
    def empty():
        boot(); palette('zzzzzzzz-no-result')
        page.keyboard.press('ArrowDown'); page.keyboard.press('Enter')
        assert page.locator('#command-palette').evaluate('(d)=>d.open')
        page.locator('#command-input').fill('Go to System map'); page.keyboard.press('Enter')
        return page.locator('#architecture-view').is_visible()
    check('palette empty results recover after arrow and Enter', empty)
    def disabled():
        boot(); palette('Retain edition')
        row=page.locator('[data-cmd]').first
        assert row.get_attribute('aria-disabled')=='true'
        before=page.evaluate('CantosPreviewState.reportCount'); page.keyboard.press('Enter')
        return page.evaluate('CantosPreviewState.reportCount')==before
    check('palette unavailable command is announced and cannot mutate', disabled)
    def focus_return():
        boot(); page.locator('#command-btn').click(); page.keyboard.press('Escape')
        return page.locator('#command-btn').evaluate('(e)=>e===document.activeElement')
    check('palette Escape restores invoker focus', focus_return)
    def short_palette():
        boot(); page.set_viewport_size(dict(width=390,height=420)); palette()
        for _ in range(11): page.keyboard.press('ArrowDown')
        return page.locator('[aria-selected="true"]').evaluate('(e)=>{const r=e.getBoundingClientRect(),p=e.parentElement.getBoundingClientRect();return r.top>=p.top && r.bottom<=p.bottom+1}')
    check('palette arrows scroll selected option into view', short_palette)
    def modal_stack():
        boot(); page.locator('[data-inspect="source"]').first.click(); page.keyboard.press('Control+k')
        return page.locator('dialog[open]').count()==1 and page.locator('#inspector').evaluate('(d)=>d.open')
    check('palette shortcut preserves an existing modal without stacking', modal_stack)
    def tile_focus(width):
        boot(width); cell=page.locator('.task-cell').first; cell.focus(); page.wait_for_timeout(200)
        return page.locator('#tile-card').evaluate("(e)=>e.matches(':popover-open') && getComputedStyle(e).display!=='none' && e.getAttribute('aria-hidden')!=='true'") and cell.get_attribute('aria-describedby')=='tile-card'
    for width in [1440,390,320]: check(f'tile focus exposes described tooltip {width}', lambda w=width:tile_focus(w))
    def tile_edge():
        boot(motion='reduce'); page.set_viewport_size(dict(width=1440,height=400)); cell=page.locator('.task-cell').first
        cell.evaluate('(e)=>{e.focus({preventScroll:true});window.scrollBy(0,e.getBoundingClientRect().top-12)}')
        page.wait_for_timeout(100)
        cell.evaluate('(e)=>e.dispatchEvent(new FocusEvent("focusin",{bubbles:true}))'); page.wait_for_timeout(100)
        return page.locator('#tile-card').evaluate('(e)=>{let r=e.getBoundingClientRect();return r.top>=0&&r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight}')
    check('tile tooltip flips at viewport top', tile_edge)
    def tile_escape():
        boot(); page.locator('.task-cell').first.focus(); page.keyboard.press('Escape'); page.wait_for_timeout(200)
        return page.locator('#tile-card').evaluate("e=>!e.matches(':popover-open')")
    check('tile tooltip dismisses with Escape', tile_escape)
    def tile_pending():
        boot()
        page.locator('.task-cell').first.evaluate("e=>{e.dispatchEvent(new PointerEvent('pointerover',{bubbles:true}));e.click()}")
        page.wait_for_timeout(250)
        return page.locator('#inspector').evaluate('(d)=>d.open') and page.locator('#tile-card').evaluate("e=>!e.matches(':popover-open')")
    check('pending tile hover cannot reopen over inspection dialog', tile_pending)
    def numeric_values():
        return page.evaluate("""() => [...document.querySelectorAll('.comp-value')].map(e=>e.textContent) .every((s,i)=>s==='$'+viewState.calc.data.results[i].cost_per_success.toFixed(2))""")
    def ticker(motion):
        boot(motion=motion)
        for val in ['extract_json','strict_json','extract_json']:
            page.select_option('#grader',val); page.click('#apply-btn')
            wait('!busy && !CantosPreviewState.current')
            # DOM click while the view-transition is active: validates handler
            # independently of the separate real-pointer interception probe.
            page.locator('#recompute-btn').evaluate('(e)=>e.click()')
            wait('!busy && CantosPreviewState.current')
            if motion=='reduce': assert numeric_values()
        page.wait_for_timeout(800)
        return numeric_values()
    check('ticker rapid successive changes end at committed values', lambda:ticker('no-preference'))
    check('ticker reduced motion immediately shows committed values', lambda:ticker('reduce'))
    def pointer_transition():
        boot(); page.select_option('#grader','extract_json'); page.click('#apply-btn')
        wait('!busy && !CantosPreviewState.current')
        box=page.locator('#recompute-btn').bounding_box()
        page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
        page.wait_for_timeout(1000)
        return page.evaluate('CantosPreviewState.current')
    check('real pointer click during view transition reaches recompute', pointer_transition)
    def tile_transition():
        boot(); page.select_option('#grader','extract_json'); page.click('#apply-btn'); wait('!busy')
        box=page.locator('.task-cell').first.bounding_box()
        page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
        page.wait_for_timeout(150)
        return page.locator('#inspector').evaluate('(d)=>d.open')
    check('real pointer tile inspection during transition reaches its dialog', tile_transition)
    def mid_motion():
        boot(); page.select_option('#grader','extract_json'); page.click('#apply-btn'); wait('!busy')
        page.locator('#recompute-btn').evaluate('(e)=>e.click()');wait('!busy')
        page.emulate_media(reduced_motion='reduce');page.wait_for_timeout(60)
        return numeric_values()
    check('enabling reduced motion cancels an active ticker', mid_motion)
    def reduced_css():
        boot(motion='reduce')
        return page.evaluate("[...document.getAnimations()].every(a=>a.playState!=='running') && getComputedStyle(document.documentElement).scrollBehavior==='auto'")
    check('reduced motion has no running document animation', reduced_css)
    boot()
    font_data=page.evaluate("async()=>{await document.fonts.ready;return [...document.fonts].map(f=>({family:f.family,status:f.status}))}")
    check('embedded Inter and Fraunces load', lambda:all(any(f['status']=='loaded' and family in f['family'] for f in font_data) for family in ['Inter','Fraunces']))
    for view in ['decision','evidence','architecture']:
        for width in [1440,390,320]:
            boot(width,motion='reduce'); page.locator(f'button.nav[data-view="{view}"]').click()
            check(f'{view} no horizontal overflow {width}', lambda:page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            page.screenshot(path=str(a.out/f'{view}-{width}.png'),full_page=True)
    def stamps():
        boot(); page.locator('button.nav[data-view="evidence"]').click()
        nodes=page.locator('#evidence-view .stamp')
        if a.allow_missing_stamps and nodes.count()==0: return 'Explicit isolated-patch exemption; integrated floor must omit --allow-missing-stamps'
        assert nodes.count()>0, 'Evidence freshness stamps missing (Opus-owned integration)'
        assert all(len(t.strip())>10 and ('2026' in t or 'Run 3' in t) for t in nodes.all_text_contents())
        figures=page.locator('#evidence-view figure')
        return all(figures.nth(i).locator('.stamp').count()>0 for i in range(figures.count()))
    check('evidence freshness stamps are present and substantive', stamps)
    # ---- cold-visitor entry (added with the root-entry change) ----
    def cold_run3():
        boot(select_example_first=False)
        d=page.evaluate("D.decisionClass(workspace)")
        assert d=='hardware', 'cold load did not open the Run 3 decision: '+str(d)
        assert page.locator('[data-arm="A/T0"]').count()==1 and page.locator('[data-arm="N/T0"]').count()==1, 'arm cards missing'
        assert page.locator('.task-cell').count()==0, 'invoice tiles present on cold load'
        return page.locator('#comparison .comp-value').all_text_contents()==['$0.74','$1.20']
    check('cold load with no saved state opens the Run 3 decision (Edition 01, $0.74 vs $1.20)', cold_run3)
    def cold_orientation():
        boot(select_example_first=False)
        want='One retained decision from the Second Run compute campaign: the same coding workload on two rented seats, cost per 1,000 accepted requests at list price, every figure stamped with its source. Cantos is the record it lives in.'
        return page.locator('.orientation').count()==1 and page.locator('.orientation').inner_text()==want
    check('Run 3 view carries the one-sentence orientation line', cold_orientation)
    def rail_order():
        boot(select_example_first=False)
        links=page.locator('.case-nav .case-link')
        assert links.count()==2
        first,second=links.nth(0).inner_text().replace(chr(10),' | '),links.nth(1).inner_text().replace(chr(10),' | ')
        assert 'Real decision · Run 3, 24 Sep 2026' in first and 'GPU inference' in first, first
        assert 'Worked example · synthetic' in second and 'Invoice extraction' in second, second
        return links.nth(0).get_attribute('class').find('active')>=0
    check('rail lists GPU inference first (real decision) and the invoice example second (worked example)', rail_order)
    def example_header():
        boot()
        return page.locator('#decision-view .case-heading h1').inner_text()=='Synthetic worked example' and page.locator('.orientation').count()==0
    check('worked example header says Synthetic worked example', example_header)
    def palette_pair():
        boot(select_example_first=False); palette('Open the')
        labels=page.locator('[data-cmd]').all_text_contents()
        return any('Open the Run 3 decision' in l for l in labels) and any('Open the worked example' in l for l in labels)
    check('palette offers Open the Run 3 decision and Open the worked example', palette_pair)
    def saved_restore():
        boot()  # example selected
        page.click('#save-btn');wait('persist===true')
        page.reload();wait('Boolean(window.CantosPreviewState) && !busy')
        ok=page.locator('.task-cell').count()==48 and page.evaluate("D.decisionClass(workspace)")!='hardware'
        page.evaluate("localStorage.clear()")
        return ok
    check('saved state still restores the invoice example on reload', saved_restore)
    check('no runtime JavaScript errors', lambda:not errors)
    check('no non-loopback request attempted', lambda:not blocked)
    browser.close()
except Exception:
    errors.append(traceback.format_exc())
finally:
    server.shutdown()
report=dict(page_sha256=hashlib.sha256(a.page.read_bytes()).hexdigest(),page_bytes=a.page.stat().st_size,checks=checks,errors=errors,requests=requests,blocked=blocked,all_pass=bool(checks) and all(c['passed'] for c in checks) and not errors,stamp_exemption=a.allow_missing_stamps)
(a.out/'FLOOR.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['all_pass'] else 1)
