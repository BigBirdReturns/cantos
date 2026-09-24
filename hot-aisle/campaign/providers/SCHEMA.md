# Provider offer staging · schema

Purpose: compile every provider a Second Run customer could rent a single accelerator
from, with the list price, billing terms, self-serve status and observed availability,
so each offer can be placed against the Run 3 ledger ($0.74 vs $1.20 per 1k accepted).

Rows are gathered by cheap lanes into `staging/*.jsonl` and merged by a human-reviewed
step into `compute/data/catalog.json` (which keeps its own schema and human approval
rule; see `compute/scripts/review_prices.py`). Staging rows are evidence, not catalogue.

One JSON object per line. Fields:

| field | type | rule |
|---|---|---|
| `provider_id` | string | lowercase slug, e.g. `lambda`, `tensorwave`, `aws` |
| `provider_name` | string | as the provider writes it |
| `offer_id` | string | `<provider_id>-<gpu>-<gpus>[-spot]`, lowercase |
| `gpu` | string | canonical: `MI300X`, `MI325X`, `MI350X`, `MI355X`, `H100`, `H200`, `B200`, `B300`, `A100`, `L40S`, `RTX PRO 6000`, ... |
| `vendor` | string | `AMD` or `NVIDIA` |
| `memoryGB` | int or null | per GPU, as advertised |
| `gpus` | int | GPUs in the smallest rentable unit for this offer |
| `rate_usd_per_gpu_hour` | number or null | list price divided by `gpus`; null when not public |
| `rate_basis` | string | `per_gpu_hour`, `per_instance_hour` (then also give `instance_rate_usd_per_hour`) |
| `kind` | string | `on-demand`, `spot`, `reserved`, `marketplace`, `capacity-block` |
| `minimum_billing` | string | e.g. `1 minute`, `5 minutes`, `1 hour`, `1 month`, `unknown` |
| `regions` | list of strings | as advertised; `[]` if unknown |
| `self_serve` | string | `yes` (card + sign-up rents it), `quota` (sign-up plus a limit request), `sales` (contact sales), `unknown` |
| `availability_observed` | string | `available`, `out_of_stock`, `waitlist`, `unknown` |
| `availability_ts` | string or null | UTC ISO time of the observation |
| `source_url` | string | the page the price came from |
| `source_quote` | string | exact text from that page containing the price, at most 200 chars |
| `retrieved_at` | string | UTC ISO time the page was read |
| `campaign_role` | string | `h100-comparator`, `mi300x-neutral`, `amd-next`, `nvidia-next`, `other` |
| `notes` | string | anything the buyer must know: egress, storage extras, price effective dates, login-only pricing |

Rules for lanes:
- Never invent a price. If the price is behind a login or a sales call, set the rate to null and say so in `notes`.
- Prefer the provider's own pricing page. A third-party aggregator is acceptable only with `notes: "aggregator"` and the aggregator URL.
- One row per SKU per provider per kind. Spot and on-demand are separate rows.
- Append rows as you go; a killed lane must leave its rows on disk.
- Record the smallest rentable unit. If a provider sells only 8-GPU nodes, `gpus: 8`.
