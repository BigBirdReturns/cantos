```json
{
  "id": "voltagepark-pricing",
  "title": "Voltage Park H100 starting-price statement",
  "spine": "Voltage Park pricing page | publication date unknown; retrieved 2026-09-25 UTC | H100 starts at $1.99/GPU-hour for one GPU, no contract | imported + attributed | allocation and running cost unknown",
  "dimensions": {
    "measured": null,
    "imported": true,
    "modeled": false,
    "attributed": true
  },
  "a_claim": {
    "statement": "Voltage Park's pricing page says one H100 GPU can be rented for one hour starting at $1.99 without a contract. This is a starting-price offer, not evidence of a particular obtainable seat, minimum bill, or measured cost.",
    "period": {
      "publication_date": null,
      "publication_date_basis": null,
      "experiment_date": null,
      "retrieved_at": "2026-09-25T02:18:23.480517+00:00"
    },
    "conditions": {
      "provider": "Voltage Park",
      "product": "H100 GPU",
      "gpus": {
        "value": 1,
        "unit": "GPU",
        "source": "source.json",
        "source_date": null
      },
      "purchase_basis": "Starting price; no contract",
      "minimum_rentable_unit": null,
      "commitment": "No contract stated"
    },
    "results": {
      "starting_price": {
        "value": 1.99,
        "unit": "USD / GPU-hour",
        "source": "https://voltagepark.com/pricing",
        "source_date": null,
        "date_kind": "Publication date not supplied",
        "supports": "A stated starting price for one H100 GPU for one hour without a contract."
      }
    },
    "does_not_establish": "A specific seat's availability or configuration, an actual billed amount, minimum bill, or accepted-request cost."
  },
  "b_population": {
    "population": "Pricing statement for one H100 GPU",
    "denominator": null,
    "acceptance_rule": null,
    "exclusions": null,
    "observation_window": null
  },
  "c_parties": {
    "observer": "Voltage Park pricing page",
    "conditions_controller": "Voltage Park controls its offers and allocation",
    "access": {
      "provider": "Voltage Park",
      "mode": "Public pricing page; panel says contact for pricing",
      "account_class": null
    },
    "funding": {
      "payer": null,
      "relationship": null
    },
    "observer_benefit": {
      "benefits_from_outcome": null,
      "relationship": null,
      "basis": null
    }
  },
  "d_materials": {
    "sources": [
      {
        "path_or_url": "https://voltagepark.com/pricing",
        "publication_date": null,
        "publication_date_basis": null,
        "experiment_date": null,
        "retrieved_at": "2026-09-25T02:18:23.480517+00:00",
        "local_inspection_date": "2026-09-24"
      }
    ],
    "primary_url": "https://voltagepark.com/pricing",
    "obtainable": "Selected visible excerpts from the primary pricing page; the supplied capture is not a full page.",
    "procedure": null,
    "missing": [
      "Publication date",
      "Specific allocation availability and configuration",
      "Minimum bill and actual billing details",
      "Benchmark or accepted-request data"
    ],
    "capture_sha256": "bdb6b3b079e8f8a14bac1b7eaf2ead1f98ce44bf0382f9e9796522d9a665f7d9"
  },
  "e_checks": {
    "inspected": {
      "who": null,
      "when": null,
      "scope": "Supplied selected excerpts only; no full-page inspection",
      "independent_validation": false
    },
    "recomputed": {
      "who": null,
      "when": null,
      "scope": null
    },
    "repeated": {
      "who": null,
      "when": null,
      "scope": null
    }
  },
  "filing_version": 2
}
```

For “MI300X is cheaper per accepted request than H100 on a self-serve seat in September 2026,” **run3-at0** is the only supplied record with an accepted-request comparison: it reports $0.74 per 1,000 accepted requests for the MI300X own-seat equivalent versus a reported $1.20 for the DigitalOcean H100 comparator, a $0.46 difference (about 38% lower) under that workload and accounting. It is one run per arm; the H100 receipt was not inspected. The $0.90 shared-seat aggregate includes mixed arms and cannot be assigned to the MI300X arm alone, so it does not establish that same comparison for an actual standalone MI300X seat.

The new Voltage Park page gives a starting H100 hourly price, but no accepted-work result or publication date; retrieval in September does not establish when the price was published. It cannot be combined with the run’s MI300X result to establish September accepted-request costs. InferenceX reports aggregate latency without request-level acceptance; ClusterMAX is a managed-cluster rating; Mercatus is a volume-weighted index of on-demand hourly prices, **not a specific rental price**; and the Hot Aisle blog is an attributed July price and capacity statement, not September accepted-work evidence. The packet does not establish Voltage Park seat availability, its minimum bill, or its actual cost for accepted requests.
