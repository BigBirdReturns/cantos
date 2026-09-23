# Run 3 source lock and verification status

Read-only upstream documentation was checked during this build. No production dataset,
image, model, GPU seat or grader was downloaded or executed. URLs identify the exact
intended releases; **a URL/tag is not a verified byte hash**.

| Input | Version / exact seat fetch URL | SHA-256 status |
|---|---|---|
| HumanEval+ | v0.1.10, `https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz` | **UNVERIFIED** compressed asset bytes |
| MBPP+ | v0.2.0, `https://github.com/evalplus/mbppplus_release/releases/download/v0.2.0/MbppPlus.jsonl.gz` | **UNVERIFIED** compressed asset bytes |
| Azure CODE 2023 | `AzureLLMInferenceTrace_code.csv`, `https://raw.githubusercontent.com/Azure/AzurePublicDataset/master/data/AzureLLMInferenceTrace_code.csv` | **UNVERIFIED**; mutable branch URL, retain downloaded bytes and SHA before freezing |
| EvalPlus | Python distribution `evalplus==0.3.1` | **UNVERIFIED** wheel/dependency bytes and final CPU image identity |
| CPU base image | Operator-reviewed Python 3.11 CPU image at a registry digest | **UNVERIFIED**, no default tag |

The workload builder requires two explicit verified SHA-256 values, refuses mismatches,
and records both compressed and uncompressed identities. The replayer likewise requires
the trace SHA. The arm additionally requires the frozen task-file SHA. Do not substitute
the word UNVERIFIED or an invented digest. On the seat, retain the downloaded files,
check their origin and expected counts, compute `sha256sum`, and record those hashes in
a dated freeze packet **before renting**. The CPU grader image must also be frozen then.
The build brief explicitly allows unresolved identities to be marked UNVERIFIED; these
are execution prerequisites, not completed verification.

Primary documentation:

- [HumanEval+ release](https://github.com/evalplus/humanevalplus_release/releases/tag/v0.1.10)
  and [EvalPlus 0.3.1 HumanEval loader](https://github.com/evalplus/evalplus/blob/v0.3.1/evalplus/data/humaneval.py).
- [MBPP+ v0.2.0 release](https://github.com/evalplus/mbppplus_release/releases/tag/v0.2.0)
  identifies 378 tasks; [the pinned loader](https://github.com/evalplus/evalplus/blob/v0.3.1/evalplus/data/mbpp.py)
  selects that version and deserializes its special input types.
- [EvalPlus evaluator](https://github.com/evalplus/evalplus/blob/v0.3.1/evalplus/evaluate.py)
  checks sample coverage, sorts results within each task by completion order, writes
  `solution`, `base_status`, and `plus_status`, and hashes the reference file with MD5.
  We retain that MD5 for its compatibility join and use SHA-256 for our artifacts.
  [Status definitions](https://github.com/evalplus/evalplus/blob/v0.3.1/evalplus/eval/__init__.py)
  include pass, fail, and timeout. Both base and plus must pass.
- [Azure 2023 trace description](https://github.com/Azure/AzurePublicDataset/blob/master/AzureLLMInferenceDataset2023.md)
  defines `TIMESTAMP`, `ContextTokens`, `GeneratedTokens`. Use the CODE CSV, not the
  2024 week-long trace or the conversation file. The schedule uses only arrivals:
  prompt contents and lengths come from frozen EvalPlus tasks; generation ends at EOS
  or 1,024 tokens. This is not a reproduction of Azure's token-size workload.
  Azure data is CC-BY; attribute Patel et al., *Splitwise: Efficient generative LLM
  inference using phase splitting*, ISCA 2024, in any resulting publication.

Model and serving-image pins are supplied by lane A and the repository's Run 2 record:

```
Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8
dcaee4d4dfc5ee71ad501f01f530e5652438fde0
vllm/vllm-openai@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90
vllm/vllm-openai-rocm:v0.30.0@sha256:2e7da1ad1c66836802072588adea75f9f4991da5f9545b4318e91d422c22ce6a
```

Their bytes are **UNVERIFIED by this build**; on-seat Docker digest resolution, image
inspection, vLLM version output and serve logs become the runtime evidence. No image
tag-only fallback is permitted. Fixture data is authored synthetic data; see fixtures/README.md.
