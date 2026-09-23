#!/usr/bin/env python3
"""Pinned upstream run() control-flow probes; dependencies are mocked. No host audit."""
from __future__ import annotations
import argparse, contextlib, hashlib, importlib.util, io, json, sys, tempfile, types
from pathlib import Path
from unittest.mock import patch
COMMIT='97865af001e5bbf2f0ea5672ec0f8c0d7fb123f4'
BLOB='b8086eccad5ceb4bf65325355a47209d49bc1aa7'
URL=f'https://github.com/SemiAnalysisAI/ClusterMAX/blob/{COMMIT}/cmax/audit_runner.py'

def probe(path: Path):
    source=path.read_bytes()
    blob=hashlib.sha1(b'blob '+str(len(source)).encode()+b'\0'+source).hexdigest()
    if blob!=BLOB: raise ValueError('Upstream source differs from pinned Git blob; review it as a new target.')
    cmax=types.ModuleType('cmax')
    modules={name:types.ModuleType('cmax.'+name) for name in ['audit_report','progress','runtime_paths','security']}
    for name,m in modules.items():setattr(cmax,name,m)
    audit_report,progress,runtime_paths,security=[modules[x] for x in ['audit_report','progress','runtime_paths','security']]
    security.SecurityAuditError=type('SecurityAuditError',(RuntimeError,),{})
    audit_report.FAIL='fail'
    progress.AuditProgress=lambda *a,**k:None
    progress.audit_plan=lambda *a,**k:[]
    progress.print_failure_tail=lambda output:None
    results=[]
    fixtures=[('default_fail','fail',False,0,True,0),('gating_fail','fail',True,0,True,2),
      ('gating_warning','warning',True,0,True,0),('gating_skipped','skipped',True,0,True,0),
      ('gating_pass','pass',True,0,True,0),('collector_failure','pass',True,7,True,'AuditError'),
      ('missing_artifact','pass',True,0,False,'AuditError')]
    with patch.dict(sys.modules,{'cmax':cmax,**{'cmax.'+k:v for k,v in modules.items()}}):
        spec=importlib.util.spec_from_file_location('secondrun_upstream_runner',path)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        for name,status,gating,collector_rc,artifact,expected in fixtures:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); target=types.SimpleNamespace(harness='standalone',environment='vm')
                security.find_runtime_root=lambda repo:root
                security.detect_target=lambda requested:target
                runtime_paths.audit_runner=lambda runtime:root/'not_executed.sh'
                audit_report.render=lambda *a,**k:status.upper()+' [synthetic reporter]'
                audit_report.evaluate=lambda *a,**k:[types.SimpleNamespace(status=status)]
                def collect(*a,**kwargs):
                    if artifact:
                        (Path(kwargs['env']['RUN_RESULTS_DIR'])/'audit.values.json').write_text('{}')
                    return collector_rc,'synthetic collector; no subprocess launched'
                progress.run_with_progress=collect
                stream=io.StringIO()
                with patch.object(mod,'_audit_dir',return_value=root/'audit'),contextlib.redirect_stdout(stream):
                    try:actual=mod.run(exit_on_fail=gating)
                    except mod.AuditError:actual='AuditError'
                results.append({'case':name,'synthetic_check_status':status,'exit_on_fail':gating,
                  'collector_exit':collector_rc,'artifact_present':artifact,'expected':expected,
                  'observed':actual,'expectation_met':actual==expected,
                  'stdout':stream.getvalue().replace(str(root),'<TEMP>')})
    return {'schema':'secondrun.upstream-control-flow-probes.v1','source_url':URL,
      'upstream_commit':COMMIT,'upstream_git_blob':blob,'source_sha256':hashlib.sha256(source).hexdigest(),
      'scope':'Exact upstream run() executed; collector, reporter and detection replaced by synthetic doubles.',
      'not_tested':['full CLI','real collectors','cloud hosts','provider ratings','ClusterMAX 3.0 private tests'],
      'finding':'Process success is not a coverage or all-checks-passed certificate. This is documented API behavior, not an exploit.',
      'cases':results,'expectations_met':sum(x['expectation_met'] for x in results),'cases_run':len(results)}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source',type=Path);ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    try:r=probe(args.source)
    except (OSError,ValueError) as exc:print(str(exc),file=sys.stderr);return 2
    text=json.dumps(r,indent=2)+'\n'
    if args.output:args.output.write_text(text,encoding='utf-8')
    else:print(text,end='')
    return 0 if r['expectations_met']==r['cases_run'] else 1
if __name__=='__main__':sys.exit(main())
