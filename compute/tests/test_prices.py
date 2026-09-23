import importlib.util,json,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('review',R/'scripts/review_prices.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PriceReview(unittest.TestCase):
 def setUp(self):self.c=json.loads((R/'data/catalog.json').read_text(encoding='utf-8'))
 def test_hidden_script_not_price_evidence(self):self.assertEqual(m.plain('<script>$1.00</script><p>GPU $2.00</p>'),'GPU $2.00')
 def test_missing_source_fail_loud(self):self.assertEqual(m.review(self.c,{})['state'],'REVIEW_REQUIRED')
 def test_changed_price_not_silently_accepted(self):o=self.c['offers'][0];r=m.observe('MI300X $9.99',[o])[0];self.assertEqual(r['state'],'REVIEW_REQUIRED')
 def test_present_price_not_semantic_verification(self):o=self.c['offers'][0];r=m.observe('MI300X $2.99',[o])[0];self.assertEqual(r['state'],'EXPECTED_TOKENS_PRESENT');self.assertFalse(r['semantic_price_verified'])
 def test_date_never_renewed(self):r=m.review(self.c,{});self.assertEqual(r['catalog_reviewed_on'],'2026-09-22');self.assertFalse(r['price_date_renewed'])
 def test_foreign_gpu_values_do_not_pass(self):o=self.c['offers'][0];r=m.observe('H100 $2.99',[o])[0];self.assertEqual(r['state'],'REVIEW_REQUIRED')
 def test_expected_future_and_current_needed(self):o=next(x for x in self.c['offers'] if x['id']=='nb-h100');r=m.observe('H100 $3.85 current $4.50 future',[o])[0];self.assertEqual(r['state'],'EXPECTED_TOKENS_PRESENT')
if __name__=='__main__':unittest.main()
