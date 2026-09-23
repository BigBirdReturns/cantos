# R1 result: do ClusterMAX medals track providers’ own public incident records?

Study: `R1-medals-vs-status-incidents`. Generated 2026-09-23T10:12:32.927782+00:00.

Plan hash verified: **True** (PLAN.md sha256 `6ba62fe9e0cd1ce13cc51c8215e33bdf375ae5fb77a7e4f603722085dce1b364` matches `retrospective/plan.json`).

## Input hashes

- `PLAN.md`: `6ba62fe9e0cd1ce13cc51c8215e33bdf375ae5fb77a7e4f603722085dce1b364`
- `incidents/akamai.json`: `5901e1b3929c38028f8a4bea97bf16d1bdf5fa017bd8c6248efd6799f94648d9`
- `incidents/cirrascale.json`: `7d872050683f362071bd8c213ff4885eac96f9ab665c84fe93013ac09988d60c`
- `incidents/digitalocean.json`: `0ee139bd5d4379740ca3daeea738d77a4965122d625e965744e80f326d9aeb01`
- `incidents/hyperstack.json`: `b9e7e73317adf4fb12e26f3f4e08aabf9fb1ed0a3feb57bbc7b296a3c102bfc1`
- `incidents/lambda.json`: `70faa611f7ad0c5a163c8396622cc45ad2278ba9d7b5cec5629cef903d355c77`
- `incidents/latitude-sh.json`: `9173f3c27efa737f6cac2853cbb4e7870268b7290b04a5b5b87c9265d3649743`
- `incidents/lightning-ai.json`: `c2852fec9975c66abbd381cad69ed5870ea3ef9b14856644b3ec00d31b7c162b`
- `incidents/nebius.json`: `beeec36b1b24b89dc18351c9b8e0795d8ff74f703740ef971a4694bd6be10776`
- `incidents/scaleway.json`: `59bbbc2c0ec900d773fb69605c9e579cd7f90120c6fa4a24930c9bbb1c91cf2a`
- `incidents/sharon-ai.json`: `5a6e0d8ca19a91dbfe6b28c1f204304ac71db041c6727265cd84f524736c22f9`
- `plan.json`: `2ffe38d650bd7ef5fe1512b3e3f85b89d237a5b07101da9c212556925011b950`
- `provider_map.json`: `473e46513c3a081e436e1bad1b9c00c51dd2684ccf4716b0d67a428c6e1f0e62`
- `ratings/clustermax-1.0.json`: `e1fc6438d71e90273c728851acf58e7215bd0be2c53375b0001a590339331306`
- `ratings/clustermax-2.0.json`: `9b980bb111f0cb457b6fbe9e8158879e08c98489e33665453a96986cb3c6366c`

## Deviations from the frozen plan

None.

## Primary release: 2.0
Published 2025-11-06. Window: [2025-11-06, 2026-05-05) (180 days).
Included in correlation: 9 (minimum required: 8).
**Reading: inconclusive**

### Analysis
#### `major_or_critical_incident_count`
- Spearman rho (average ranks): 0.6377928041432807
- Bootstrap 95% interval: [0.0, 0.9365858115816939] (4999/5000 valid draws, 1 skipped for zero rank variance, seed 20260923)
- Permutation p-value (two-sided): 0.07525 (method=random_20000, 20000 permutations, 0 skipped for zero rank variance)
- Reading: **inconclusive**

#### `all_incident_count`
- Spearman rho (average ranks): 0.41017349611934645
- Bootstrap 95% interval: [-0.4570983002634959, 0.8800782326533971] (4999/5000 valid draws, 1 skipped for zero rank variance, seed 20260923)
- Permutation p-value (two-sided): 0.2731 (method=random_20000, 20000 permutations, 0 skipped for zero rank variance)

#### `incident_hours`
- Spearman rho (average ranks): 0.05292561240249632
- Bootstrap 95% interval: [-0.7668931921093695, 0.7990508158506007] (4999/5000 valid draws, 1 skipped for zero rank variance, seed 20260923)
- Permutation p-value (two-sided): 0.9109 (method=random_20000, 20000 permutations, 0 skipped for zero rank variance)

### Providers
- **CoreWeave** (Platinum): excluded -- no incident data file found (expected coreweave.json)
- **Oracle** (Gold): excluded -- no incident data file found (expected oracle.json)
- **Nebius** (Gold): eligible -- ordinal=4 major/critical=28 all=56 hours=174.4379
- **Azure** (Gold): excluded -- no incident data file found (expected azure.json)
- **Crusoe** (Gold): excluded -- no incident data file found (expected crusoe.json)
- **FluidStack** (Gold): excluded -- no incident data file found (expected fluidstack.json)
- **Together.ai** (Silver): excluded -- no incident data file found (expected together-ai.json)
- **Lambda** (Silver): excluded -- coverage_start/coverage_end not recorded; manual verification pending
- **Google Cloud** (Silver): excluded -- no incident data file found (expected google-cloud.json)
- **AWS** (Silver): excluded -- no incident data file found (expected aws.json)
- **Scaleway** (Silver): eligible -- ordinal=3 major/critical=29 all=258 hours=22594.1893
- **Cirrascale** (Silver): eligible -- ordinal=3 major/critical=1 all=1 hours=0.0
- **Vultr** (Silver): excluded -- no incident data file found (expected vultr.json)
- **Voltage Park** (Silver): excluded -- no incident data file found (expected voltage-park.json)
- **GCore** (Silver): excluded -- no incident data file found (expected gcore.json)
- **Firmus** (Silver): excluded -- no incident data file found (expected firmus.json)
- **GMO GPU Cloud** (Silver): excluded -- no incident data file found (expected gmo-gpu-cloud.json)
- **TensorWave** (Silver): excluded -- no incident data file found (expected tensorwave.json)
- **Hyperstack** (Bronze): eligible -- ordinal=2 major/critical=6 all=12 hours=394.81
- **Shadeform** (Bronze): excluded -- no incident data file found (expected shadeform.json)
- **Neysa** (Bronze): excluded -- no incident data file found (expected neysa.json)
- **STN** (Bronze): excluded -- no incident data file found (expected stn.json)
- **GMI** (Bronze): excluded -- no incident data file found (expected gmi.json)
- **RunPod** (Bronze): excluded -- no incident data file found (expected runpod.json)
- **Atlas Cloud** (Bronze): excluded -- no incident data file found (expected atlas-cloud.json)
- **Prime Intellect** (Bronze): excluded -- no incident data file found (expected prime-intellect.json)
- **Cudo Compute** (Bronze): excluded -- no incident data file found (expected cudo-compute.json)
- **Qubrid** (Bronze): excluded -- no incident data file found (expected qubrid.json)
- **latitude.sh** (Bronze): eligible -- ordinal=2 major/critical=7 all=17 hours=75.2256
- **Lightning AI** (Bronze): eligible -- ordinal=2 major/critical=0 all=4 hours=4.8823
- **Verda** (Bronze): excluded -- no incident data file found (expected verda.json)
- **DENVR Dataworks** (Bronze): excluded -- no incident data file found (expected denvr-dataworks.json)
- **IBM Cloud** (Bronze): excluded -- no incident data file found (expected ibm-cloud.json)
- **DigitalOcean** (Bronze): eligible -- ordinal=2 major/critical=3 all=56 hours=175.9123
- **Hot Aisle** (Bronze): excluded -- no incident data file found (expected hot-aisle.json)
- **Buzz HPC** (Bronze): excluded -- no incident data file found (expected buzz-hpc.json)
- **Vast.ai** (Bronze): excluded -- no incident data file found (expected vast-ai.json)
- **Sharon AI** (Underperforming): eligible -- ordinal=1 major/critical=0 all=0 hours=0.0
- **IREN** (Underperforming): excluded -- no incident data file found (expected iren.json)
- **Hydra** (Underperforming): excluded -- no incident data file found (expected hydra.json)
- **FarmGPU** (Underperforming): excluded -- no incident data file found (expected farmgpu.json)
- **Whitefiber** (Underperforming): excluded -- no incident data file found (expected whitefiber.json)
- **deepinfra** (Underperforming): excluded -- no incident data file found (expected deepinfra.json)
- **dstack** (Underperforming): excluded -- no incident data file found (expected dstack.json)
- **PaleBlueDot.AI** (Underperforming): excluded -- no incident data file found (expected palebluedot-ai.json)
- **Hyperbolic** (Underperforming): excluded -- no incident data file found (expected hyperbolic.json)
- **GPU.NET** (Underperforming): excluded -- no incident data file found (expected gpu-net.json)
- **Akamai** (Underperforming): eligible -- ordinal=1 major/critical=1 all=52 hours=2840.7336
- **Hetzner** (Underperforming): excluded -- no incident data file found (expected hetzner.json)
- **Clore.ai** (Underperforming): excluded -- no incident data file found (expected clore-ai.json)
- **Massed Compute** (Underperforming): excluded -- no incident data file found (expected massed-compute.json)
- **Exabits** (Underperforming): excluded -- no incident data file found (expected exabits.json)
- **Sesterce** (Underperforming): excluded -- no incident data file found (expected sesterce.json)
- **E2E Cloud** (Underperforming): excluded -- no incident data file found (expected e2e-cloud.json)
- **OVHcloud** (Underperforming): excluded -- no incident data file found (expected ovhcloud.json)
- **Aethir** (Underperforming): excluded -- no incident data file found (expected aethir.json)
- **Akash** (Underperforming): excluded -- no incident data file found (expected akash.json)
- **Salad** (Underperforming): excluded -- no incident data file found (expected salad.json)
- **Mithril** (Underperforming): excluded -- no incident data file found (expected mithril.json)
- **Nscale** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Core42** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Humain** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Corvex** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Highrise** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **BluSky AI** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Arc Compute** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Telus** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Telenor** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Mistral AI** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Firebird** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Alibaba Cloud** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **MegaSpeed International** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **BitDeer** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **RunSun Cloud** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **FPT Cloud** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **backend AI** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **NAVER** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Indosat Ooredoo Hutchison** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Sakura** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **Yotta** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **neevcloud** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **evroc** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release
- **greenai.cloud** (Unavailable): excluded -- unrated/unavailable tier 'Unavailable' in this release

## Secondary release: 1.0
Published 2025-03-26. Window: [2025-03-26, 2025-09-22) (180 days).
Included in correlation: 2 (minimum required: 8).
**Reading: insufficient**

### Providers
- **CoreWeave** (Platinum): excluded -- no incident data file found (expected coreweave.json)
- **Crusoe** (Gold): excluded -- no incident data file found (expected crusoe.json)
- **Together.ai** (Gold): excluded -- no incident data file found (expected together-ai.json)
- **Nebius** (Gold): eligible -- ordinal=4 major/critical=22 all=35 hours=47.9196
- **Lepton AI** (Gold): excluded -- no incident data file found (expected lepton-ai.json)
- **Oracle** (Gold): excluded -- no incident data file found (expected oracle.json)
- **Azure** (Gold): excluded -- no incident data file found (expected azure.json)
- **AWS** (Silver): excluded -- no incident data file found (expected aws.json)
- **Lambda** (Silver): excluded -- coverage_start/coverage_end not recorded; manual verification pending
- **Scaleway** (Silver): eligible -- ordinal=3 major/critical=28 all=225 hours=24410.0461
- **SMC** (Silver): excluded -- no incident data file found (expected smc.json)
- **Google Cloud** (Bronze): excluded -- no incident data file found (expected google-cloud.json)
- **TensorWave** (Bronze): excluded -- no incident data file found (expected tensorwave.json)
- **DataCrunch** (Bronze): excluded -- no incident data file found (expected verda.json)
- **RunPod** (Bronze): excluded -- no incident data file found (expected runpod.json)
- **DENVR Dataworks** (Bronze): excluded -- no incident data file found (expected denvr-dataworks.json)
- **Hot Aisle** (Underperforming): excluded -- no incident data file found (expected hot-aisle.json)
- **Shadeform** (Underperforming): excluded -- no incident data file found (expected shadeform.json)
- **Vast.ai** (Underperforming): excluded -- no incident data file found (expected vast-ai.json)
- **Massed Compute** (Underperforming): excluded -- no incident data file found (expected massed-compute.json)
- **Prime Intellect** (Underperforming): excluded -- no incident data file found (expected prime-intellect.json)
- **Iris Energy** (Underperforming): excluded -- no incident data file found (expected iren.json)
- **GMI Cloud** (Underperforming): excluded -- no incident data file found (expected gmi.json)
- **Salad** (Underperforming): excluded -- no incident data file found (expected salad.json)
- **Akash** (Underperforming): excluded -- no incident data file found (expected akash.json)
- **GPU.NET** (Underperforming): excluded -- no incident data file found (expected gpu-net.json)

## Known limits (from PLAN.md)

Status pages are self-reported; this is retrospective and observational; reliability is one of ten ClusterMAX criteria. See `retrospective/PLAN.md` in full for all stated limits.
