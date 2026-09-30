"""Independent Cantos qualification: actual file/HTTP navigation, no mocks.

Usage: python tests/qualify.py --artifact /path/to/index.html --out /path/to/results
Requires the already installed Playwright Python package and Chromium.
"""
from __future__ import annotations
import argparse
import hashlib
import http.server
import json
import re
import threading
import traceback
from functools import partial
from pathlib import Path
from playwright.sync_api import sync_playwright

PRIVATE_PATTERNS = {
    'absolute Windows custody path': r'(?i)\b[A-Z]:[\\/](?:Projects|Scratch|Users)[\\/]',
    'private key': r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',
    'credential assignment': r'(?i)(?:api_key|access_token|client_secret)\s*[=:]\s*[\"\x27][A-Za-z0-9_\-]{16,}',
    'private IP': r'\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)\b',
}

def privacy_errors(text):
    return [name for name,pattern in PRIVATE_PATTERNS.items() if re.search(pattern,text)]

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass

class Qualification:
    def __init__(self,artifact,out):
        self.artifact=artifact.resolve()
        self.out=out.resolve()
        self.out.mkdir(parents=True,exist_ok=True)
        self.checks=[]
        self.requests=[]
        self.errors=[]

    def check(self,name,operation):
        try:
            detail=operation()
            self.checks.append({'name':name,'status':'PASS','detail':detail})
        except Exception as exc:
            self.checks.append({'name':name,'status':'FAIL','detail':str(exc),'traceback':traceback.format_exc()})
        self.save()

    def save(self):
        result={'artifact':str(self.artifact),'sha256':hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
                'status':'FAIL' if any(x['status']=='FAIL' for x in self.checks) else 'PASS',
                'checks':self.checks,'external_requests':self.requests,'page_errors':self.errors,
                'limits':['Local Chromium software qualification; no source-truth, live supply, provider execution or authenticated-review claim.']}
        (self.out/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result

    def scan(self):
        text=self.artifact.read_text(encoding='utf-8-sig')
        assert not privacy_errors(text),privacy_errors(text)
        assert not re.search(r'<script[^>]+src\s*=',text,re.I),'External script dependency in portable artifact'
        assert not re.search(r'<link[^>]+rel=[\"\x27]stylesheet',text,re.I),'External stylesheet dependency'
        assert 'connect-src' in text and "connect-src 'none'" in text,'Missing network-blocking CSP'
        return 'Portable HTML has no script/style dependency or tested private patterns.'

    def page(self,context,url):
        page=context.new_page()
        page.on('pageerror',lambda e:self.errors.append(str(e)))
        def request(req):
            if req.url.startswith(('http://','https://')) and not req.url.startswith(self.origin+'/'):
                self.requests.append(req.url)
        page.on('request',request)
        page.goto(url,wait_until='load')
        page.wait_for_function('typeof CantosDesk !== "undefined"',timeout=15000)
        page.wait_for_function('document.querySelector("#rec-body") && !document.querySelector("#rec-body").innerText.includes("Loading")',timeout=15000)
        return page

    @staticmethod
    def no_overflow(page):
        widths=page.evaluate('({viewport:innerWidth,doc:document.documentElement.scrollWidth,body:document.body.scrollWidth})')
        assert widths['doc']<=widths['viewport']+1,widths
        assert widths['body']<=widths['viewport']+1,widths
        return widths

    def layout(self,browser,width):
        context=browser.new_context(viewport={'width':width,'height':960},reduced_motion='reduce')
        try:
            page=self.page(context,self.origin+'/'+self.artifact.name)
            widths=self.no_overflow(page)
            page.screenshot(path=str(self.out/f'viewport-{width}.png'),full_page=True)
            page.locator('#btn-arch').click()
            page.wait_for_selector('#drawer[data-open="true"]')
            self.no_overflow(page)
            assert page.locator('#drawer-body').inner_text().strip(),'Empty architecture drawer'
            duration=page.locator('.sheet').evaluate('(e)=>getComputedStyle(e).animationDuration')
            assert all(float(t.strip().rstrip('s'))==0 for t in duration.split(',')),duration
            page.keyboard.press('Escape')
            assert page.locator('#drawer').get_attribute('data-open')=='false','Escape failed to close drawer'
            assert page.locator('#btn-arch').evaluate('(e)=>e===document.activeElement'),'Drawer did not restore keyboard focus'
            return widths
        finally:
            context.close()

    def keyboard(self,browser):
        context=browser.new_context(viewport={'width':1024,'height':900})
        try:
            page=self.page(context,self.origin+'/'+self.artifact.name)
            page.keyboard.press('Tab')
            assert page.locator('.skip').evaluate('(e)=>e===document.activeElement'),'Skip link is not first keyboard target'
            page.keyboard.press('Enter')
            assert page.locator('#work').evaluate('(e)=>e===document.activeElement'),'Skip link does not reach main'
            page.locator('#btn-arch').focus()
            page.keyboard.press('Enter')
            for _ in range(25):
                page.keyboard.press('Tab')
                assert page.evaluate('document.querySelector("#drawer").contains(document.activeElement)'),'Modal keyboard focus escaped drawer'
            page.keyboard.press('Escape')
            return 'Skip navigation, keyboard-open/close and modal focus containment.'
        finally:
            context.close()

    def text_zoom(self,browser):
        context=browser.new_context(viewport={'width':1024,'height':900})
        try:
            page=self.page(context,self.origin+'/'+self.artifact.name)
            # Text-only enlargement keeps the viewport width unchanged.
            page.evaluate('''() => { const els=[...document.querySelectorAll('body *')]; const sizes=els.map(e=>parseFloat(getComputedStyle(e).fontSize)); els.forEach((e,i)=>e.style.fontSize=(sizes[i]*2)+'px'); }''')
            self.no_overflow(page)
            page.screenshot(path=str(self.out/'text-200-percent.png'),full_page=True)
            return 'Every rendered font enlarged to 200%, unchanged 1024px viewport; no document overflow.'
        finally:
            context.close()

    def disclosures(self,browser):
        context=browser.new_context()
        try:
            page=self.page(context,self.origin+'/'+self.artifact.name)
            identity=page.evaluate('CantosDesk.identity()')
            assert identity['seed_status']=='sol','Provisional evidence is not a final deliverable'
            assert identity['core_matches_build'],'Embedded native owner identity mismatch'
            records=page.evaluate('CantosDesk.view().records')
            seed=page.evaluate('JSON.parse(document.querySelector("#cantos-seed").textContent)')
            page.locator('#btn-arch').click()
            text=page.locator('body').inner_text()
            for record in records:
                if record['role']=='measurement':
                    data=record['data']
                    for key in ['model','revision','runtime','backend']:
                        value=data.get('identity',{}).get(key)
                        if value:
                            assert value in text,f'Measurement identity hidden: {record["id"]} {key}'
                    if data.get('grading',{}).get('posthoc'):
                        assert '6,192' in text or '6192' in text,'Post-hoc correctness value missing from evidence'
            assert '64.7' in text,'Modeled own-seat cost window missing from visible detail'
            assert '69.8' in text,'Comparator closed-ledger cost window missing from visible detail'
            assert 'self-funded' in text.lower(),'Comparator funding missing'
            groups=seed.get('architecture',{}).get('groups',[])
            assert groups,'Sol ownership map missing from built seed/drawer'
            for group in groups:
                for item in group.get('items',[]):
                    assert item['name'] in text,'Ownership map entry missing from drawer'
            return 'Final source seed, embedded owner identity, model/recipe pins, billing windows, post-hoc distinction and funding visible.'
        finally:
            context.close()
    def file_navigation(self,browser):
        context=browser.new_context()
        try:
            page=self.page(context,self.artifact.as_uri())
            assert page.locator('#rec-body').inner_text().strip()
            return 'Actual file URI loaded and initialized.'
        finally:
            context.close()

    def run(self):
        self.check('portable artifact privacy and dependency scan',self.scan)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(self.artifact.parent)))
        self.origin=f'http://127.0.0.1:{server.server_port}'
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                for width in [1440,1024,390,320]:
                    self.check(f'HTTP layout {width}px and reduced motion',lambda w=width:self.layout(browser,w))
                self.check('keyboard focus',lambda:self.keyboard(browser))
                self.check('200% text',lambda:self.text_zoom(browser))
                self.check('evidence and owner disclosures',lambda:self.disclosures(browser))
                self.check('file navigation',lambda:self.file_navigation(browser))
                self.check('integrated user journey',lambda:self.journey(browser))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
        self.check('no unintended external requests',lambda:self.assert_empty(self.requests))
        self.check('no browser runtime errors',lambda:self.assert_empty(self.errors))
        result=self.save()
        print(json.dumps({'status':result['status'],'checks':len(self.checks),'results':str(self.out/'results.json')},indent=2))
        return 0 if result['status']=='PASS' else 1

    @staticmethod
    def assert_empty(values):
        assert not values,values
        return 'None observed.'

    def journey(self,browser):
        context=browser.new_context(accept_downloads=True,viewport={'width':1440,'height':1000})
        fresh=None
        try:
            page=self.page(context,self.origin+'/'+self.artifact.name)
            view=lambda:page.evaluate('CantosDesk.view()')
            baseline=view()
            assert baseline['recommendation']['dependency']['current'],baseline['recommendation']
            measurements=[r for r in baseline['records'] if r['role']=='measurement']
            assert measurements,'Missing retained measurements'
            assert all(r['metrics'] for r in measurements),'Missing measurement values'
            price=next(r for r in baseline['records'] if r['role']=='price')
            assert price['offer']['rate']>0,'Missing initial rate'
            derived=next(r for r in baseline['records'] if r['role']=='economics')
            assert derived['derived']['verified'],'Initial economics failed native verification'
            assert not baseline['recommendation']['review']['ready'],'Demo must not invent user acceptance'
            assert not baseline['deliveries'],'Demo must not invent issued reviews'
            page.locator('#btn-freeze').click()
            assert not view()['deliveries'],'Unreviewed issue succeeded'
            page.locator('[name=reviewer]').fill('Independent test reviewer')
            page.locator('[name=rationale]').fill('Reviewed retained measurements, dated price assumptions and limitations for this software test.')
            page.locator('#btn-review').click()
            page.wait_for_function('CantosDesk.view().recommendation.review.ready === true')
            page.locator('#btn-freeze').click()
            page.wait_for_function('CantosDesk.view().deliveries.length === 1')
            first=view()
            first_packet=json.loads(page.evaluate('CantosDesk.exportPacket()')['text'])
            frozen=next(e for e in first_packet['workspace']['events'] if e['type']=='freeze')
            price_input=page.locator('input[type=number]').first
            changed_price=float(price['offer']['rate'])*1.25+0.1
            price_input.fill(str(changed_price))
            page.locator('[name=note]').fill('Explicit hypothetical price; measured work and dated supply unchanged.')
            page.locator('#btn-change').click()
            page.wait_for_function('CantosDesk.view().recommendation.status === "stale"')
            stale=view()
            assert [r for r in stale['records'] if r['role']=='measurement']==measurements,'Price changed retained measurement records'
            assert not stale['recommendation']['review']['ready'],'Earlier review survived changed input'
            assert stale['scenario']['active'],'Changed price is not labeled scenario'
            assert stale['scenario']['rate']==changed_price
            stale_ids={r['id'] for r in stale['records'] if r['stale']}
            assert derived['id'] in stale_ids and baseline['recommendation']['id'] in stale_ids,stale_ids
            assert not any(r['stale'] for r in stale['records'] if r['role']=='measurement'),'Measured work became stale on price-only change'
            page.locator('[name=rationale]').fill('Attempted acceptance of stale dependencies must be rejected.')
            stale_events=stale['workspace']['event_count']
            page.locator('#btn-review').click()
            page.wait_for_function('!document.querySelector("#btn-review").hasAttribute("aria-busy")')
            assert not view()['recommendation']['review']['ready'],'Stale acceptance succeeded'
            assert view()['workspace']['event_count']==stale_events,'Rejected stale review wrote a journal event'
            page.locator('#btn-freeze').click()
            assert len(view()['deliveries'])==1,'Stale version issued'
            page.screenshot(path=str(self.out/'stale-dependencies.png'),full_page=True)
            page.locator('#btn-recompute').click()
            page.wait_for_function('CantosDesk.view().recommendation.dependency.current === true')
            revised=view()
            assert not revised['recommendation']['review']['ready'],'Recompute reused review'
            assert [r for r in revised['records'] if r['role']=='measurement']==measurements,'Recompute changed historical evidence'
            assert revised['recommendation']['revision']>baseline['recommendation']['revision']
            assert revised['recommendation']['scenario'] and revised['recommendation']['tier']=='proposal'
            revised_cost=next(r for r in revised['records'] if r['role']=='economics')
            assert revised_cost['derived']['verified'],'Successor fails native arithmetic verification'
            assert revised_cost['derived']['usd_per_1k_accepted']!=derived['derived']['usd_per_1k_accepted'],'Changed rate did not change economics'
            page.locator('#btn-freeze').click()
            assert len(view()['deliveries'])==1,'Successor issued without new review'
            page.locator('[name=rationale]').fill('Fresh review of recomputed successor with unchanged measurement and scenario-only price.')
            page.locator('#btn-review').click()
            page.wait_for_function('CantosDesk.view().recommendation.review.ready === true')
            page.locator('#btn-freeze').click()
            page.wait_for_function('CantosDesk.view().deliveries.length === 2')
            final=view()
            with page.expect_popup() as popup_info:
                page.locator('[data-open-report]').first.click()
            popup=popup_info.value
            popup.wait_for_load_state()
            assert final['deliveries'][-1]['snapshot_hash'] in popup.locator('body').inner_text(),'Opened report lost snapshot identity'
            popup.close()
            with page.expect_download() as report_download:
                page.locator('[data-dl-report]').first.click()
            report_download.value.save_as(str(self.out/'issued-successor-report.html'))
            assert final['deliveries'][-1]['snapshot_hash'] in (self.out/'issued-successor-report.html').read_text(encoding='utf-8')
            assert final['deliveries'][1]['snapshot_hash']!=final['deliveries'][0]['snapshot_hash'],'Successor not distinct'
            with page.expect_download() as download:
                page.locator('#btn-export').click()
            packet_file=self.out/'issued-packet.json'
            download.value.save_as(str(packet_file))
            packet_text=packet_file.read_text(encoding='utf-8-sig')
            packet=json.loads(packet_text)
            assert next(e for e in packet['workspace']['events'] if e['type']=='freeze')==frozen,'First issued snapshot was mutated'
            assert not privacy_errors(packet_text),privacy_errors(packet_text)
            fresh=browser.new_context(accept_downloads=True)
            restored=self.page(fresh,self.artifact.as_uri())
            assert restored.evaluate('CantosDesk.view()')['deliveries']==[],'Fresh browser unexpectedly retained state'
            restored.locator('#file-restore').set_input_files(str(packet_file))
            restored.wait_for_function('CantosDesk.view().deliveries.length === 2')
            restored_view=restored.evaluate('CantosDesk.view()')
            assert restored_view['deliveries']==final['deliveries'],'Independent restore lost history'
            assert restored_view['recommendation']==final['recommendation'],'Independent restore changed conclusion'
            assert [r for r in restored_view['records'] if r['role']=='measurement']==measurements
            for name,payload in [('malformed','{not JSON'),('tampered',self.tamper(packet_text))]:
                before=restored.evaluate('CantosDesk.exportPacket()')
                restored.evaluate('document.querySelector("#toast").hidden=true')
                restored.locator('#file-restore').set_input_files({'name':name+'.json','mimeType':'application/json','buffer':payload.encode()})
                restored.wait_for_function('document.querySelector("#toast").hidden === false && document.querySelector("#toast").style.borderLeftColor === "var(--bad)"')
                after=restored.evaluate('CantosDesk.exportPacket()')
                assert json.loads(after['text'])==json.loads(before['text']),f'{name} import destroyed current work'
            restored.screenshot(path=str(self.out/'independent-restore.png'),full_page=True)
            return {'issued_versions':2,'first_sha256':final['deliveries'][0]['snapshot_hash'],'second_sha256':final['deliveries'][1]['snapshot_hash'],
                    'restore':'Fresh browser context, file navigation, actual file upload',
                    'refusals':['unreviewed freeze','stale accept','stale freeze','successor without review','malformed packet','tampered packet']}
        finally:
            context.close()
            if fresh:
                fresh.close()

    @staticmethod
    def tamper(text):
        packet=json.loads(text)
        if 'workspace' in packet:
            packet['workspace']['label']='Tampered workspace'
        elif 'packet' in packet:
            packet['packet']['workspace']['label']='Tampered workspace'
        else:
            raise AssertionError('Packet envelope shape unrecognized; mutation check cannot be claimed')
        return json.dumps(packet)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    raise SystemExit(Qualification(args.artifact,args.out).run())
