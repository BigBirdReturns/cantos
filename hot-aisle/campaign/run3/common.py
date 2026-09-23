"""Run 3 local evidence utilities; stdlib only. Tested by selftest.py."""
import hashlib
import json
from pathlib import Path

MODEL = 'Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8'
REVISION = 'dcaee4d4dfc5ee71ad501f01f530e5652438fde0'
IMAGES = {
    'amd': 'vllm/vllm-openai-rocm:v0.30.0@sha256:2e7da1ad1c66836802072588adea75f9f4991da5f9545b4318e91d422c22ce6a',
    'nvidia': 'vllm/vllm-openai@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('utf-8')


def write_json(path, value):
    Path(path).write_bytes(encoded(value))


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def verify(path, expected):
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        raise ValueError('A verified lowercase SHA-256 is required; UNVERIFIED is not executable')
    if sha(path) != expected:
        raise ValueError('SHA-256 mismatch: ' + str(path))
