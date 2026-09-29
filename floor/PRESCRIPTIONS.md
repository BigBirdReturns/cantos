# Prescriptions: what recurs in the review sentences, what it costs, and how to fix and verify it

Built 2026-09-29 from `floor/floor.json` and the 1,273 ClusterMAX review sentences. Local draft; not committed. Machine form: `prescriptions.json`. Paths are relative to `D:/Projects/Organs/AXM/axm-tools/` unless they start with `floor/`.

## How the rows were made

- Corpus: `sessions/clustermax-cloudreview-20260929/claims.all.jsonl` (sha256 `2c61f975a28dd779...`), 1273 verbatim sentences from 85 provider review pages. 483 carry stance -1; 72 pages have at least one.
- I read all 483 negative sentences and the access, pricing and disclosure sentences of every stance, and assigned sentences to shortfalls by hand. 292 negative sentences and 5 non-negative ones are assigned; the rest are business context, predictions, financing or one-off remarks (single-provider shortfalls such as Akamai or Hetzner product strategy are not rows).
- "Providers affected" counts distinct review pages, not customers. A provider missing from a row was not reported for it; that is not evidence it complies. Sentences are ClusterMAX 2.0 text (Nov 2025) plus 28 rows from 2.1 updates (Apr 2026); providers may have changed since (cmcr-tensorwave-08 and -10 state their items are already fixed; cmcr-hotaisle-10 does not reproduce against the live Hot Aisle site).
- Cost columns quote our own measurements where a shortfall has one and say UNKNOWN where the estate has none. Our measurements are single-GPU, one-hour, one-run-per-arm (Run 3); they do not price multi-node effects.
- Effort class: config (settings or image content), software (something must be built or deployed), process (policy or human workflow), capital (hardware or inventory).

## Ranking (by providers affected, ties by sentence count)

| # | shortfall | providers | sentences | effort | floor items |
|---|---|---:|---:|---|---|
| 1 | No active or passive GPU health checks, or checks not wired into the scheduler | 25 | 31 | software | O-01, O-02, O-03 |
| 2 | No monitoring dashboard, or a dashboard that is broken or missing GPU/job metrics | 23 | 30 | software | O-05 |
| 3 | Slurm or Kubernetes delivered but broken, misconfigured, or stuck at first use | 16 | 28 | process | O-08, A-02 |
| 4 | No usable shared filesystem at delivery (no shared home, RWX class missing, mounts flake, volume not mounted) | 13 | 16 | config | O-06 |
| 5 | Access blocked or delayed by KYC, account deactivation, invitation-only beta, or waits of weeks to months | 12 | 15 | process | A-03, A-04 |
| 6 | Capacity shown sold out, unavailable, or no bids when the reviewers tried to rent | 12 | 15 | capital | A-05 |
| 7 | Slurm and/or Kubernetes not offered, not available to test, or advertised but not set up | 12 | 13 | software | O-08 |
| 8 | Instability, outages or unexplained failures seen in testing or reported by users | 11 | 18 | process | R-01, R-02, R-04, R-07 |
| 9 | No RBAC, SSO or user management; shared root login only | 10 | 12 | software | O-15 |
| 10 | No third-party security attestation (SOC 2 or ISO 27001) in place | 10 | 10 | process | O-16 |
| 11 | Underlying provider undisclosed, or hardware quality a roll of the dice (aggregators) | 9 | 21 | process | O-22 |
| 12 | Base image not AI-ready: no GPU driver, Docker or container toolkit, or outdated PyTorch/CUDA | 9 | 13 | config | O-13, P-11 |
| 13 | Failed nodes are not drained or replaced automatically; repair is manual or customer-detected | 9 | 12 | software | O-03, R-07 |
| 14 | Provisioning stuck, repeatedly failed, or very slow | 7 | 11 | software | A-02 |
| 15 | Shared storage or network slower than expected (slow filesystem, laggy SSH, traffic shaping, collectives below reference) | 7 | 10 | config | O-06, O-12 |
| 16 | HPC software missing on Slurm nodes: no HPC-X, MPI, NCCL, nvcc or lmod modules | 7 | 8 | config | O-11 |
| 17 | Current-generation datacenter GPUs not offered | 6 | 6 | capital | O-26 |
| 18 | Slurm topology.conf / topology-aware scheduling not configured | 6 | 6 | config | O-09 |
| 19 | Vulnerable or outdated security stack on delivery (container toolkit / operators with critical CVEs), no proactive patch process | 5 | 10 | process | O-14a, O-14b, O-18 |
| 20 | Documented setup path does not produce a working result | 5 | 7 | process | A-02 |
| 21 | Login/head node lacks basic tools or sudo (git, vim, nano, python, sudo, helm); login pods stateless | 5 | 7 | config | O-13 |
| 22 | Not self-serve: purchase form, phone call, approval queue, quota request, or an engineer must set up the cluster | 5 | 7 | process | A-01, A-03 |
| 23 | No Pyxis/Enroot container support for Slurm | 5 | 6 | config | O-10 |
| 24 | No true on-demand: prepay, minimum commitment, or whole-cluster contract required | 5 | 5 | process | A-06 |
| 25 | No 24x7 or proactive support; premium support gated by contract size | 5 | 5 | process | O-23 |
| 26 | Billed while the instance is not usable (stuck creating, down, or halted but reserved) | 4 | 9 | software | R-05, A-06 |
| 27 | GPUDirect RDMA off or ACS not disabled; NCCL bandwidth far below reference | 4 | 9 | config | O-12 |
| 28 | Kubernetes GPU Operator or Network Operator missing or outdated at delivery | 4 | 4 | config | O-08 |
| 29 | SLA absent, unclear, or not honored | 4 | 4 | process | R-05, R-06 |
| 30 | Restrictive defaults block standard tooling (profiling, systemd, sinfo/scontrol, VPN-only access) | 3 | 8 | config | O-19, A-08 |
| 31 | Health-check prolog so heavy that a job takes over a minute to start (or checks take 60-120 minutes) | 3 | 5 | config | O-04 |
| 32 | No downloadable kubeconfig; cluster reached only by SSH into a jump host | 3 | 4 | config | O-08 |
| 33 | Passwordless SSH between nodes or SSH keys not provisioned on the cluster | 3 | 3 | config | O-15 |
| 34 | InfiniBand tenant isolation misconfigured (PKey/SAKey): tenant could see every other endpoint | 2 | 2 | config | O-17 |
| 35 | NVML driver/library mismatch or driver provisioning failure on a delivered instance | 2 | 2 | software | O-13 |

Ties: ranks 5-7 (12 providers each), 9-10 (10), 11-13 (9) are ordered by sentence count, so the order inside a tie is not a finding.

## Detail by row

### 1. No active or passive GPU health checks, or checks not wired into the scheduler

- Id: `S-HEALTH`. Providers affected: **25**, 31 sentences. Effort: **software**.
- Providers: Atlas Cloud (Bronze on the 2.0 page; 3.0: Unavailable), Azure (Gold on the 2.0 page; 3.0: Silver), BuzzHPC (Bronze on the 2.0 page; 3.0: Participation Ribbon), CUDO Compute (Bronze on the 2.0 page; 3.0: Unavailable), Digital Ocean (Bronze on the 2.0 page; 3.0: Bronze), Fluidstack (Gold on the 2.0 page; 3.0: Unavailable), GCORE (Silver on the 2.0 page; 3.0: Bronze), GMI (Bronze on the 2.0 page; 3.0: Silver), GMO Cloud (Silver on the 2.0 page; 3.0: Bronze), Google Cloud (GCP) (Silver on the 2.0 page; 3.0: Gold), Hot Aisle (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Latitude.sh (Bronze on the 2.0 page; 3.0: Participation Ribbon), Neysa (Bronze on the 2.0 page; 3.0: Participation Ribbon), Oracle (Gold on the 2.0 page; 3.0: Gold), Prime Intellect (Bronze on the 2.0 page; 3.0: Bronze), Radiant/Ori (Unavailable on the 2.0 page; 3.0: Participation Ribbon), Runpod (Bronze on the 2.0 page; 3.0: Participation Ribbon), Sesterce (Underperforming on the 2.0 page; 3.0: Unavailable), Shadeform (Bronze on the 2.0 page; 3.0: Participation Ribbon), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon), Tensorwave (Silver on the 2.0 page; 3.0: Silver), Together (Silver on the 2.0 page; 3.0: Bronze), Vast.ai (Bronze on the 2.0 page; 3.0: Participation Ribbon), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon), Whitefiber (Underperforming on the 2.0 page; 3.0: Underperforming).
- Claim ids: `cmcr-azure-09`, `cmcr-azure-10`, `cmcr-buzzhpc-11`, `cmcr-buzzhpc-12`, `cmcr-cudocompute-16`, `cmcr-digitalocean-06`, `cmcr-fluidstack-22`, `cmcr-gcore-18`, `cmcr-gmi-12`, `cmcr-gmocloud-23`, `cmcr-googlecloud-33`, `cmcr-googlecloud-34`, `cmcr-googlecloud-36`, `cmcr-hotaisle-09`, `cmcr-latitudesh-11`, `cmcr-neysa-12`, `cmcr-oracle-26`, `cmcr-primeintellect-10`, `cmcr-radiantori-06`, `cmcr-runpod-04`, `cmcr-sesterce-12`, `cmcr-shadeform-11`, `cmcr-stn-12`, `cmcr-tensorwave-13`, `cmcr-together-41`, `cmcr-together-54`, `cmcr-vastai-14`, `cmcr-vultr-13`, `cmcr-vultr-21`, `cmcr-whitefiber-14`, `cmcr-atlascloud-10`.
- Example sentence (`cmcr-azure-09`): "In stark contrast, CycleCloud relies on the traditional HPC model via slurm’s HealthCheckProgram. However, CycleCloud does not provide a good default, like LBNL’s Node Health Check ..."
- What the customer observes: Nodes with failing GPUs stay in the scheduler; the customer discovers a bad node by losing a job. Some shops have DCGM installed but not plugged into the scheduler.
- What it costs them: Lost job time on the failed node plus restart from checkpoint. SemiAnalysis's TCO model puts goodput loss at 0.02% (gold, inference H200) to 4.98% (silver, pretrain GB300) of GPU spend, an assumption not a measurement.
- Tie to our measurements: Our three 1-hour Run 3 arms saw 0, 7 and 0 failed of 8,622 requests, so single-seat health-check value is not visible in our data. Multi-node loss: UNKNOWN (no estate measurement).
- Likely fix: Enable DCGM background health checks (dcgmi health -c), run them as Slurm HealthCheckProgram or NHC, add Node Problem Detector/GPUd with automated cordon and drain (Draino, NVSentinel or equivalent), and run weekly active checks (dcgmi diag -r 3, nvbandwidth, nccl-tests) on idle nodes.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Monitoring and Health Checks; sessions/clustermax-cloudreview-20260929/raw/expectations_health-checks.html :: Passive, Active, Automation (links: DCGM diagnostics docs.nvidia.com/datacenter/dcgm/latest/user-guide/dcgm-diagnostics.html; Node Problem Detector github.com/kubernetes/node-problem-detector; GPUd github.com/leptonai/gpud; Draino github.com/planetlabs/draino; NVSentinel github.com/NVIDIA/NVSentinel); sessions/clustermax-cloudreview-20260929/raw/criteria_monitoring.html :: Automated Active and Passive Health Checks
- How the kit verifies it: audit checks `healthChecks.dcgmInstalled`, `healthChecks.dcgmSlurm`, `healthChecks.nhcInstalled`. Kit steps: probe/fingerprint.sh (rubric HW-01, HW-03); MANUAL section 5 recovery drill. Manual checks: `scontrol show config | grep HealthCheckProgram`; `dcgmi health -c -j`.

### 2. No monitoring dashboard, or a dashboard that is broken or missing GPU/job metrics

- Id: `S-MONITOR`. Providers affected: **23**, 30 sentences. Effort: **software**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), Atlas Cloud (Bronze on the 2.0 page; 3.0: Unavailable), Azure (Gold on the 2.0 page; 3.0: Silver), BuzzHPC (Bronze on the 2.0 page; 3.0: Participation Ribbon), CUDO Compute (Bronze on the 2.0 page; 3.0: Unavailable), Digital Ocean (Bronze on the 2.0 page; 3.0: Bronze), Fluidstack (Gold on the 2.0 page; 3.0: Unavailable), GCORE (Silver on the 2.0 page; 3.0: Bronze), GMI (Bronze on the 2.0 page; 3.0: Silver), GMO Cloud (Silver on the 2.0 page; 3.0: Bronze), Hot Aisle (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Lambda (Silver on the 2.0 page; 3.0: Silver), Latitude.sh (Bronze on the 2.0 page; 3.0: Participation Ribbon), Neysa (Bronze on the 2.0 page; 3.0: Participation Ribbon), Prime Intellect (Bronze on the 2.0 page; 3.0: Bronze), Sesterce (Underperforming on the 2.0 page; 3.0: Unavailable), Shadeform (Bronze on the 2.0 page; 3.0: Participation Ribbon), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon), Tensorwave (Silver on the 2.0 page; 3.0: Silver), Together (Silver on the 2.0 page; 3.0: Bronze), Vast.ai (Bronze on the 2.0 page; 3.0: Participation Ribbon), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon), Whitefiber (Underperforming on the 2.0 page; 3.0: Underperforming).
- Claim ids: `cmcr-amazonwebservices-26`, `cmcr-azure-11`, `cmcr-buzzhpc-13`, `cmcr-cudocompute-16`, `cmcr-digitalocean-06`, `cmcr-gcore-17`, `cmcr-gcore-18`, `cmcr-gmi-05`, `cmcr-gmi-12`, `cmcr-gmocloud-21`, `cmcr-gmocloud-22`, `cmcr-hotaisle-09`, `cmcr-lambda-19`, `cmcr-lambda-20`, `cmcr-latitudesh-11`, `cmcr-neysa-12`, `cmcr-neysa-13`, `cmcr-primeintellect-10`, `cmcr-sesterce-12`, `cmcr-shadeform-11`, `cmcr-stn-17`, `cmcr-vultr-13`, `cmcr-vultr-21`, `cmcr-whitefiber-13`, `cmcr-whitefiber-15`, `cmcr-fluidstack-16`, `cmcr-together-43`, `cmcr-tensorwave-13`, `cmcr-vastai-14`, `cmcr-atlascloud-10`.
- Example sentence (`cmcr-amazonwebservices-26`): "Unfortunately, monitoring dashboards for slurm or Kubernetes cluster health, performance, and job stats are basically non-existent beyond standard, manual, open source tooling."
- What the customer observes: No dashboard, or a Grafana that is non-functional, missing NVLink/tensor-core/job metrics, or showing wrong numbers (for example InfiniBand at 1.14 Tbit/s).
- What it costs them: Customer builds its own DCGM/Grafana or runs blind; link flaps and throttling go unnoticed (cmcr-vultr-13: flaps with no proactive notification).
- Tie to our measurements: Run 3 used no shop dashboard; the kit captured GPU state itself via the fingerprint probe. Cost of building monitoring: UNKNOWN (no estate measurement).
- Likely fix: Deploy kube-prometheus-stack plus dcgm-exporter (at or above 4.8.2 per the audit table), Promtail for dmesg, alert routing, and Slurm sacct-based job views.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_monitoring.html :: Monitoring Stack, Hardware Monitoring (dcgm-exporter github.com/NVIDIA/dcgm-exporter; kube-prometheus-stack github.com/prometheus-community/helm-charts); sessions/clustermax-cloudreview-20260929/raw/criteria_monitoring.html; sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json :: dcgmExporter minimum 4.8.2
- How the kit verifies it: audit checks `healthChecks.monitoringStack.dcgmExporter`, `securityVersions.dcgmExporter.status`. Kit steps: counter step 9 (support path). Manual checks: `kubectl get pods -n monitoring`; `dcgmi discovery -l`.

### 3. Slurm or Kubernetes delivered but broken, misconfigured, or stuck at first use

- Id: `S-ORCH-BROKEN`. Providers affected: **16**, 28 sentences. Effort: **process**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), Azure (Gold on the 2.0 page; 3.0: Silver), BuzzHPC (Bronze on the 2.0 page; 3.0: Participation Ribbon), Crusoe (Gold on the 2.0 page; 3.0: Bronze), E2E Networks (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), GCORE (Silver on the 2.0 page; 3.0: Bronze), GMI (Bronze on the 2.0 page; 3.0: Silver), GMO Cloud (Silver on the 2.0 page; 3.0: Bronze), Hyperstack/NexGen (Bronze on the 2.0 page; 3.0: Bronze), Lambda (Silver on the 2.0 page; 3.0: Silver), Neysa (Bronze on the 2.0 page; 3.0: Participation Ribbon), Prime Intellect (Bronze on the 2.0 page; 3.0: Bronze), Tensorwave (Silver on the 2.0 page; 3.0: Silver), Voltage Park (Silver on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon), Whitefiber (Underperforming on the 2.0 page; 3.0: Underperforming).
- Claim ids: `cmcr-amazonwebservices-05`, `cmcr-amazonwebservices-06`, `cmcr-amazonwebservices-07`, `cmcr-amazonwebservices-11`, `cmcr-amazonwebservices-12`, `cmcr-buzzhpc-04`, `cmcr-crusoe-19`, `cmcr-gcore-12`, `cmcr-gcore-15`, `cmcr-gmi-04`, `cmcr-hyperstacknexgen-05`, `cmcr-hyperstacknexgen-06`, `cmcr-hyperstacknexgen-10`, `cmcr-lambda-21`, `cmcr-neysa-08`, `cmcr-neysa-09`, `cmcr-primeintellect-09`, `cmcr-tensorwave-05`, `cmcr-voltagepark-09`, `cmcr-voltagepark-10`, `cmcr-vultr-05`, `cmcr-whitefiber-09`, `cmcr-whitefiber-10`, `cmcr-whitefiber-11`, `cmcr-e2enetworks-07`, `cmcr-azure-04`, `cmcr-gmocloud-05`, `cmcr-gmocloud-06`.
- Example sentence (`cmcr-amazonwebservices-05`): "Our initial setup process following the primary documentation path for creating a slurm cluster through the SageMaker console. This path proved to be a dead end."
- What the customer observes: Slurm or Kubernetes exists but fails first use: clusters stuck provisioning, rollbacks, sinfo/scontrol disabled, no shared home, slurm-bridge unconfigured, engineers on calls to make it work.
- What it costs them: Engineer days before the first job. SemiAnalysis logged 14 straight hours and five AWS engineers for one HyperPod cluster (cmcr-amazonwebservices-14), and 2 hours to a failed K8s cluster at Gcore (cmcr-gcore-12).
- Tie to our measurements: Our Run 3 kit went from SSH to workload-ready in 144 s on Hot Aisle and 349 s on DigitalOcean with a working Docker image (ledger-times.json); orchestration handover cost: UNKNOWN (no estate measurement).
- Likely fix: Add an automated handover acceptance test that runs the expectations-page commands (sinfo, srun -N4 hostname, findmnt -T $HOME, kubectl get storageclass, a two-node nccl-test) before delivery, and fix defaults found (shared home, passwordless SSH, Pyxis/Enroot, topology).
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Access, Configuration, Containers; sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html :: Access, Configuration; sessions/clustermax-cloudreview-20260929/raw/criteria_orchestration.html
- How the kit verifies it: audit checks `access.slurmCommandsOk`, `access.sshToComputeNodes`, `containers.pyxisRuntimeWorks`, `networking.topologyConfigured`, `storage.rwxStatus`. Kit steps: counter step 3 (time to SSH) only covers the VM; cluster handover has no kit step yet. Manual checks: `srun -N4 hostname`; `sbatch --wrap hostname`; `kubectl get storageclass -o wide`.

### 4. No usable shared filesystem at delivery (no shared home, RWX class missing, mounts flake, volume not mounted)

- Id: `S-STORAGE`. Providers affected: **13**, 16 sentences. Effort: **config**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), BuzzHPC (Bronze on the 2.0 page; 3.0: Participation Ribbon), Crusoe (Gold on the 2.0 page; 3.0: Bronze), CUDO Compute (Bronze on the 2.0 page; 3.0: Unavailable), Digital Ocean (Bronze on the 2.0 page; 3.0: Bronze), E2E Networks (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), GMI (Bronze on the 2.0 page; 3.0: Silver), Hot Aisle (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Lambda (Silver on the 2.0 page; 3.0: Silver), Latitude.sh (Bronze on the 2.0 page; 3.0: Participation Ribbon), Prime Intellect (Bronze on the 2.0 page; 3.0: Bronze), Runpod (Bronze on the 2.0 page; 3.0: Participation Ribbon), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-buzzhpc-06`, `cmcr-cudocompute-10`, `cmcr-cudocompute-16`, `cmcr-crusoe-24`, `cmcr-crusoe-30`, `cmcr-digitalocean-06`, `cmcr-e2enetworks-10`, `cmcr-gmi-07`, `cmcr-hotaisle-09`, `cmcr-lambda-22`, `cmcr-latitudesh-11`, `cmcr-primeintellect-08`, `cmcr-runpod-10`, `cmcr-vultr-07`, `cmcr-amazonwebservices-11`, `cmcr-amazonwebservices-15`.
- Example sentence (`cmcr-buzzhpc-06`): "initially, no NFS mount, and then user’s default workdir was not on the shared filesystem"
- What the customer observes: Home directory is node-local, so data must be copied by hand; RWX StorageClass missing so PVCs cannot deploy; filesystems randomly unmount; a 200 GB disk attached but not mounted.
- What it costs them: Multi-node jobs cannot start or lose data on unmounts; hours of manual setup per user.
- Tie to our measurements: The Hot Aisle Run 3 arm used a local HF cache (/home/hotaisle/hf-cache, invocation.json); neither Run 3 arm exercised shared storage. Cost: UNKNOWN (no estate measurement).
- Likely fix: Provision a parallel or NFS shared filesystem mounted at the default home with a stated quota, a default RWX StorageClass, and keep it mounted (health-check mounts).
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Access, shared filesystem (findmnt -T $HOME; quota -s || lfs quota -h -u $USER $HOME; srun -N4 df -h $HOME); sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html :: Configuration, CSI provider with ReadWriteMany (K8s PV access modes kubernetes.io/docs/concepts/storage/persistent-volumes/#access-modes); sessions/clustermax-cloudreview-20260929/raw/criteria_storage.html
- How the kit verifies it: audit checks `storage.rwxStatus`. Kit steps: fio per expectations page (not yet a kit step). Manual checks: `findmnt -T $HOME`; `kubectl get storageclass`; `fio --name=seqread --rw=read --bs=1M --size=1G --numjobs=4 --direct=1`.

### 5. Access blocked or delayed by KYC, account deactivation, invitation-only beta, or waits of weeks to months

- Id: `S-ACCESS-BLOCK`. Providers affected: **12**, 15 sentences. Effort: **process**.
- Providers: ARC Compute (Unavailable on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Backend (Unavailable on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Bitdeer (Unavailable on the 2.0 page; 3.0: Participation Ribbon), Clore (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Denvr Dataworks (Bronze on the 2.0 page; 3.0: Unavailable), E2E Networks (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), GMI (Bronze on the 2.0 page; 3.0: Silver), IBM Cloud (Bronze on the 2.0 page; 3.0: Participation Ribbon), MegaSpeed (Unavailable on the 2.0 page; 3.0: Unavailable), Mithril/ML Foundry (Underperforming on the 2.0 page; 3.0: Underperforming), Neev Cloud (Unavailable on the 2.0 page; 3.0: NOT IN 3.0 TABLE), NScale (Unavailable on the 2.0 page; 3.0: Unavailable).
- Claim ids: `cmcr-ibmcloud-07`, `cmcr-ibmcloud-08`, `cmcr-ibmcloud-09`, `cmcr-ibmcloud-13`, `cmcr-bitdeer-06`, `cmcr-e2enetworks-06`, `cmcr-gmi-05`, `cmcr-mithrilmlfoundry-12`, `cmcr-clore-05`, `cmcr-arccompute-05`, `cmcr-megaspeed-04`, `cmcr-nscale-05`, `cmcr-denvrdataworks-06`, `cmcr-neevcloud-02`, `cmcr-backend-04`.
- Example sentence (`cmcr-ibmcloud-07`): "Unfortunately, when we tried to line up testing with IBM, they went so far as to deactivate our account and block us from making new sign-ups"
- What the customer observes: KYC blocks a first test, accounts are deactivated mid-test, verification calls demand use-case explanations, invitation-only betas, or waits of weeks to months.
- What it costs them: Weeks of calendar time before any GPU-hour; for IBM the account was shut down twice during a simple docker download test (cmcr-ibmcloud-13).
- Tie to our measurements: Our reference seats took 122 s (Hot Aisle) and 83 s (DigitalOcean) from create to SSH once an account existed; DigitalOcean's zero GPU limit took a support ticket ('under a day', untimed). Signup-to-first-create time: UNKNOWN (both records 'unobserved').
- Likely fix: Publish KYC requirements up front, verify at signup rather than mid-use, set a service-level target for review (hours), and provide a small pre-approved self-serve tier.
- Fix sources: main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md :: step 1; sessions/clustermax-cloudreview-20260929/claims.all.jsonl :: cmcr-ibmcloud-07..13, cmcr-gmi-05, cmcr-mithrilmlfoundry-12; sessions/clustermax-cloudreview-20260929/raw/criteria_lifecycle.html :: Easy onboarding, Transparent onboarding costs and delivery timelines that are met
- How the kit verifies it: No graded audit check exists for this. Kit steps: counter step 1 (kyc_required, card_required, quota_gate, signup_to_active_account_s). Manual checks: `stopwatch from first sign-up screen to first create attempt`.

### 6. Capacity shown sold out, unavailable, or no bids when the reviewers tried to rent

- Id: `S-CAPACITY`. Providers affected: **12**, 15 sentences. Effort: **capital**.
- Providers: Akash Network (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Azure (Gold on the 2.0 page; 3.0: Silver), Corvex (Unavailable on the 2.0 page; 3.0: Unavailable), DeepInfra (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), E2E Networks (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Exabits (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), GPU.net (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Hot Aisle (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Hydra Host (Underperforming on the 2.0 page; 3.0: Underperforming), IREN/Iris Energy (Underperforming on the 2.0 page; 3.0: Underperforming), Lambda (Silver on the 2.0 page; 3.0: Silver), Lightning.ai (Bronze on the 2.0 page; 3.0: Unavailable).
- Claim ids: `cmcr-akashnetwork-05`, `cmcr-akashnetwork-07`, `cmcr-deepinfra-05`, `cmcr-e2enetworks-09`, `cmcr-exabits-05`, `cmcr-gpunet-05`, `cmcr-hydrahost-04`, `cmcr-hydrahost-05`, `cmcr-hotaisle-11`, `cmcr-hotaisle-12`, `cmcr-irenirisenergy-09`, `cmcr-lambda-11`, `cmcr-lightningai-18`, `cmcr-corvex-03`, `cmcr-azure-04`.
- Example sentence (`cmcr-akashnetwork-05`): "Unfortunately, we weren’t able to access any H100 or H200 on the platform."
- What the customer observes: The console shows sold out, a booking error, or no bids; or a listing that does not provision.
- What it costs them: No seat means no accepted work: cost per accepted is undefined, and the whole evaluation stalls.
- Tie to our measurements: Run 3: DigitalOcean MI300X and H200 listed no capacity in any region all night (arm C did not run); Hot Aisle had one 1x VM (RUN3-RESULTS item 5; availability ledger 2026-09-23 and 2026-09-24). Dollar value of missed work: UNKNOWN (no estate measurement).
- Likely fix: More stock (capital), or an honest capacity signal and waitlist so listed equals deliverable.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/criteria_availability.html; main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md :: PRICE-03; main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md :: step 4
- How the kit verifies it: No graded audit check exists for this. Kit steps: counter step 4 (ledger_attempts); rubric PRICE-03; availability/observations.jsonl. Manual checks: `repeat creates at more than one time of day`.

### 7. Slurm and/or Kubernetes not offered, not available to test, or advertised but not set up

- Id: `S-ORCH-ABSENT`. Providers affected: **12**, 13 sentences. Effort: **software**.
- Providers: Akamai/Linode (Underperforming on the 2.0 page; 3.0: Underperforming), CUDO Compute (Bronze on the 2.0 page; 3.0: Unavailable), Digital Ocean (Bronze on the 2.0 page; 3.0: Bronze), GCORE (Silver on the 2.0 page; 3.0: Bronze), Hot Aisle (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Latitude.sh (Bronze on the 2.0 page; 3.0: Participation Ribbon), Neev Cloud (Unavailable on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Neysa (Bronze on the 2.0 page; 3.0: Participation Ribbon), Runpod (Bronze on the 2.0 page; 3.0: Participation Ribbon), Sesterce (Underperforming on the 2.0 page; 3.0: Unavailable), Shadeform (Bronze on the 2.0 page; 3.0: Participation Ribbon), Vast.ai (Bronze on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-akamailinode-05`, `cmcr-cudocompute-16`, `cmcr-digitalocean-04`, `cmcr-digitalocean-06`, `cmcr-latitudesh-11`, `cmcr-sesterce-12`, `cmcr-shadeform-11`, `cmcr-neevcloud-06`, `cmcr-neysa-15`, `cmcr-vastai-10`, `cmcr-runpod-04`, `cmcr-gcore-07`, `cmcr-hotaisle-10`.
- Example sentence (`cmcr-akamailinode-05`): "Unsurprisingly, the platform has no managed Slurm cluster, and its Kubernetes engine is not optimized for GPU servers."
- What the customer observes: No managed Slurm or Kubernetes, or the website advertises one that was not set up when help was requested.
- What it costs them: Buyer needing a cluster cannot use the shop; single-node buyers are unaffected.
- Tie to our measurements: Not relevant to the 1-GPU Run 3 seat. Hot Aisle is in this row on its own 2.0 review (cmcr-hotaisle-10), not reproducible against today's site (README: no Slurm mention). Cost: UNKNOWN (no estate measurement).
- Likely fix: Offer an automated Slurm and/or Kubernetes path (self-service), or state plainly that the product is single-node. Advertised features must be deployable.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/criteria_orchestration.html :: Slurm, Kubernetes requirements; sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html; sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html
- How the kit verifies it: audit checks `access.slurmCommandsOk`. Kit steps: desk review of docs (MANUAL public desk review). 

### 8. Instability, outages or unexplained failures seen in testing or reported by users

- Id: `S-RELIAB`. Providers affected: **11**, 18 sentences. Effort: **process**.
- Providers: Crusoe (Gold on the 2.0 page; 3.0: Bronze), GPU.net (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Hyperbolic (Underperforming on the 2.0 page; 3.0: Participation Ribbon), Lambda (Silver on the 2.0 page; 3.0: Silver), Latitude.sh (Bronze on the 2.0 page; 3.0: Participation Ribbon), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon), Tensorwave (Silver on the 2.0 page; 3.0: Silver), Together (Silver on the 2.0 page; 3.0: Bronze), Vast.ai (Bronze on the 2.0 page; 3.0: Participation Ribbon), Verda/DataCrunch (Bronze on the 2.0 page; 3.0: Bronze), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-crusoe-26`, `cmcr-crusoe-30`, `cmcr-crusoe-31`, `cmcr-crusoe-32`, `cmcr-hyperbolic-06`, `cmcr-hyperbolic-07`, `cmcr-latitudesh-07`, `cmcr-latitudesh-08`, `cmcr-lambda-29`, `cmcr-stn-10`, `cmcr-tensorwave-15`, `cmcr-tensorwave-16`, `cmcr-verdadatacrunch-14`, `cmcr-verdadatacrunch-15`, `cmcr-together-05`, `cmcr-vultr-12`, `cmcr-vastai-11`, `cmcr-gpunet-11`.
- Example sentence (`cmcr-crusoe-26`): "During our testing, we also encountered several performance and reliability issues on slurm, kubernetes, and on a standalone machine."
- What the customer observes: Connection drops, instances in 'Unknown status', NVML mismatches, link flaps, multi-hour or multi-day outages, sites going dark with no explanation, and 7 distinct interruptions in two months at one AMD shop.
- What it costs them: Interrupted jobs and lost hours; SemiAnalysis's public TCO presets for GPU MTBF run from 10,000 to 169,800 GPU-hr.
- Tie to our measurements: Our arms: 0 / 7 / 0 failed of 8,622 in 1 hour each; fleet MTBF and outage frequency: UNKNOWN (single seats cannot measure it).
- Likely fix: Reduce root causes (link cleaning and monitoring, driver/image management), add automated remediation and disclose an incident history.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/criteria_reliability.html :: Key Requirements; sessions/clustermax-cloudreview-20260929/raw/expectations_health-checks.html; sessions/clustermax-cloudreview-20260929/tco-model.json :: goodput_presets
- How the kit verifies it: No graded audit check exists for this. Kit steps: MANUAL section 5 recovery drill; R2 status collection. 

### 9. No RBAC, SSO or user management; shared root login only

- Id: `S-RBAC`. Providers affected: **10**, 12 sentences. Effort: **software**.
- Providers: Crusoe (Gold on the 2.0 page; 3.0: Bronze), CUDO Compute (Bronze on the 2.0 page; 3.0: Unavailable), Dstack Sky (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Hot Aisle (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Neysa (Bronze on the 2.0 page; 3.0: Participation Ribbon), Runpod (Bronze on the 2.0 page; 3.0: Participation Ribbon), Sesterce (Underperforming on the 2.0 page; 3.0: Unavailable), Tensorwave (Silver on the 2.0 page; 3.0: Silver), Verda/DataCrunch (Bronze on the 2.0 page; 3.0: Bronze), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-cudocompute-11`, `cmcr-crusoe-23`, `cmcr-dstacksky-14`, `cmcr-hotaisle-09`, `cmcr-neysa-06`, `cmcr-neysa-07`, `cmcr-runpod-09`, `cmcr-sesterce-13`, `cmcr-tensorwave-09`, `cmcr-tensorwave-10`, `cmcr-verdadatacrunch-11`, `cmcr-vultr-06`.
- Example sentence (`cmcr-cudocompute-11`): "We also found it unfortunate that we were logging into the VM as a shared root user, instead of passing RBAC-enforced auth credentials from the console to the underlying VMs."
- What the customer observes: Everyone logs in as root; no way to add teammates; user/group sync fails between jump box and login nodes; no external IdP.
- What it costs them: Team onboarding by shared credentials; audit and offboarding impossible.
- Tie to our measurements: UNKNOWN (no estate measurement). Single-operator runs never needed it.
- Likely fix: Add user and group management by CLI/console, RBAC on cluster and storage, and OIDC/OAuth IdP integration.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Access (Easy to add new users, RBAC, external IDPs); sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html :: Access (K8s RBAC docs kubernetes.io/docs/reference/access-authn-authz/rbac/); sessions/clustermax-cloudreview-20260929/raw/criteria_orchestration.html
- How the kit verifies it: audit checks `access.userManagement`, `access.externalIdp.detected`, `access.sudoAvailable`. 

### 10. No third-party security attestation (SOC 2 or ISO 27001) in place

- Id: `S-ATTEST`. Providers affected: **10**, 10 sentences. Effort: **process**.
- Providers: Aethir (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), DeepInfra (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Dstack Sky (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), FarmGPU (Underperforming on the 2.0 page; 3.0: Underperforming), GPU.net (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Hydra Host (Underperforming on the 2.0 page; 3.0: Underperforming), Hyperbolic (Underperforming on the 2.0 page; 3.0: Participation Ribbon), PaleBlueDot (Underperforming on the 2.0 page; 3.0: Underperforming), Sesterce (Underperforming on the 2.0 page; 3.0: Unavailable), Whitefiber (Underperforming on the 2.0 page; 3.0: Underperforming).
- Claim ids: `cmcr-aethir-07`, `cmcr-deepinfra-05`, `cmcr-farmgpu-06`, `cmcr-gpunet-11`, `cmcr-hydrahost-02`, `cmcr-hyperbolic-08`, `cmcr-palebluedot-02`, `cmcr-sesterce-19`, `cmcr-whitefiber-17`, `cmcr-dstacksky-23`.
- Example sentence (`cmcr-aethir-07`): "Aethir does not have any security compliance attestation in place for users to assess if the company taking payments and managing the GPU access has access controls in place."
- What the customer observes: No SOC 2 or ISO 27001 attestation; marketplaces reported as losing Fortune 500 deals because of it.
- What it costs them: Cannot sell to the primary market; buyers with compliance gates cannot use the shop (cmcr-hydrahost-02).
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Complete SOC 2 Type I then Type II and/or ISO 27001 with an independent auditor; scope to include the fabric.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/criteria_security.html :: Critical Failure; SOC 1 or SOC 2 Type II; SOC 2 and pentesting cover InfiniBand/RoCEv2; sessions/clustermax-cloudreview-20260929/claims.all.jsonl :: cmcr-sesterce-19, cmcr-whitefiber-17
- How the kit verifies it: No graded audit check exists for this. Kit steps: desk review of trust page. 

### 11. Underlying provider undisclosed, or hardware quality a roll of the dice (aggregators)

- Id: `S-PROVIDER`. Providers affected: **9**, 21 sentences. Effort: **process**.
- Providers: Dstack Sky (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Hyperbolic (Underperforming on the 2.0 page; 3.0: Participation Ribbon), Mithril/ML Foundry (Underperforming on the 2.0 page; 3.0: Underperforming), Qubrid (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Runpod (Bronze on the 2.0 page; 3.0: Participation Ribbon), Sesterce (Underperforming on the 2.0 page; 3.0: Unavailable), Shadeform (Bronze on the 2.0 page; 3.0: Participation Ribbon), Together (Silver on the 2.0 page; 3.0: Bronze), Vast.ai (Bronze on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-dstacksky-11`, `cmcr-dstacksky-12`, `cmcr-dstacksky-13`, `cmcr-dstacksky-19`, `cmcr-runpod-15`, `cmcr-runpod-16`, `cmcr-sesterce-07`, `cmcr-sesterce-10`, `cmcr-sesterce-19`, `cmcr-qubrid-08`, `cmcr-qubrid-13`, `cmcr-vastai-04`, `cmcr-vastai-05`, `cmcr-vastai-11`, `cmcr-vastai-12`, `cmcr-vastai-13`, `cmcr-mithrilmlfoundry-09`, `cmcr-mithrilmlfoundry-10`, `cmcr-hyperbolic-09`, `cmcr-together-06`, `cmcr-shadeform-11`.
- Example sentence (`cmcr-dstacksky-11`): "However, the abstraction comes with a significant lack of transparency."
- What the customer observes: Customer lands on hardware from an unnamed datacenter (Sesterce on Verda's Helsinki hardware, Qubrid on AWS Ashburn), sees PCIe vs SXM chosen by chance, and cannot see who patches or secures it.
- What it costs them: Roll-of-the-dice performance and unclear responsibility; users waste time spinning pods up and down to test quality (cmcr-runpod-16).
- Tie to our measurements: Between two disclosed providers running the same freeze, Run 3 p99 TTFT differed 3.9x (571 ms vs 2,254 ms) while accepted counts differed 1.3%; whether an undisclosed mix widens that is a hypothesis, not a measurement.
- Likely fix: Name the underlying operator in the console/docs, expose SXM vs PCIe, and publish region and provider per instance.
- Fix sources: sessions/clustermax-cloudreview-20260929/claims.all.jsonl :: cmcr-sesterce-19, cmcr-qubrid-13, cmcr-dstacksky-12; sessions/clustermax-cloudreview-20260929/raw/criteria_pricing.html
- How the kit verifies it: audit checks `vm_iommu.status`, `pcie-passthrough`. Kit steps: desk review + IP/whois lookup on the delivered seat; probe/fingerprint.sh (gpu model, PCIe link). Manual checks: `whois on the public IP`.

### 12. Base image not AI-ready: no GPU driver, Docker or container toolkit, or outdated PyTorch/CUDA

- Id: `S-IMAGE`. Providers affected: **9**, 13 sentences. Effort: **config**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), BuzzHPC (Bronze on the 2.0 page; 3.0: Participation Ribbon), CUDO Compute (Bronze on the 2.0 page; 3.0: Unavailable), GMI (Bronze on the 2.0 page; 3.0: Silver), GPU.net (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Hyperbolic (Underperforming on the 2.0 page; 3.0: Participation Ribbon), IBM Cloud (Bronze on the 2.0 page; 3.0: Participation Ribbon), Latitude.sh (Bronze on the 2.0 page; 3.0: Participation Ribbon), Qubrid (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE).
- Claim ids: `cmcr-amazonwebservices-17`, `cmcr-amazonwebservices-18`, `cmcr-buzzhpc-08`, `cmcr-cudocompute-12`, `cmcr-cudocompute-13`, `cmcr-gmi-06`, `cmcr-gpunet-07`, `cmcr-gpunet-08`, `cmcr-hyperbolic-05`, `cmcr-ibmcloud-12`, `cmcr-latitudesh-10`, `cmcr-qubrid-09`, `cmcr-qubrid-10`.
- Example sentence (`cmcr-amazonwebservices-17`): "In addition, the standard, documented path for getting started with a single GPU instance does not actually produce a working GPU instance."
- What the customer observes: Default image has no GPU driver or Docker or container toolkit, an 8 GB root volume too small to install drivers, outdated PyTorch, CUDA 12.4 toolkit on Blackwell, or drivers on one machine but Docker on another.
- What it costs them: Setup hours before the first job; insecure or non-working stack.
- Tie to our measurements: On images that already had Docker and GPU runtime our kit reached workload-ready in 144 s (Hot Aisle) and 349 s (DigitalOcean); install time on a bare image: UNKNOWN (no estate measurement).
- Likely fix: Curate one AI-ready image per GPU vendor: driver, Docker with NVIDIA/ROCm runtime, Python with pip/venv, current PyTorch, CUDA at or above the Blackwell minimum.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html :: Configuration (nvidia-smi && nvcc --version; docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi; docker run --device=/dev/kfd --device=/dev/dri rocm/pytorch rocm-smi); sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json :: nvidiaDriver branches, rocm programs
- How the kit verifies it: audit checks `containers.nvidiaContainerToolkit`, `securityVersions.nvidiaDriver.status`, `software.nccl.installed`. Kit steps: probe/fingerprint.sh; evaluate.sh / arm.sh (arm.sh installs docker.io through apt when Docker is absent but installs no GPU driver or NVIDIA container toolkit, so a missing NVIDIA runtime would show up at docker run --gpus all). Manual checks: `nvidia-smi && nvcc --version`; `python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"`.

### 13. Failed nodes are not drained or replaced automatically; repair is manual or customer-detected

- Id: `S-REMEDIATE`. Providers affected: **9**, 12 sentences. Effort: **software**.
- Providers: Fluidstack (Gold on the 2.0 page; 3.0: Unavailable), Google Cloud (GCP) (Silver on the 2.0 page; 3.0: Gold), Oracle (Gold on the 2.0 page; 3.0: Gold), Radiant/Ori (Unavailable on the 2.0 page; 3.0: Participation Ribbon), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon), Tensorwave (Silver on the 2.0 page; 3.0: Silver), Together (Silver on the 2.0 page; 3.0: Bronze), Voltage Park (Silver on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-fluidstack-23`, `cmcr-googlecloud-33`, `cmcr-googlecloud-36`, `cmcr-oracle-32`, `cmcr-radiantori-07`, `cmcr-stn-11`, `cmcr-tensorwave-13`, `cmcr-together-49`, `cmcr-together-50`, `cmcr-together-61`, `cmcr-voltagepark-24`, `cmcr-vultr-13`.
- Example sentence (`cmcr-fluidstack-23`): "By injecting PCIe replay errors (dcgmi test --inject --gpuid 0 -f 202), we confirmed that the node would not automatically drain."
- What the customer observes: An injected PCIe replay error did not drain the node; hardware failure with no alert over 18 hours; a node down two days; customers must notice and report; automated drain 'still on the roadmap'.
- What it costs them: Downtime measured in days; SemiAnalysis credits automated detection-plus-remediation as the differentiator of gold-tier providers.
- Tie to our measurements: UNKNOWN (no estate measurement). No recovery drill has been run on a real shop (MANUAL preamble).
- Likely fix: Wire detection to automatic cordon/drain and replace: DCGM health plus NHC HealthCheckProgram in Slurm, Node Problem Detector plus Draino/NVSentinel in Kubernetes.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_health-checks.html :: Automation; sessions/clustermax-cloudreview-20260929/claims.all.jsonl :: cmcr-fluidstack-24 (recommended thresholds >8 PCIe replays per minute or >100 NVLink CRC errors per second)
- How the kit verifies it: audit checks `healthChecks.dcgmSlurm`. Kit steps: MANUAL section 5 recovery drill (host operator authority required). Manual checks: `dcgmi test --inject --gpuid 0 -f 202 on a disposable node, then observe drain`.

### 14. Provisioning stuck, repeatedly failed, or very slow

- Id: `S-PROVISION`. Providers affected: **7**, 11 sentences. Effort: **software**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), Atlas Cloud (Bronze on the 2.0 page; 3.0: Unavailable), E2E Networks (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), GCORE (Silver on the 2.0 page; 3.0: Bronze), Hyperbolic (Underperforming on the 2.0 page; 3.0: Participation Ribbon), Hyperstack/NexGen (Bronze on the 2.0 page; 3.0: Bronze), Voltage Park (Silver on the 2.0 page; 3.0: NOT IN 3.0 TABLE).
- Claim ids: `cmcr-amazonwebservices-11`, `cmcr-amazonwebservices-12`, `cmcr-amazonwebservices-13`, `cmcr-amazonwebservices-14`, `cmcr-gcore-12`, `cmcr-hyperstacknexgen-06`, `cmcr-hyperstacknexgen-10`, `cmcr-e2enetworks-11`, `cmcr-hyperbolic-07`, `cmcr-atlascloud-07`, `cmcr-voltagepark-09`.
- Example sentence (`cmcr-amazonwebservices-11`): "On our first try, we didn’t define enough controller nodes to handle our 4-node ml.p5en.48xlarge (H200) cluster. On our second try, 1 of the 4 nodes in the cluster didn’t mount the Lustre FSx ..."
- What the customer observes: Clusters stuck 'creating' for hours, vague 'reconcile failed' with no logs, 14 hours across five engineers, or a failed provisioning system.
- What it costs them: Billable seat-hours with no work; the 122 s of Hot Aisle provisioning in Run 3 was 3.1% of the 64.68-minute costed window ($0.10 of $3.22).
- Tie to our measurements: Measured: 122 s and 83 s request-to-SSH. Failure and retry cost: UNKNOWN (no estate measurement).
- Likely fix: Make provisioning idempotent with visible logs and timeouts that fail fast and stop billing; automate the documented workshop path.
- Fix sources: sessions/clustermax-cloudreview-20260929/claims.all.jsonl :: cmcr-amazonwebservices-06 (workshop CloudFormation route worked), cmcr-hyperstacknexgen-07; main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md :: FLEET-01
- How the kit verifies it: No graded audit check exists for this. Kit steps: counter step 3 (three timed creates); rubric FLEET-01. 

### 15. Shared storage or network slower than expected (slow filesystem, laggy SSH, traffic shaping, collectives below reference)

- Id: `S-PERF`. Providers affected: **7**, 10 sentences. Effort: **config**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), Dstack Sky (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), FPT CLOUD (Unavailable on the 2.0 page; 3.0: Participation Ribbon), GMI (Bronze on the 2.0 page; 3.0: Silver), Google Cloud (GCP) (Silver on the 2.0 page; 3.0: Gold), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon), Together (Silver on the 2.0 page; 3.0: Bronze).
- Claim ids: `cmcr-gmi-08`, `cmcr-fptcloud-07`, `cmcr-dstacksky-15`, `cmcr-together-22`, `cmcr-together-23`, `cmcr-stn-15`, `cmcr-googlecloud-17`, `cmcr-googlecloud-18`, `cmcr-amazonwebservices-28`, `cmcr-amazonwebservices-41`.
- Example sentence (`cmcr-gmi-08`): "After negotiating to get a shared fs configured on the cluster, we found that the performance was terrible. Basic file-saving operations and carriage returns in the terminal would take multiple ..."
- What the customer observes: Shared filesystem where file saves take multiple seconds, VS Code remote SSH lag, upload speed tests that look good while downloads are shaped, EFA collectives disliked at scale.
- What it costs them: Slow storage or network throttles multi-node jobs; measured only by the reviewers.
- Tie to our measurements: UNKNOWN (no estate measurement). Our runs are single-GPU with local cache.
- Likely fix: Benchmark fio and nccl-tests at handover and publish them; fix the shared-fs tier or WAN shaping.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Performance Testing (fio; nccl-tests github.com/NVIDIA/nccl-tests); sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html :: Performance Testing
- How the kit verifies it: No graded audit check exists for this. Manual checks: `fio`; `nccl-tests`.

### 16. HPC software missing on Slurm nodes: no HPC-X, MPI, NCCL, nvcc or lmod modules

- Id: `S-HPCSW`. Providers affected: **7**, 8 sentences. Effort: **config**.
- Providers: BuzzHPC (Bronze on the 2.0 page; 3.0: Participation Ribbon), Fluidstack (Gold on the 2.0 page; 3.0: Unavailable), GMI (Bronze on the 2.0 page; 3.0: Silver), Prime Intellect (Bronze on the 2.0 page; 3.0: Bronze), Runpod (Bronze on the 2.0 page; 3.0: Participation Ribbon), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-buzzhpc-09`, `cmcr-fluidstack-14`, `cmcr-gmi-06`, `cmcr-primeintellect-08`, `cmcr-runpod-11`, `cmcr-stn-09`, `cmcr-stn-14`, `cmcr-vultr-06`.
- Example sentence (`cmcr-buzzhpc-09`): "modules not installed, also no hpcx, nccl, nvcc"
- What the customer observes: No HPC-X, no MPI, no nvcc, no lmod, NCCL absent from the image.
- What it costs them: Each user reinstalls the toolchain; NCCL medium-message performance suffers without HPC-X.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Preinstall HPC-X (or equivalent MPI), nvcc, NCCL and Lmod in the base image and on compute nodes.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Configuration (NVIDIA HPC-X developer.nvidia.com/networking/hpc-x; Lmod lmod.readthedocs.io)
- How the kit verifies it: audit checks `software.nvhpc.status`, `software.lmod.modulesStatus`, `software.nccl.installed`. Manual checks: `module avail hpcx || ls /opt/hpcx*/`; `nvcc --version`.

### 17. Current-generation datacenter GPUs not offered

- Id: `S-GPUGEN`. Providers affected: **6**, 6 sentences. Effort: **capital**.
- Providers: Akamai/Linode (Underperforming on the 2.0 page; 3.0: Underperforming), Alibaba Cloud (Unavailable on the 2.0 page; 3.0: Unavailable), HETZNER (Underperforming on the 2.0 page; 3.0: Underperforming), Hot Aisle (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), OVHcloud (Underperforming on the 2.0 page; 3.0: Underperforming), Salad Cloud (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE).
- Claim ids: `cmcr-akamailinode-04`, `cmcr-hetzner-03`, `cmcr-saladcloud-03`, `cmcr-ovhcloud-05`, `cmcr-alibabacloud-08`, `cmcr-hotaisle-14`.
- Example sentence (`cmcr-akamailinode-04`): "Akamai has completely ignored all high end GPUs and instead focuses on the RTX 6000 Blackwell."
- What the customer observes: Only RTX-class, PCIe H100 or no current datacenter GPUs; MI355X arrives late.
- What it costs them: Buyers needing current silicon leave.
- Tie to our measurements: Hot Aisle MI300X vs H100 economics in Run 3 are unaffected. Cost: UNKNOWN (no estate measurement).
- Likely fix: Acquire current-generation GPUs (capital).
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/criteria_availability.html :: Critical Failure
- How the kit verifies it: No graded audit check exists for this. Kit steps: desk review. 

### 18. Slurm topology.conf / topology-aware scheduling not configured

- Id: `S-TOPO`. Providers affected: **6**, 6 sentences. Effort: **config**.
- Providers: Firmus / Sustainable Metal Cloud (SMC) (Silver on the 2.0 page; 3.0: Silver), GMO Cloud (Silver on the 2.0 page; 3.0: Bronze), Neysa (Bronze on the 2.0 page; 3.0: Participation Ribbon), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon), Tensorwave (Silver on the 2.0 page; 3.0: Silver), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-firmussustainablemetalcloud-10`, `cmcr-gmocloud-09`, `cmcr-neysa-10`, `cmcr-stn-09`, `cmcr-vultr-06`, `cmcr-tensorwave-13`.
- Example sentence (`cmcr-firmussustainablemetalcloud-10`): "Once connected, our slurm environment also had some configuration issues. The standard topology.conf file was not set for topology-aware scheduling, and a simple “srun -N1 –gpus-per-node=8 –pty bash” ..."
- What the customer observes: No topology.conf; topology-aware scheduling absent or judged redundant by hand allocation.
- What it costs them: Jobs can span leaf switches, hurting collectives.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Configure topology/block or topology/tree in topology.yaml or topology.conf.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Configuration (Slurm topology.yaml slurm.schedmd.com/topology.yaml.html)
- How the kit verifies it: audit checks `networking.topologyConfigured`. Manual checks: `scontrol show topology`.

### 19. Vulnerable or outdated security stack on delivery (container toolkit / operators with critical CVEs), no proactive patch process

- Id: `S-PATCH`. Providers affected: **5**, 10 sentences. Effort: **process**.
- Providers: CUDO Compute (Bronze on the 2.0 page; 3.0: Unavailable), Fluidstack (Gold on the 2.0 page; 3.0: Unavailable), GMO Cloud (Silver on the 2.0 page; 3.0: Bronze), Voltage Park (Silver on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-cudocompute-12`, `cmcr-fluidstack-19`, `cmcr-fluidstack-30`, `cmcr-fluidstack-31`, `cmcr-gmocloud-14`, `cmcr-gmocloud-15`, `cmcr-voltagepark-26`, `cmcr-voltagepark-27`, `cmcr-vultr-10`, `cmcr-vultr-11`.
- Example sentence (`cmcr-cudocompute-12`): "Furthermore, the base Ubuntu image was not AI-ready out of the box. The driver version and nvidia container toolkit version provided were significantly out of date (meaning insecure)."
- What the customer observes: Container toolkit 1.16.2/1.17.4 or operators over a year old on a new cluster, vulnerable to NVIDIAScape (CVE-2025-23266, CVSS 9.0) and CVE-2025-23267 (8.5).
- What it costs them: Tenant escape risk; fix took minutes to under an hour once reported at Fluidstack.
- Tie to our measurements: Host toolkit versions on our Hot Aisle and DigitalOcean seats were not captured in the sources: UNKNOWN. Current minimum is nvidia-container-toolkit 1.19.1.
- Likely fix: Track NVIDIA advisories, join the embargo program, automate container-toolkit and operator rollouts.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/criteria_security.html :: NVIDIA security program; Automated rollout of new NVIDIA Container Toolkit; sessions/public-tail-20260929/lanes/cmax-audit/repo/cmax/scripts/1-audit/minimum-versions.json
- How the kit verifies it: audit checks `securityVersions.nvidiaContainerToolkit.status`, `securityVersions.nvidiaDriver.status`, `securityVersions.runc.status`, `securityVersions.docker.status`. Kit steps: probe/fingerprint.sh (STK-01 same-vendor versions). Manual checks: `nvidia-container-cli --version`.

### 20. Documented setup path does not produce a working result

- Id: `S-DOCS`. Providers affected: **5**, 7 sentences. Effort: **process**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), Azure (Gold on the 2.0 page; 3.0: Silver), GCORE (Silver on the 2.0 page; 3.0: Bronze), Lambda (Silver on the 2.0 page; 3.0: Silver), Runpod (Bronze on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-amazonwebservices-05`, `cmcr-amazonwebservices-06`, `cmcr-amazonwebservices-44`, `cmcr-lambda-16`, `cmcr-azure-12`, `cmcr-gcore-08`, `cmcr-runpod-13`.
- Example sentence (`cmcr-amazonwebservices-05`): "Our initial setup process following the primary documentation path for creating a slurm cluster through the SageMaker console. This path proved to be a dead end."
- What the customer observes: The console guide yields a non-working instance; docs split between old and new; setup buried in an API reference.
- What it costs them: Multi-attempt setup and support tickets.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Make the primary documentation path the tested path.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/criteria_lifecycle.html :: Easy onboarding well-documented
- How the kit verifies it: No graded audit check exists for this. Kit steps: handoff test (MANUAL section 5: second operator reproduces from sanitized procedure). 

### 21. Login/head node lacks basic tools or sudo (git, vim, nano, python, sudo, helm); login pods stateless

- Id: `S-LOGIN`. Providers affected: **5**, 7 sentences. Effort: **config**.
- Providers: Crusoe (Gold on the 2.0 page; 3.0: Bronze), Tensorwave (Silver on the 2.0 page; 3.0: Silver), Together (Silver on the 2.0 page; 3.0: Bronze), Voltage Park (Silver on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Whitefiber (Underperforming on the 2.0 page; 3.0: Underperforming).
- Claim ids: `cmcr-crusoe-22`, `cmcr-tensorwave-11`, `cmcr-voltagepark-10`, `cmcr-voltagepark-11`, `cmcr-voltagepark-14`, `cmcr-whitefiber-12`, `cmcr-together-26`.
- Example sentence (`cmcr-crusoe-22`): "Unfortunately, the login pod was missing vim, nano, git, python, and sudo permissions."
- What the customer observes: Login pod missing vim, nano, git, python or sudo; login pods are stateless so installs vanish on reconnect; Helm missing.
- What it costs them: Every session begins with package setup that resets on reconnect.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Ship a fuller login image, sudo, and persistent home.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Access (essential packages, sudo); sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html :: Access (Helm)
- How the kit verifies it: audit checks `access.sudoAvailable`. Manual checks: `which python3 git curl wget apt vim nano`.

### 22. Not self-serve: purchase form, phone call, approval queue, quota request, or an engineer must set up the cluster

- Id: `S-NOT-SELFSERVE`. Providers affected: **5**, 7 sentences. Effort: **process**.
- Providers: Aethir (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Exabits (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), GCORE (Silver on the 2.0 page; 3.0: Bronze), Lambda (Silver on the 2.0 page; 3.0: Silver), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-aethir-05`, `cmcr-stn-06`, `cmcr-lambda-09`, `cmcr-lambda-14`, `cmcr-gcore-10`, `cmcr-gcore-11`, `cmcr-exabits-06`.
- Example sentence (`cmcr-aethir-05`): "Unfortunately, Aethir is not truly a self service experience, requiring prospective buyers to fill out a form in order to purchase GPU time on their platform."
- What the customer observes: A purchase form, phone calls to review PDFs, approval before a '1-Click' cluster, quota requests taking three attempts over two working days, or an engineer building the cluster.
- What it costs them: Days of delay; not a self-serve product.
- Tie to our measurements: Run 3 seats were self-serve on both shops; DigitalOcean's initial GPU limit of 0 needed a ticket (under a day).
- Likely fix: Make the path API/console driven with automatic default quota.
- Fix sources: main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md :: step 1; main/hot-aisle/campaign/shop-eval/SHORTLIST.md :: rule 1
- How the kit verifies it: No graded audit check exists for this. Kit steps: counter step 1. 

### 23. No Pyxis/Enroot container support for Slurm

- Id: `S-PYXIS`. Providers affected: **5**, 6 sentences. Effort: **config**.
- Providers: BuzzHPC (Bronze on the 2.0 page; 3.0: Participation Ribbon), GMO Cloud (Silver on the 2.0 page; 3.0: Bronze), Prime Intellect (Bronze on the 2.0 page; 3.0: Bronze), Runpod (Bronze on the 2.0 page; 3.0: Participation Ribbon), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-buzzhpc-10`, `cmcr-gmocloud-11`, `cmcr-gmocloud-12`, `cmcr-primeintellect-08`, `cmcr-vultr-06`, `cmcr-runpod-04`.
- Example sentence (`cmcr-buzzhpc-10`): "no pyxis or enroot"
- What the customer observes: Pyxis and Enroot absent, forcing Singularity rewrites of Docker workflows.
- What it costs them: Workflow rebuild per team.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Install Pyxis and Enroot; keep Docker/Apptainer available.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Containers (NVIDIA Pyxis github.com/NVIDIA/pyxis; Enroot github.com/NVIDIA/enroot)
- How the kit verifies it: audit checks `containers.pyxisRuntimeWorks`, `containers.enroot`, `containers.enrootImportWorks`. Manual checks: `srun --help | grep -A4 -- --container-image`; `enroot version`.

### 24. No true on-demand: prepay, minimum commitment, or whole-cluster contract required

- Id: `S-COMMIT`. Providers affected: **5**, 5 sentences. Effort: **process**.
- Providers: CoreWeave (Platinum on the 2.0 page; 3.0: Platinum), Hydra Host (Underperforming on the 2.0 page; 3.0: Underperforming), Lightning.ai (Bronze on the 2.0 page; 3.0: Unavailable), Qubrid (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Scaleway (Silver on the 2.0 page; 3.0: Unavailable).
- Claim ids: `cmcr-hydrahost-07`, `cmcr-qubrid-12`, `cmcr-coreweave-68`, `cmcr-scaleway-16`, `cmcr-lightningai-12`.
- Example sentence (`cmcr-hydrahost-07`): "Unfortunately, in order to actually get access to one of these servers, Hydra forces users to pre-pay for a weekly bill, and promises to “refund for the unused portion” rather than running a truly ..."
- What the customer observes: Weekly prepay with later refund, 1-week/1-month/3-month minimums, whole-cluster contract for large jobs, multi-GPU studios behind paid tiers.
- What it costs them: Cash locked up; not on-demand.
- Tie to our measurements: Hot Aisle 1x VM: 1-minute minimum; 2x VM: 1-hour minimum observed; 8x bare metal: 1-month minimum. Run 3 overhead of shared seat raised cost/1k from $0.74 to $0.90.
- Likely fix: Offer true on-demand at minute granularity.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html :: Hardware Support (flexible billing granularity); sessions/clustermax-cloudreview-20260929/raw/criteria_pricing.html
- How the kit verifies it: No graded audit check exists for this. Kit steps: counter steps 2 and 6; rubric PRICE-01. 

### 25. No 24x7 or proactive support; premium support gated by contract size

- Id: `S-SUPPORT`. Providers affected: **5**, 5 sentences. Effort: **process**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), CUDO Compute (Bronze on the 2.0 page; 3.0: Unavailable), Google Cloud (GCP) (Silver on the 2.0 page; 3.0: Gold), Hot Aisle (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Neysa (Bronze on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-cudocompute-16`, `cmcr-hotaisle-09`, `cmcr-neysa-17`, `cmcr-googlecloud-39`, `cmcr-amazonwebservices-40`.
- Example sentence (`cmcr-cudocompute-16`): "However, the platform is not ready for large scale training and inference due to a lack of managed slurm or kubernetes services, shared file storage, monitoring dashboards, health checks, and any ..."
- What the customer observes: No proactive or vertically integrated support; premium support requires a multi-million dollar contract and a 3% premium; debugging by ticket.
- What it costs them: Slow resolution; SemiAnalysis quotes fixes in hours at gold tier vs weeks or months in a hyperscaler ticket queue (cmcr-fluidstack-35).
- Tie to our measurements: First human response time for Hot Aisle: UNKNOWN (unobserved).
- Likely fix: Provide 24x7 engineer-level support without a contract floor.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html :: General Expectations; main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md :: step 9
- How the kit verifies it: No graded audit check exists for this. Kit steps: counter step 9. 

### 26. Billed while the instance is not usable (stuck creating, down, or halted but reserved)

- Id: `S-BILLOUT`. Providers affected: **4**, 9 sentences. Effort: **software**.
- Providers: E2E Networks (Underperforming on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Qubrid (Bronze on the 2.0 page; 3.0: NOT IN 3.0 TABLE), Verda/DataCrunch (Bronze on the 2.0 page; 3.0: Bronze), Voltage Park (Silver on the 2.0 page; 3.0: NOT IN 3.0 TABLE).
- Claim ids: `cmcr-e2enetworks-11`, `cmcr-e2enetworks-13`, `cmcr-e2enetworks-15`, `cmcr-qubrid-07`, `cmcr-verdadatacrunch-16`, `cmcr-verdadatacrunch-17`, `cmcr-verdadatacrunch-19`, `cmcr-voltagepark-21`, `cmcr-voltagepark-22`.
- Example sentence (`cmcr-e2enetworks-11`): "The most serious issue occurred while we were stuck in this queue, waiting for our slurm cluster to be deployed. We watched as our credit balance was drained, and then went into the negatives."
- What the customer observes: Credit balance drained to negative while a cluster was stuck creating ($7,061.05 owed); charged while instances or whole sites are down; 'Shutdown' halts instances but keeps billing.
- What it costs them: Direct dollars; SemiAnalysis calls it the most offensive business practice it has seen.
- Tie to our measurements: Measured Run 3 overhead of billed but non-productive seat time: whole seat $0.90/1k vs $0.74 own-window (+20.7%), all honest billing. Outage billing itself: UNKNOWN.
- Likely fix: Bill only from usable-ready; auto-credit downtime (Verda: at least 2x, refunds in 24 h weekdays).
- Fix sources: sessions/clustermax-cloudreview-20260929/claims.all.jsonl :: cmcr-verdadatacrunch-21, -23; main/hot-aisle/campaign/shop-eval/counter/PROTOCOL.md :: step 6
- How the kit verifies it: No graded audit check exists for this. Kit steps: counter steps 6 and 10. Manual checks: `balance before and after delete`.

### 27. GPUDirect RDMA off or ACS not disabled; NCCL bandwidth far below reference

- Id: `S-RDMA`. Providers affected: **4**, 9 sentences. Effort: **config**.
- Providers: BuzzHPC (Bronze on the 2.0 page; 3.0: Participation Ribbon), IREN/Iris Energy (Underperforming on the 2.0 page; 3.0: Underperforming), Radiant/Ori (Unavailable on the 2.0 page; 3.0: Participation Ribbon), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-buzzhpc-14`, `cmcr-buzzhpc-16`, `cmcr-irenirisenergy-05`, `cmcr-irenirisenergy-06`, `cmcr-irenirisenergy-07`, `cmcr-irenirisenergy-08`, `cmcr-stn-09`, `cmcr-stn-14`, `cmcr-radiantori-05`.
- Example sentence (`cmcr-buzzhpc-14`): "To get around all of this, we ran a 2-node nccl test with the pytorch-bundled libnccl. Unfortunately, we did not see expected bandwidth (we about 10x lower than expected)."
- What the customer observes: GPUDirect RDMA not installed, ACS not disabled, NCCL AllReduce at 129.27 GB/s vs at least 300 GB/s reference (IREN), or about 10x lower than expected (BuzzHPC).
- What it costs them: Multi-node training throughput cut by 2.3x (300/129.27) to 10x on collectives.
- Tie to our measurements: Single-GPU Run 3: none. Multi-node: UNKNOWN (no estate measurement).
- Likely fix: Load dma_buf/nvidia-open, disable ACS on the GPU-NIC switches, install GDRCopy, and verify with nccl-tests.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Configuration (GPUDirect RDMA docs docs.nvidia.com/cuda/gpudirect-rdma/); sessions/clustermax-cloudreview-20260929/claims.all.jsonl :: cmcr-irenirisenergy-05..08
- How the kit verifies it: audit checks `gpus.gpuDirectRdmaPath`, `gpus.pcieAcs.enabled`, `gpus.gdrcopy.installed`. Kit steps: probe/fingerprint.sh. Manual checks: `nccl-tests two-node`.

### 28. Kubernetes GPU Operator or Network Operator missing or outdated at delivery

- Id: `S-K8SOPS`. Providers affected: **4**, 4 sentences. Effort: **config**.
- Providers: Fluidstack (Gold on the 2.0 page; 3.0: Unavailable), GCORE (Silver on the 2.0 page; 3.0: Bronze), Radiant/Ori (Unavailable on the 2.0 page; 3.0: Participation Ribbon), Vultr (Silver on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-gcore-15`, `cmcr-vultr-10`, `cmcr-fluidstack-30`, `cmcr-radiantori-05`.
- Example sentence (`cmcr-gcore-15`): "Unfortunately, the cluster was delivered without the Nvidia GPU Operator or the Network Operator."
- What the customer observes: No GPU Operator or Network Operator at delivery, or versions more than a year old.
- What it costs them: GPUs invisible to Kubernetes; unpatched drivers.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Install and maintain the GPU and Network Operators at current versions.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html :: Configuration, Other (GPU Operator docs docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/getting-started.html)
- How the kit verifies it: audit checks `securityVersions.nvidiaContainerToolkit.status`. Manual checks: `kubectl get pods -n gpu-operator`.

### 29. SLA absent, unclear, or not honored

- Id: `S-SLA`. Providers affected: **4**, 4 sentences. Effort: **process**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), Google Cloud (GCP) (Silver on the 2.0 page; 3.0: Gold), STN (Bronze on the 2.0 page; 3.0: Participation Ribbon), Verda/DataCrunch (Bronze on the 2.0 page; 3.0: Bronze).
- Claim ids: `cmcr-stn-13`, `cmcr-verdadatacrunch-19`, `cmcr-googlecloud-42`, `cmcr-amazonwebservices-37`.
- Example sentence (`cmcr-stn-13`): "We suggest that in the future, STN focus on actual cluster reliability instead of reporting fake “Uptime SLA” metrics to Grafana."
- What the customer observes: SLA figures that are not upheld, unclear, or mis-reported ('fake Uptime SLA' metrics in Grafana).
- What it costs them: Compensation not received.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Publish an MSA SLA with credits and honor it.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/criteria_reliability.html :: MSA SLA evaluation
- How the kit verifies it: No graded audit check exists for this. Kit steps: desk review. 

### 30. Restrictive defaults block standard tooling (profiling, systemd, sinfo/scontrol, VPN-only access)

- Id: `S-TOOLING`. Providers affected: **3**, 8 sentences. Effort: **config**.
- Providers: CoreWeave (Platinum on the 2.0 page; 3.0: Platinum), Firmus / Sustainable Metal Cloud (SMC) (Silver on the 2.0 page; 3.0: Silver), GMO Cloud (Silver on the 2.0 page; 3.0: Bronze).
- Claim ids: `cmcr-coreweave-40`, `cmcr-coreweave-41`, `cmcr-gmocloud-05`, `cmcr-gmocloud-06`, `cmcr-gmocloud-07`, `cmcr-firmussustainablemetalcloud-07`, `cmcr-firmussustainablemetalcloud-08`, `cmcr-firmussustainablemetalcloud-09`.
- Example sentence (`cmcr-coreweave-40`): "The feedback is here is the security concerns from CoreWeave is way to limiting for a lot of power users. For example as default, systemd is not available, and a lot of CPU and GPU profiling tooling ..."
- What the customer observes: No systemd or profiling tools by default; sinfo/scontrol disabled for users; mandatory VPN with no alternative.
- What it costs them: Standard debugging and profiling workflows break.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Enable non-root profiling (NVreg_RestrictProfilingToAdminUsers=0; perf_event_paranoid <= 1; kptr_restrict = 0) and restore standard Slurm commands.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Monitoring and Health Checks (perf security docs kernel.org/doc/html/latest/admin-guide/perf-security.html)
- How the kit verifies it: audit checks `software.ncu.profilingEnabled`, `software.perf.perfEventParanoid`, `software.perf.kptrRestrict`, `access.slurmCommandsOk`. Manual checks: `cat /proc/sys/kernel/perf_event_paranoid /proc/sys/kernel/kptr_restrict`.

### 31. Health-check prolog so heavy that a job takes over a minute to start (or checks take 60-120 minutes)

- Id: `S-PROLOG`. Providers affected: **3**, 5 sentences. Effort: **config**.
- Providers: Amazon Web Services (AWS) (Silver on the 2.0 page; 3.0: Bronze), Firmus / Sustainable Metal Cloud (SMC) (Silver on the 2.0 page; 3.0: Silver), Fluidstack (Gold on the 2.0 page; 3.0: Unavailable).
- Claim ids: `cmcr-firmussustainablemetalcloud-10`, `cmcr-firmussustainablemetalcloud-11`, `cmcr-fluidstack-11`, `cmcr-fluidstack-12`, `cmcr-amazonwebservices-25`.
- Example sentence (`cmcr-firmussustainablemetalcloud-10`): "Once connected, our slurm environment also had some configuration issues. The standard topology.conf file was not set for topology-aware scheduling, and a simple “srun -N1 –gpus-per-node=8 –pty bash” ..."
- What the customer observes: Interactive srun on one node takes over a minute because the prolog runs full NCCL and bandwidth tests every job.
- What it costs them: Over 60 s per job start vs the 30 s expectation.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Move deep checks to weekly idle-node runs; keep prolog to DCGM level 1 or 2, use epilog HealthCheckProgram.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Prolog and Epilog scripts lightweight (<30s); sessions/clustermax-cloudreview-20260929/claims.all.jsonl :: cmcr-firmussustainablemetalcloud-11
- How the kit verifies it: No graded audit check exists for this. Manual checks: `time srun -N1 hostname`.

### 32. No downloadable kubeconfig; cluster reached only by SSH into a jump host

- Id: `S-KUBECONFIG`. Providers affected: **3**, 4 sentences. Effort: **config**.
- Providers: Oracle (Gold on the 2.0 page; 3.0: Gold), Tensorwave (Silver on the 2.0 page; 3.0: Silver), Together (Silver on the 2.0 page; 3.0: Bronze).
- Claim ids: `cmcr-oracle-23`, `cmcr-together-25`, `cmcr-tensorwave-07`, `cmcr-tensorwave-08`.
- Example sentence (`cmcr-oracle-23`): "A key point of frustration in the OKE setup is the lack of a direct kubeconfig file. Users are instead required to SSH into the cluster to perform management functions."
- What the customer observes: Must SSH into a jump host to use kubectl; no kubeconfig download.
- What it costs them: Extra setup; no remote tooling.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Provide a downloadable kubeconfig.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_kubernetes.html :: Access, Kubeconfig simple download
- How the kit verifies it: No graded audit check exists for this. Manual checks: `kubectl cluster-info`.

### 33. Passwordless SSH between nodes or SSH keys not provisioned on the cluster

- Id: `S-SSH`. Providers affected: **3**, 3 sentences. Effort: **config**.
- Providers: BuzzHPC (Bronze on the 2.0 page; 3.0: Participation Ribbon), Lambda (Silver on the 2.0 page; 3.0: Silver), Prime Intellect (Bronze on the 2.0 page; 3.0: Bronze).
- Claim ids: `cmcr-buzzhpc-07`, `cmcr-primeintellect-08`, `cmcr-lambda-22`.
- Example sentence (`cmcr-buzzhpc-07`): "initially, no passwordless ssh between nodes"
- What the customer observes: No passwordless SSH between nodes or keys not provisioned.
- What it costs them: MPI and multi-node launch fail.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Provision keys and passwordless SSH at cluster creation.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_slurm.html :: Access, Passwordless SSH connectivity between nodes
- How the kit verifies it: audit checks `access.sshToComputeNodes`. Manual checks: `srun -N4 hostname`.

### 34. InfiniBand tenant isolation misconfigured (PKey/SAKey): tenant could see every other endpoint

- Id: `S-ISOLATION`. Providers affected: **2**, 2 sentences. Effort: **config**.
- Providers: FPT CLOUD (Unavailable on the 2.0 page; 3.0: Participation Ribbon), Radiant/Ori (Unavailable on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-fptcloud-10`, `cmcr-radiantori-04`.
- Example sentence (`cmcr-fptcloud-10`): "Our testing showed that PKeys and SAKey were not configured correctly, allowing us to see every other endpoint on the network (i.e. every other customer)."
- What the customer observes: Tenant could see every other endpoint on the InfiniBand network.
- What it costs them: Cross-tenant data exposure risk; blocks the Silver tier at FPT.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Configure PKeys and SAKey, enable UFM secured profile.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/criteria_security.html :: PKeys, InfiniBand Security Keys, UFM Secured Bare Metal Cloud profile
- How the kit verifies it: audit checks `ufm-profile`. 

### 35. NVML driver/library mismatch or driver provisioning failure on a delivered instance

- Id: `S-NVML`. Providers affected: **2**, 2 sentences. Effort: **software**.
- Providers: Crusoe (Gold on the 2.0 page; 3.0: Bronze), Latitude.sh (Bronze on the 2.0 page; 3.0: Participation Ribbon).
- Claim ids: `cmcr-crusoe-27`, `cmcr-latitudesh-07`.
- Example sentence (`cmcr-crusoe-27`): "We repeatedly saw NVML driver mismatch errors inside individual Docker containers, indicating potential image or driver management instability."
- What the customer observes: NVML driver/library mismatch errors inside containers; H100 VM driver provisioning failed.
- What it costs them: Instance unusable until fixed.
- Tie to our measurements: UNKNOWN (no estate measurement).
- Likely fix: Pin and validate driver and library together at image build; monitor with a post-boot nvidia-smi check.
- Fix sources: sessions/clustermax-cloudreview-20260929/raw/expectations_standalone.html :: Configuration (nvidia-smi && nvcc --version); main/hot-aisle/campaign/shop-eval/diagnose/RUBRIC.md :: STK-01
- How the kit verifies it: audit checks `securityVersions.nvidiaDriver.status`. Kit steps: probe/fingerprint.sh; rubric STK-01. Manual checks: `nvidia-smi`.

## Corpus by topic and stance

| topic | negative | neutral | positive |
|---|---:|---:|---:|
| criticism | 354 | 38 | 0 |
| praise | 0 | 4 | 226 |
| business | 10 | 167 | 22 |
| rating | 29 | 65 | 7 |
| hardware | 13 | 73 | 15 |
| access | 46 | 45 | 6 |
| prediction | 13 | 22 | 16 |
| methodology | 2 | 36 | 0 |
| pricing | 14 | 9 | 11 |
| financing | 0 | 17 | 2 |
| disclosure | 2 | 6 | 3 |

Stance and topic are the labels in the source rows (`claims.all.jsonl`), assigned by the capture session, not by me.
