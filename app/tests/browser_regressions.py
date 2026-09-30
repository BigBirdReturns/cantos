"""Browser acceptance for the revised candidate. Original council packets can be supplied.
python tests/browser_regressions.py --packets PATH/TO/council-review/astra --out NEW_OUTPUT
No browser policy, sandbox setting, or external service is modified.
"""
from pathlib import Path
import argparse, hashlib, json, time, functools, http.server, threading, traceback
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--page',type=Path,default=ROOT/'Cantos.html');p.add_argument('--packets',type=Path,default=ROOT/'tests/reproduced-packets');p.add_argument('--out',type=Path,required=True);p.add_argument('--browser-executable');a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
checks=[];errors=[];requests=[];packet_hashes={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(name,condition):
 checks.append({'name':name,'pass':bool(condition)})
 if not condition:raise AssertionError(name)
def wait(page,expression):
 deadline=time.monotonic()+8
 while time.monotonic()<deadline:
  if page.evaluate(expression):return
  time.sleep(.04)
 raise AssertionError('Condition not reached: '+expression)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(a.page.resolve().parent)))
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f'http://127.0.0.1:{server.server_port}/{a.page.name}'
try:
 with sync_playwright() as pw:
  options={'headless':True}
  if a.browser_executable:options['executable_path']=a.browser_executable
  browser=pw.chromium.launch(**options);ctx=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
  page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
  def boot():page.goto(url);wait(page,'Boolean(window.CantosPreviewState)')
  def actual():return page.evaluate('C.pack(workspace).then(p=>p.sha256)')
  def exported_hash(name):
   with page.expect_download() as download:page.locator('#export-btn').click()
   f=a.out/name;download.value.save_as(str(f));return json.loads(f.read_text())['sha256']
  boot();initial=actual();edition=page.evaluate('viewState.reports[0].snapshot_hash')
  page.reload();wait(page,'Boolean(window.CantosPreviewState)');check('fresh startup preserves baseline edition identity',edition==page.evaluate('viewState.reports[0].snapshot_hash'))
  # Real exports, rather than the cached UI hash alone, establish preservation.
  for name in ['null-quote.json','detached-decision.json','mixed-evidence.json','review-mismatch.json']:
   f=a.packets/name;packet_hashes[name]=sha(f);before=actual();saved=page.evaluate('localStorage.getItem(KEY)')
   page.locator('#packet-file').set_input_files(str(f.resolve()));wait(page,"document.getElementById('notice').textContent.startsWith('Import refused:')")
   check(name+' preserves actual workspace, cached display and saved copy',actual()==before==page.evaluate('CantosPreviewState.packetHash') and page.evaluate('localStorage.getItem(KEY)')==saved)
   check(name+' export contains the original workspace',exported_hash(name+'.export.json')==before)
  page.select_option('#grader','extract_json');page.click('#apply-btn');wait(page,'!CantosPreviewState.current');page.click('#recompute-btn');wait(page,'CantosPreviewState.current')
  check('new contract joins unchanged fields and deadlines',page.evaluate('viewState.calc.data.results.map(r=>r.accepted)')==[22,20])
  check('causal explanation is visible',"10 of A’s" in page.locator('#outcome-diff').inner_text())
  page.fill('#reviewer','Boundary reviewer');page.fill('#rationale','Reviewed the synthetic answer keys, original timings and complete quote.')
  page.click('#review-btn');wait(page,'!document.getElementById("freeze-btn").disabled');page.click('#freeze-btn');wait(page,'CantosPreviewState.reportCount===2')
  check('successor identifies the earlier edition','Supersedes Edition 01' in page.locator('#editions').inner_text())
  page.locator('[data-edition="1"]').click();check('edition inspection includes a readable comparison',page.locator('#inspector-readable table').count()==1);page.keyboard.press('Escape')
  before=actual();candidate=page.evaluate('CantosDesk.create().then(w=>CantosDesk.pack(w))');f=a.out/'replacement.json';f.write_text(json.dumps(candidate))
  page.locator('#packet-file').set_input_files(str(f));wait(page,'document.getElementById("import-dialog").open');check('replacement waits for confirmation',actual()==before)
  page.click('#cancel-import');check('cancel preserves unsaved work',actual()==before)
  page.locator('#packet-file').set_input_files(str(f));wait(page,'document.getElementById("import-dialog").open');page.click('#confirm-import');wait(page,'!document.getElementById("import-dialog").open');check('confirmed import commits the verified candidate',actual()==candidate['sha256'])
  # A render-preparation exception after native verification must also preserve work.
  different=page.evaluate("async()=>{let w=await D.change(workspace,{costA:4.8});await D.recompute(w);return C.pack(w)}")
  f.write_text(json.dumps(different));before=actual();page.evaluate("()=>{window.originalView=D.view;D.view=async()=>{throw Error('Injected presentation failure')}}")
  page.locator('#packet-file').set_input_files(str(f));wait(page,"document.getElementById('notice').textContent.includes('Injected presentation failure')")
  page.evaluate('()=>{D.view=window.originalView}');check('render failure leaves actual and displayed workspace unchanged',actual()==before==page.evaluate('CantosPreviewState.packetHash'))
  page.click('#save-btn');wait(page,'persist===true');saved=page.evaluate('localStorage.getItem(KEY)')
  page.evaluate("()=>{window.originalSet=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw Error('Injected quota failure')}}")
  page.fill('#quote','4.80');page.click('#apply-btn');wait(page,'persist===false')
  check('autosave failure labels current memory honestly',page.locator('#save-btn').inner_text()=='Save on this device' and page.evaluate('localStorage.getItem(KEY)')==saved)
  page.evaluate('()=>{Storage.prototype.setItem=window.originalSet}');page.click('#save-btn');wait(page,'persist===true')
  before=actual();saved=page.evaluate('localStorage.getItem(KEY)');page.evaluate("()=>{window.originalRemove=Storage.prototype.removeItem;Storage.prototype.removeItem=function(){throw Error('Injected deletion failure')}}")
  page.click('#reset-btn');page.click('#confirm-reset');wait(page,"document.getElementById('notice').textContent.startsWith('Reset refused:')")
  check('failed reset preserves memory and saved copy',actual()==before and page.evaluate('localStorage.getItem(KEY)')==saved);page.evaluate('()=>{Storage.prototype.removeItem=window.originalRemove}')
  page.screenshot(path=str(a.out/'revised-desktop.png'),full_page=True)
  for name in ['decision','evidence','architecture']:
   page.locator('button.nav[data-view="'+name+'"]').click()
   for width in [1440,390,320]:
    page.set_viewport_size({'width':width,'height':1000});check(name+' no overflow '+str(width),page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
  check('no page errors',not errors);check('no unexpected runtime requests',all(r==url for r in requests));browser.close()
except Exception:errors.append(traceback.format_exc())
finally:
 server.shutdown()
 report={'page_sha256':sha(a.page),'packet_sha256':packet_hashes,'checks':checks,'errors':errors,'requests':requests,'all_pass':bool(checks) and not errors,'packet_directory':str(a.packets),'scope':'Browser behavior only; no audience comprehension, source truth, external action or production qualification.'}
 (a.out/'BROWSER.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
raise SystemExit(0 if report['all_pass'] else 1)
