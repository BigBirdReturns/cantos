#!/usr/bin/env python3
"""Shortfall themes repeated across providers in the ClusterMAX cloudreview claims (stance -1 only).
Provider = slug in claim id (cmcr-<slug>-NN). A quote may match several themes. Theme regexes are ours (keyword heuristics),
run on the verbatim quote text. Usage: cloudreview_shortfalls.py <claims.all.jsonl> <out.json>"""
import json, sys, re, collections, hashlib
src, dst = sys.argv[1], sys.argv[2]
raw = open(src, 'rb').read(); sha = hashlib.sha256(raw).hexdigest()
rows = [json.loads(l) for l in raw.decode('utf-8').splitlines()]
slug = lambda r: r['id'].split('-')[1]
T = collections.OrderedDict([
 ('security / compliance attestation (SOC 2, ISO, HIPAA)', r'soc ?2|attestation|iso ?27001|hipaa|compliance|security'),
 ('slurm setup / scheduler gaps', r'slurm|sacct|scheduler|sbatch|srun'),
 ('monitoring / observability / dashboards', r'monitor|dcgm|grafana|observab|dashboard|metrics|telemetry'),
 ('node health checks / auto-drain / remediation', r'drain|health[ -]?check|faulty|remediat|node health|auto(matic)?(ally)? (repair|replace)'),
 ('storage / filesystem', r'storage|filesystem|file system|lustre|weka|vast data|nfs|\bs3\b|fsx'),
 ('networking / InfiniBand / NCCL', r'infiniband|nccl|rdma|roce|ethernet|network'),
 ('support / ticket response', r'support|ticket|response time'),
 ('documentation / tutorials', r'document|docs\b|tutorial|guide'),
 ('reliability / outages / instability', r'reliab|outage|downtime|uptime|unstable|instabilit|crash|fail'),
 ('billing / pricing transparency', r'billing|hidden|egress|pricing|price|invoice|charge'),
 ('kubernetes gaps', r'kubernetes|k8s|kubeflow'),
 ('status page / incident communication', r'status page|incident'),
 ('onboarding / user experience / signup friction', r'onboarding|user experience|\bux\b|sign[ -]?up|kyc|friction|easy to|difficult'),
 ('ssh / access / root / login node limitations', r'\bsudo\b|\broot\b|\bssh\b|login node|bastion|access token'),
 ('OS images / drivers / software stack out of date', r'\bdriver|ubuntu|\bimage\b|cuda version|outdated|out of date|stale'),
])
neg = [r for r in rows if r['stance'] == -1]
allprov = sorted(set(slug(r) for r in rows)); negprov = sorted(set(slug(r) for r in neg))
print('claims', len(rows), 'negative', len(neg), 'providers (slugs) with any claim', len(allprov), 'with >=1 negative', len(negprov), 'sha', sha)
res = []
for name, rx in T.items():
    R = re.compile(rx, re.I)
    m = [r for r in neg if R.search(r['quote'])]
    ps = sorted(set(slug(r) for r in m))
    res.append(dict(theme=name, providers=len(ps), quotes=len(m), example_ids=[r['id'] for r in m[:4]], provider_slugs=ps))
res.sort(key=lambda d: -d['providers'])
for d in res: print('%3d providers  %3d quotes  %s' % (d['providers'], d['quotes'], d['theme']))
# topic-level
tp = collections.defaultdict(set)
for r in neg: tp[r['topic']].add(slug(r))
print({k: len(v) for k, v in tp.items()})
json.dump(dict(input_sha256=sha, claims=len(rows), negative=len(neg), providers_with_claims=len(allprov), providers_with_negative=len(negprov), themes=res, topic_providers={k: len(v) for k, v in tp.items()}), open(dst, 'w'), indent=1)
