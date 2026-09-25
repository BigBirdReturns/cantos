#!/usr/bin/env python3
"""Exercise the actual page; CI requires native URL navigation, local review records fallback."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import argparse,json,subprocess,tempfile,time,os,sys,urllib.request
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--out',default=str(ROOT.parent/'compute-browser-qa'));parser.add_argument('--require-navigation',action='store_true');args=parser.parse_args()
OUT=Path(args.out);OUT.mkdir(parents=True,exist_ok=True)
checks=[]
def check(name,ok):
    if not ok:raise AssertionError(name)
    checks.append(name)
def wait_text(page,sel,value):
    page.wait_for_function('(x)=>document.querySelector(x.s).textContent.includes(x.v)',arg={'s':sel,'v':value})
def wait_connected(page):
    page.wait_for_function("()=>document.querySelector('#connection-status').textContent.startsWith('CONNECTED ·')")
with tempfile.TemporaryDirectory(prefix='compute-browser-') as td:
    td=Path(td);fixture=json.loads((ROOT/'tests/fixtures.json').read_text(encoding='utf-8'));(td/'test-run.json').write_text(json.dumps(fixture['a']))
    cp=subprocess.Popen(['node',str(ROOT/'scripts/connect.cjs'),'--results',str(td)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    first=cp.stdout.readline();url=cp.stdout.readline().strip();assert url.startswith('http://127.0.0.1:'),first+url
    try:
      with sync_playwright() as w:
        executable=os.environ.get('CHROMIUM_EXECUTABLE') or ('/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None)
        browser=w.chromium.launch(executable_path=executable,args=['--no-sandbox'])
        browser.on('disconnected',lambda:None)
        context=browser.new_context(viewport={'width':1440,'height':960},color_scheme='dark',accept_downloads=True)
        context.set_default_timeout(4000)
        page=context.new_page();errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
        mode='NATIVE_LOCALHOST_NAVIGATION'
        try:page.goto(url.split('#')[0],wait_until='networkidle',timeout=12000)
        except Exception as e:
          if args.require_navigation:raise
          mode='EXACT_HTML_SET_CONTENT_HOST_NAVIGATION_BLOCKED';page.close();page=context.new_page();errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url));page.set_content((ROOT/'index.html').read_text(encoding='utf-8'),wait_until='load')
        check('26 rows without account, upload or model call',page.locator('#price-rows tr').count()==26)
        check('shortlist hidden when empty',not page.locator('#shortlist-tray').is_visible())
        check('default price derived correctly','$0.27' in page.locator('#lowest').inner_text())
        check('default period cost correct','$43.20' in page.locator('#period-cost').inner_text())
        page.screenshot(path=str(OUT/'compare-dark.png'),full_page=True)
        page.locator('#theme').click();page.screenshot(path=str(OUT/'compare-light.png'),full_page=True)
        check('theme changes actual palette',page.evaluate('document.documentElement.dataset.theme')=='light')
        page.locator('#memory').select_option('192');check('memory filter 192GB',all(int(x)>=192 for x in page.locator('#price-rows tr td:nth-child(4)').all_text_contents()))
        page.locator('#provider').select_option('hotaisle');page.locator('#vendor').select_option('NVIDIA');check('no fabricated result for impossible filter','No results' in page.locator('#price-rows').inner_text())
        page.locator('#reset-market').click();page.locator('#search').fill('H100');check('search matches three providers',page.locator('#price-rows tr').count()==4)
        page.locator('#provider').select_option('nebius');check('source effective date current','$3.85' in page.locator('#lowest').inner_text())
        page.locator('#as-of').select_option('2026-10-01');check('source effective date future','$4.50' in page.locator('#lowest').inner_text())
        page.locator('#reset-market').click();page.locator('[data-select="rp-a5000"]').check();page.locator('[data-select="rp-a40"]').check();check('shortlist appears with selections',page.locator('#shortlist-tray').is_visible())
        page.locator('#compare-shortlist').click();check('comparison contains both selected cards',page.locator('#modal .comparison-card').count()==2)
        page.locator('#compare-save').click();check('decision retained in current workspace',page.locator('#saved-count').inner_text()=='1')
        # A stored decision from another engine version must survive a reload: listed, badged, exportable, never overwritten away.
        page.evaluate("()=>{const k='second-run-compute-decisions-v1';const s=JSON.parse(localStorage.getItem(k));s.push({schema:'second-run/sealed-compute-decision@1',sha256:'0'.repeat(64),payload:{schema:'second-run/compute-decision@1',version:'9.9.9',title:'Older engine decision',createdAt:'2026-01-01T00:00:00.000Z',kind:'own',inputs:{},result:{}}});localStorage.setItem(k,JSON.stringify(s));}")
        if mode=='NATIVE_LOCALHOST_NAVIGATION':page.reload(wait_until='networkidle')
        else:page.set_content((ROOT/'index.html').read_text(encoding='utf-8'),wait_until='load')
        check('unverifiable saved decision is kept, not dropped',page.locator('#saved-count').inner_text()=='2')
        check('saved shortlist survives a reload',page.locator('#shortlist-tray').is_visible() and '2 configurations' in page.locator('#shortlist-title').inner_text())
        check('return visit strip announces saved decisions','2 saved decisions' in page.locator('#saved-strip').inner_text())
        page.locator('#tab-work').click();check('unverifiable entry is badged','needs re-verification' in page.locator('#saved-list').inner_text().lower())
        page.locator('[data-saved="1"]').click();check('unverifiable entry opens with an export, not a crash','needs re-verification' in page.locator('#modal-body').inner_text().lower() and page.locator('#export-decision').count()==1);page.locator('#modal-close').click()
        page.locator('#tab-market').click();page.locator('#plan-shortlist').click();check('a later save writes back every stored entry',page.evaluate("()=>JSON.parse(localStorage.getItem('second-run-compute-decisions-v1')).length")==3)
        page.evaluate("()=>{const k='second-run-compute-decisions-v1';localStorage.setItem(k,JSON.stringify(JSON.parse(localStorage.getItem(k)).filter(e=>e.payload.version!=='9.9.9')));}")
        if mode=='NATIVE_LOCALHOST_NAVIGATION':page.reload(wait_until='networkidle')
        else:page.set_content((ROOT/'index.html').read_text(encoding='utf-8'),wait_until='load')
        check('cleaned store reloads to the two good decisions',page.locator('#saved-count').inner_text()=='2')
        page.locator('#tab-work').click();page.locator('[data-saved="0"]').click();check('saved decision view has scenario boundary','PLANNING' in page.locator('#modal-body').inner_text().upper() or 'proposal' in page.locator('#modal-body').inner_text().lower())
        with page.expect_download() as dl:page.locator('#export-decision').click()
        decision=OUT/'browser-decision.json';dl.value.save_as(str(decision));v=subprocess.run(['node',str(ROOT/'scripts/recompute.cjs'),str(decision)],capture_output=True,text=True);check('native exported decision recomputes in new Node process',v.returncode==0)
        page.locator('#modal-close').click();page.locator('#tab-own').click();check('ownership counts whole system','$80.64' in page.locator('#own-cost').inner_text())
        page.locator('#own-name').fill('My workstation');page.locator('#view-own details summary').click();page.locator('#local-rate').fill('10');check('incomplete same-work rates held','both' in page.locator('#own-error').inner_text())
        page.locator('#cloud-rate').fill('20');check('same work scales comparison hours','80' in page.locator('#rent-hours-label').inner_text())
        page.screenshot(path=str(OUT/'ownership.png'),full_page=True)
        page.locator('#residual').fill('2000');check('invalid residual clears result',page.locator('#own-cost').inner_text()=='—')
        check('validation message sits beside the edited field',page.locator('#view-own .field-error').count()==1 and page.locator('#residual').get_attribute('aria-invalid')=='true');page.locator('#residual').fill('300')
        check('field message clears with the correction',page.locator('#view-own .field-error').count()==0)
        page.locator('#tab-reuse').click();check('workload request share separated from GPU time',page.locator('#moved-pct').inner_text()!=page.locator('#time-pct').inner_text())
        check('initial qualification in first batch',page.locator('#break-even-batch').inner_text()=='9')
        page.screenshot(path=str(OUT/'second-run.png'),full_page=True)
        # Workload share controls are generated by the actual app.
        share=page.locator('#route-classes input[data-field="share"]')
        if share.count()==0:share=page.locator('#route-classes input').nth(0)
        share.first.fill('61');check('bad class totals held','100' in page.locator('#reuse-error').inner_text())
        check('mid-typing share imbalance is a soft hint, numbers stay',page.locator('#baseline-batch').inner_text()!='—' and page.locator('#view-reuse .field-error.soft').count()==1)
        share.first.dispatch_event('change');check('committed share imbalance holds the numbers',page.locator('#baseline-batch').inner_text()=='—');page.locator('#reset-reuse').click()
        page.locator('#tab-work').click();page.locator('#sample-work').click();check('synthetic examples marked and both loaded',page.locator('#run-list [data-run]').count()==2 and 'Synthetic' in page.locator('#run-list').inner_text())
        page.locator('[data-run="0"]').click();check('observation preserves producer/fixture status','synthetic fixture' in page.locator('#modal-body').inner_text().lower())
        check('cost denominator is completed not correct','completed responses' in page.locator('#run-economics').inner_text())
        with page.expect_download() as dl:page.locator('#run-export').click()
        dl.value.save_as(str(OUT/'normalized-sample.json'));normalized=json.loads((OUT/'normalized-sample.json').read_text(encoding='utf-8'));check('normalized export omits raw generated content','generated_texts' not in json.dumps(normalized))
        page.locator('#modal-close').click();page.screenshot(path=str(OUT/'workspace.png'),full_page=True)
        # Native File input with a malformed source retains earlier evidence.
        page.locator('#import-files').set_input_files({'name':'bad.json','mimeType':'application/json','buffer':b'{bad'})
        wait_text(page,'#import-error','JSON');check('transactional failed import retains prior results',page.locator('#run-list [data-run]').count()==2)
        page.locator('#connect-top').click();check('connection offers real executable and MCP configuration','connect.cjs' in page.locator('#modal-body').inner_text() and '--mcp' in page.locator('#modal-body').inner_text());page.locator('#modal-close').click()
        page.locator('#tab-market').focus();page.keyboard.press('ArrowRight');check('keyboard tabs select corresponding panel',page.locator('#view-own').is_visible())
        page.locator('#tab-market').click();page.locator('#source-note').click();check('sources retain current DO correction and billing conflict','$2.59' in page.locator('#modal-body').inner_text() and 'disagree' in page.locator('#modal-body').inner_text());page.locator('#modal-close').click()
        for width in (390,320):
          page.set_viewport_size({'width':width,'height':844})
          for view in ('market','own','reuse','work'):
            page.locator('#tab-'+view).click();check(f'{view} has no page overflow at {width}px',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            if view=='market':check(f'phone priceboard keeps the $/allocation-hour column at {width}px',page.locator('#price-rows tr').first.locator('td:nth-child(5)').is_visible() and page.locator('#tab-work').evaluate('e=>e.getBoundingClientRect().right<=innerWidth'))
          if width==390:
            page.locator('#tab-market').click();check('status toast does not intercept controls',page.locator('#toast').evaluate('(e)=>getComputedStyle(e).pointerEvents')=='none');page.locator('#clear-shortlist').click();page.evaluate('document.getElementById("toast").hidden=true');page.screenshot(path=str(OUT/'phone.png'),full_page=True)
        check('no JS errors',not errors)
        foreign=[u for u in requests if not u.startswith(url.split('#')[0])]
        check('zero external application requests',not foreign)
        # Test a future clock: repricing follows the effective schedule while source age remains visible.
        age_page=context.new_page();age_page.clock.install(time=__import__('datetime').datetime(2026,11,1,tzinfo=__import__('datetime').timezone.utc));(age_page.goto(url.split('#')[0],wait_until='networkidle') if mode=='NATIVE_LOCALHOST_NAVIGATION' else age_page.set_content((ROOT/'index.html').read_text(encoding='utf-8')));check('stale source banner visible under future clock',age_page.locator('#stale-banner').is_visible());check('announced price schedule activates on effective date',age_page.locator('#as-of').input_value()=='2026-10-01');age_page.close()
        if mode=='NATIVE_LOCALHOST_NAVIGATION':
          hp=context.new_page();hp.goto(url.split('#')[0]+'?from=hot-aisle&memory=192',wait_until='networkidle')
          check('handoff presets the memory floor',hp.locator('#memory').input_value()=='192')
          check('handoff shortlists MI300X and both H100 offers','3 configurations' in hp.locator('#shortlist-title').inner_text())
          check('handoff headlines the comparison, not the cheapest card','MI300X' in hp.locator('#handoff-banner').inner_text() and 'H100' in hp.locator('#handoff-banner').inner_text() and hp.locator('#handoff-banner').is_visible())
          check('header links back to the workload report',hp.get_by_role('banner').get_by_role('link',name='Workload report',exact=True).get_attribute('href')=='../hot-aisle/')
          hp.close()
        connected='HTTP and MCP independently tested by Node; browser connection requires native navigation'
        if mode=='NATIVE_LOCALHOST_NAVIGATION':
          page.set_viewport_size({'width':1440,'height':960});page.goto(url,wait_until='networkidle');wait_connected(page)
          check('native browser connected without file transport',page.locator('#run-list [data-run]').count()==1)
          check('connection token stripped from browser address',page.evaluate('location.hash')=='')
          page.locator('#refresh-work').click();wait_connected(page)
          check('native reconnect returns same supplied run',page.locator('#run-list [data-run]').count()==1)
          connected='NATIVE_LOCALHOST_READ_ONLY_BROWSER_CONNECTION'
        receipt={'checks':len(checks),'passed':checks,'failed':0,'browser_mode':mode,'connected_browser':connected,'console_errors':errors,'external_requests':foreign,'scope':'Synthetic fixtures and software interactions. No GPU benchmark, provider account or execution policy admitted.'}
        (OUT/'browser.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2));context.close();browser.close()
    finally:cp.terminate();cp.wait(timeout=5)
