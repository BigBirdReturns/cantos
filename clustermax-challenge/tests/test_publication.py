"""Launch-day presentation/ledger regressions; no provider benchmark is run."""
import copy, hashlib, importlib.util, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import launch_ledger as ll
class Publication(unittest.TestCase):
    def setUp(self):
        self.ledger=json.loads((ROOT/'launch/claims-3.0.observed.json').read_text(encoding='utf-8'))
    def test_scoped_ledger_admitted(self):
        r=ll.validate_ledger(self.ledger)
        self.assertEqual(len(r['medals']),17); self.assertFalse(r['has_sources'])
    def test_unknown_observation_tier_rejected(self):
        self.ledger['medals']['Nebius']['medal']='Diamond'
        with self.assertRaises(ll.InvalidLedger): ll.validate_ledger(self.ledger)
    def test_limitation_required(self):
        del self.ledger['medals']['Nebius']['scope']['limitation']
        with self.assertRaises(ll.InvalidLedger): ll.validate_ledger(self.ledger)
    def test_source_required_for_unreviewed(self):
        del self.ledger['medals']['Nebius']['test_dates']['source']
        with self.assertRaises(ll.InvalidLedger): ll.validate_ledger(self.ledger)
    def test_ribbon_observation_never_extends_transform(self):
        p={'rating_name':'ClusterMAX','rating_version':'3.0','trials':[{'provider_id':'Vultr'}]}
        with self.assertRaises(ll.InvalidLedger): ll.build_binding_draft(self.ledger,p,'a'*64)
    def test_unavailable_is_not_quality(self):
        p={'rating_name':'ClusterMAX','rating_version':'3.0','trials':[{'provider_id':'Fluidstack'}]}
        with self.assertRaises(ll.InvalidLedger): ll.build_binding_draft(self.ledger,p,'a'*64)
    def test_binding_wrong_version_rejected(self):
        p={'rating_name':'ClusterMAX','rating_version':'2.1','trials':[{'provider_id':'Nebius'}]}
        with self.assertRaises(ll.InvalidLedger): ll.build_binding_draft(self.ledger,p,'a'*64)
    def test_binding_supported_tier(self):
        p={'rating_name':'ClusterMAX','rating_version':'3.0','trials':[{'provider_id':'Nebius'}]}
        self.ledger['rubric_source']=copy.deepcopy(self.ledger['methodology_source'])  # synthetic test citation only
        b=ll.build_binding_draft(self.ledger,p,'a'*64)
        self.assertEqual(b['medals'],{'Nebius':'Platinum'})
    def test_public_copy_scope(self):
        h=(ROOT/'index.html').read_text(encoding='utf-8')
        self.assertIn('ClusterMAX 3.0 is out',h)
        self.assertNotIn('9 publish status history',h)
        self.assertNotIn('When ClusterMAX 3.0 ships',h)
        self.assertNotIn('We could find no published study',h)
        self.assertIn('$200',h); self.assertIn('managed-cluster',h)
    def test_submission_route(self):
        t=(ROOT/'SUBMITTING.md').read_text(encoding='utf-8')
        self.assertIn('https://github.com/BigBirdReturns/axm-tools/issues/new?template=clustermax-outcomes.yml',t)
    def test_original_transform_unchanged(self):
        t=json.loads((ROOT/'design/transform.json').read_text(encoding='utf-8'))
        self.assertNotIn('Participation Ribbon',json.dumps(t))
    def test_no_full_copyrighted_page_redistributed(self):
        self.assertFalse((ROOT/'launch/sources-20260923/newsletter.html').exists())
    def test_unverified_rubric_blocks_binding(self):
        p={'rating_name':'ClusterMAX','rating_version':'3.0','trials':[{'provider_id':'Nebius'}]}
        with self.assertRaises(ll.InvalidLedger): ll.build_binding_draft(self.ledger,p,'a'*64)
    def test_primary_ranking_digest_matches_retained_bytes(self):
        p=ROOT/'launch/release-3.0/raw/neocloud-ranking-v3.0-newsletter-source.png'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),self.ledger['medal_table_source']['sha256'])
if __name__=='__main__': unittest.main()
