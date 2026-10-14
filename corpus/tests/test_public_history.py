"""Checks for the published historical source projection and its source boundaries."""
import gzip, json, unittest
from pathlib import Path
from corpus import build_history as history
ROOT=Path(__file__).resolve().parents[2]
class PublicHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((ROOT/'corpus/history/manifest.json').read_text(encoding='utf-8'))
    def test_collection_totals_match_complete_source_manifest(self):
        m=self.manifest
        self.assertEqual(sum(s['count'] for s in m['sources']),m['total_rows'])
        self.assertEqual(sum(s['count'] for s in m['shards']),m['total_rows'])
        self.assertEqual(sum(m['counts'].values()),m['total_rows'])
        self.assertGreater(m['counts']['benchmarks'],100000)
        self.assertGreater(m['counts']['prices'],1000000)
    def test_original_producer_and_capture_times_remain_separate(self):
        shards=self.manifest['shards']
        for kind in ['benchmarks','issues','prices','research','traces','models','datasets']:
            sh=next(s for s in shards if s['kind']==kind)
            row=json.loads(gzip.decompress((ROOT/'corpus/history'/sh['file']).read_bytes()))[0]
            self.assertIn('date',row);self.assertIn('captured',row)
            self.assertIn('source',row);self.assertIn('row',row);self.assertIn('context',row)
    def test_research_is_bibliography_not_article_republication(self):
        for shard in (s for s in self.manifest['shards'] if s['kind']=='research'):
            rows=json.loads(gzip.decompress((ROOT/'corpus/history'/shard['file']).read_bytes()))
            for row in rows:
                self.assertTrue(row['title']);self.assertTrue(row['url'])
                self.assertNotIn('free_preview_text',row['context']);self.assertNotIn('verbatim_text',row['context'])
    def test_source_coordinates_are_portable(self):
        for s in self.manifest['sources']:
            self.assertNotIn('\\',s['file']);self.assertNotIn(':',s['file'])
            self.assertEqual(len(s['raw_sha256']),64)
        for s in self.manifest['shards']:
            self.assertTrue(s['file'].startswith('shards/'));self.assertNotIn('..',s['file'])
            self.assertLess(s['bytes'],25*1024*1024)
    def test_model_metadata_excludes_conversation_samples(self):
        s={'id':'dataset','kind':'datasets','label':'Dataset','raw_sha256':'a'*64,'evidence_class':'public_listing'}
        row=history.project(s,1,{'source':'metadata','dataset_id':'example','sample':{'messages':['private']},'provenance':{'url':'https://example.org/source','retrieved_at':'2026-01-01'}})
        self.assertNotIn('sample',row['context']);self.assertEqual(row['row'],1)
    def test_unsafe_urls_are_not_hyperlinks(self):
        self.assertIsNone(history.web_url('javascript:alert(1)'))
        self.assertIsNone(history.web_url('file:///private'))
        self.assertEqual(history.web_url('https://example.org'), 'https://example.org')
    def test_price_accounting_preserves_instance_and_gpu_units(self):
        s={'id':'prices','kind':'prices','label':'Price','raw_sha256':'a'*64,'evidence_class':'public_listing'}
        r=history.project(s,0,{'provider':'example','gpu':'H100','gpu_count':8,'hourly_price_usd':2,'instance_hourly_usd':16,'commitment_period':'annual','snapshot_ts':'2026-01-01'})
        self.assertEqual(r['value'],2);self.assertEqual(r['unit'],'USD/GPU-hour')
        self.assertEqual(r['context']['instance_hourly_usd'],16);self.assertEqual(r['context']['commitment_period'],'annual')
    def test_native_projection_owner_is_unchanged(self):
        self.assertEqual(self.manifest['native_projection_sha256'],history.sha(ROOT/'corpus/bulk_import.py'))
if __name__=='__main__':unittest.main()
