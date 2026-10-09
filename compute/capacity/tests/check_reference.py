#!/usr/bin/env python3
"""Cross-check Node-produced packets against separately written Python arithmetic."""
import hashlib,importlib.util,json,random,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('checker',ROOT/'check_math.py');checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
rng=random.Random(20261009);inputs=[]
for i in range(250):
    hours=rng.randint(1,87600);rate=None if i%7==0 else 0 if i%11==0 else rng.randint(1,1000000)/17
    inputs.append({'schema':'cantos/dedicated-capacity-scenario@0.1','asOf':'2026-10-09','label':'Independent arithmetic case '+str(i),'gpu':'Unmeasured','gpus':rng.randint(1,1024),'commitmentUSD':rng.randint(0,100000000)/100,'committedHours':hours,'productiveHours':0 if i%13==0 else hours*rng.random(),'acceptedPerProductiveHour':rate,'costs':{k:None if rng.random()<.25 else rng.randint(0,1000000)/100 for k in checker.COSTS},'acceptance':'Quality and deadline criteria remain untested.','runtime':'Target unqualified.'})
js="const A=require('./capacity.cjs'),crypto=require('node:crypto'),fs=require('node:fs');for(const x of JSON.parse(fs.readFileSync(0,'utf8'))){const body_json=A.canonical(A.body(x,2.99));console.log(JSON.stringify({schema:A.PACKET,body_json,sha256:crypto.createHash('sha256').update(body_json).digest('hex')}));}"
p=subprocess.run(['node','-e',js],input=json.dumps(inputs),cwd=ROOT,capture_output=True,text=True,check=True)
packets=[json.loads(line) for line in p.stdout.splitlines()];assert len(packets)==250
with tempfile.TemporaryDirectory(prefix='capacity-reference-') as tmp:
    f=Path(tmp)/'p.json'
    for packet in packets:
        f.write_text(json.dumps(packet));assert checker.check(f)['status']=='PASS'
    for key in ['known_cost_total','modeled_accepted','cost_per_1000_accepted']:
        packet=packets[1].copy();body=json.loads(packet['body_json']);body['result'][key]=-100
        packet['body_json']=json.dumps(body,ensure_ascii=False,separators=(',',':'));packet['sha256']=hashlib.sha256(packet['body_json'].encode()).hexdigest();f.write_text(json.dumps(packet))
        try:checker.check(f)
        except ValueError:pass
        else:raise AssertionError('Rehashed numerical tampering accepted: '+key)
print(json.dumps({'status':'PASS','reference_cases':250,'rehashed_numeric_tampering_rejections':3,'scope':'Independent arithmetic over generated inputs; no target workload or provider measurement.'},indent=2))
