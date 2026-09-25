# Tasks B and C: Record Analysis

## Task B: Records Supporting "MI300X is Cheaper per Accepted Request than H100 on Self-Serve Seat in September 2026"

**Supporting Record:**

**record 1 (run3-at0)** directly supports this claim. It reports MI300X at $0.74/1k accepted requests (own-seat equivalent) versus H100 at $1.20/1k accepted requests (DigitalOcean), with experiment date 2026-09-24 in September. However, support is heavily qualified: the record disclaims that this "does not establish a hardware-wide or September-wide ordering," the MI300X metric is "modeled provisioning latency" not a direct measure, the H100 comparator is an "imported" DigitalOcean report not independently verified, and invoices are unreconciled. The record notes "no claim that available cheaper H100 offers preserve the ranking"—other H100 providers may undercut this price.

**Records I must refuse to use:**

- **record 2 (inferencex-artifact):** No H100 comparison present; latency metrics only, not request acceptance costs. Record states: "This aggregate is not that evidence."
- **record 3 (clustermax-coreweave):** Managed clusters, not self-serve seats. Record explicitly states: "does not establish accepted-request cost...for an ordinary self-serve seat."
- **record 4 (mercatus-index):** Per GPU-hour rates, not per accepted request. Worse, it shows the opposite: MI300X $4.98/hr > H100 $3.89/hr. Record disclaims: "cost per accepted request."
- **record 5 (hotaisle-blog):** MI300X price only, no H100. Per GPU-hour, not per request. Published July 2026, not September; notes "not September capacity evidence."
- **record 6 (latitude-h100):** H100 only, no MI300X comparison. Per GPU-hour, not per accepted request.

## Task C: Unclear Fields and Missing Field

**Fields I did not understand or could not fill:**

- `trace` (record 1): Listed as "Azure LLM CODE trace"—its semantics and use are opaque.
- `replay_factor` (record 1): Value 0.95 without clear definition; unclear whether this is a scaling factor, a fidelity metric, or workload adjustment.
- `acceptance.correctness` (record 1): States "Raw registered output passes base AND plus tests" but the evaluation framework (EvalPlus vs. MBPP) and pass/fail semantics are implicit.
- `precision` (record 2): Listed as "FP4" but appears inconsistently across records; unclear if all records should declare this or if it is optional.

**Missing field:**

A field capturing **observer conflict of interest or observer funding relationship** would strengthen integrity. Record 1 notes Hot Aisle is provider-crediting the operator ("Second Run is pitching Hot Aisle a paid engagement"), but there is no structured field flagging such relationships across records. The `c_parties.funding` field documents what was paid, but not whether the observer benefits from a particular outcome, which could bias metric selection, acceptance criteria, or public reporting.
