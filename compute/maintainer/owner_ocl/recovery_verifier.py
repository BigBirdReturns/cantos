"""Independent replay and evidence integrity gate for owned loopback recovery."""
import argparse,hashlib,json,html,math,pathlib,sys

def sha(raw): return hashlib.sha256(raw).hexdigest()
def load(path):
    b=path.read_bytes()
    return json.loads(b),sha(b)
def percentile(values,p):
    if not values:return None
    a=sorted(values)
    return a[min(len(a)-1,int((len(a)-1)*p))]
def verify(raw,summary,raw_sha,label):
    if raw.get("schema")!="ocl.owned-loopback-recovery/1":raise ValueError(label+": raw schema")
    if summary.get("schema")!="ocl.owned-loopback-summary/1":raise ValueError(label+": summary schema")
    if raw.get("run_id")!=summary.get("run_id") or summary["raw_sha256"]!=raw_sha:raise ValueError(label+": identity/digest mismatch")
    if raw.get("error") is not None or not summary.get("exit_success"):raise ValueError(label+": run error")
    order=raw["condition_order"]
    if set(order)!={"normal","restart"} or len(order)!=2:raise ValueError(label+": condition set")
    if raw["seconds_per_condition"]<23 or raw["interval_s"]<=0:raise ValueError(label+": invalid duration")
    tr=raw["transitions"]; attempts=raw["attempts"]
    if len(attempts)<150:raise ValueError(label+": insufficient traffic")
    if any(attempts[i]["t_s"]>attempts[i+1]["t_s"] for i in range(len(attempts)-1)):
        raise ValueError(label+": unsorted event times")
    nonces=[x["nonce"] for x in attempts]
    if len(set(nonces))!=len(nonces):raise ValueError(label+": repeated request nonce")
    if nonces!=[str(i)+":"+raw["run_id"] for i in range(len(nonces))]:raise ValueError(label+": missing/altered nonce")
    if len([t for t in tr if t["kind"]=="recovered"])!=3:raise ValueError(label+": recovery count")
    starts=[t for t in tr if t["kind"]=="start"]
    if len(starts)!=5:raise ValueError(label+": expected five owned child generations")
    if len({t["pid"] for t in starts})!=5:raise ValueError(label+": child PID reuse")
    if len([t for t in tr if t["kind"]=="condition_start"])!=2:raise ValueError(label+": incomplete conditions")
    metrics={}
    all_start={(t["condition"],t["ordinal"]):t for t in starts}
    for cond in order:
        group=[x for x in attempts if x["condition"]==cond]
        if not group:raise ValueError(label+": no traffic "+cond)
        count_ok=0; failed=[]
        for x in group:
            k=(cond,x["ordinal"])
            if k not in all_start:raise ValueError(label+": unknown child ordinal")
            if x["accepted"]:
                if x["status"]!=200 or x["error"] is not None or x["pid"]!=all_start[k]["pid"]:
                    raise ValueError(label+": accepted but invalid status/error/process")
                count_ok+=1
            else:failed.append(x)
        observed=summary["conditions"][cond]
        if (observed["attempts"],observed["accepted"],observed["failed"])!=(len(group),count_ok,len(failed)):
            raise ValueError(label+": summary count mismatch")
        good=[x["elapsed_ms"] for x in group if x["accepted"]]
        for p,key in [(.5,"p50_good_ms"),(.95,"p95_good_ms"),(.99,"p99_good_ms")]:
            if percentile(good,p)!=observed[key]:raise ValueError(label+": summary percentile mismatch")
        metrics[cond]={"attempted":len(group),"accepted":count_ok,"failed":len(failed),
           "observed_request_success_pct":round(100*count_ok/len(group),5),
           "p50_accepted_ms":percentile(good,.5),"p95_accepted_ms":percentile(good,.95),
           "p99_accepted_ms":percentile(good,.99)}
    if metrics["normal"]["failed"]>0:metrics["normal"]["warning"]="Normal-window failures retained, investigate."
    # Each deliberately killed task-owned process must produce rejected probes
    # between its stop and recovery. These do not measure an actual provider SLA.
    trial=[]
    stops=[t for t in tr if t["kind"]=="stop" and t["condition"]=="restart"]
    recover=[t for t in tr if t["kind"]=="recovered"]
    if len(stops)!=4:raise ValueError(label+": missing final stop or injected stop")
    for i,r in enumerate(recover):
        s=stops[i]
        if not r["elapsed_s"]>s["elapsed_s"]:raise ValueError(label+": invalid time ordering")
        bad=[x for x in attempts if not x["accepted"] and s["elapsed_s"]<=x["t_s"]<=r["elapsed_s"]]
        if len(bad)<1:raise ValueError(label+": no witnessed unavailability")
        trial.append({"trial":i+1,"stop_to_recovered_s":round(r["elapsed_s"]-s["elapsed_s"],6),
                      "observed_failed_requests":len(bad)})
    return {"run_id":raw["run_id"],"label":label,"raw_sha256":raw_sha,
            "order":order,"conditions":metrics,"injected_recovery_trials":trial,
            "limits":"Loopback child-process fault injection, not independent uptime, storage durability, network or cloud-provider SLA."}
def main():
    p=argparse.ArgumentParser();p.add_argument("--w02",required=True);p.add_argument("--w03",required=True)
    p.add_argument("--out-json",required=True);p.add_argument("--out-html",required=True)
    a=p.parse_args();results=[]
    for label,root in [("W02",pathlib.Path(a.w02)),("W03",pathlib.Path(a.w03))]:
        raw_path=(root/"raw.json") if (root/"raw.json").exists() else root.parent/(root.name+"-raw.json")
        summary_path=(root/"summary.json") if (root/"summary.json").exists() else root.parent/(root.name+"-summary.json")
        raw,hash_value=load(raw_path);summary,_=load(summary_path)
        results.append(verify(raw,summary,hash_value,label))
    obj={"schema":"ocl.owned-recovery-comparison/1","classification":"authorized Estate local operational audit",
         "findings":results,"executed_trial_count":6,
         "provider_ratings":None,"facility_energy_wh":None,
         "external_network_evidence":None,
         "conclusion":"Verified task-owned service failure and process recovery on two hosts; scoped to loopback and controlled fault windows."}
    for target in (a.out_json,a.out_html):
        if pathlib.Path(target).exists():raise FileExistsError("Refusing overwrite of retained output: "+target)
    with pathlib.Path(a.out_json).open("xb") as f:f.write((json.dumps(obj,sort_keys=True,indent=2)+"\n").encode())
    rows=[]
    for r in results:
        for cond,m in r["conditions"].items():
            rows.append("<tr><td>"+html.escape(r["label"])+"</td><td>"+html.escape(cond)+"</td>"+
            "".join("<td>"+str(m[k])+"</td>" for k in ["attempted","accepted","failed","p50_accepted_ms","p95_accepted_ms","p99_accepted_ms"])+"</tr>")
    site=("""<!doctype html><html lang="en"><meta charset="utf-8"><title>OCL: Owned-service recovery evidence</title>
    <style>body{font:16px/1.5 system-ui;max-width:950px;margin:2rem auto;padding:0 1rem}td,th{padding:.6rem;border-bottom:1px solid #ccc;text-align:left}table{border-collapse:collapse;width:100%}</style>
    <h1>Authenticated local service recovery</h1><p>Two existing Estate hosts, isolated 127.0.0.1 task-owned child services. Each host ran an intact baseline and three controlled child restarts, in opposite condition order. Every request and lifecycle transition is retained.</p>
    <table><thead><tr><th>Host</th><th>Condition</th><th>Requests</th><th>Accepted</th><th>Failed</th><th>P50 ms</th><th>P95 ms</th><th>P99 ms</th></tr></thead><tbody>"""+
    "".join(rows)+"""</tbody></table><p>Failures inside the deliberate shutdown intervals demonstrate detection and recovery. These observations do not rank external clouds, infer network performance, or establish a production availability distribution. See raw.json and summary.json for exact attempts and source identity.</p>
    <p>Source: scripts/audit_owned_loopback_recovery.py and scripts/reanalyze_owned_loopback_recovery.py. Original A/B/C/recipient outcome remains open.</p></html>""")
    with pathlib.Path(a.out_html).open("xb") as f:f.write(site.encode("utf-8"))
    print(json.dumps({"json_sha256":sha(pathlib.Path(a.out_json).read_bytes()),
        "html_sha256":sha(pathlib.Path(a.out_html).read_bytes()),
        "counts":[(r["label"],r["conditions"]) for r in results]}))
if __name__=="__main__":main()
