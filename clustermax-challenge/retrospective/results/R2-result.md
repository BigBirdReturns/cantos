# R2 result: ClusterMAX 3.0 medals vs status-page incidents in the 180 days before release

Study: `R2-3.0-medals-vs-status-incidents`. Generated 2026-09-29T22:01:18.888186+00:00.

Plan hash verified: **True** (PLAN-R2.md sha256 `a8c93b65041ca8144a21cf4890d2f2724b58a9d91df260e364ec2d3ffc163bdd`; run_r2.py sha256 `5520aee90e2d675abf73c654aa5d78d2ab757f109cb8bcfd238031d5c8e182bd`).

## Input hashes

- `PLAN-R2.md`: `a8c93b65041ca8144a21cf4890d2f2724b58a9d91df260e364ec2d3ffc163bdd`
- `clustermax-3.0.json`: `2be56fa1c95cec7491eb92777a97e772595d294eb24d865dba824a71facf32c4`
- `incidents/akamai.json`: `5901e1b3929c38028f8a4bea97bf16d1bdf5fa017bd8c6248efd6799f94648d9`
- `incidents/atlas-cloud.json`: `b990a784b732f926a68164435c420ec8fdf2b9604d5e8e1757016fb020116632`
- `incidents/cirrascale.json`: `7d872050683f362071bd8c213ff4885eac96f9ab665c84fe93013ac09988d60c`
- `incidents/coreweave.json`: `c9750f3e6f20d3ad442f5ea672267f01dd2de10ee20bd992b65cc3810cc7262b`
- `incidents/crusoe-r2.json`: `1e45be562b57b8e650c24ee407ea879248b93285d9407342a3f3188fca4fed3c`
- `incidents/cudo-compute.json`: `d28dd0b02f4962060f94f0f093db37c7fa1d31dfabbef980abff1c1310e4f20c`
- `incidents/digitalocean.json`: `0ee139bd5d4379740ca3daeea738d77a4965122d625e965744e80f326d9aeb01`
- `incidents/fluidstack.json`: `2884fb3bbed7a76426be89c5d07304f18c448ca0a8399d412dd2e8d713dc6eba`
- `incidents/gcore.json`: `08a4e3763a22e1b0d6e1cc5e9015b942178a0816e45f6b433a9a9db325825227`
- `incidents/google-cloud.json`: `9edbf1059071ae608f6d2833ce6c91eaf67bd58b63cfbbffadeb22f07c13cf4d`
- `incidents/hydra.json`: `d78e10e6ecfbc200c0dcd362ff450296217077b86e8be94ac0b615ef1332b90c`
- `incidents/hyperstack.json`: `b9e7e73317adf4fb12e26f3f4e08aabf9fb1ed0a3feb57bbc7b296a3c102bfc1`
- `incidents/lambda.json`: `70faa611f7ad0c5a163c8396622cc45ad2278ba9d7b5cec5629cef903d355c77`
- `incidents/latitude-sh.json`: `9173f3c27efa737f6cac2853cbb4e7870268b7290b04a5b5b87c9265d3649743`
- `incidents/lightning-ai.json`: `c2852fec9975c66abbd381cad69ed5870ea3ef9b14856644b3ec00d31b7c162b`
- `incidents/mithril.json`: `22f030e07556e8c4b06f2c9602a677bb4cc8e077e69bec2c6491127fad04f595`
- `incidents/nebius.json`: `beeec36b1b24b89dc18351c9b8e0795d8ff74f703740ef971a4694bd6be10776`
- `incidents/ovhcloud.json`: `ecea9b91f048e00184af91667a385f87dc65503430b498f187578401cff1e151`
- `incidents/prime-intellect.json`: `15557b653fea8e0d90de3727d4dc1a819da76136584facd0bde6982413f47eff`
- `incidents/radiant.json`: `56b990637a1f5031a745a38b25306874a7681e21e9c8f1b258bf56262b3ee212`
- `incidents/runpod.json`: `c0400327178458de02a53f13ac733994e6bbea4c6b5b54c80a7993bc3b7f8959`
- `incidents/scaleway.json`: `59bbbc2c0ec900d773fb69605c9e579cd7f90120c6fa4a24930c9bbb1c91cf2a`
- `incidents/sharon-ai.json`: `5a6e0d8ca19a91dbfe6b28c1f204304ac71db041c6727265cd84f524736c22f9`
- `incidents/together-ai.json`: `1d4c3d36a5b5d4fef08b815010b8c879ee1a35072511d19461413a713ae22b6c`
- `incidents/verda.json`: `8f5f889a124b776f205e520e1f9db05fb19e2c751c0626ba2d83350919c33c6c`
- `plan-R2.json`: `5efa99728e6cce2fc462f1073e446e5bdfdccec16508145509d2182402f55ab7`
- `provider_map.json`: `473e46513c3a081e436e1bad1b9c00c51dd2684ccf4716b0d67a428c6e1f0e62`
- `provider_map_R2.json`: `da4b0f14e8a1cdc06631479fe08ec655d8a2f078e61ad51e47f16b540baa9953`
- `ratings/clustermax-2.0.json`: `9b980bb111f0cb457b6fbe9e8158879e08c98489e33665453a96986cb3c6366c`
- `run_r2.py`: `5520aee90e2d675abf73c654aa5d78d2ab757f109cb8bcfd238031d5c8e182bd`

## Deviations from the frozen plan

- After the first R2 run, retrospective/incidents/crusoe.json was renamed crusoe-r2.json, provider_map_R2.json now maps Crusoe to crusoe-r2, run_r2.py was changed only to print these amendments as deviations, and R2 was re-run. (The first run left a file named crusoe.json in incidents/, which scripts/retrospective.py (R1) reads by that name; a rerun of R1 would have admitted Crusoe and changed R1's frozen numbers (n 9 to 10) and failed tests/test_r1_sensitivity.py.) Effect: None on R2 numbers: the file bytes are unchanged and the R2 output was diffed against the first run (only the file path in input_hashes and this deviation entry differ). PLAN-R2.md is unchanged.

## Primary release: ClusterMAX 3.0
Published 2026-09-23. Window: [2026-03-27, 2026-09-23) (180 days).
Included in correlation: 17 (minimum 8).
**Reading (R1 rule, primary measure): inconclusive**

### Analysis
#### `major_or_critical_incident_count`
- Spearman rho: 0.44010131440379385
- Bootstrap 95% interval: [-0.006624921342637869, 0.7488838726248624] (5000/5000 valid draws, 0 skipped, seed 20260929)
- Permutation p (two-sided): 0.0762 (method=random_20000, 20000 permutations)
- Reading: **inconclusive**

#### `all_incident_count`
- Spearman rho: 0.27289286848173583
- Bootstrap 95% interval: [-0.24497620900850944, 0.6996989534243511] (5000/5000 valid draws, 0 skipped, seed 20260929)
- Permutation p (two-sided): 0.28455 (method=random_20000, 20000 permutations)

#### `incident_hours`
- Spearman rho: 0.35847326786003975
- Bootstrap 95% interval: [-0.1731478528596335, 0.7686369625725608] (5000/5000 valid draws, 0 skipped, seed 20260929)
- Permutation p (two-sided): 0.157 (method=random_20000, 20000 permutations)

### Pre-declared sensitivities
```json
{
  "S1_leave_one_out": {
    "runs": [
      {
        "dropped": "Nebius",
        "n": 16,
        "rho": 0.33882831359667626,
        "bootstrap_95ci": [
          -0.10445642710983763,
          0.6908756065541629
        ],
        "permutation_p": 0.20085,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Google Cloud",
        "n": 16,
        "rho": 0.409599575497516,
        "bootstrap_95ci": [
          -0.06936868166337846,
          0.7610303428380517
        ],
        "permutation_p": 0.11635,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Lambda",
        "n": 16,
        "rho": 0.4900989140346001,
        "bootstrap_95ci": [
          0.036906922738736615,
          0.7963693444671506
        ],
        "permutation_p": 0.057,
        "permutation_method": "random_20000",
        "reading": "inconsistent"
      },
      {
        "dropped": "GCore",
        "n": 16,
        "rho": 0.4418602219077721,
        "bootstrap_95ci": [
          -0.05339476582023529,
          0.7833283304257358
        ],
        "permutation_p": 0.08575,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Verda",
        "n": 16,
        "rho": 0.5055874058151759,
        "bootstrap_95ci": [
          0.045449857199701134,
          0.8077531738642963
        ],
        "permutation_p": 0.04595,
        "permutation_method": "random_20000",
        "reading": "inconsistent"
      },
      {
        "dropped": "Prime Intellect",
        "n": 16,
        "rho": 0.45781960839230845,
        "bootstrap_95ci": [
          0.0064741228694181726,
          0.7778872594423153
        ],
        "permutation_p": 0.07545,
        "permutation_method": "random_20000",
        "reading": "inconsistent"
      },
      {
        "dropped": "together.ai",
        "n": 16,
        "rho": 0.5055874058151759,
        "bootstrap_95ci": [
          0.04085058456414856,
          0.8015616894801402
        ],
        "permutation_p": 0.0457,
        "permutation_method": "random_20000",
        "reading": "inconsistent"
      },
      {
        "dropped": "Crusoe",
        "n": 16,
        "rho": 0.43143678350190423,
        "bootstrap_95ci": [
          -0.026236980697037338,
          0.7492442427943781
        ],
        "permutation_p": 0.0943,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "DigitalOcean",
        "n": 16,
        "rho": 0.43875399890666295,
        "bootstrap_95ci": [
          -0.014292970687568438,
          0.7584005042423645
        ],
        "permutation_p": 0.089,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Hyperstack",
        "n": 16,
        "rho": 0.43875399890666295,
        "bootstrap_95ci": [
          -0.014292970687568438,
          0.7584005042423645
        ],
        "permutation_p": 0.089,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "RunPod",
        "n": 16,
        "rho": 0.5168457169548667,
        "bootstrap_95ci": [
          0.10911364858911071,
          0.7878129992424826
        ],
        "permutation_p": 0.0407,
        "permutation_method": "random_20000",
        "reading": "inconsistent"
      },
      {
        "dropped": "Radiant",
        "n": 16,
        "rho": 0.4144314637258632,
        "bootstrap_95ci": [
          -0.06209174398528617,
          0.7591269534230485
        ],
        "permutation_p": 0.10765,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "latitude.sh",
        "n": 16,
        "rho": 0.4487471216448498,
        "bootstrap_95ci": [
          0.0,
          0.751000073707729
        ],
        "permutation_p": 0.0794,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Sharon AI",
        "n": 16,
        "rho": 0.405552109830022,
        "bootstrap_95ci": [
          -0.07080415685968744,
          0.746531073325282
        ],
        "permutation_p": 0.11475,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Hydra",
        "n": 16,
        "rho": 0.3728589977990665,
        "bootstrap_95ci": [
          -0.1034136612864654,
          0.7156425298741611
        ],
        "permutation_p": 0.14935,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Akamai",
        "n": 16,
        "rho": 0.3728589977990665,
        "bootstrap_95ci": [
          -0.1034136612864654,
          0.7156425298741611
        ],
        "permutation_p": 0.14935,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Mithril",
        "n": 16,
        "rho": 0.4727844594185581,
        "bootstrap_95ci": [
          -0.0036694130371822163,
          0.7827848387566597
        ],
        "permutation_p": 0.066,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      }
    ],
    "rho_min": 0.33882831359667626,
    "rho_max": 0.5168457169548667,
    "readings": {
      "consistent": 0,
      "inconclusive": 12,
      "inconsistent": 5
    }
  },
  "S2_permutation": {
    "note": "n! = 355687428096000 > 500000: main p uses 20000 random draws; stability check with 200000 draws, seed 20260930",
    "main_p": 0.0762,
    "stability_p": 0.07845
  },
  "S3_maintenance_mislabel": {
    "regex": "\\b(maintenance|planned|scheduled|upgrade)\\b",
    "providers_affected": [
      {
        "provider": "GCore",
        "major_or_critical_titles_matching_maintenance_regex": 1
      },
      {
        "provider": "Hyperstack",
        "major_or_critical_titles_matching_maintenance_regex": 2
      }
    ],
    "rho": 0.44010131440379385,
    "bootstrap_95ci": [
      -0.006624921342637869,
      0.7488838726248624
    ],
    "permutation_p": 0.076,
    "reading": "inconclusive"
  },
  "S4_bootstrap_seed_robustness": {
    "seeds": "1..200",
    "draws": 5000,
    "readings": {
      "consistent": 0,
      "inconclusive": 142,
      "inconsistent": 58
    },
    "lower_bound_min": -0.03430821606407587,
    "lower_bound_max": 0.02297217816293665,
    "upper_bound_min": 0.7360953419911146,
    "upper_bound_max": 0.7661532683217395
  },
  "S5_strict_coverage": {
    "n": 15,
    "dropped": [
      "Google Cloud",
      "Lambda"
    ],
    "rho": 0.4640833215001505,
    "bootstrap_95ci": [
      -0.04553445130592149,
      0.8041849863590823
    ],
    "permutation_p": 0.0815,
    "permutation_method": "random_20000",
    "reading": "inconclusive"
  },
  "S6_critical_only": {
    "rho": -0.04596269680428604,
    "bootstrap_95ci": [
      -0.5265123716169108,
      0.4423528664586551
    ],
    "permutation_p": 0.85655,
    "reading": "inconclusive"
  }
}
```

### Eligible providers
- **Nebius** (Platinum): eligible -- ordinal=6 major/critical=17 all=39 hours=179.8016 [declared_coverage]
- **Google Cloud** (Gold): eligible -- ordinal=5 major/critical=5 all=5 hours=546.9333 [capped_feed_rule (oldest record 2026-02-27 < window start 2026-03-27)]
- **Lambda** (Silver): eligible -- ordinal=4 major/critical=2 all=16 hours=1442.9692 [capped_feed_rule (oldest record 2026-02-13 < window start 2026-03-27)]
- **GCore** (Bronze): eligible -- ordinal=3 major/critical=58 all=85 hours=1027.9349 [declared_coverage]
- **Verda** (Bronze): eligible -- ordinal=3 major/critical=0 all=6 hours=17.4833 [declared_coverage]
- **Prime Intellect** (Bronze): eligible -- ordinal=3 major/critical=2 all=10 hours=1689.0167 [declared_coverage]
- **together.ai** (Bronze): eligible -- ordinal=3 major/critical=0 all=0 hours=0.0 [declared_coverage]
- **Crusoe** (Bronze): eligible -- ordinal=3 major/critical=5 all=21 hours=139.2309 [declared_coverage]
- **DigitalOcean** (Bronze): eligible -- ordinal=3 major/critical=8 all=59 hours=332.9301 [declared_coverage]
- **Hyperstack** (Bronze): eligible -- ordinal=3 major/critical=9 all=10 hours=57.2871 [declared_coverage]
- **RunPod** (Participation Ribbon): eligible -- ordinal=2 major/critical=11 all=33 hours=439.1833 [declared_coverage]
- **Radiant** (Participation Ribbon): eligible -- ordinal=2 major/critical=0 all=0 hours=0.0 [declared_coverage]
- **latitude.sh** (Participation Ribbon): eligible -- ordinal=2 major/critical=4 all=9 hours=54.6994 [declared_coverage]
- **Sharon AI** (Underperforming): eligible -- ordinal=1 major/critical=1 all=1 hours=0.4569 [declared_coverage]
- **Hydra** (Underperforming): eligible -- ordinal=1 major/critical=0 all=0 hours=0.0 [declared_coverage]
- **Akamai** (Underperforming): eligible -- ordinal=1 major/critical=0 all=59 hours=2706.1629 (capped) [declared_coverage]
- **Mithril** (Underperforming): eligible -- ordinal=1 major/critical=4 all=6 hours=38.6835 [declared_coverage]

### Excluded providers
- **CoreWeave** (Platinum): excluded -- coverage_start not recorded and the feed does not reach back past the window start (oldest non-maintenance record 2026-09-11; coverage_end 2026-09-29)
- **Oracle** (Gold): excluded -- no incident data file found (expected oracle.json)
- **Azure** (Silver): excluded -- no incident data file found (expected azure.json)
- **Firmus** (Silver): excluded -- no incident data file found (expected firmus.json)
- **GMI** (Silver): excluded -- no incident data file found (expected gmi.json)
- **TensorWave** (Silver): excluded -- no incident data file found (expected tensorwave.json)
- **AWS** (Bronze): excluded -- no incident data file found (expected aws.json)
- **moonlite** (Bronze): excluded -- no incident data file found (expected moonlite.json)
- **GMO GPU Cloud** (Bronze): excluded -- no incident data file found (expected gmo-gpu-cloud.json)
- **Vultr** (Participation Ribbon): excluded -- no incident data file found (expected vultr.json)
- **neysa** (Participation Ribbon): excluded -- no incident data file found (expected neysa.json)
- **VESSL AI** (Participation Ribbon): excluded -- no incident data file found (expected vessl-ai.json)
- **Shadeform** (Participation Ribbon): excluded -- no incident data file found (expected shadeform.json)
- **FPT AI Factory** (Participation Ribbon): excluded -- no incident data file found (expected fpt-ai-factory.json)
- **Core42** (Participation Ribbon): excluded -- no incident data file found (expected core42.json)
- **IBM Cloud** (Participation Ribbon): excluded -- no incident data file found (expected ibm-cloud.json)
- **Buzz HPC** (Participation Ribbon): excluded -- no incident data file found (expected buzz-hpc.json)
- **Vast.ai** (Participation Ribbon): excluded -- no incident data file found (expected vast-ai.json)
- **BitDeer** (Participation Ribbon): excluded -- no incident data file found (expected bitdeer.json)
- **Hyperbolic** (Participation Ribbon): excluded -- no incident data file found (expected hyperbolic.json)
- **STN** (Participation Ribbon): excluded -- no incident data file found (expected stn.json)
- **IREN** (Underperforming): excluded -- no incident data file found (expected iren.json)
- **FarmGPU** (Underperforming): excluded -- no incident data file found (expected farmgpu.json)
- **Whitefiber** (Underperforming): excluded -- no incident data file found (expected whitefiber.json)
- **PaleBlueDot.AI** (Underperforming): excluded -- no incident data file found (expected palebluedot-ai.json)
- **Hetzner** (Underperforming): excluded -- no incident data file found (expected hetzner.json)
- **OVHcloud** (Underperforming): excluded -- coverage_start not recorded and the feed does not reach back past the window start (oldest non-maintenance record 2026-09-25; coverage_end 2026-09-29)
- **Massed Compute** (Underperforming): excluded -- no incident data file found (expected massed-compute.json)
- **FluidStack** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Cirrascale** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Lightning AI** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Scaleway** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Cudo Compute** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **DENVR Dataworks** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Atlas Cloud** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **SpaceX** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Mistral AI** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **PIC** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **NScale** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Highrise** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Corvex** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Andromeda** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Volta** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **firebird** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Tatra SuperCompute** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Sesterce** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **groq** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Yotta** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **darya.ai** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **boostrun** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **GLOBAL AI** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Argentum** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **QumulusAI** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Alibaba Cloud** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **MegaSpeed International** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **BytePlus** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Humain** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **SK telecom** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **NAVER** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Indosat Ooredoo Hutchison** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)

## Secondary release: ClusterMAX 2.0
Published 2025-11-06. Window: [2026-03-27, 2026-09-23) (180 days).
Included in correlation: 22 (minimum 8).
**Reading (R1 rule, primary measure): inconclusive**

### Analysis
#### `major_or_critical_incident_count`
- Spearman rho: 0.23086658330454984
- Bootstrap 95% interval: [-0.20034227988152564, 0.6187366819111348] (5000/5000 valid draws, 0 skipped, seed 20260929)
- Permutation p (two-sided): 0.2959 (method=random_20000, 20000 permutations)
- Reading: **inconclusive**

#### `all_incident_count`
- Spearman rho: 0.0861258498936082
- Bootstrap 95% interval: [-0.38878802733975554, 0.5238285768824379] (5000/5000 valid draws, 0 skipped, seed 20260929)
- Permutation p (two-sided): 0.69615 (method=random_20000, 20000 permutations)

#### `incident_hours`
- Spearman rho: 0.10627856293678117
- Bootstrap 95% interval: [-0.34660393470755263, 0.5636977756474592] (5000/5000 valid draws, 0 skipped, seed 20260929)
- Permutation p (two-sided): 0.63675 (method=random_20000, 20000 permutations)

### Pre-declared sensitivities
```json
{
  "S1_leave_one_out": {
    "runs": [
      {
        "dropped": "Nebius",
        "n": 21,
        "rho": 0.15332778361925628,
        "bootstrap_95ci": [
          -0.28633267307511623,
          0.562661273950926
        ],
        "permutation_p": 0.4986,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Crusoe",
        "n": 21,
        "rho": 0.20448483515790844,
        "bootstrap_95ci": [
          -0.2509280349023866,
          0.624825169069892
        ],
        "permutation_p": 0.3677,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "FluidStack",
        "n": 21,
        "rho": 0.3564112921193785,
        "bootstrap_95ci": [
          -0.06354463243969166,
          0.6766758520455325
        ],
        "permutation_p": 0.1137,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Together.ai",
        "n": 21,
        "rho": 0.3042195826057476,
        "bootstrap_95ci": [
          -0.12813912723127055,
          0.6692304500703258
        ],
        "permutation_p": 0.17705,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Lambda",
        "n": 21,
        "rho": 0.2516205600502124,
        "bootstrap_95ci": [
          -0.18855238603232174,
          0.639741509045089
        ],
        "permutation_p": 0.2673,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Google Cloud",
        "n": 21,
        "rho": 0.2161697653922319,
        "bootstrap_95ci": [
          -0.23436870194041534,
          0.6095755421890815
        ],
        "permutation_p": 0.34325,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Scaleway",
        "n": 21,
        "rho": 0.19528234432383315,
        "bootstrap_95ci": [
          -0.2565237608676249,
          0.5861122054548229
        ],
        "permutation_p": 0.3913,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Cirrascale",
        "n": 21,
        "rho": 0.3042195826057476,
        "bootstrap_95ci": [
          -0.12982954396206914,
          0.6731541304445231
        ],
        "permutation_p": 0.17925,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "GCore",
        "n": 21,
        "rho": 0.1855007599927646,
        "bootstrap_95ci": [
          -0.25676263168397156,
          0.5864393712311061
        ],
        "permutation_p": 0.42,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Hyperstack",
        "n": 21,
        "rho": 0.24790870708605023,
        "bootstrap_95ci": [
          -0.185263609671288,
          0.6279570780096394
        ],
        "permutation_p": 0.27735,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "RunPod",
        "n": 21,
        "rho": 0.24790870708605023,
        "bootstrap_95ci": [
          -0.185263609671288,
          0.6279570780096394
        ],
        "permutation_p": 0.27735,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Atlas Cloud",
        "n": 21,
        "rho": 0.27356639145579525,
        "bootstrap_95ci": [
          -0.16460829916870037,
          0.6516386279581741
        ],
        "permutation_p": 0.2292,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Prime Intellect",
        "n": 21,
        "rho": 0.22548954741457009,
        "bootstrap_95ci": [
          -0.21594695351756057,
          0.614879144338691
        ],
        "permutation_p": 0.3278,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Cudo Compute",
        "n": 21,
        "rho": 0.21827871934034876,
        "bootstrap_95ci": [
          -0.23575152277264444,
          0.630391359923369
        ],
        "permutation_p": 0.3415,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "latitude.sh",
        "n": 21,
        "rho": 0.22633517318081295,
        "bootstrap_95ci": [
          -0.2047809825760318,
          0.6113243486559655
        ],
        "permutation_p": 0.3223,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Lightning AI",
        "n": 21,
        "rho": 0.22548954741457009,
        "bootstrap_95ci": [
          -0.2076976998987915,
          0.6098076560790693
        ],
        "permutation_p": 0.32325,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Verda",
        "n": 21,
        "rho": 0.21827871934034876,
        "bootstrap_95ci": [
          -0.23179979886310131,
          0.630382726232861
        ],
        "permutation_p": 0.34275,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "DigitalOcean",
        "n": 21,
        "rho": 0.24790870708605023,
        "bootstrap_95ci": [
          -0.18364015161868877,
          0.6354651695362825
        ],
        "permutation_p": 0.27685,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Sharon AI",
        "n": 21,
        "rho": 0.20292912413326344,
        "bootstrap_95ci": [
          -0.2357601131168215,
          0.6000897310377111
        ],
        "permutation_p": 0.3739,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Hydra",
        "n": 21,
        "rho": 0.16182856037726304,
        "bootstrap_95ci": [
          -0.27225642908646164,
          0.5658266134522691
        ],
        "permutation_p": 0.48115,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Akamai",
        "n": 21,
        "rho": 0.16182856037726304,
        "bootstrap_95ci": [
          -0.27225642908646164,
          0.5658266134522691
        ],
        "permutation_p": 0.48115,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      },
      {
        "dropped": "Mithril",
        "n": 21,
        "rho": 0.24280195641914765,
        "bootstrap_95ci": [
          -0.2008479689991682,
          0.6359843752893444
        ],
        "permutation_p": 0.2898,
        "permutation_method": "random_20000",
        "reading": "inconclusive"
      }
    ],
    "rho_min": 0.15332778361925628,
    "rho_max": 0.3564112921193785,
    "readings": {
      "consistent": 0,
      "inconclusive": 22,
      "inconsistent": 0
    }
  },
  "S2_permutation": {
    "note": "n! = 1124000727777607680000 > 500000: main p uses 20000 random draws; stability check with 200000 draws, seed 20260930",
    "main_p": 0.2959,
    "stability_p": 0.29877
  },
  "S3_maintenance_mislabel": {
    "regex": "\\b(maintenance|planned|scheduled|upgrade)\\b",
    "providers_affected": [
      {
        "provider": "GCore",
        "major_or_critical_titles_matching_maintenance_regex": 1
      },
      {
        "provider": "Hyperstack",
        "major_or_critical_titles_matching_maintenance_regex": 2
      }
    ],
    "rho": 0.23086658330454984,
    "bootstrap_95ci": [
      -0.20034227988152564,
      0.6187366819111348
    ],
    "permutation_p": 0.29585,
    "reading": "inconclusive"
  },
  "S4_bootstrap_seed_robustness": {
    "seeds": "1..200",
    "draws": 5000,
    "readings": {
      "consistent": 0,
      "inconclusive": 200,
      "inconsistent": 0
    },
    "lower_bound_min": -0.23702196070615866,
    "lower_bound_max": -0.18017887569798902,
    "upper_bound_min": 0.5940216817700527,
    "upper_bound_max": 0.6263426739598797
  },
  "S5_strict_coverage": {
    "n": 20,
    "dropped": [
      "Lambda",
      "Google Cloud"
    ],
    "rho": 0.23651584262814088,
    "bootstrap_95ci": [
      -0.22596725632213066,
      0.6425339358186556
    ],
    "permutation_p": 0.31325,
    "permutation_method": "random_20000",
    "reading": "inconclusive"
  },
  "S6_critical_only": {
    "rho": -0.0432508546623793,
    "bootstrap_95ci": [
      -0.46730444597451937,
      0.3821831235722228
    ],
    "permutation_p": 0.85135,
    "reading": "inconclusive"
  }
}
```

### Eligible providers
- **Nebius** (Gold): eligible -- ordinal=5 major/critical=17 all=39 hours=179.8016 [declared_coverage]
- **Crusoe** (Gold): eligible -- ordinal=5 major/critical=5 all=21 hours=139.2309 [declared_coverage]
- **FluidStack** (Gold): eligible -- ordinal=5 major/critical=0 all=0 hours=0.0 [declared_coverage]
- **Together.ai** (Silver): eligible -- ordinal=4 major/critical=0 all=0 hours=0.0 [declared_coverage]
- **Lambda** (Silver): eligible -- ordinal=4 major/critical=2 all=16 hours=1442.9692 [capped_feed_rule (oldest record 2026-02-13 < window start 2026-03-27)]
- **Google Cloud** (Silver): eligible -- ordinal=4 major/critical=5 all=5 hours=546.9333 [capped_feed_rule (oldest record 2026-02-27 < window start 2026-03-27)]
- **Scaleway** (Silver): eligible -- ordinal=4 major/critical=32 all=268 hours=14392.892 (capped) [declared_coverage]
- **Cirrascale** (Silver): eligible -- ordinal=4 major/critical=0 all=0 hours=0.0 [declared_coverage]
- **GCore** (Silver): eligible -- ordinal=4 major/critical=58 all=85 hours=1027.9349 [declared_coverage]
- **Hyperstack** (Bronze): eligible -- ordinal=3 major/critical=9 all=10 hours=57.2871 [declared_coverage]
- **RunPod** (Bronze): eligible -- ordinal=3 major/critical=11 all=33 hours=439.1833 [declared_coverage]
- **Atlas Cloud** (Bronze): eligible -- ordinal=3 major/critical=40 all=40 hours=3.3168 [declared_coverage]
- **Prime Intellect** (Bronze): eligible -- ordinal=3 major/critical=2 all=10 hours=1689.0167 [declared_coverage]
- **Cudo Compute** (Bronze): eligible -- ordinal=3 major/critical=0 all=0 hours=0.0 [declared_coverage]
- **latitude.sh** (Bronze): eligible -- ordinal=3 major/critical=4 all=9 hours=54.6994 [declared_coverage]
- **Lightning AI** (Bronze): eligible -- ordinal=3 major/critical=2 all=10 hours=68.6461 [declared_coverage]
- **Verda** (Bronze): eligible -- ordinal=3 major/critical=0 all=6 hours=17.4833 [declared_coverage]
- **DigitalOcean** (Bronze): eligible -- ordinal=3 major/critical=8 all=59 hours=332.9301 [declared_coverage]
- **Sharon AI** (Underperforming): eligible -- ordinal=1 major/critical=1 all=1 hours=0.4569 [declared_coverage]
- **Hydra** (Underperforming): eligible -- ordinal=1 major/critical=0 all=0 hours=0.0 [declared_coverage]
- **Akamai** (Underperforming): eligible -- ordinal=1 major/critical=0 all=59 hours=2706.1629 (capped) [declared_coverage]
- **Mithril** (Underperforming): eligible -- ordinal=1 major/critical=4 all=6 hours=38.6835 [declared_coverage]

### Excluded providers
- **CoreWeave** (Platinum): excluded -- coverage_start not recorded and the feed does not reach back past the window start (oldest non-maintenance record 2026-09-11; coverage_end 2026-09-29)
- **Oracle** (Gold): excluded -- no incident data file found (expected oracle.json)
- **Azure** (Gold): excluded -- no incident data file found (expected azure.json)
- **AWS** (Silver): excluded -- no incident data file found (expected aws.json)
- **Vultr** (Silver): excluded -- no incident data file found (expected vultr.json)
- **Voltage Park** (Silver): excluded -- no incident data file found (expected voltage-park.json)
- **Firmus** (Silver): excluded -- no incident data file found (expected firmus.json)
- **GMO GPU Cloud** (Silver): excluded -- no incident data file found (expected gmo-gpu-cloud.json)
- **TensorWave** (Silver): excluded -- no incident data file found (expected tensorwave.json)
- **Shadeform** (Bronze): excluded -- no incident data file found (expected shadeform.json)
- **Neysa** (Bronze): excluded -- no incident data file found (expected neysa.json)
- **STN** (Bronze): excluded -- no incident data file found (expected stn.json)
- **GMI** (Bronze): excluded -- no incident data file found (expected gmi.json)
- **Qubrid** (Bronze): excluded -- no incident data file found (expected qubrid.json)
- **DENVR Dataworks** (Bronze): excluded -- no incident data file found (expected denvr-dataworks.json)
- **IBM Cloud** (Bronze): excluded -- no incident data file found (expected ibm-cloud.json)
- **Hot Aisle** (Bronze): excluded -- no incident data file found (expected hot-aisle.json)
- **Buzz HPC** (Bronze): excluded -- no incident data file found (expected buzz-hpc.json)
- **Vast.ai** (Bronze): excluded -- no incident data file found (expected vast-ai.json)
- **IREN** (Underperforming): excluded -- no incident data file found (expected iren.json)
- **FarmGPU** (Underperforming): excluded -- no incident data file found (expected farmgpu.json)
- **Whitefiber** (Underperforming): excluded -- no incident data file found (expected whitefiber.json)
- **deepinfra** (Underperforming): excluded -- no incident data file found (expected deepinfra.json)
- **dstack** (Underperforming): excluded -- no incident data file found (expected dstack.json)
- **PaleBlueDot.AI** (Underperforming): excluded -- no incident data file found (expected palebluedot-ai.json)
- **Hyperbolic** (Underperforming): excluded -- no incident data file found (expected hyperbolic.json)
- **GPU.NET** (Underperforming): excluded -- no incident data file found (expected gpu-net.json)
- **Hetzner** (Underperforming): excluded -- no incident data file found (expected hetzner.json)
- **Clore.ai** (Underperforming): excluded -- no incident data file found (expected clore-ai.json)
- **Massed Compute** (Underperforming): excluded -- no incident data file found (expected massed-compute.json)
- **Exabits** (Underperforming): excluded -- no incident data file found (expected exabits.json)
- **Sesterce** (Underperforming): excluded -- no incident data file found (expected sesterce.json)
- **E2E Cloud** (Underperforming): excluded -- no incident data file found (expected e2e-cloud.json)
- **OVHcloud** (Underperforming): excluded -- coverage_start not recorded and the feed does not reach back past the window start (oldest non-maintenance record 2026-09-25; coverage_end 2026-09-29)
- **Aethir** (Underperforming): excluded -- no incident data file found (expected aethir.json)
- **Akash** (Underperforming): excluded -- no incident data file found (expected akash.json)
- **Salad** (Underperforming): excluded -- no incident data file found (expected salad.json)
- **Nscale** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Core42** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Humain** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Corvex** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Highrise** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **BluSky AI** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Arc Compute** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Telus** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Telenor** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Mistral AI** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Firebird** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Alibaba Cloud** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **MegaSpeed International** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **BitDeer** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **RunSun Cloud** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **FPT Cloud** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **backend AI** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **NAVER** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Indosat Ooredoo Hutchison** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Sakura** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **Yotta** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **neevcloud** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **evroc** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)
- **greenai.cloud** (Unavailable): excluded -- tier 'Unavailable' is not rated in this analysis (excluded by plan)

## Known limits (from PLAN-R2.md)

Self-reported status pages; provider-wide records; severity vocabularies differ and were mapped by rules fixed in PLAN-R2.md; the 3.0 rating is dated at the end of the window, so this is a concurrent, not predictive, comparison; reliability is one of ten criteria. See PLAN-R2.md in full.
