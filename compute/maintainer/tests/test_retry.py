"""Retry campaign checks use local protocol/grade fixtures, never GPU evidence."""
import copy
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import retry
from common import load, sha256_file
from test_instrument import Endpoint


class RetryCampaign(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.endpoint=Endpoint()
        identity={"implementation":{"name":"protocol fixture","revision":"1"},
                  "model":{"revision":"1","sha256":"a"*64},"tokenizer":{"revision":"1"},
                  "hardware":{"id":"fixture","description":"CPU HTTP fixture, no inference"},
                  "precision":"fixture","context_limit":4096,"settings":{}}
        self.arm={"base_url":self.endpoint.url,"model":"fixture-model","identity":identity}
        self.spec={"schema":"cantos.maintainer.spec/1","workload":"workload.json",
                   "protocol":{"trials":1,"repeats":1,"concurrency":1,"seed":11,"timeout_s":2},
                   "baseline":self.arm,"candidate":self.arm}
        self.work={"schema":"cantos.maintainer.workload/1","name":"fixture","version":"1",
                   "cases":[{"id":"case","messages":[{"role":"user","content":"fixture"}],
                             "expect":{"kind":"json_exact","value":{"value":2}}}]}
        self.rp={"schema":"cantos.maintainer.retry-policy/1","max_attempts":3,
                 "backoff_s":0.01,"retry_on":["rejected","transport_error"],"attempt_seed_stride":2}
        self.save()

    def save(self):
        for n,v in (("spec",self.spec),("workload",self.work),("retry-policy",self.rp)):
            (self.root/(n+".json")).write_text(json.dumps(v))

    def execute(self,name="run",grader=None):
        self.save()
        return retry.run(self.root/"spec.json","baseline",self.root/"retry-policy.json",
                         self.root/name,name,grader)

    def tearDown(self):
        self.endpoint.close()
        self.tmp.cleanup()

    def test_stops_after_first_success_and_has_all_clock_boundaries(self):
        value=self.execute()
        self.assertEqual(self.endpoint.requests,1)
        self.assertEqual(value["metrics"]["accepted_tasks"],1)
        self.assertEqual(value["metrics"]["retries_total"],0)
        self.assertEqual(value["metrics"]["first_pass_success_rate"],1)
        task=value["tasks"][0]
        self.assertGreaterEqual(task["duration_s"],task["attempts"][0]["duration_s"])
        self.assertGreaterEqual(value["campaign_duration_s"],task["duration_s"])
        self.assertEqual(value["timebase"],value["clock_identity"])
        self.assertEqual(retry.validate_campaign(self.root/"run")["metrics"],value["metrics"])

    def test_failed_work_counts_all_attempts_null_success_denominators_and_seed_schedule(self):
        self.endpoint.mode="wrong"
        value=self.execute()
        m=value["metrics"]
        self.assertEqual((m["offered_tasks"],m["accepted_tasks"],m["total_task_attempts"],m["retries_total"]),(1,0,3,2))
        self.assertEqual(m["total_http_requests"],3)
        self.assertIsNone(m["retries_per_accepted_task"])
        self.assertIsNone(m["mean_retries_among_successes"])
        self.assertGreaterEqual(value["tasks"][0]["duration_s"],0.02)
        seeds=[]
        for a in value["tasks"][0]["attempts"]:
            run=load(self.root/"run"/a["run"]["path"])
            seeds.append(run["protocol"]["seed"])
        self.assertEqual(seeds,[11,13,15])

    def test_early_sleep_return_still_satisfies_pinned_backoff(self):
        self.endpoint.mode="wrong"
        real_sleep=time.sleep
        calls=[]
        def early_return(seconds):
            calls.append(seconds)
            return real_sleep(min(seconds, 0.0001))
        with patch.object(retry.time, "sleep", side_effect=early_return):
            result=self.execute("early-sleep")
        self.assertEqual(result["metrics"]["retries_total"],2)
        self.assertGreater(len(calls),2)
        events=[json.loads(s) for s in (self.root/"early-sleep/events.jsonl").read_text().splitlines()]
        starts={e["attempt"]:e["monotonic_ns"] for e in events if e["event"]=="backoff_start"}
        ends={e["attempt"]:e["monotonic_ns"] for e in events if e["event"]=="backoff_end"}
        self.assertEqual(sorted(starts),[2,3])
        self.assertTrue(all((ends[n]-starts[n])/1e9 >= self.rp["backoff_s"] for n in starts))
        self.assertEqual(retry.validate_campaign(self.root/"early-sleep")["metrics"],result["metrics"])

    def test_task_queue_delay_is_recorded(self):
        self.endpoint.delay=0.04
        self.work["cases"].append({**copy.deepcopy(self.work["cases"][0]),"id":"second"})
        value=self.execute()
        self.assertGreater(max(t["queue_duration_s"] for t in value["tasks"]),0.03)
        self.assertEqual(value["metrics"]["first_pass_success_rate"],1)

    def test_metric_tamper_is_refused(self):
        self.execute()
        p=self.root/"run/retry-campaign.json"
        value=load(p);value["metrics"]["retries_total"]=999
        p.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,"summary"):
            retry.validate_campaign(p)

    def test_durable_unknown_request_never_authorizes_replay(self):
        p=self.root/"unknown";p.mkdir()
        j=retry.Journal(p/"events.jsonl")
        j.event("campaign_start")
        j.event("request_start",request_id="owned-attempt",task_instance="task",attempt=1,step=0)
        j.close()
        check=retry.inspect_journal(p)
        self.assertEqual(check["attempted_http_requests"],1)
        self.assertEqual(check["unknown_request_ids"],["owned-attempt"])
        self.assertFalse(check["automatic_replay_authorized"])
        self.assertEqual(self.endpoint.requests,0)

    def test_retry_controls_enter_identity_prices_do_not(self):
        first=retry.prepare(self.root/"spec.json","baseline",self.root/"retry-policy.json")
        self.spec["policy"]="policy.json"
        (self.root/"policy.json").write_text(json.dumps({"prices":{"baseline_per_hour":123}}))
        self.save()
        priced=retry.prepare(self.root/"spec.json","baseline",self.root/"retry-policy.json")
        self.assertEqual(first["observation_key"],priced["observation_key"])
        self.rp["max_attempts"]=4;self.save()
        other=retry.prepare(self.root/"spec.json","baseline",self.root/"retry-policy.json")
        self.assertNotEqual(first["observation_key"],other["observation_key"])

    def external_fixture(self):
        self.endpoint.mode="external"
        ref=self.root/"reference.jsonl"
        ref.write_text(json.dumps({"task_id":"case","prompt":"fixture reference","entry_point":"f"})+"\n")
        norm=Path(retry.__file__).parent/"normalize.py"
        self.work["cases"][0]["expect"]={"kind":"external","grader":{
            "name":"EvalPlus","revision":"0.3.1",
            "criterion":"humanevalplus-v0.1.10-base-and-plus-chat-complete-code-v1",
            "artifact_sha256":"1"*64,"reference_sha256":sha256_file(ref),"normalizer_sha256":sha256_file(norm)}}
        docker=self.root/"fixture-docker"
        docker.write_text("""#!/usr/bin/env python3
# Labeled protocol fixture: this never executes generated Python.
import hashlib,json,pathlib,sys
a=sys.argv[1:]
if a[:2]==['image','inspect']:
    print(json.dumps([{'Id':a[2],'fixture':True}]))
elif a[0]=='run':
    p=pathlib.Path(a[a.index('-v')+1].removesuffix(':/work'))
    ref=(p/'humaneval-reference.jsonl').read_bytes()
    samples=[json.loads(s) for s in (p/'humaneval.jsonl').read_text().splitlines()]
    result={'hash':hashlib.md5(ref).hexdigest(),'eval':{}}
    for s in samples:
        result['eval'].setdefault(s['task_id'],[]).append(
            {'task_id':s['task_id'],'solution':s['solution'],'base_status':'pass','plus_status':'pass'})
    (p/'humaneval_eval_results.json').write_text(json.dumps(result))
    print('CPU protocol fixture; no generated code executed')
elif a[0]=='stop':
    sys.exit(1)
else:
    sys.exit(2)
""")
        docker.chmod(0o700)
        return {"kind":"evalplus","reference":str(ref),"normalizer":str(norm),
                "docker":str(docker),"timeout_s":30}

    @unittest.skipUnless(os.name=="posix","existing EvalPlus owner is POSIX")
    def test_evalplus_adapter_reuses_real_binding_and_derives_exact_reference_subset(self):
        grader=self.external_fixture()
        value=self.execute(grader=grader)
        self.assertEqual(value["metrics"]["accepted_tasks"],1,value)
        a=value["tasks"][0]["attempts"][0]
        self.assertIsNotNone(a["grades"])
        grade=load(self.root/"run"/a["grades"]["path"])
        self.assertEqual(grade["results"][0]["accepted"],True)
        # Parent and deterministically serialized single-case child have separate pins.
        child_ref=self.root/"run"/Path(a["run"]["path"]).parent.parent/"inputs/reference.jsonl"
        self.assertNotEqual(sha256_file(child_ref),sha256_file(self.root/"reference.jsonl"))
        retry.validate_campaign(self.root/"run")
        self.assertEqual(self.endpoint.requests,1)

    def test_external_unknown_adapter_or_reference_refuses_before_network(self):
        grader=self.external_fixture()
        (self.root/"reference.jsonl").write_text('{"task_id":"different"}\n')
        self.save()
        with self.assertRaisesRegex(ValueError,"reference or normalizer"):
            retry.prepare(self.root/"spec.json","baseline",self.root/"retry-policy.json",grader)
        self.assertEqual(self.endpoint.requests,0)


if __name__=="__main__":
    unittest.main()
