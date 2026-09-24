import copy, hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path
S=Path(__file__).resolve().parents[1]/'scripts/campaign_intake.py'
spec=importlib.util.spec_from_file_location('campaign_intake',S); ci=importlib.util.module_from_spec(spec); spec.loader.exec_module(ci)

class CampaignIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        d=self.root/'arm'; (d/'grade').mkdir(parents=True)
        self.detail={'synthetic':False,'completed':3,'errors':['','','','failed'],'ttfts':[.1,.2,2,None],'latencies':[1,2,3,None],'queue_times':[0,0,0,0]}
        self.put('arm/detailed.json',self.detail); self.put('arm/grade/mapping.json',{})
        for suite in ['humaneval','mbpp']: self.put('arm/grade/'+suite+'_eval_results.json',{})
        self.grade={'schema':'hot-aisle/request-evaluation@1','synthetic':False,'criterion_id':'unit-test-evaluator','source_sha256':self.hash('arm/detailed.json'),'mapping_sha256':self.hash('arm/grade/mapping.json'),'result_sha256':{s:self.hash('arm/grade/'+s+'_eval_results.json') for s in ['humaneval','mbpp']},'passed':[True,False,True,False]}
        self.put('arm/grade/evaluation.json',self.grade)
        self.ledger={'schema':'second-run/run-ledger@1','identity':{'run_id':'r1','provider':'p','seat_id':'s1','sku':'gpu1','region':'r','gpus':1,'model':{},'runtime':{},'workload_id':'w'},'work':{'attempted':4,'completed':3,'correct':2,'accepted':1,'evaluator':{'criterion_id':'unit-test-evaluator','frozen':True},'acceptance_rule':{'correctness':True,'queue':True,'ttft_ms':1000,'e2e_ms':60000}},'clocks':{},'money':{'modeled_usd':2,'billed_usd':None}}
        self.put('arm/ledger.json',self.ledger)
        self.spec={'schema':'secondrun.campaign-intake-spec.v1','runs':[{'directory':'arm','ledger':'arm/ledger.json','role':'scored_arm'}]}
    def put(self,name,value):
        (self.root/name).write_text(json.dumps(value),encoding='utf-8')
    def hash(self,name): return ci.sha((self.root/name).read_bytes())
    def run_intake(self): return ci.build(self.root,self.spec)
    def test_real_intake_recomputes_and_holds(self):
        r=self.run_intake(); self.assertEqual(r['runs'][0]['counts'],{'attempted':4,'completed':3,'correct':2,'accepted':1}); self.assertEqual(r['challenge_status'],'HOLD'); self.assertIsNone(r['runs'][0]['whole_bill_share_usd'])
    def test_duplicate_run_refused(self):
        self.spec['runs']*=2
        with self.assertRaises(ci.IntakeError): self.run_intake()
    def test_path_escape(self):
        self.spec['runs'][0]['directory']='../outside'
        with self.assertRaises(ci.IntakeError): self.run_intake()
    def test_mutations_refused(self):
        cases=[('synthetic',lambda d,g,l:d.update(synthetic=True)),('tampered-detail',lambda d,g,l:d.update(duration=999)),('sidecar',lambda d,g,l:g.update(source_sha256='0'*64)),('mapping',lambda d,g,l:g.update(mapping_sha256='0'*64)),('count',lambda d,g,l:l['work'].update(accepted=3)),('criterion',lambda d,g,l:g.update(criterion_id='different')),('judgment',lambda d,g,l:g.update(passed=[1,False,True,False])),('array',lambda d,g,l:g.update(passed=[True])),('queue',lambda d,g,l:l['work']['acceptance_rule'].update(queue=False))]
        for label,fn in cases:
            with self.subTest(label=label):
                d,g,l=copy.deepcopy((self.detail,self.grade,self.ledger)); fn(d,g,l)
                self.put('arm/detailed.json',d); self.put('arm/grade/evaluation.json',g); self.put('arm/ledger.json',l)
                with self.assertRaises(ci.IntakeError): self.run_intake()
    def bill(self):
        (self.root/'receipt.txt').write_text('test allocation invoice',encoding='utf-8')
        return {'schema':'secondrun.allocation-bill.v1','allocation_id':'s1','currency':'USD','complete_run_roster':True,'receipt_path':'receipt.txt','receipt_sha256':self.hash('receipt.txt'),'gross_charge_usd':10,'credits_usd':6,'cash_charge_usd':4,'line_items':[{'category':'compute','amount_usd':8},{'category':'storage','amount_usd':2}],'run_shares':{'r1':1},'allocation_basis':'Single run owns entire lease including setup, idle and storage.'}
    def test_invoice_reconciles_and_stays_separate(self):
        r=ci.build(self.root,self.spec,[self.bill()]); x=r['runs'][0]
        self.assertEqual(x['whole_bill_share_usd'],10); self.assertEqual(x['credits_share_usd'],6); self.assertEqual(x['cash_share_usd'],4); self.assertEqual(x['native_money']['modeled_usd'],2); self.assertEqual(r['challenge_status'],'HOLD')
    def test_bill_mutations_refused(self):
        for key,value in [('cash_charge_usd',5),('credits_usd',11),('run_shares',{'r1':2}),('complete_run_roster',False),('receipt_sha256','0'*64),('currency','EUR'),('gross_charge_usd',float('nan')),('line_items',[{'amount_usd':9}]),('allocation_id','other'),('allocation_basis','')]:
            with self.subTest(key=key):
                b=self.bill(); b[key]=value
                with self.assertRaises(ci.IntakeError): ci.build(self.root,self.spec,[b])
    def test_duplicate_bill_refused(self):
        b=self.bill()
        with self.assertRaises(ci.IntakeError): ci.build(self.root,self.spec,[b,b])
    def test_shared_seat_billed_once(self):
        runs=self.run_intake()['runs']; second=copy.deepcopy(runs[0]); second['run_id']='r2'; runs.append(second)
        b=self.bill(); b['run_shares']={'r1':.25,'r2':.75}; ci.reconcile_bills(self.root,runs,[b])
        self.assertEqual([x['whole_bill_share_usd'] for x in runs],[2.5,7.5]); self.assertEqual(sum(x['whole_bill_share_usd'] for x in runs),10)
    def test_plain_level_of_cost_never_counts_as_bill(self):
        r=self.run_intake(); self.assertEqual(r['allocation_bills'],[]); self.assertEqual(r['runs'][0]['billing_status'],'AWAITING_ALLOCATION_BILL')

if __name__=='__main__': unittest.main()
