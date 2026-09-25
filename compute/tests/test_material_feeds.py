import copy
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('feeds',ROOT/'scripts/material_feeds.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)
RAW=(ROOT/'materials/registry.json').read_bytes()
HASH=hashlib.sha256(RAW).hexdigest()
NOW=datetime(2026,9,24,20,0,tzinfo=timezone.utc)

def response(source):
    return (json.dumps([dict(tag_name='v1',published_at='2026-09-20T00:00:00Z',prerelease=False)]).encode()
            if source['kind']=='github_releases' else b'<html>source</html>')

class MaterialFeedTests(unittest.TestCase):
    def setUp(self):self.reg=F.load_registry(RAW)
    def run_collect(self, **kw):return F.collect(self.reg,HASH,now=NOW,fetcher=response,**kw)
    def reject(self, change):
        reg=copy.deepcopy(self.reg);change(reg)
        with self.assertRaises(ValueError):F.load_registry(json.dumps(reg).encode())
    def test_registry_counts_and_complete_recipe_dependencies(self):
        self.assertEqual(len(self.reg['sources']),25);self.assertEqual(len(self.reg['recipes']),4)
    def test_localhost_refused(self):self.reject(lambda r:r['sources'][0].update(url='https://127.0.0.1/secrets'))
    def test_http_refused(self):self.reject(lambda r:r['sources'][0].update(url='http://hotaisle.xyz/'))
    def test_credentials_refused(self):self.reject(lambda r:r['sources'][0].update(url='https://u:p@hotaisle.xyz/'))
    def test_custom_port_refused(self):self.reject(lambda r:r['sources'][0].update(url='https://hotaisle.xyz:444/'))
    def test_duplicate_id_refused(self):self.reject(lambda r:r['sources'].append(r['sources'][0]))
    def test_unknown_dependency_refused(self):self.reject(lambda r:r['recipes'][0]['sources'].append('missing'))
    def test_ttl_boolean_refused(self):self.reject(lambda r:r['sources'][0].update(ttl_seconds=True))
    def test_new_observations_have_no_dispatch_authority(self):
        x=self.run_collect();self.assertEqual(x['summary']['observed'],25)
        self.assertTrue(all(o['change']=='NEW' for o in x['observations']))
        self.assertIn('No live inventory',x['boundary'])
    def test_unchanged(self):
        x=self.run_collect();y=self.run_collect(previous=x)
        self.assertTrue(all(o['change']=='UNCHANGED' for o in y['observations']))
    def test_doc_change_requires_review(self):
        x=self.run_collect();y=F.collect(self.reg,HASH,x,lambda s:b'<html>new</html>' if s['kind']=='document' else response(s),NOW)
        self.assertEqual(y['observations'][0]['change'],'CHANGED')
    def test_release_reformat_not_semantic_change(self):
        x=self.run_collect()
        y=F.collect(self.reg,HASH,x,lambda s:json.dumps(json.loads(response(s)),indent=4).encode() if s['kind']=='github_releases' else response(s),NOW)
        self.assertTrue(all(o['change']=='UNCHANGED' for o in y['observations']))
    def test_failure_preserves_timestamp_and_old_digest(self):
        x=self.run_collect()
        def fail(_):raise TimeoutError('bounded timeout')
        y=F.collect(self.reg,HASH,x,fail,NOW+timedelta(days=2))
        self.assertEqual(y['summary']['unavailable'],25)
        self.assertEqual(y['observations'][0]['last_good'],x['observations'][0]['last_good'])
    def test_registry_change_does_not_reuse_unbound_observation(self):
        x=self.run_collect();x['registry_sha256']='a'*64
        def fail(_):raise ValueError('blocked')
        y=F.collect(self.reg,HASH,x,fail,NOW)
        self.assertFalse(y['previous_compatible']);self.assertIsNone(y['observations'][0]['last_good'])
    def test_error_does_not_disappear_among_success(self):
        def mixed(s):
            if s['id']=='ha-price':raise ValueError('403')
            return response(s)
        x=F.collect(self.reg,HASH,fetcher=mixed,now=NOW)
        self.assertEqual(x['summary'],dict(observed=24,unavailable=1))
    def test_oversized_document_refused(self):
        with self.assertRaises(ValueError):F.identity(self.reg['sources'][0],b'x'*(F.MAX_BYTES+1))
    def test_empty_document_refused(self):
        with self.assertRaises(ValueError):F.identity(self.reg['sources'][0],b'')
    def test_bad_release_json_refused(self):
        with self.assertRaises(ValueError):F.identity(self.reg['sources'][-1],b'{}')
    def test_no_release_is_empty_metadata_not_fake_version(self):
        x=F.identity(self.reg['sources'][-1],b'[]');self.assertEqual(x['releases'],[])
    def test_future_release_held(self):
        def future(s):return b'[{"tag_name":"v2","published_at":"2099-01-01T00:00:00Z"}]' if s['kind']=='github_releases' else response(s)
        x=F.collect(self.reg,HASH,fetcher=future,now=NOW)
        self.assertEqual(x['summary']['unavailable'],8)
    def test_old_operator_capture_keeps_original_time(self):
        old=NOW-timedelta(days=10)
        def old_data(s):return dict(raw=response(s),observed_at=old.isoformat())
        x=F.collect(self.reg,HASH,fetcher=old_data,now=NOW)
        g=x['observations'][0]['last_good'];self.assertEqual(F.stamp(g['observed_at']),old)
        self.assertLess(F.stamp(g['expires_at']),NOW)
    def test_future_operator_capture_refused(self):
        def future(s):return dict(raw=response(s),observed_at='2099-01-01T00:00:00Z')
        x=F.collect(self.reg,HASH,fetcher=future,now=NOW)
        self.assertEqual(x['summary']['observed'],0)
    def test_no_raw_documents_or_release_bodies_emitted(self):
        data=json.dumps(self.run_collect());self.assertNotIn('<html>',data);self.assertNotIn('release_body',data)
    def test_redirect_refused(self):
        with self.assertRaises(ValueError):F.NoRedirect().redirect_request(None,None,302,None,None,'http://127.0.0.1')

if __name__=='__main__':unittest.main()
