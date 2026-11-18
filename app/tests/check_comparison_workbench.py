"""Independent recipient: frozen evidence -> native review -> immutable reanalysis."""
from pathlib import Path
import hashlib, importlib.util, json, subprocess, sys, tempfile, threading, urllib.request
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]

def main():
    sys.path.insert(0, str(ROOT/'compute/maintainer'))
    from packets import unpack_owner
    with tempfile.TemporaryDirectory(prefix='cantos-comparison-recipient-') as tmp:
        root = Path(tmp)
        package = unpack_owner(ROOT/'public/open-compute/open-compute-workbench.zip',root/'owner')
        spec = importlib.util.spec_from_file_location('comparison_recipient_engine',package/'engine/engine.py')
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        ledger = engine.Ledger(package, root/'store')
        server = ThreadingHTTPServer(('127.0.0.1',0),engine.handler_for(ledger))
        origin = 'http://127.0.0.1:'+str(server.server_port)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path, value=None, binary=False):
            data = None if value is None else json.dumps(value).encode()
            req = urllib.request.Request(origin+path,data=data,headers={'Origin':origin,'Content-Type':'application/json'})
            with opener.open(req,timeout=90) as response:
                body = response.read()
                return body if binary else json.loads(body)
        try:
            initial = request('/api/comparison/example',{})
            assert initial['kind']=='maintainer-comparison' and not initial['post_hoc']
            assert initial['native']['verdict']=='incomparable'
            assert initial['native']['policy']['min_baseline_acceptance']==.8
            for side in ('baseline','candidate'):
                assert initial['native'][side]['accepted_tasks']==21
                assert initial['native'][side]['total_tasks']==96
            assert request('/api/comparison/example',{})['id']==initial['id']
            policy = dict(initial['native']['policy'])
            policy['prices']={'baseline_per_hour':2.,'candidate_per_hour':4.}
            changed = request('/api/comparison/reanalyze',{'id':initial['id'],'policy':policy})
            assert changed['post_hoc'] and changed['parent_id']==initial['id']
            assert changed['original_id']==initial['id'] and changed['id']!=initial['id']
            assert changed['native']['verdict']=='incomparable'
            assert changed['observation_hashes']==initial['observation_hashes']
            assert changed['execution']['inference_requests']==0
            old = request('/api/export/'+initial['id'])
            assert old['native']==initial['native'] and not old['post_hoc']
            exported = request('/api/export/'+changed['id'])
            assert exported['post_hoc'] and exported['native']['policy']==changed['native']['policy']
            archive = request('/api/comparison/'+changed['id']+'/bundle',binary=True)
            assert hashlib.sha256(archive).digest()==hashlib.sha256((package/'comparisons/frozen-vllm.zip').read_bytes()).digest()
            history = request('/api/history')
            assert len(history['items'])==2
            print(json.dumps({'status':'passed','native_verdict':'incomparable','accepted_per_arm':21,
                'offered_per_arm':96,'original_requirement':.8,'history_editions':2,'new_inference_requests':0,
                'boundary':'Extracted public workbench over real loopback HTTP; original and post-hoc receipts plus exact original evidence export.'}))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

if __name__=='__main__':
    main()
