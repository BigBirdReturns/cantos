"""Pairwise quality accounting with explicit comparability gates.

These are source-receipt comparisons, never a generic hardware or provider ranking.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .core import summarize, validate_record

IDENTITY_FIELDS=("workload_sha256","model_sha256","precision","context_limit")
def _index(receipt):
    return {(o["task_id"],o["repetition"]):o for o in receipt["observations"]}

def _template_modes(receipt):
    modes=set()
    for obs in receipt["observations"]:
        for attempt in obs["attempts"]:
            req=attempt.get("request") or {}
            if not isinstance(req,dict):continue
            modes.add(json.dumps(req.get("chat_template_kwargs",{}),sort_keys=True))
    return sorted(modes)

def compare(a,b):
    for value in (a,b):
        errors=validate_record(value)
        if errors:raise ValueError("invalid receipt: "+"; ".join(errors))
    x,y=_index(a),_index(b)
    sa,sb=summarize(a),summarize(b)
    wa,wb=a["workload"],b["workload"]
    pa,pb=a["provenance"],b["provenance"]
    deviations=[]
    for field in ("name","version","seed","repeats","fixture_sha256","concurrency","max_tokens"):
        if wa.get(field)!=wb.get(field):deviations.append("workload."+field)
    if set(x)!=set(y):deviations.append("task identities/repetitions")
    for field in ("model","model_sha256","runtime","precision","context_limit","hardware"):
        if pa.get(field)!=pb.get(field):deviations.append("provenance."+field)
    modes_a,modes_b=_template_modes(a),_template_modes(b)
    if modes_a!=modes_b:deviations.append("chat template options")
    def request_controls(r):
        # Messages contain task-specific text, but all other request controls
        # (sampling, server options, stream, token budget) affect comparability.
        controls=set()
        for obs in r["observations"]:
            for attempt in obs["attempts"]:
                req=attempt.get("request")
                if isinstance(req,dict):
                    controls.add(json.dumps({k:v for k,v in req.items() if k not in ("messages","model")},sort_keys=True))
        return sorted(controls)
    if request_controls(a)!=request_controls(b):deviations.append("request protocol controls")
    ev_a={o.get("evaluator_version") for o in a["observations"]}
    ev_b={o.get("evaluator_version") for o in b["observations"]}
    if ev_a!=ev_b:deviations.append("evaluator version")
    keys=sorted(set(x)&set(y))
    paircounts={"both_accepted":0,"a_only":0,"b_only":0,"both_failed":0}
    transitions=[]
    for key in keys:
        aa,bb=x[key]["accepted"],y[key]["accepted"]
        state="both_accepted" if aa and bb else "a_only" if aa else "b_only" if bb else "both_failed"
        paircounts[state]+=1
        transitions.append({"task_id":key[0],"repetition":key[1],"outcome":state,
          "a_error":x[key].get("error"),"b_error":y[key].get("error")})
    paired_workload=all(k not in deviations for k in
      ("workload.name","workload.version","workload.seed","workload.repeats","workload.fixture_sha256","task identities/repetitions","evaluator version"))
    controlled_hardware=paired_workload and not deviations
    return {"schema":"ocl.comparison/1","a_run_id":a["run_id"],"b_run_id":b["run_id"],
      "paired_task_accounting":paired_workload,"identical_execution_conditions":controlled_hardware,
      "deviations":deviations,"paired_counts":paircounts,"task_transitions":transitions,
      "a":sa,"b":sb,"a_template_options":modes_a,"b_template_options":modes_b,
      "classification":"controlled matched-conditions experiment" if controlled_hardware else
        "paired outcomes with changed conditions" if paired_workload else "descriptive nonpaired observations",
      "interpretation":"This comparison counts only exact accepted outcomes. Differences in templates, models, runtime or host are not hardware speedups; partial or unsupported variables forbid ranking.",
      "rate_uncertainty":"Small correlated synthetic fixtures do not support a population reliability estimate."}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("a");p.add_argument("b");p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    result=compare(json.loads(Path(args.a).read_text(encoding="utf-8")),
                   json.loads(Path(args.b).read_text(encoding="utf-8")))
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True)
    print(json.dumps({"classification":result["classification"],
      "paired_counts":result["paired_counts"],"deviations":result["deviations"]}))
if __name__=="__main__":main()
