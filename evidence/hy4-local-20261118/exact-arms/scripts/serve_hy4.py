#!/usr/bin/env python3
"""Minimal OpenAI-compatible streaming endpoint over the publisher transformers model code, on processors.

Serves one local Hy4 flash snapshot for the Cantos maintainer instrument:
GET /health, /version, /v1/models and POST /v1/chat/completions (streaming only, one request at a time).
Greedy decoding when temperature is 0; chat_template_kwargs are passed to the chat template.

BF16 arm: the publisher loader reads the snapshot as float32 (BF16 values widen exactly).

FP8 arm (--fp8 with --skeleton): the library's processor fallback for the FP8 checkpoint does not yield a
runnable model at this commit, so the model structure is loaded from the dense snapshot and then every
parameter is overwritten from the FP8 checkpoint. FP8 tensors are multiplied by their checkpoint block
scales with the library's own dequantize routine; all other tensors widen to float32. Loading fails unless
every parameter was overwritten and every FP8-scaled tensor was matched. The inputs of each matmul whose
checkpoint weight is FP8 are then rounded through FP8 with the scaling of the kernels-community/finegrained-fp8
kernels (per row, per block of 128 along the input, scale = max|x| / 448). Arithmetic is float32 on both
arms, as in the kernels' accumulators; the vendor path additionally rounds each result to BF16.
"""
import argparse, json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

parser = argparse.ArgumentParser()
parser.add_argument('--model', required=True, help='snapshot folder being served')
parser.add_argument('--name', default='hy4-flash')
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--threads', type=int, default=56)
parser.add_argument('--fp8', action='store_true', help='--model is the FP8 checkpoint; needs --skeleton')
parser.add_argument('--skeleton', help='dense snapshot folder used only for the model structure of the FP8 arm')
parser.add_argument('--status', required=True, help='JSON file updated with load and request facts')
args = parser.parse_args()

import torch, transformers
from transformers import AutoModelForImageTextToText, AutoProcessor, TextIteratorStreamer

torch.set_num_threads(args.threads)
status = {'model': args.model, 'name': args.name, 'threads': args.threads, 'fp8': args.fp8, 'skeleton': args.skeleton,
          'torch': torch.__version__, 'transformers': transformers.__version__, 'state': 'loading',
          'load_started_epoch': time.time(), 'requests': []}
hooked = {'linear': [], 'experts': []}
calls = {'linear': 0, 'experts_in': 0, 'experts_mid': 0}


def save():
    with open(args.status, 'w') as handle:
        json.dump(status, handle, indent=2)


def fail(reason, **facts):
    status.update(state='failed: ' + reason, **facts)
    save()
    raise SystemExit(status['state'])


def fp8_round_trip(x, block=128):
    """What the FP8 kernels see of an activation: quantize per row and per input block, then scale back."""
    def blocks(part, width):
        b = part.unflatten(-1, (-1, width))
        scale = b.abs().amax(dim=-1, keepdim=True) / 448.0
        quantized = (b / scale.clamp_min(1e-12)).clamp(-448.0, 448.0).to(torch.float8_e4m3fn).to(x.dtype)
        return (quantized * scale).flatten(-2)
    width = x.shape[-1]
    full = width - width % block
    parts = ([blocks(x[..., :full], block)] if full else []) + ([blocks(x[..., full:], width - full)] if full != width else [])
    return parts[0] if len(parts) == 1 else torch.cat(parts, dim=-1)


def load_fp8(model, source):
    """Overwrite every parameter of the dense model from the FP8 checkpoint and hook its FP8 matmul inputs."""
    from safetensors import safe_open
    from transformers.conversion_mapping import get_model_conversion_mapping
    from transformers.integrations.finegrained_fp8 import Fp8Dequantize

    index = json.load(open(source + '/model.safetensors.index.json'))['weight_map']
    renamings = get_model_conversion_mapping(model)
    parameters = dict(model.named_parameters())
    buffers = dict(model.named_buffers())
    modules = dict(model.named_modules())
    dequantize = Fp8Dequantize(None)._dequantize_one

    def model_key(key):
        renamed = key
        for renaming in renamings:
            renamed, _ = renaming.rename_source_key(renamed)
        for candidate in (renamed, 'model.' + renamed, renamed.replace('model.', 'model.language_model.', 1)):
            if candidate in parameters or candidate in buffers:
                return candidate
        return None

    def scale_key_for(key):
        return key[:-len('.weight')] + '.weight_scale_inv' if key.endswith('.weight') else key + '_scale_inv'

    def similarity(a, b):
        a, b = a.flatten(1) if a.dim() > 2 else a.reshape(1, -1), b.flatten(1) if b.dim() > 2 else b.reshape(1, -1)
        dot = (a * b).sum(dim=1, dtype=torch.float64).sum()
        return float(dot / ((a * a).sum(dim=1, dtype=torch.float64).sum().sqrt() * (b * b).sum(dim=1, dtype=torch.float64).sum().sqrt()))

    handles = {}

    def tensor(key):
        shard = index[key]
        if shard not in handles:
            handles[shard] = safe_open(source + '/' + shard, 'pt')
        return handles[shard].get_tensor(key)

    covered, unmapped, draft, fp8_tensors = set(), [], 0, {}
    plain_same = plain_changed = 0
    for key in sorted(index):
        if key.endswith('_scale_inv'):
            continue
        if 'dfly' in key:            # draft layers for speculative decoding: not part of this model, unused here
            draft += 1
            continue
        target = model_key(key)
        if target is None:
            unmapped.append(key)
            continue
        destination = parameters[target] if target in parameters else buffers[target]
        value = tensor(key)
        scale_key = scale_key_for(key)
        with torch.no_grad():
            if scale_key in index:
                if value.dtype != torch.float8_e4m3fn:
                    fail('scaled tensor is not FP8', key=key)
                value = dequantize(value, tensor(scale_key), output_dtype=torch.float32)
                if value.shape != destination.shape:
                    fail('shape mismatch', key=key, checkpoint=list(value.shape), model=list(destination.shape))
                fp8_tensors[target] = similarity(destination, value)
            else:
                if value.dtype == torch.float8_e4m3fn:
                    fail('FP8 tensor without a scale grid', key=key)
                value = value.to(destination.dtype)
                if value.shape != destination.shape:
                    fail('shape mismatch', key=key, checkpoint=list(value.shape), model=list(destination.shape))
                if torch.equal(destination, value):
                    plain_same += 1
                else:
                    plain_changed += 1
            destination.copy_(value)
        covered.add(target)
    handles.clear()
    missed = sorted(name for name in parameters if name not in covered)
    status['fp8_load'] = {'checkpoint_tensors_applied': len(covered), 'model_parameters': len(parameters),
                          'parameters_not_overwritten': missed[:20], 'checkpoint_tensors_unmapped': unmapped[:20],
                          'draft_tensors_skipped': draft, 'fp8_tensors_dequantized': len(fp8_tensors),
                          'unscaled_tensors_identical_to_skeleton': plain_same, 'unscaled_tensors_different_from_skeleton': plain_changed,
                          'fp8_vs_skeleton_cosine_min': min(fp8_tensors.values()) if fp8_tensors else None,
                          'fp8_vs_skeleton_cosine_max': max(fp8_tensors.values()) if fp8_tensors else None}
    if missed or unmapped:
        fail('FP8 checkpoint and model parameters do not line up')
    if not fp8_tensors or min(fp8_tensors.values()) < 0.98:
        fail('a dequantized FP8 tensor is not close to its dense counterpart')

    def linear_hook(module, inputs):
        calls['linear'] += 1
        return (fp8_round_trip(inputs[0]),) + tuple(inputs[1:])

    def experts_hook(module, inputs, kwargs):
        calls['experts_in'] += 1
        return (fp8_round_trip(inputs[0]),) + tuple(inputs[1:]), kwargs

    def wrap_gate(module):
        original = module._apply_gate

        def gated(value):
            calls['experts_mid'] += 1
            return fp8_round_trip(original(value))
        module._apply_gate = gated

    for target in sorted(fp8_tensors):
        owner, leaf = target.rsplit('.', 1)
        module = modules[owner]
        if leaf == 'weight' and type(module) is torch.nn.Linear:
            module.register_forward_pre_hook(linear_hook)
            hooked['linear'].append(owner)
        elif leaf == 'gate_up_proj' and (owner + '.down_proj') in fp8_tensors:
            module.register_forward_pre_hook(experts_hook, with_kwargs=True)
            wrap_gate(module)
            hooked['experts'].append(owner)
        elif leaf != 'down_proj' or (owner + '.gate_up_proj') not in fp8_tensors:
            fail('FP8 tensor on an unexpected module', key=target, module=type(module).__name__)
    status['fp8_load'].update(hooked_linears=len(hooked['linear']), hooked_experts=len(hooked['experts']),
                              hooked_linear_kinds=sorted({name.rsplit('.', 1)[-1] for name in hooked['linear']}))
    if len(hooked['linear']) + 2 * len(hooked['experts']) != len(fp8_tensors):
        fail('hooked modules do not account for every FP8 tensor')


save()
processor = AutoProcessor.from_pretrained(args.model)
tokenizer = processor.tokenizer
model = AutoModelForImageTextToText.from_pretrained(args.skeleton if args.fp8 else args.model, dtype=torch.float32)
model.eval()
if args.fp8:
    status['skeleton_load_seconds'] = time.time() - status['load_started_epoch']
    save()
    load_fp8(model, args.model)
dtypes = {}
for parameter in model.parameters():
    dtypes[str(parameter.dtype)] = dtypes.get(str(parameter.dtype), 0) + parameter.numel()
if set(dtypes) != {'torch.float32'}:
    fail('parameters are not all float32', element_counts_by_dtype=dtypes)
status.update(state='ready', load_seconds=time.time() - status['load_started_epoch'], element_counts_by_dtype=dtypes,
              model_class=type(model).__name__)
save()
print('READY', json.dumps({k: status.get(k) for k in ('load_seconds', 'element_counts_by_dtype', 'fp8_load')}), flush=True)
busy = threading.Lock()


class CountingStreamer(TextIteratorStreamer):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.tokens, self.prompt_seen, self.last_ids = 0, False, None

    def put(self, value):
        if self.prompt_seen:
            self.tokens += value.numel()
            self.last_ids = value.reshape(-1)[-1:].tolist()
        self.prompt_seen = True
        super().put(value)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def send_json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health':
            self.send_json(200, {'status': 'ok'})
        elif self.path == '/version':
            # One string for both arms: the arm is declared in the spec and shown under /v1/models, not here.
            self.send_json(200, {'version': 'serve_hy4/4 transformers %s torch %s' % (transformers.__version__, torch.__version__)})
        elif self.path == '/v1/models':
            self.send_json(200, {'object': 'list', 'data': [{'id': args.name, 'object': 'model', 'owned_by': 'transformers', 'meta': {
                'snapshot': args.model, 'element_counts_by_dtype': dtypes, 'fp8': args.fp8, 'fp8_load': status.get('fp8_load')}}]})
        else:
            self.send_json(404, {'error': 'not found'})

    def event(self, body):
        data = ('data: ' + (body if isinstance(body, str) else json.dumps(body)) + '\n\n').encode()
        self.wfile.write(('%x\r\n' % len(data)).encode() + data + b'\r\n')
        self.wfile.flush()

    def do_POST(self):
        if self.path != '/v1/chat/completions':
            return self.send_json(404, {'error': 'not found'})
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if request.get('model') != args.name or not request.get('stream'):
            return self.send_json(400, {'error': 'model must be %s and stream true' % args.name})
        messages = [{'role': m['role'], 'content': [{'type': 'text', 'text': m['content']}]} for m in request['messages']]
        template = dict(request.get('chat_template_kwargs') or {})
        with busy:
            started = time.time()
            before = dict(calls)
            inputs = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=True, return_dict=True,
                                                   return_tensors='pt', **template)
            prompt_tokens = int(inputs['input_ids'].shape[-1])
            streamer = CountingStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
            sampling = float(request.get('temperature', 0) or 0) > 0
            generation = dict(max_new_tokens=int(request.get('max_tokens', 256)), do_sample=sampling, streamer=streamer)
            if sampling:
                generation.update(temperature=float(request['temperature']), top_p=float(request.get('top_p', 1)))
            torch.manual_seed(int(request.get('seed', 0)))
            failure = {}

            def work():
                try:
                    with torch.inference_mode():
                        model.generate(**inputs, **generation)
                except Exception as exc:  # surface the failure to the client instead of hanging the stream
                    failure['error'] = type(exc).__name__ + ': ' + str(exc)[:400]
                    streamer.text_queue.put(streamer.stop_signal)

            thread = threading.Thread(target=work)
            thread.start()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            base = {'id': 'chatcmpl-%d' % int(started * 1000), 'object': 'chat.completion.chunk', 'created': int(started), 'model': args.name}
            first_at = None
            for piece in streamer:
                if piece:
                    first_at = first_at or time.time()
                    self.event({**base, 'choices': [{'index': 0, 'delta': {'content': piece}, 'finish_reason': None}]})
            thread.join()
            record = {'started_epoch': started, 'prompt_tokens': prompt_tokens, 'completion_tokens': streamer.tokens,
                      'seconds': time.time() - started, 'first_text_seconds': (first_at - started) if first_at else None,
                      'template_kwargs': template, 'fp8_round_trips': {k: calls[k] - before[k] for k in calls}}
            if failure:
                record.update(failure)
                self.event({'error': failure['error']})
            else:
                limit = streamer.tokens >= generation['max_new_tokens'] and streamer.last_ids != [tokenizer.eos_token_id]
                self.event({**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'length' if limit else 'stop'}]})
                self.event({**base, 'choices': [], 'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': streamer.tokens,
                                                              'total_tokens': prompt_tokens + streamer.tokens}})
            self.event('[DONE]')
            self.wfile.write(b'0\r\n\r\n')
            self.wfile.flush()
            status['requests'].append(record)
            save()


ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
