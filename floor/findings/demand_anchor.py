#!/usr/bin/env python3
"""Demand vs public-efficiency-anchor gap on MI300X. Name-level judgement, not a measurement.
Demand: OpenRouter weekly top-10 tokens, Ollama library pulls (top non-embedding). Anchors on MI300X: InferenceX rows
(ix_rows from ix_extract.py) and MLPerf v4.1-v5.1 LLM summaries. Anchor level: 'exact' = same model family AND the size class people pull
by default appears on MI300X; 'family-other-size' = family appears only at a very different size/version; 'none'.
Usage: demand_anchor.py <ix_rows.jsonl> <out.json>"""
import json, sys, re, collections
ix = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8')]
mlp_p = 'D:/Projects/Organs/AXM/axm-tools/sessions/public-tail-20260929/lanes/mlperf/rows/mlperf.jsonl'
base = 'D:/Projects/Organs/AXM/axm-tools/sessions/public-tail-20260929/lanes/demand-signals/rows/'
ixm = sorted(set(re.sub(r'^.*/', '', r['model'] or '') for r in ix if r['hw'] == 'MI300X'))
mlm = sorted(set(json.loads(l).get('model') for l in open(mlp_p, encoding='utf-8') if '"hardware": "MI300X"' in l))
print('InferenceX MI300X models:', ixm); print('MLPerf MI300X models:', mlm)
# OpenRouter weekly top-10 (open weights judged by name; closed = n/a)
orr = [json.loads(l) for l in open(base + 'openrouter_rankings.jsonl', encoding='utf-8')]
wk = [r for r in orr if r['window'] == 'week' and r['rank'] <= 10]
OR = {'DeepSeek V4.1 Flash': ('exact', 'InferenceX MI300X: DeepSeek-V4.1-Flash (vllm, agentic-coding only, 4 source rows)'),
      'Space Bunny Alpha': ('unknown', 'stealth model, identity unknown'),
      'GLM 5.3 Flash': ('family-other-size', 'InferenceX MI300X has GLM-5.2-FP8 (sglang, 60 rows), not 5.3 Flash'),
      'Hy4 preview': ('none', 'Tencent Hy: no InferenceX/MLPerf row on any hardware'),
      'GPT-5.6 Luna': ('closed', 'closed model, not self-hostable'),
      'DeepSeek V4 Flash 0731': ('family-other-size', 'InferenceX MI300X has V4.1-Flash and V4-Pro; V4-Flash rows exist only on B200/B300/MI355X'),
      'MiMo-V2.6-Flash': ('none', 'Xiaomi MiMo: no row on any hardware'),
      'Nemotron 3 Ultra (free)': ('none', 'no Nemotron row on MI300X'),
      'GPT-6 Luna': ('closed', 'closed model'),
      'DeepSeek V4 Flash 0423': ('family-other-size', 'as V4 Flash 0731')}
tot = sum(r['token_volume'] for r in wk); by = collections.defaultdict(float)
print('OpenRouter weekly top-10 total %.2fT tokens' % (tot / 1e12))
for r in wk:
    lvl, why = OR[r['model_name']]; by[lvl] += r['token_volume']
    print('  %2d %-26s %6.2fT %-18s %s' % (r['rank'], r['model_name'], r['token_volume'] / 1e12, lvl, why))
selfhost = tot - by['closed'] - by['unknown']
print('  by level (T tokens):', {k: round(v / 1e12, 2) for k, v in by.items()}, '| self-hostable open-weight identified = %.2fT; exact anchor share %.1f%%; exact+family %.1f%%' % (selfhost / 1e12, 100 * by['exact'] / selfhost, 100 * (by['exact'] + by['family-other-size']) / selfhost))
# Ollama
ol = [json.loads(l) for l in open(base + 'ollama_models.jsonl', encoding='utf-8')]
emb = {'nomic-embed-text', 'mxbai-embed-large', 'bge-m3', 'all-minilm', 'qwen3-embedding', 'glm-ocr', 'snowflake-arctic-embed'}
ol = sorted([r for r in ol if r['model'] not in emb and r.get('pulls')], key=lambda r: -r['pulls'])[:20]
OL = {'llama3.1': ('family-other-size', 'MLPerf MI300X: llama3.1-70b, 405b (v5.0/5.1); default tag is 8B, no 8B row on MI300X'),
      'deepseek-r1': ('family-other-size', 'InferenceX MI300X: DeepSeek-R1-0528 (671B sglang, 4 rows); default tag is 8B distill'),
      'llama3.2': ('none', ''), 'qwen2.5': ('none', 'no Qwen2.5 row on MI300X'),
      'gemma3': ('none', ''), 'qwen3': ('family-other-size', 'InferenceX MI300X: Qwen3-0.6B only; default Ollama tag is 8B'),
      'gemma2': ('none', ''), 'mistral': ('none', 'MLPerf mixtral-8x7b is a different model'),
      'gemma4': ('none', ''), 'llama3': ('none', ''), 'qwen2.5-coder': ('none', ''),
      'qwen3.5': ('family-other-size', 'InferenceX MI300X: Qwen3.5-397B only; Ollama default is a small size'),
      'phi3': ('none', ''), 'llava': ('none', ''), 'gpt-oss': ('none', 'InferenceX has gpt-oss-120b on MI355X only'),
      'qwen3-coder': ('none', 'no Qwen3-Coder row on any hardware in InferenceX or MLPerf; only our Runs 1-3 (30B-A3B)'),
      'gemma': ('none', ''), 'qwen': ('none', ''), 'phi4': ('none', ''), 'llama2': ('family-other-size', 'MLPerf MI300X: llama2-70b; default tag is 7B')}
totp = sum(r['pulls'] for r in ol); byo = collections.defaultdict(float)
print('Ollama top-20 non-embedding total pulls %.1fM' % (totp / 1e6))
for r in ol:
    lvl, why = OL.get(r['model'], ('unmapped', '')); byo[lvl] += r['pulls']
    print('  %-14s %6.1fM  %-18s %s' % (r['model'], r['pulls'] / 1e6, lvl, why))
print('  by level (M pulls):', {k: round(v / 1e6, 1) for k, v in byo.items()}, '| none = %.1f%%; family-other-size = %.1f%%; exact = %.1f%%' % (100 * byo['none'] / totp, 100 * byo['family-other-size'] / totp, 100 * byo['exact'] / totp))
json.dump(dict(ix_mi300x_models=ixm, mlperf_mi300x_models=mlm, openrouter_week_total=tot, openrouter_by_level=dict(by), ollama_top20_total=totp, ollama_by_level=dict(byo), ollama_rows=[(r['model'], r['pulls'], OL.get(r['model'])) for r in ol]), open(sys.argv[2], 'w'), indent=1)
