"""Native navigation, source custody, exports and origin-loss portability. No model calls."""
import argparse, functools, hashlib, http.server, json, os, shutil, subprocess, tempfile, threading
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
NODE=shutil.which('node')
checks=[]
def check(name,ok):
    checks.append({'name':name,'pass':bool(ok)})
    if not ok: raise AssertionError(name)
def node(code,*args):
    return subprocess.check_output([NODE,'-e',code,*map(str,args)],text=True,cwd=ROOT).strip()
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
def server(directory):
    s=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(directory)))
    threading.Thread(target=s.serve_forever,daemon=True).start()
    return s,'http://127.0.0.1:'+str(s.server_address[1])
def run(output):
    output.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='sr-community-native-'))
    servers=[]
    try:
        # Authored historical observations exercise publishing without impersonating a real provider result.
        fixture_js="""const C=require('./core.cjs'),fs=require('fs');const meta={title:'Fixture path <img src=x onerror=globalThis.pwned=1>',provider:'Authored software qualification fixture',hardware:'No real GPU',workload:'Fixture task',variant:'fixture',observed_at:'2026-09-24',contributor:'Test author',funding:'Authored fixture, no cloud cost',relationship:'Test author',limitations:['Authored test data; never a public benchmark result.'],sources:[{label:'Authored fixture',url:'',sha256:'b'.repeat(64),revision:null}],relation:null};const body={model:'test-model',support:'fixture',task:'fixture-work',measure:'fixture accepted count',value:1,maximum:2,cost_usd:null,cost_basis:'unknown',source_sha256:'b'.repeat(64),source_excerpt:'Authored software fixture.',study_status:'software-only'};fs.writeFileSync(process.argv[1],JSON.stringify(C.make('historical-finding',body,meta)));"""
        incoming=work/'incoming.json';node(fixture_js,incoming)
        p=json.loads(incoming.read_text());hub=work/'first';second=work/'second'
        for cmd in [['init',str(hub),'--name','First independent test hub','--empty'],['stage',str(incoming),'--hub',str(hub)],['review',p['sha256'],'--hub',str(hub),'--decision','accept','--reviewer','Qualification test','--reason','Authored isolation fixture'],['build',str(hub)]]:
            subprocess.run([NODE,str(ROOT/'cli.cjs'),*cmd],check=True,capture_output=True)
        s,origin=server(hub/'site');servers.append(s)
        with sync_playwright() as pw:
            binary=os.environ.get('SECOND_RUN_BROWSER')
            if not binary and Path('/usr/bin/chromium').exists(): binary='/usr/bin/chromium'
            browser=pw.chromium.launch(headless=True,**({'executable_path':binary} if binary else {}))
            context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
            external=[];errors=[]
            def request(route):
                if route.request.url.startswith(('http://127.0.0.1:','file:','blob:','data:')):route.continue_()
                else:external.append(route.request.url);route.abort()
            context.route('**/*',request);page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(origin,wait_until='networkidle');check('native first visit shows source rows',page.locator('[data-open]').count()==1)
            check('HTML-shaped labels stay text',not page.evaluate('Boolean(globalThis.pwned)'))
            page.locator('[data-open]').click();page.wait_for_selector('#detail-check');check('source-bound inspection opens',page.locator('#detail').is_visible())
            with page.expect_download() as info:page.locator('#detail-download').click()
            exported=output/'exported-evidence.json';info.value.save_as(exported);check('export preserves packet identity',json.loads(exported.read_text())['sha256']==p['sha256'])
            subprocess.run([NODE,str(ROOT/'cli.cjs'),'verify',str(exported)],check=True,capture_output=True);check('separate process recomputes exported evidence',True)
            page.locator('#detail-check').click();page.select_option('#metric','ratio');page.select_option('#operator','at_least');page.fill('#threshold','0.5');page.fill('#wording','The fixture record reaches 50%');page.locator('#check').click();page.wait_for_selector('#save-check')
            check('claim interpretation returns the observed result','Supported by these observations' in page.locator('#check-output').inner_text())
            page.locator('#save-check').click();page.reload(wait_until='networkidle');page.locator('[data-tab="saved"]').click();check('saved decision survives reload',page.locator('.saved-card').count()==1)
            with page.expect_download() as info:page.locator('[data-export]').click()
            decision=output/'decision.json';info.value.save_as(decision);subprocess.run([NODE,str(ROOT/'cli.cjs'),'verify-decision',str(decision)],check=True,capture_output=True);check('downloaded decision recomputes in another process',True)
            page.locator('[data-tab="contribute"]').click();page.locator('#import').set_input_files(str(exported));page.wait_for_selector('#draft-form',state='visible');page.locator('#preview').click();check('public export requires separate approval',page.locator('#export-packet').is_disabled());page.locator('#consent').check();check('reviewed packet can be exported',page.locator('#export-packet').is_enabled());page.fill('#draft-title','Changed after review');check('editing a public label revokes old approval',page.locator('#export-packet').is_disabled())
            page.locator('[data-tab="results"]').click();
            for width in [1440,768,390,320]:
                page.set_viewport_size({'width':width,'height':900});check('no document overflow at '+str(width),page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path=str(output/'independent-hub.png'),full_page=True)
            # Second generation is constructed entirely from the first hub's copied source and feed.
            subprocess.run([NODE,str(hub/'app/cli.cjs'),'init',str(second),'--name','Second generation hub'],check=True,capture_output=True)
            s.shutdown();s.server_close();servers.remove(s)
            s2,origin2=server(second/'site');servers.append(s2);page.goto(origin2,wait_until='networkidle');check('second-generation board works after origin loss',page.locator('[data-open]').count()==1);page.locator('[data-open]').click();page.wait_for_selector('#detail-check');check('second-generation record verifies without origin',page.locator('#detail').is_visible());page.locator('#detail-close').click()
            # A standalone portable result opens from disk and recomputes locally.
            offline=second/'site/r'/f"{p['sha256']}.html";page.goto(offline.as_uri(),wait_until='load');check('standalone result verifies on file origin','CALCULATION RECOMPUTED' in page.locator('#verified').inner_text())
            check('no page JavaScript errors',not errors);check('zero external network requests',not external)
            # Exercise the actual shipped board if its data have been built.
            if (ROOT.parent/'results.html').exists():
                sp,public=server(ROOT.parent);servers.append(sp);page.goto(public+'/results.html',wait_until='networkidle');check('release board native navigation',page.locator('[data-open]').count()>0)
                page.locator('[data-tab="claims"]').click();page.locator('[data-example="cost"]').click();page.locator('#check').click();page.wait_for_selector('#save-check');check('native cost example is selected and calculated','SUPPORTED IN SELECTED RECORDS' in page.locator('#check-output').inner_text());check('small currency values are not rounded to zero','$0.000' in page.locator('#check-output').inner_text())
                page.locator('[data-example="tail"]').click();page.locator('#check').click();page.wait_for_selector('#save-check');check('unfavorable claim remains visible','CONTRADICTED' in page.locator('#check-output').inner_text())
                page.locator('[data-example="method"]').click();page.locator('#check').click();page.wait_for_selector('#save-check');check('historical method comparison is accessible','SUPPORTED IN SELECTED RECORDS' in page.locator('#check-output').inner_text())
                page.locator('[data-tab="results"]').click();page.fill('#search','');page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path=str(output/'results-desktop.png'),full_page=True);page.locator('#theme').click();page.screenshot(path=str(output/'results-light.png'),full_page=True)
                for width in [390,320]:page.set_viewport_size({'width':width,'height':900});check('release no horizontal overflow '+str(width),page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                page.screenshot(path=str(output/'results-phone.png'),full_page=True)
            browser.close()
        result={'native_navigation':True,'set_content_used':False,'checks':checks,'passed':sum(x['pass'] for x in checks),'failed':sum(not x['pass'] for x in checks),'external_requests':external,'page_errors':errors,'scope':'Two isolated local owners and second-generation custody are simulated. No outside contributor adoption or native hardware replication is inferred.'}
        (output/'community-browser.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'passed':result['passed'],'failed':result['failed'],'output':str(output)}))
    finally:
        for s in servers:s.shutdown();s.server_close()
        shutil.rmtree(work,ignore_errors=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('community-browser-qa'));args=parser.parse_args();run(args.out.resolve())
