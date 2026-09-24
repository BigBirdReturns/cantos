# POST-HOC, NOT REGISTERED: EvalPlus sanitize applied to A/T0's raw completions

The registered score is in `../grade/`: raw completion, no sanitizer, per PREREG. This directory re-grades the same completions after `evalplus.sanitize`. It uses the same pinned grader image and references, with no model calls. The purpose is to separate model capability from output format.

| | pass@1, base + plus (raw, registered) | pass@1, sanitized (post-hoc) |
|---|---|---|
| HumanEval+ | 24.4 % (640 / 2624) | 82.4 % |
| MBPP+ | 62.2 % (3731 / 5998) | 67.2 % |

About three quarters of HumanEval's raw failures are format: stray markdown fences, re-declared functions, and test prints. They are not wrong logic. The latency gates are unchanged by sanitizing, since the completions are the same.
