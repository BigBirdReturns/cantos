"""Convert retained replay journal to the page engine's detailed vLLM schema."""
import argparse
import hashlib
from pathlib import Path
from common import MODEL, REVISION, encoded, sha, write_json
from replay import recover, buckets


def convert(directory, output, runtime='UNVERIFIED'):
    plan, rows = recover(directory)
    good = [r for r in rows if not r['error']]
    end = max([plan['start_ts'] + plan['duration_s']] + [r['end_ts'] for r in rows if r['end_ts'] is not None])
    def delta(r, key):
        return max(0, r[key] - r['send_ts']) if not r['error'] else 0
    requests_bytes = b''.join(encoded(r) for r in rows)
    result = {'duration': end-plan['start_ts'], 'num_prompts': len(rows),
              'completed': len(good), 'failed': len(rows)-len(good),
              'errors': [r['error'] for r in rows],
              'ttfts': [delta(r, 'first_token_ts') for r in rows],
              'latencies': [delta(r, 'end_ts') for r in rows],
              'queue_times': [max(0, r['send_ts']-r['scheduled_ts']) if r['send_ts'] else 0 for r in rows],
              'input_lens': [r['input_tokens'] if not r['error'] else 0 for r in rows],
              'output_lens': [r['output_tokens'] if not r['error'] else 0 for r in rows],
              'total_output_tokens': sum(r['output_tokens'] for r in good),
              'model_id': MODEL, 'synthetic': plan['synthetic'],
              'metadata': {'model_revision': REVISION, 'tokenizer_revision': REVISION,
                           'precision': 'FP8', 'workload_id': 'sha256:' + plan['tasks_sha256'],
                           'cache_policy': 'no-prefix-cache', 'runtime_digest': runtime,
                           'load_profile': f"azure-code:{plan['trace_sha256']}:{plan['trace_start']}:factor={plan['rate_factor']}:duration={plan['duration_s']}:seed={plan['requests'][0]['seed']}:workers={plan['workers']}:max_tokens=1024:temperature=0.2",
                           'plan_sha256': sha(Path(directory) / 'plan.json'),
                           'requests_sha256': hashlib.sha256(requests_bytes).hexdigest(),
                           'lost_requests': sum(r['error'] == 'lost_after_send' for r in rows),
                           'never_sent_requests': sum(r['error'] in ('never_sent_after_interrupt', 'client_concurrency_limit') for r in rows),
                           'send_unknown_requests': sum(r['error'] == 'send_unknown_after_interrupt' for r in rows)}}
    write_json(output, result)
    Path(directory, 'requests.jsonl').write_bytes(requests_bytes)
    write_json(Path(directory, 'buckets.json'), buckets(plan, rows))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory'); p.add_argument('output')
    p.add_argument('--runtime', default='UNVERIFIED')
    a = p.parse_args()
    convert(a.directory, a.output, a.runtime)
