#!/usr/bin/env python3
"""Real HTTP and file navigation. Requires test-only Playwright and Chromium."""
import functools,hashlib,http.server,json,subprocess,tempfile,threading,sys,os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(tempfile.mkdtemp(prefix='capacity-browser-'))
OUT.mkdir(parents=True,exist_ok=True)
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
checks=[]
def check(name,condition):
    if not condition:raise AssertionError(name)
    checks.append(name)
with sync_playwright() as p:
    options={'headless':True,'args':['--no-sandbox']}
    executable=os.environ.get('CHROMIUM_EXECUTABLE')
    if executable: options['executable_path']=executable
    browser=p.chromium.launch(**options)
    context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
    page=context.new_page();errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url) if not r.url.startswith(('http://127.0.0.1:','file:','data:','blob:')) else None)
    page.goto(f'http://127.0.0.1:{server.server_port}/index.html',wait_until='networkidle')
    check('initial throughput unknown',page.locator('#accepted-out').inner_text()=='Unknown')
    check('seven costs remain unknown','upkeep' in page.locator('#cost-scope').inner_text())
    check('initial commitment',page.locator('#fee-out').inner_text()=='$10,000.00')
    check('blank page keeps the starting-example note','$10,000 / 720-hour' in page.locator('#scenario-note').inner_text())
    page.screenshot(path=str(OUT/'desktop.png'),full_page=True)
    context.set_offline(True)
    page.locator('#example-rate').click();check('offline productive output',page.locator('#accepted-out').inner_text()=='360,000')
    check('offline scenario cost',page.locator('#per-out').inner_text()=='$27.78')
    page.locator('#productive').fill('180');check('utilization denominator',page.locator('#per-out').inner_text()=='$55.56')
    check('commitment unchanged under lower use',page.locator('#fee-out').inner_text()=='$10,000.00')
    page.locator('#productive').fill('0');check('zero-use bill remains',page.locator('#fee-out').inner_text()=='$10,000.00')
    check('zero output has no cost ratio',page.locator('#per-out').inner_text()=='No modeled accepted output')
    page.locator('#productive').fill('180');page.locator('#fee').fill('5000')
    page.get_by_text('Whole-route costs for this same period',exact=True).click();page.locator('#zero-costs').click()
    check('explicit-zero scope','All listed cost categories' in page.locator('#cost-scope').inner_text())
    page.locator('#cost-operations').fill('2500');check('route costs included',page.locator('#per-out').inner_text()=='$41.67')
    page.locator('#productive').fill('900');check('invalid hours block export',page.locator('#export').is_disabled())
    page.locator('#productive').fill('180');check('valid inputs restore export',page.locator('#export').is_enabled())
    with page.expect_download() as d:page.locator('#export').click()
    packet=OUT/'decision.json';d.value.save_as(str(packet))
    node=subprocess.run(['node',str(ROOT/'verify.cjs'),str(packet)],capture_output=True,text=True)
    check('fresh-process full projection verification',node.returncode==0)
    independent=subprocess.run([sys.executable,str(ROOT/'check_math.py'),str(packet)],capture_output=True,text=True)
    check('independent Python arithmetic check',independent.returncode==0)
    (OUT/'node-verifier.json').write_text(node.stdout);(OUT/'python-arithmetic.json').write_text(independent.stdout)
    original=json.loads(packet.read_text());bad=dict(original);bad['sha256']='0'*64
    tampered=OUT/'tampered.json';tampered.write_text(json.dumps(bad));page.locator('#importer').set_input_files(str(tampered));page.wait_for_function("document.querySelector('#feedback').textContent.includes('mismatch')")
    check('checksum mismatch refused',page.locator('#feedback').evaluate('(e)=>e.classList.contains("error")'))
    check('refused packet leaves the starting-example note','$10,000 / 720-hour' in page.locator('#scenario-note').inner_text())
    page.locator('#fee').fill('2000');page.locator('#importer').set_input_files(str(packet));page.wait_for_function("document.querySelector('#fee').value === '5000'")
    check('successful reopen restores inputs',page.locator('#cost-operations').input_value()=='2500')
    check('reopened decision is named in the note',page.locator('#scenario-note').inner_text().startswith('Scenario “Dedicated allocation”, opened from a saved decision'))
    changed=json.loads(original['body_json']);changed['result']['target_qualified']=True
    bad={'schema':original['schema'],'body_json':json.dumps(changed,separators=(',',':'),ensure_ascii=False)};bad['sha256']=hashlib.sha256(bad['body_json'].encode()).hexdigest();tampered.write_text(json.dumps(bad));page.locator('#importer').set_input_files(str(tampered));page.wait_for_function("document.querySelector('#feedback').textContent.includes('disagrees')")
    check('rehashing false qualification fails full derivation',page.locator('#feedback').evaluate('(e)=>e.classList.contains("error")'))
    injection='<script>globalThis.__injected=true</script>'
    page.locator('#runtime').fill(injection)
    page.locator('#label').fill('<img src=x onerror="globalThis.__labelInjected=true">')
    with page.expect_download() as d:page.locator('#save-page').click()
    saved=OUT/'saved-page.html';d.value.save_as(str(saved))
    check('saved file carries the starting note until its packet verifies','id="scenario-note">The starting $10,000 / 720-hour' in saved.read_text(encoding='utf-8'))
    fresh=context.new_page();fresh.on('pageerror',lambda e:errors.append(str(e)))
    fresh.goto(saved.as_uri(),wait_until='load');fresh.wait_for_function("document.querySelector('#runtime').value.includes('__injected')")
    check('saved offline HTML restores packet',fresh.locator('#fee').input_value()=='5000')
    fresh_note=fresh.locator('#scenario-note').inner_text()
    check('saved page names its scenario, not the starting example','opened from a saved decision' in fresh_note and '$10,000' not in fresh_note)
    check('scenario label is shown as text, never markup','<img src=x' in fresh_note and not fresh.evaluate('Boolean(globalThis.__labelInjected)') and fresh.locator('#scenario-note img').count()==0)
    check('snapshot boot escapes HTML payload',not fresh.evaluate('Boolean(globalThis.__injected)'))
    check('reopened page has one input per cost',fresh.locator('#cost-fields input').count()==7)
    fresh.locator('#cost-operations').fill('2000');check('reopened inputs remain wired',fresh.locator('#per-out').inner_text()=='$38.89')
    page.locator('#runtime').fill('Target model, runtime and allocation remain unqualified.')
    page.locator('#historical-rate').fill('4.41');check('historical reprice works offline',page.locator('#historical-out').inner_text()=='$1.10')
    check('historical count remains separate',page.locator('.evidence-stat').inner_text()=='4,336 accepted / 8,622 scheduled')
    page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
    page.locator('#fee').fill('36821.2')
    one_line="[...document.querySelectorAll('.metrics .metric:not(.wide) strong')].every(e=>{const r=document.createRange();r.selectNodeContents(e);return new Set([...r.getClientRects()].map(x=>Math.round(x.top))).size===1})"
    for width in (834,768,390,360,320):
        page.set_viewport_size({'width':width,'height':844})
        check(f'{width}px result tiles stack in one column',page.evaluate("getComputedStyle(document.querySelector('.metrics')).gridTemplateColumns.trim().split(/\\s+/).length===1"))
        check(f'{width}px figures stay on one line',page.evaluate(one_line))
        check(f'{width}px page has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
        page.screenshot(path=str(OUT/f'mobile-{width}.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    check('mobile page has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
    check('no external application requests',not external)
    check('no JavaScript runtime errors',not errors)
    browser.close()
server.shutdown()
report={'status':'PASS','checks':checks,'count':len(checks),'scope':'Candidate browser and packet workflow, not estate acceptance or hosted deployment.','external_requests':external,'runtime_errors':errors}
(OUT/'browser-results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
