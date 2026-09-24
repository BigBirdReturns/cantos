"""Offline Run 3 tests; all temporary outputs stay under this lane."""
import copy
import http.server
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import threading
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
import arm
from common import encoded, jsonl, read_json, sha, write_json
import convert
import grade
import replay
import workload

HERE = Path(__file__).resolve().parent
FIX = HERE/'fixtures'


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.root = HERE / ('.selftest-' + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(self.clean_temp)
        self.tasks = self.root/'tasks.json'
        self.frozen = workload.build(FIX/'humaneval.jsonl', FIX/'mbpp.jsonl',
            {d:sha(FIX/(d+'.jsonl')) for d in ('humaneval','mbpp')}, self.tasks, fixture=True)

    def clean_temp(self):
        assert self.root.resolve().parent == HERE.resolve()
        shutil.rmtree(self.root)

    def evidence(self):
        directory=self.root/'replay'; directory.mkdir()
        specs=[]; rows=[]
        for i in range(6):
            spec=dict(request_index=i, task_id=self.frozen['tasks'][i%5]['task_id'], seed=700000+i, scheduled_ts=1000+i*300)
            specs.append(spec)
            row=dict(spec,send_ts=spec['scheduled_ts']+(2 if i==2 else 0.01), first_token_ts=spec['scheduled_ts']+(2.1 if i==2 else 0.1),
                end_ts=spec['scheduled_ts']+3, output_text=f'    return x + {i}\n', input_tokens=20, output_tokens=4, finish_reason='stop',error='')
            if i==4:
                row.update(error='HTTP 500',first_token_ts=None,output_tokens=None,input_tokens=None)
            rows.append(row)
        plan=dict(schema='second-run/replay-plan@1',synthetic=True,start_ts=1000,duration_s=3600,
            rate_factor=0.1,trace_sha256=sha(FIX/'code-slice.csv'),trace_start='2023-11-16T00:00:00Z',tasks_sha256=sha(self.tasks),workers=256,requests=specs)
        write_json(directory/'plan.json',plan)
        (directory/'journal.jsonl').write_bytes(b''.join(encoded(r) for r in rows))
        detail=self.root/'detailed.json';convert.convert(directory,detail)
        return directory,detail

    def grading(self):
        directory, detail=self.evidence()
        output=self.root/'grade'
        mapping=grade.prepare(self.tasks,directory/'requests.jsonl',detail,output)
        # Actual EvalPlus 0.3.1 result shape; ordered within task, not global order.
        for dataset,meta in mapping['datasets'].items():
            result={'hash':meta['reference_md5'],'eval':{}}
            for sample,n in zip(jsonl(output/(dataset+'.jsonl')),meta['request_indices']):
                result['eval'].setdefault(sample['task_id'],[]).append(dict(sample,base_status='pass',
                    plus_status='pass' if n in (0,2,4,5) else 'fail'))
            write_json(output/(dataset+'_eval_results.json'),result)
        return directory,detail,output


class WorkloadTests(FixtureCase):
    def test_five_frozen_tasks_and_determinism(self):
        self.assertEqual(len(self.frozen['tasks']),5)
        other=self.root/'again.json'
        workload.build(FIX/'humaneval.jsonl',FIX/'mbpp.jsonl',{d:sha(FIX/(d+'.jsonl')) for d in ('humaneval','mbpp')},other,True)
        self.assertEqual(sha(self.tasks),sha(other))
        self.assertIn('plus_input',json.loads(self.frozen['tasks'][0]['grading_reference']['record_raw']))

    def test_hash_and_count_and_overwrite_refused(self):
        hashes={d:sha(FIX/(d+'.jsonl')) for d in ('humaneval','mbpp')}
        with self.assertRaises(ValueError):
            workload.build(FIX/'humaneval.jsonl',FIX/'mbpp.jsonl',dict(hashes,humaneval='UNVERIFIED'),self.root/'x',True)
        with self.assertRaises(ValueError):
            workload.build(FIX/'humaneval.jsonl',FIX/'mbpp.jsonl',hashes,self.root/'x')
        with self.assertRaises(FileExistsError):
            workload.build(FIX/'humaneval.jsonl',FIX/'mbpp.jsonl',hashes,self.tasks,True)


class FakeServer(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):
        pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.payloads.append(payload)
        if self.server.mode=='http-error':
            self.send_response(503);self.send_header('Content-Length','0');self.end_headers();return
        self.send_response(200);self.send_header('Content-Type','text/event-stream')
        self.send_header('Connection','close');self.end_headers()
        chunks=[{'choices':[{'text':'','finish_reason':None}]},
                {'choices':[{'text':'    return x\n','finish_reason':None}]},
                {'choices':[{'text':'','finish_reason':'stop'}]},
                {'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':4}}]
        try:
            if self.server.mode=='slow':time.sleep(.3)
            for item in chunks:
                if self.server.mode=='no-usage' and 'usage' in item:continue
                self.wfile.write(b'data: '+encoded(item)+b'\n');self.wfile.flush()
            if self.server.mode!='truncated':self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
        except OSError:pass
        self.close_connection=True


class ReplayTests(FixtureCase):
    def setUp(self):
        super().setUp()
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),FakeServer)
        self.server.mode='good';self.server.payloads=[]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.endpoint=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()

    def test_schedule_scaling_coverage_and_boundary(self):
        args=(FIX/'code-slice.csv',sha(FIX/'code-slice.csv'),'2023-11-16T00:00:00Z')
        offsets=replay.schedule(*args,1,duration=.1)
        self.assertEqual(len(offsets),5)
        self.assertEqual(len(replay.schedule(*args,2,duration=.1)),6)
        with self.assertRaises(ValueError):replay.schedule(*args,float('nan'))
        with self.assertRaises(ValueError):replay.schedule(*args,2)

    def test_stream_records_usage_and_sampling(self):
        row=replay.request(self.endpoint,self.frozen['tasks'][0],7,time.time(),timeout=1)
        self.assertEqual(row['error'],'');self.assertEqual(row['output_tokens'],4)
        self.assertLessEqual(row['send_ts'],row['first_token_ts']);self.assertLessEqual(row['first_token_ts'],row['end_ts'])
        sent=self.server.payloads[0]
        self.assertEqual(sent['temperature'],.2);self.assertEqual(sent['seed'],7)
        self.assertNotIn('ignore_eos',sent);self.assertEqual(sent['prompt'],self.frozen['tasks'][0]['prompt'])

    def test_errors_truncation_usage_timeout(self):
        for mode in ('http-error','truncated','no-usage','slow'):
            self.server.mode=mode
            row=replay.request(self.endpoint,self.frozen['tasks'][0],7,time.time(),timeout=.1)
            self.assertTrue(row['error'],mode)

    def test_actual_replay_distinct_seeds_and_buckets(self):
        plan,rows=replay.replay(self.tasks,FIX/'code-slice.csv',sha(FIX/'code-slice.csv'),
            '2023-11-16T00:00:00Z',1,self.root/'live',endpoint=self.endpoint,duration=.15,timeout=1,workers=8,fixture=True)
        self.assertEqual(len(rows),6);self.assertEqual(len({r['seed'] for r in rows}),6)
        self.assertTrue(all(not r['error'] for r in rows))
        self.assertEqual(rows[0]['task_id'],rows[5]['task_id'])
        self.assertEqual(read_json(self.root/'live'/'buckets.json')[0]['completed'],6)

    def test_recovery_keeps_missing_requests(self):
        directory,detail=self.evidence()
        journal=directory/'journal.jsonl';lines=journal.read_bytes().splitlines(keepends=True)
        journal.write_bytes(b''.join(lines[:2])+b'{"partial":')
        raw=convert.convert(directory,detail)
        self.assertEqual(raw['num_prompts'],6);self.assertEqual(raw['completed'],2)
        self.assertEqual(raw['metadata']['lost_requests'],0)
        self.assertEqual(raw['metadata']['send_unknown_requests'],4)
        self.assertEqual(raw['duration'],3600)

    def test_recovery_separates_sent_unsent_and_uncertain(self):
        directory,detail=self.evidence()
        plan=read_json(directory/'plan.json');plan['journal_events']=1
        write_json(directory/'plan.json',plan)
        rows=jsonl(directory/'journal.jsonl')
        events=[dict(plan['requests'][2],event='dispatch'),
                dict(plan['requests'][2],event='sent',send_ts=1600.01),
                dict(plan['requests'][3],event='dispatch')]
        (directory/'journal.jsonl').write_bytes(b''.join(encoded(r) for r in rows[:2]+events)+b'{"partial":')
        raw=convert.convert(directory,detail)
        self.assertEqual((raw['num_prompts'],raw['completed'],raw['failed']),(6,2,4))
        self.assertEqual(raw['metadata']['lost_requests'],1)
        self.assertEqual(raw['metadata']['never_sent_requests'],2)
        self.assertEqual(raw['metadata']['send_unknown_requests'],1)
        recovered=jsonl(directory/'requests.jsonl')
        self.assertEqual(recovered[2]['error'],'lost_after_send')
        self.assertEqual(recovered[2]['send_ts'],1600.01)
        self.assertEqual(recovered[3]['error'],'send_unknown_after_interrupt')
        self.assertEqual(recovered[4]['error'],'never_sent_after_interrupt')
        with (directory/'journal.jsonl').open('wb') as f:
            f.write(encoded(events[1]))
        with self.assertRaises(ValueError):replay.recover(directory)

    def test_overload_is_counted_and_not_queued(self):
        self.server.mode='slow'
        plan,rows=replay.replay(self.tasks,FIX/'code-slice.csv',sha(FIX/'code-slice.csv'),
            '2023-11-16T00:00:00Z',1,self.root/'overload',endpoint=self.endpoint,duration=.15,timeout=1,workers=1,fixture=True)
        self.assertEqual(len(rows),6)
        self.assertEqual(sum(r['error']=='client_concurrency_limit' for r in rows),5)
        self.assertTrue(all(r['send_ts'] is None for r in rows if r['error']))
        raw=convert.convert(self.root/'overload',self.root/'overload.json')
        self.assertEqual(raw['metadata']['never_sent_requests'],5)
        self.assertEqual(raw['metadata']['lost_requests'],0)
        self.assertGreater(raw['failed']/raw['num_prompts'],.01)


class GradeTests(FixtureCase):
    def test_repeat_join_and_page_engine(self):
        directory,detail,output=self.grading()
        sidecar=output/'evaluation.json'
        result=grade.join(self.tasks,directory/'requests.jsonl',detail,output,sidecar)
        self.assertEqual(result['passed'],[True,False,True,False,False,True])
        grade.summary(directory,sidecar,detail,output/'buckets.json')
        summary=read_json(output/'buckets.json')
        self.assertEqual(len(summary['buckets']),12)
        self.assertEqual(sum(b['accepted'] for b in summary['buckets']),2)
        run=subprocess.run(['node',str(HERE/'engine_check.cjs'),str(detail),str(sidecar),'--fixture'],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        print('ENGINE '+run.stdout.strip())

    def test_missing_result_is_not_a_false_grade(self):
        directory,detail,output=self.grading()
        path=output/'humaneval_eval_results.json';value=read_json(path)
        value['eval']['HumanEval/0'].pop();write_json(path,value)
        with self.assertRaises(ValueError):grade.join(self.tasks,directory/'requests.jsonl',detail,output,output/'evaluation.json')

    def test_stale_reference_or_reordered_solution_refused(self):
        directory,detail,output=self.grading()
        path=output/'humaneval_eval_results.json';value=read_json(path)
        value['eval']['HumanEval/0'].reverse();write_json(path,value)
        with self.assertRaises(ValueError):grade.join(self.tasks,directory/'requests.jsonl',detail,output,output/'evaluation.json')
        value['hash']='bad';write_json(path,value)
        with self.assertRaises(ValueError):grade.join(self.tasks,directory/'requests.jsonl',detail,output,output/'evaluation.json')

    def test_changed_raw_requests_refused(self):
        directory,detail,output=self.grading()
        with (directory/'requests.jsonl').open('ab') as f:f.write(b'\n')
        with self.assertRaises(ValueError):grade.join(self.tasks,directory/'requests.jsonl',detail,output,output/'evaluation.json')

    def test_unattempted_tasks_are_scaffolding_and_timeouts_fail(self):
        directory,detail=self.evidence()
        plan=read_json(directory/'plan.json');plan['requests']=plan['requests'][:1]
        write_json(directory/'plan.json',plan)
        (directory/'journal.jsonl').write_bytes(encoded(jsonl(directory/'journal.jsonl')[0]))
        convert.convert(directory,detail)
        output=self.root/'partial-grade'
        mapping=grade.prepare(self.tasks,directory/'requests.jsonl',detail,output)
        all_ids=[]
        for dataset,meta in mapping['datasets'].items():
            result={'hash':meta['reference_md5'],'eval':{}}
            all_ids+=meta['request_indices']
            for sample,n in zip(jsonl(output/(dataset+'.jsonl')),meta['request_indices']):
                result['eval'].setdefault(sample['task_id'],[]).append(dict(sample,base_status='timeout',plus_status='timeout'))
            write_json(output/(dataset+'_eval_results.json'),result)
        self.assertEqual(all_ids.count(None),4)
        result=grade.join(self.tasks,directory/'requests.jsonl',detail,output,output/'evaluation.json')
        self.assertEqual(result['passed'],[False])


class ArmTests(FixtureCase):
    def test_backend_real_and_authored_fixtures(self):
        result=arm.backends((FIX/'serve-amd.log').read_text())
        self.assertEqual(result['attention_backend'],['ROCM_ATTN'])
        self.assertEqual(result['linear_kernel'],['RowWiseTorchFP8ScaledMMLinearKernel'])
        exploration=arm.backends((FIX/'serve-amd-exploration.log').read_text())
        self.assertEqual(exploration['attention_backend'],['ROCM_AITER_FA'])
        self.assertEqual(exploration['linear_kernel'],result['linear_kernel'])
        self.assertEqual(arm.backends((FIX/'serve-nvidia.log').read_text())['attention_backend'],['FLASH_ATTN'])
        self.assertEqual(arm.backends('unrecognized')['attention_backend'],['UNVERIFIED'])
        unknown=arm.backends('Using FUTURE_BACKEND backend (selected via --attention-backend)')
        self.assertEqual(unknown['attention_backend'],['FUTURE_BACKEND'])
        self.assertEqual(len(arm.backend_holds(unknown)),2)
        self.assertEqual(arm.backend_holds(result),[])

    def test_vendor_tiers_and_watchdog(self):
        t0=arm.serve_command('amd','T0','fixture',Path('/tmp/cache'))
        t1=arm.serve_command('amd','T1','fixture',Path('/tmp/cache'))
        nv=arm.serve_command('nvidia','T0','fixture',Path('/tmp/cache'))
        self.assertIn('VLLM_ROCM_USE_AITER=1',t0);self.assertNotIn('--attention-backend',t0)
        self.assertIn('ROCM_AITER_FA',t1);self.assertNotIn('VLLM_ROCM_USE_AITER=1',nv)
        with self.assertRaises(ValueError):arm.serve_command('nvidia','T1','fixture',Path('/tmp/cache'))
        self.assertEqual(arm.REPLAY_TIMEOUT,3600+60+60)
        self.assertEqual(2400+120+arm.REPLAY_TIMEOUT+60+300,arm.WATCHDOG)

    def test_unknown_backend_continues_t0_but_stops_t1(self):
        full=self.root/'full.json'
        write_json(full,{'synthetic':False,'tasks':[{}]*542})
        for tier,log,expected in [('T0','unrecognized',0),('T1','unrecognized',1),
                                 ('T1','Using ROCM_AITER_FA backend (selected via --attention-backend)',0)]:
            out=self.root/('arm-'+tier+'-'+str(expected))
            argv=['arm.py','amd',tier,'--approved-run','--tasks',str(full),'--tasks-sha256',sha(full),
                  '--trace',str(FIX/'code-slice.csv'),'--trace-sha256',sha(FIX/'code-slice.csv'),
                  '--start','2023-11-16T00:00:00Z','--rate-factor','0.1','--out',str(out),
                  '--hf-cache',str(self.root/'cache'),'--t-ssh','2023-11-16T00:00:00Z']
            def run(cmd,**kwargs):
                data=log.encode() if cmd[1]=='logs' else b'0.30.0'
                return subprocess.CompletedProcess(cmd,0,stdout=data,stderr=b'')
            def urlopen(req,**kwargs):
                return io.BytesIO(encoded({'data':[{'id':arm.MODEL}], 'choices':[{'text':'smoke'}]}))
            child=mock.Mock();child.wait.return_value=0;child.poll.return_value=0
            with mock.patch.object(sys,'argv',argv), mock.patch.object(arm.subprocess,'run',side_effect=run), \
                 mock.patch.object(arm.subprocess,'Popen',return_value=child) as launch, \
                 mock.patch.object(arm.urllib.request,'urlopen',side_effect=urlopen), \
                 mock.patch.object(arm,'convert'), mock.patch.object(arm.signal,'signal'), \
                 mock.patch.object(arm.signal,'alarm',create=True):
                self.assertEqual(arm.main(),expected)
            self.assertTrue(read_json(out/'env.json')['holds'])
            self.assertEqual(read_json(out/'ledger.json')['schema'],'second-run/run3-arm-summary@1')
            if expected:
                launch.assert_not_called()
            else:
                launch.assert_called_once();child.wait.assert_called_once_with(timeout=3720)

    def test_startup_failure_seals_ledger_and_manifest(self):
        full=self.root/'full.json'
        write_json(full,{'synthetic':False,'tasks':[{}]*542})
        out=self.root/'failed-arm'
        argv=['arm.py','amd','T0','--approved-run','--tasks',str(full),'--tasks-sha256',sha(full),
              '--trace',str(FIX/'code-slice.csv'),'--trace-sha256',sha(FIX/'code-slice.csv'),
              '--start','2023-11-16T00:00:00Z','--rate-factor','0.1','--out',str(out),
              '--hf-cache',str(self.root/'cache'),'--t-ssh','2023-11-16T00:00:00Z']
        error=subprocess.CalledProcessError(1,['docker','pull'],output=b'fixture pull failed',stderr=b'')
        with mock.patch.object(sys,'argv',argv), mock.patch.object(arm.subprocess,'run',side_effect=error), \
             mock.patch.object(arm.signal,'signal'), mock.patch.object(arm.signal,'alarm',create=True):
            self.assertEqual(arm.main(),1)
        self.assertEqual(read_json(out/'ledger.json')['status'],'failed')
        self.assertIsNone(read_json(out/'ledger-times.json')['t_released'])
        self.assertEqual((out/'failed-command.log').read_bytes(),b'fixture pull failed')
        for line in (out/'MANIFEST.sha256').read_text().splitlines():
            digest,name=line.split('  ',1);self.assertEqual(sha(out/name),digest)

    def test_shell_and_container_contract(self):
        shell=(HERE/'arm3.sh').read_text();grader=(HERE/'grade.sh').read_text()
        self.assertIn('110m python3 -B',shell)
        self.assertIn('--self-test',shell);self.assertIn('--self-test',grader)
        self.assertIn('--network none',grader);self.assertIn('--build-image',grader)
        self.assertIn('evalplus==0.3.1',(HERE/'grader.Dockerfile').read_text())
        self.assertNotIn('pip install',shell)


if __name__=='__main__':
    unittest.main(verbosity=2)
