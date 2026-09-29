#!/usr/bin/env python3
"""Stream the retained 1.27 GB InferenceX import (metric-per-line) and reduce to one compact record per
source row (artifact_id,row_index). stdlib only. Usage: ix_extract.py <in.jsonl> <out.jsonl>"""
import json, sys, hashlib, collections
src, dst = sys.argv[1], sys.argv[2]
rows = collections.OrderedDict()
names = collections.Counter()
h = hashlib.sha256(); nlines = 0
with open(src, 'rb') as f:
    for line in f:
        h.update(line); nlines += 1
        d = json.loads(line)
        k = (d['provenance']['artifact_id'], d['row_index'])
        r = rows.get(k)
        c = d['config']; w = d['workload']
        if r is None:
            ra = d.get('request_accounting') or c.get('request_accounting') or {}
            r = dict(artifact=k[0], row=k[1], created=d['provenance'].get('created_at'),
                     hw=d['hardware'], hw_raw=c.get('hw'), fw=d['framework'], model=d.get('model'),
                     scen=w.get('scenario'), isl=w.get('input_tokens'), osl=w.get('output_tokens'),
                     conc=w.get('concurrency'), dataset=(w.get('dataset') if isinstance(w.get('dataset'),str) else (w.get('dataset') or {}).get('hf_dataset_name')),
                     prec=c.get('precision'), tp=c.get('tp'), ep=c.get('ep'), pp=c.get('pp'), gpus=d.get('gpus'),
                     disagg=c.get('disagg'), spec=c.get('spec_decoding'), dpa=c.get('dp_attention'),
                     multinode=c.get('is_multinode'), image=(c.get('image') or '')[:120],
                     ok=d.get('num_requests_successful'), tot=d.get('num_requests_total'),
                     err_drop=ra.get('records_error_dropped'), warm_drop=ra.get('records_warmup_dropped'),
                     outcome=d.get('outcome'), benchmark_outcome=c.get('benchmark_outcome'), m={})
            rows[k] = r
        n = d['metric']['name']; names[n] += 1
        if n in ('output_throughput_per_gpu','total_token_throughput_per_gpu','median_ttft_ms','p99_ttft_ms','median_e2el_ms','p99_e2el_ms','median_itl_ms','tput_per_gpu','output_tput_per_gpu','successful_requests'):
            r['m'][n] = d['metric']['value']
with open(dst, 'w', encoding='utf-8') as o:
    for r in rows.values(): o.write(json.dumps(r) + '\n')
print(json.dumps(dict(lines=nlines, source_rows=len(rows), sha256=h.hexdigest(), metric_names=names.most_common())))
