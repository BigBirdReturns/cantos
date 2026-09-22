# Hot Aisle workload economics: free proof starter

Prepared by Second Run, 22 September 2026. Independent research prototype; no provider endorsement. No rented hardware, cloud benchmarks, model loading, private account access or outreach occurred in creating this package.

## What is implemented

Open `index.html` locally. It uses a pinned public-price snapshot to calculate allocation-level price/throughput break-even thresholds. It optionally applies user-entered accepted-work rates and exports a local JSON receipt of the assumptions and result. It does not verify those rates. Zero accepted work, missing comparison criteria and invalid inputs do not produce a positive comparison.

The page runs offline without dependencies, telemetry or automatic network requests. External source links open only when selected. A matching standard-library Python implementation is in `scripts/price_math.py`; run `python -m unittest discover -s hot-aisle/scripts -v` from the repository root for the arithmetic tests.

`data/prices.json` preserves the exact rates, source locations, review date and commercial boundaries. The displayed October prices are announced future prices effective 1 October 2026. This is Nebius AI Cloud infrastructure pricing, not a Token Factory Dedicated Endpoint quote. Confirm actual allocation sizes and capacity availability; per-GPU list pricing does not establish single-GPU availability for each instance family. Additional costs default to zero and remain outside the calculation until supplied. Include all billed hardware and the entire paid commitment, including any idle period.

## What is proposed, not implemented or measured

`FIRST_CAMPAIGN.md` specifies one bounded workload experiment using Hot Aisle's existing OpenCode/vLLM example as the starting point. The capture runner, runtime-specific import adapter, independent task evaluator, matched competitor measurement and public workload verdict are not implemented by this package. The gift can start with already-approved raw run logs and an applicable quote instead of allocating compute.

A future report must separately classify producer-run results, independently rerun results, modeled prices and actual billed costs. A portable evidence packet supports inspection; it is not an attestation of historical authenticity or a claim of full execution survivability.

## Reuse

Original code and original documentation are MIT licensed. Provider trademarks, model licenses, runtime licenses and third-party pages retain their own rights. No model weights or third-party article copies are bundled. Hot Aisle can host or adapt this calculator without buying a service. The evidence methodology must permit any provider to lose a workload comparison.

## Published location and deployment

Live calculator: https://bigbirdreturns.github.io/axm-tools/hot-aisle/

The existing root Pages workflow serves this directory unchanged. No new backend, accounts, shared libraries or scheduled work are introduced. The free source kit is this directory: the HTML, arithmetic implementation and tests, pricing snapshot, license and proposed campaign. The original standalone calculator still runs by opening index.html locally.

## Ownership and what can rot

All files are steward-owned. No customer inputs are persisted or uploaded. The rates are a visibly dated 22 September 2026 snapshot, not a live quote. Effective dates, available configurations and terms can change. Refresh data/prices.json and the matching embedded price-data block together after reviewing the cited primary sources. New GPU measurements require separate evidence and must not be inferred from price ratios. Model/runtime recipes in the proposed campaign can age independently. No frozen release is rewritten.
