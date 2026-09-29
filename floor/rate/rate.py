#!/usr/bin/env python3
"""Desk-tier rating of every ClusterMAX-reviewed provider against the floor.

stdlib only.  Emits RATINGS.jsonl (one row per provider) and RATINGS.md next to
this file.  Every dimension is MEETS / SHORT / UNKNOWN and carries its evidence
ids.  UNKNOWN is never counted as SHORT.  ClusterMAX page tier and 3.0 medal are
imported context columns only; they are never read by any scoring function.

Run:  python rate.py [--refresh-prices] [--out DIR]

Desk tier means: scored from public documents already captured on disk (review
sentences, provider-owned public surfaces, public status pages, a public price
feed).  It is compatible with, and does not replace, the per-shop counter
(hot-aisle/campaign/shop-eval/counter/PROTOCOL.md) and diagnose rubric
(RUBRIC.md): the same UNKNOWN discipline (absent evidence is never a pass or a
fail) and the same "SIGNAL vs WRONG" restraint -- a SHORT here is a documented
shortfall against a named label, not a verdict about cause.

floor.json item ids are bound afterwards: see FLOOR_BINDING (label -> None).
"""
import argparse
import collections
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[1]                 # .../axm-tools/main
AXM = MAIN.parent                      # .../axm-tools
SESSION = AXM / "sessions" / "clustermax-cloudreview-20260929"
PRICES = AXM / "sessions" / "public-tail-20260929" / "lanes" / "opencomputeprices" / "rows" / "prices.jsonl"
CM = MAIN / "clustermax-challenge"
CAMPAIGN_PROVIDERS = MAIN / "hot-aisle" / "campaign" / "providers" / "providers.jsonl"
CACHE = HERE / "cache" / "price_agg_2026-07.json"

AS_OF = "2026-09-29"
METHOD_VERSION = "desk-rate-0.1.0"
DIMENSIONS = ["access", "delivery", "security", "reliability", "pricing", "transparency"]
PRICE_BAND_PERCENTILE = 75.0           # SHORT above_price_band when provider median is above this percentile
MIN_PRICE_ROWS = 5                     # July on-demand rows needed for a price percentile
ARTEFACT_FACTOR = 3.0                  # July row dropped if > 3x provider's own June median
WINDOW_DAYS = 180

# floor.json item ids are written by another hand; bind afterwards.
FLOOR_BINDING = {lab: None for lab in [
    "no_health_checks", "no_shared_storage", "slurm_k8s_not_working", "no_slurm_k8s_offering",
    "old_driver_cve", "no_soc2", "no_rbac", "tenant_isolation_gap", "billing_during_outage",
    "undisclosed_provider", "access_weeks", "account_gate", "no_status_history", "above_price_band",
    "sales_call_only", "no_monitoring", "reliability_complaints"]}

DIM_OF_LABEL = {
    "sales_call_only": "access", "access_weeks": "access", "account_gate": "access",
    "no_health_checks": "delivery", "no_shared_storage": "delivery", "no_monitoring": "delivery",
    "slurm_k8s_not_working": "delivery", "no_slurm_k8s_offering": "delivery",
    "no_soc2": "security", "old_driver_cve": "security", "no_rbac": "security",
    "tenant_isolation_gap": "security",
    "no_status_history": "reliability", "reliability_complaints": "reliability",
    "above_price_band": "pricing", "billing_during_outage": "pricing", "undisclosed_provider": "pricing",
}

# ---------------------------------------------------------------- provider maps
# slug (clustermax.ai cloudreview) -> other corpora.  Only entries that exist are listed;
# a provider absent from a map simply has no evidence of that kind.
INCIDENT_FILE = {
    "akamailinode": "akamai", "atlascloud": "atlas-cloud", "cirrascale": "cirrascale",
    "coreweave": "coreweave", "crusoe": "crusoe-r2", "cudocompute": "cudo-compute",
    "digitalocean": "digitalocean", "fluidstack": "fluidstack", "gcore": "gcore",
    "googlecloud": "google-cloud", "hydrahost": "hydra", "hyperstacknexgen": "hyperstack",
    "lambda": "lambda", "latitudesh": "latitude-sh", "lightningai": "lightning-ai",
    "mithrilmlfoundry": "mithril", "nebius": "nebius", "ovhcloud": "ovhcloud",
    "primeintellect": "prime-intellect", "radiantori": "radiant", "runpod": "runpod",
    "scaleway": "scaleway", "together": "together-ai", "verdadatacrunch": "verda",
}
STATUS_NAME = {
    "akamailinode": "Akamai", "amazonwebservices": "AWS", "atlascloud": "Atlas Cloud", "azure": "Azure",
    "buzzhpc": "Buzz HPC", "cirrascale": "Cirrascale", "coreweave": "CoreWeave", "crusoe": "Crusoe",
    "cudocompute": "Cudo Compute", "denvrdataworks": "DENVR Dataworks", "digitalocean": "DigitalOcean",
    "dstacksky": "dstack", "deepinfra": "deepinfra", "e2enetworks": "E2E Cloud", "exabits": "Exabits",
    "farmgpu": "FarmGPU", "firmussustainablemetalcloud": "Firmus", "fluidstack": "FluidStack",
    "gcore": "GCore", "gmi": "GMI", "gmocloud": "GMO GPU Cloud", "googlecloud": "Google Cloud",
    "gpunet": "GPU.NET", "hetzner": "Hetzner", "hotaisle": "Hot Aisle", "hydrahost": "Hydra",
    "hyperbolic": "Hyperbolic", "hyperstacknexgen": "Hyperstack", "ibmcloud": "IBM Cloud",
    "irenirisenergy": "IREN", "lambda": "Lambda", "latitudesh": "latitude.sh", "lightningai": "Lightning AI",
    "massedcompute": "Massed Compute", "mithrilmlfoundry": "Mithril", "nebius": "Nebius", "neysa": "Neysa",
    "oracle": "Oracle", "ovhcloud": "OVHcloud", "palebluedot": "PaleBlueDot.AI", "primeintellect": "Prime Intellect",
    "qubrid": "Qubrid", "radiantori": "Radiant", "runpod": "RunPod", "saladcloud": "Salad", "scaleway": "Scaleway",
    "sesterce": "Sesterce", "shadeform": "Shadeform", "stn": "STN", "tensorwave": "TensorWave",
    "together": "Together.ai", "vastai": "Vast.ai", "verdadatacrunch": "Verda (formerly DataCrunch)",
    "voltagepark": "Voltage Park", "vultr": "Vultr", "whitefiber": "Whitefiber", "aethir": "Aethir",
    "akashnetwork": "Akash", "clore": "Clore.ai",
}
PRICE_KEY = {
    "akashnetwork": "akash", "amazonwebservices": "aws", "azure": "azure", "clore": "cloreai",
    "coreweave": "coreweave", "crusoe": "crusoe", "cudocompute": "cudo", "denvrdataworks": "denvr",
    "digitalocean": "digitalocean", "e2enetworks": "e2e", "fluidstack": "fluidstack", "gcore": "gcore",
    "gmi": "gmicloud", "googlecloud": "gcp", "hotaisle": "hot_aisle", "hyperstacknexgen": "hyperstack",
    "lambda": "lambda", "latitudesh": "latitude", "lightningai": "lightningai", "massedcompute": "massedcompute",
    "nebius": "nebius", "oracle": "oracle", "ovhcloud": "ovh", "primeintellect": "primeintellect",
    "qubrid": "qubrid", "runpod": "runpod", "scaleway": "scaleway", "sesterce": "sesterce",
    "together": "together", "vastai": "vastai", "verdadatacrunch": "verda", "voltagepark": "voltagepark",
    "vultr": "vultr",
}
CAMPAIGN_ID = {  # providers.jsonl provider_id -> slug
    "latitude": "latitudesh", "verda": "verdadatacrunch", "together": "together", "voltagepark": "voltagepark",
    "massedcompute": "massedcompute", "runpod": "runpod", "nebius": "nebius", "crusoe": "crusoe",
    "lambda": "lambda", "digitalocean": "digitalocean", "aws": "amazonwebservices", "coreweave": "coreweave",
    "azure": "azure", "vast-ai": "vastai", "akash": "akashnetwork", "shadeform": "shadeform",
    "tensorwave": "tensorwave", "vultr": "vultr", "oracle-cloud": "oracle", "hot-aisle": "hotaisle",
    "hotaisle": "hotaisle",
}
NAME_TOKENS = {  # tokens that must appear in a fetched trust page for it to count as that provider's page
    "amazonwebservices": ["aws", "amazon"], "googlecloud": ["google"], "core42g42": ["core42"],
    "hyperstacknexgen": ["hyperstack"], "verdadatacrunch": ["verda", "datacrunch"],
    "irenirisenergy": ["iren"], "lightningai": ["lightning"], "radiantori": ["radiant", "ori.co"],
    "hydrahost": ["hydra"], "firmussustainablemetalcloud": ["firmus"], "ibmcloud": ["ibm"],
    "digitalocean": ["digitalocean", "digital ocean"], "hotaisle": ["hot aisle", "hotaisle"],
    "voltagepark": ["voltage park", "voltagepark"], "akamailinode": ["akamai", "linode"],
    "mithrilmlfoundry": ["mithril"], "gmocloud": ["gmo"], "e2enetworks": ["e2e"],
}
DISCLOSURES = {
    "hotaisle": ("Hot Aisle is the reference shop of this project: 'Hot Aisle-grade' in the shop-eval kit names "
                 "its observed behaviors, and the project holds campaign-private measurements (Run 1/Run 3 "
                 "telemetry, invoices, TUI observations) about it.  None of that is used here.  This row is "
                 "scored ONLY from public evidence: the 2025-11-06 ClusterMAX 2.0 page, Hot Aisle's own public "
                 "site pages captured 2026-09-29, the public status-page discovery, the public OpenComputePrices "
                 "feed, and campaign listing rows whose source is a public pricing page.  Read the row as a "
                 "third-party desk view of Hot Aisle, not as an endorsement or a measured result."),
}
PUBLIC_KINDS = {"claim", "surface", "status", "incident", "price", "campaign_public_listing"}


# ---------------------------------------------------------------- claim classification
def R(p):
    return re.compile(p, re.I | re.S)

NEG = r"(?:\bno\b|\bnot\b|n.t\b|\bnon-?|without|lack(?:s|ed|ing)?\b|missing|absen(?:t|ce)|never|unable|none)"

PAT = {
    # ---- delivery
    "no_health_checks": [
        R(r"(?:\bno\b|without|\black\w*|missing|non-?existent|absence of|does not have|do not have)(?![^.;]{0,25}ability to (?:test|review))[^.;]{0,90}?health[- ]?checks?"),
        R(r"not provide[^.;]{0,40}(?:default|health)[^.;]{0,60}health[- ]?check"),
        R(r"not meet the standards[^.;]*health"),
        R(r"health[- ]?checks?[^.;]{0,60}?(?:not (?:installed|enabled|integrated|plugged|in place|provided|configured)|were not|are not|non-?existent|are lacking)"),
        R(r"dcgm\w*[^.;]{0,40}?health[^.;]{0,40}?(?:not (?:enabled|installed|integrated|plugged|configured)|is not plugged)"),
    ],
    "no_shared_storage": [
        R(r"(?:\bno\b|\bnot\b|without|\black\w*|missing|unable to create|absence of)[^.;]{0,50}?shared[- ](?:file ?system|filesystem|fs|storage|file storage|home|disk)"),
        R(r"home directory[^.;]{0,40}not shared"),
        R(r"\bno NFS mount"),
        R(r"\black(?:s|ing)? of [^.;]{0,80}\bstorage\b"),
        R(r"does not include a default ReadWriteMany"),
        R(r"does not have[^.;]{0,40}shared storage"),
    ],
    "no_monitoring": [
        R(r"(?:\bno\b|without|\black\w*|missing|non-?existent|absen\w+|does not have|do not have)(?![^.;]{0,25}ability to (?:test|review))[^.;]{0,80}?(?:monitoring|montoring|dashboards?)"),
        R(r"not meet the standards[^.;]*monitoring"),
        R(r"(?:monitoring|dashboards?)[^.;]{0,60}?(?:non-?existent|not (?:provided|functional|available|installed)|non-functional|basically non-existent)"),
    ],
    "slurm_k8s_not_working": [
        R(r"(?:slurm|kubernetes|k8s|SonK|Slinky|cluster)[^;]{0,120}?(?:unusable|not usable|broken|stuck in|did(?: not|n.t) work|neither of them worked|(?:was|were|is|are) not (?:setup|set up|working|functional|configured)|dead end|largely unstable|everything wrong|not ready)"),
        R(r"(?:became|was|were|is) stuck[^.;]{0,60}?provisioning"),
    ],
    "no_slurm_k8s_offering": [
        R(r"(?:\bno\b|without|\black\w*|not have|not offer|does not offer|has no)(?![^.;]{0,25}(?:ability|GA managed|a GA))[^.;]{0,40}?(?:managed )?slurm(?!\s*in the announcement)"),
        R(r"(?:not have|\bno\b|\black\w*)[^.;]{0,20}?(?:a )?kubernetes (?:offering|service|engine)"),
        R(r"(?:precludes|prevents)[^.;]{0,120}?(?:slurm|kubernetes|orchestration)"),
        R(r"kubernetes engine is not optimi"),
    ],
    # ---- security
    "no_soc2": [
        R(r"(?:does not have|do not have|\black\w*|without|missing|\bno\b|not have|absence of)[^.;]{0,60}?(?:attestation|SOC ?2|ISO ?27001)"),
        R(r"encourage[^.;]*(?:attestation|SOC ?2)"),
        R(r"expectations[^.;]*attestation"),
        R(r"(?:planning (?:on )?completing|pending)[^.;]{0,60}?SOC ?2"),
    ],
    "old_driver_cve": [
        R(r"\bCVE\b|CVE-\d|NVIDIAScape|vulnerab"),
        R(r"(?:driver|toolkit|GPU Operator|Network Operator)[^.;]{0,80}?(?:out[- ]of[- ]date|outdated|insecure|over 1 year old|minor version behind)"),
        R(r"security patches"),
    ],
    "no_rbac": [
        R(r"(?:\bno\b|\bnot\b|without|\black\w*|cannot|unable|no way to|doesn.t support|does not support|isn.t|does not have)[^.;]{0,120}?(?:RBAC|SSO|external IAM|IAM provider|create new users|add users|add additional users)"),
        R(r"(?:RBAC|SSO)[^.;]{0,60}?(?:not available|isn.t|is not)"),
        R(r"shared root user"),
    ],
    "tenant_isolation_gap": [
        R(r"PKeys?[^.;]*not configured|see every other endpoint|every other customer"),
    ],
    # ---- pricing
    "billing_during_outage": [
        R(r"charg\w+[^.;]{0,80}?(?:while|when|even when|stuck|spinning up|inaccessible|not usable)"),
        R(r"credit balance was drained"),
        R(r"Owing \$[\d,.]+ for a cluster stuck"),
    ],
    "undisclosed_provider": [
        R(r"(?:does not|doesn.t|not) (?:explicitly )?(?:state|disclose|expose|make clear|say)[^.;]{0,80}?underlying"),
        R(r"unclear (?:how|who|which|what)[^.;]{0,60}?underlying|unknown underlying|less introspection on who the underlying"),
        R(r"which provider is actually running|who.s hardware|hosted by an unknown|machine belongs to|who is ultimately responsible|running on AWS hardware"),
    ],
    # ---- access
    "sales_call_only": [
        R(r"not truly a self[- ]?serv\w*|fill out a form|phone calls?|contact sales|requiring an invitation|sales[- ](?:led|call)|onboarding is entirely manual"),
    ],
    "access_weeks": [
        R(r"\d+-month wait|over a month from our initial request|no capacity available[^.;]*months"),
    ],
    "account_gate": [
        R(r"\bKYC\b|deactivate\w* our account|Account Verification|shut us down|request a quota|quota (?:increase|approv)|wait for approval|issues signing up"),
    ],
    # ---- reliability (extension label; reviewer-reported)
    "reliability_complaints": [
        R(r"reliability (?:issues|complaints|challenges|problems|was)|reliability emerged|plagued by|link flaps|hit-or-miss|entire sites can go dark|unpredictable|\bdown. state|outages that stretch|persistent connection drops"),
    ],
}
GATE_STANCE = {k: True for k in PAT}   # SHORT labels need stance <= 0

RELEVANT = {
    "delivery": R(r"slurm|kubernetes|k8s|SUNK|Soperator|Slinky|health[- ]?check|dcgm|monitoring|dashboard|grafana|storage|file ?system|lustre|\bvast\b|weka|nccl|infiniband|topology|prolog|pyxis|enroot"),
    "security": R(r"SOC ?2|\bISO\b|attestation|security|\bCVE\b|vulnerab|RBAC|tenant|patch|zero-trust|isolation|compliance"),
    "reliability": R(r"reliab|outage|downtime|uptime|\bSLA\b|incident|failure|link flap|unstable|interruption|went dark"),
    "pricing": R(r"\$\d|\bprice|pricing|billing|billed|charg\w+|cost"),
    "transparency": R(r"documentation|transparen|disclos|underlying"),
}
NEUTRAL_TOPICS = {"criticism", "praise", "access", "disclosure", "pricing"}
INITIAL = R(r"\binitial(?:ly)?\b|at the time of testing|at first|prior to March 2025")
POS_ATTEST = R(r"SOC ?2|ISO ?/?(?:IEC )?27001|PCI DSS|HIPAA|achiev\w+ security compliance")
ATTEST_NOT_HELD = R(r"pending|planning|if \w+ gets|in place and fixes|soon|lack|without|no security")
POS_SECURITY = R(r"zero-trust|isolation between tenants|Secure Boot|hyperscaler mentality|rock solid|robust security|OIDC")
POS_ACCESS = R(r"self[- ]?serv|spun up|spin up|in minutes|instantly|quickly|sign ?up")
POS_BILLING = R(r"not charged|does not charge")
POS_PRICE = R(r"competitive price|reasonable|lowest price|attractive|low-cost|cheap|realistic pricing|below market")
DISCLOSED = R(r"vertically integrated|(?:owns?|own|operates?|builds?) (?:its|their|all their|the) (?:own )?(?:data ?cent\w*|hardware|infrastructure)")


def classify_claim(c):
    """Return list of hits {dim, polarity, label}.  polarity: short|meets|neutral|neg_unlabeled."""
    q = c.get("quote", "")
    stance = c.get("stance", 0)
    topic = c.get("topic", "")
    hits = []
    labeled_dims = set()
    if stance <= 0:
        for label, pats in PAT.items():
            if any(p.search(q) for p in pats):
                hits.append({"dim": DIM_OF_LABEL[label], "polarity": "short", "label": label})
                labeled_dims.add(DIM_OF_LABEL[label])
    # attestation held (positive) -- dimension security
    if POS_ATTEST.search(q) and stance >= 0 and not ATTEST_NOT_HELD.search(q):
        weak = bool(re.search(r"underlying", q, re.I))
        hits.append({"dim": "security", "polarity": "neutral" if weak else "meets",
                     "label": "attestation_held_underlying_only" if weak else "attestation_held"})
        labeled_dims.add("security")
    elif stance >= 1 and POS_SECURITY.search(q):
        hits.append({"dim": "security", "polarity": "meets", "label": None})
        labeled_dims.add("security")
    # billing positive
    if stance >= 0 and POS_BILLING.search(q):
        hits.append({"dim": "pricing", "polarity": "meets", "label": "billing_ok"})
        labeled_dims.add("pricing")
    if stance >= 1 and POS_PRICE.search(q) and (topic == "pricing" or RELEVANT["pricing"].search(q)):
        hits.append({"dim": "pricing", "polarity": "meets", "label": "price_praise"})
        labeled_dims.add("pricing")
    if DISCLOSED.search(q) and stance >= 0:
        hits.append({"dim": "transparency", "polarity": "meets", "label": "provider_disclosed"})
        labeled_dims.add("transparency")
    # access
    if topic == "access":
        if "access" not in labeled_dims:
            if stance >= 1 and POS_ACCESS.search(q):
                hits.append({"dim": "access", "polarity": "meets", "label": None})
            else:
                hits.append({"dim": "access", "polarity": "neg_unlabeled" if stance < 0 else "neutral", "label": None})
            labeled_dims.add("access")
    elif stance >= 1 and POS_ACCESS.search(q) and re.search(r"self[- ]?serv|sign ?up", q, re.I):
        hits.append({"dim": "access", "polarity": "meets", "label": None})
        labeled_dims.add("access")
    # relevance-only hits for remaining dims
    for dim in ("delivery", "security", "reliability", "pricing", "transparency"):
        if dim in labeled_dims or not RELEVANT[dim].search(q):
            continue
        if topic in ("rating", "methodology", "prediction", "financing"):
            continue
        if stance == 0 and topic not in NEUTRAL_TOPICS:
            continue
        if stance >= 1:
            pol = "meets" if dim in ("delivery",) else "neutral"
        elif stance < 0:
            pol = "neg_unlabeled"
        else:
            pol = "neutral"
        hits.append({"dim": dim, "polarity": pol, "label": None})
    return hits


# ---------------------------------------------------------------- loaders
def jl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def html_text(path, limit=3_000_000):
    try:
        raw = Path(path).read_bytes()[:limit].decode("utf-8", "replace")
    except OSError:
        return ""
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw)


def manifest_entries(slug, session=SESSION):
    p = session / "providers" / slug / "manifest.json"
    if not p.exists():
        return []
    d = jload(p)
    es = d["entries"] if isinstance(d, dict) else d
    out = []
    for e in es:
        kind = (e.get("kind") or e.get("label") or "").lower()
        f = e.get("file") or ""
        out.append({"kind": kind, "url": e.get("url"), "http": e.get("http"), "bytes": e.get("bytes") or 0,
                    "file": (session / f) if f else None, "curl_error": e.get("curl_error"),
                    "retrieved_utc": e.get("retrieved_utc")})
    return out


def load_inputs():
    headers = {h["slug"]: h for h in jload(SESSION / "headers.all.json")}
    tiers = {t["slug"]: t for t in jload(SESSION / "page-tier-vs-3.0.json")}
    claims = collections.defaultdict(list)
    for c in jl(SESSION / "claims.all.jsonl"):
        claims[c["id"].split("-")[1]].append(c)
    incidents = {}
    idir = CM / "retrospective" / "incidents"
    for slug, fname in INCIDENT_FILE.items():
        p = idir / f"{fname}.json"
        if p.exists():
            incidents[slug] = jload(p)
    sp = {p["rating_name"]: p for p in jload(CM / "retrospective" / "status-pages.json")["providers"]}
    campaign = collections.defaultdict(list)
    if CAMPAIGN_PROVIDERS.exists():
        for r in jl(CAMPAIGN_PROVIDERS):
            slug = CAMPAIGN_ID.get(r["provider_id"])
            # only rows sourced from a public URL; rows sourced from an authenticated console/TUI are private
            if slug and str(r.get("source_url", "")).startswith(("https://", "http://")):
                campaign[slug].append(r)
    return {"headers": headers, "tiers": tiers, "claims": claims, "incidents": incidents,
            "status_pages": sp, "campaign": campaign, "price": load_prices()}


# ---------------------------------------------------------------- prices
def build_price_agg(path=PRICES):
    """Stream the 954 MB feed once.  July 2026 on-demand H100 / MI300X rows per provider,
    with a June-2026 per-provider median used only to drop obvious scraper artefacts."""
    jun = collections.defaultdict(list)
    jul = collections.defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            head = line[:48]
            is_jul = '"2026-07-' in head
            is_jun = '"2026-06-' in head
            if not (is_jul or is_jun):
                continue
            r = json.loads(line)
            if r.get("price_type") != "on_demand" or r.get("gpu") not in ("H100", "MI300X"):
                continue
            v = r.get("hourly_price_usd")
            if v is None:
                continue
            (jul if is_jul else jun)[(r["provider"], r["gpu"])].append(float(v))
    agg = {}
    for key, vals in jul.items():
        jm = statistics.median(jun[key]) if jun.get(key) else None
        kept = [v for v in vals if jm is None or v <= ARTEFACT_FACTOR * jm]
        agg["%s|%s" % key] = {"provider": key[0], "gpu": key[1], "rows_total": len(vals),
                              "rows_kept": len(kept), "rows_dropped_artefact": len(vals) - len(kept),
                              "june_median": jm, "july_median": statistics.median(kept) if kept else None}
    return {"as_of_data": "2026-07-29", "source": str(path.name), "artefact_factor": ARTEFACT_FACTOR,
            "min_rows": MIN_PRICE_ROWS, "entries": agg}


def load_prices(refresh=False):
    if CACHE.exists() and not refresh:
        return jload(CACHE)
    if not PRICES.exists():
        return {"entries": {}, "as_of_data": None}
    agg = build_price_agg()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(agg, indent=1, sort_keys=True), encoding="utf-8")
    return agg


def price_position(price, key):
    """(gpu, median, percentile_mid_rank, n_market, entry) for the provider key, H100 preferred."""
    ents = price.get("entries", {})
    for gpu in ("H100", "MI300X"):
        mine = ents.get("%s|%s" % (key, gpu))
        if not mine or mine["rows_kept"] < MIN_PRICE_ROWS or mine["july_median"] is None:
            continue
        market = [e["july_median"] for e in ents.values()
                  if e["gpu"] == gpu and e["rows_kept"] >= MIN_PRICE_ROWS and e["july_median"] is not None]
        m = mine["july_median"]
        lower = sum(1 for x in market if x < m)
        equal = sum(1 for x in market if x == m)
        pct = 100.0 * (lower + 0.5 * (equal - 1)) / max(1, len(market) - 1) if len(market) > 1 else None
        return gpu, m, pct, len(market), mine
    return None


# ---------------------------------------------------------------- per-provider evidence
def new_dim():
    return {"status": "UNKNOWN", "evidence_count": 0, "evidence_ids": [], "shortfalls": [],
            "superseded": [], "facts": {}, "note": None}


def rate_provider(slug, inp):
    """Pure function of the inputs.  Empty inputs -> all UNKNOWN, distance 0, evidence_count 0."""
    hdr = (inp.get("headers") or {}).get(slug, {})
    tier = (inp.get("tiers") or {}).get(slug, {})
    claims = (inp.get("claims") or {}).get(slug, [])
    ev = {}                                    # id -> evidence record
    dimev = {d: [] for d in DIMENSIONS}        # dim -> list of (id, polarity, label)

    def add(eid, kind, dim, polarity, label, detail=None, quote=None):
        rec = ev.setdefault(eid, {"id": eid, "kind": kind, "dims": [], "polarity": {}, "labels": {}})
        if detail:
            rec["detail"] = detail
        if quote:
            rec["quote"] = quote
        if dim not in rec["dims"]:
            rec["dims"].append(dim)
        rec["polarity"][dim] = polarity
        if label and label not in rec["labels"].setdefault(dim, []):
            rec["labels"][dim].append(label)
        dimev[dim].append((eid, polarity, label))

    # ---- claims
    claim_by_id = {}
    for c in claims:
        claim_by_id[c["id"]] = c
        hits = classify_claim(c)
        seen = set()
        for h in hits:
            key = (h["dim"], h["polarity"], h["label"])
            if key in seen:
                continue
            seen.add(key)
            add(c["id"], "claim", h["dim"], h["polarity"], h["label"], quote=c["quote"])

    # ---- provider-owned surfaces
    surf = {"pricing_public": None, "docs_public": None, "trust_page": None, "attest_mentioned": None}
    for e in inp.get("manifest", {}).get(slug, []):
        if e["http"] != 200 or e["bytes"] < 2000 or not e["file"]:
            continue
        k = e["kind"]
        eid = "surf:%s:%s" % (slug, Path(e["file"]).name)
        if k.startswith("pricing") or k == "product_gpu_instances":
            t = html_text(e["file"])
            if re.search(r"\$\s?\d", t) and re.search(r"GPU|H100|H200|B200|MI300|A100|L40|hour|/hr|per hr", t, re.I):
                add(eid, "surface", "access", "meets", "self_serve_pricing_page", detail="pricing page with dollar figures, %s" % e["url"])
                add(eid, "surface", "transparency", "meets", "pricing_public", detail=e["url"])
                surf["pricing_public"] = eid
        elif k.startswith("docs"):
            add(eid, "surface", "transparency", "meets", "docs_public", detail=e["url"])
            surf["docs_public"] = surf["docs_public"] or eid
        elif k.startswith("trust") or k == "security":
            t = html_text(e["file"])
            toks = NAME_TOKENS.get(slug) or [slug, (hdr.get("provider") or "").lower().split("/")[0].strip()]
            if not any(tok and tok in t.lower() for tok in toks):
                continue                        # template of another company, or generic
            add(eid, "surface", "security", "meets", "trust_page_present", detail=e["url"])
            surf["trust_page"] = eid
            for m in re.finditer(r"SOC ?2 Type (?:I{1,2}|1|2)|SOC ?2 (?:compliance|compliant|certified|certification|report|attestation|audit)|ISO ?/?(?:IEC )?27001", t, re.I):
                ctx = t[max(0, m.start() - 80):m.end() + 80]
                if re.search(r"in progress|working (?:toward|on)|pursuing|planned|roadmap|coming soon|will (?:be|obtain|achieve)|preparing|pending|expect|journey|achieving", ctx, re.I):
                    continue
                wide = t[max(0, m.start() - 150):m.end() + 150]
                if re.search(r"vendors?|suppliers?|facilities|colocation|data center provider|international standard|underlying|involves|requiring|Digital Realty|GDPR, HIPAA", wide, re.I):
                    continue                    # a policy for others, an explainer, or a facility's certificate: not the provider's own attestation
                add(eid, "surface", "security", "meets", "attestation_mentioned_on_provider_page",
                    detail="%s :: ...%s..." % (e["url"], ctx.strip()[:160]))
                surf["attest_mentioned"] = eid
                break

    # ---- campaign listing rows (public pricing pages)
    crows = inp.get("campaign", {}).get(slug, [])
    if crows:
        ss = collections.Counter(r.get("self_serve") for r in crows)
        eid = "listing:%s" % crows[0]["provider_id"]
        urls = sorted({r["source_url"] for r in crows if r.get("source_url")})[:3]
        det = "campaign listing rows n=%d self_serve=%s sources=%s" % (len(crows), dict(ss), urls)
        if ss.get("sales") and not ss.get("yes"):
            add(eid, "campaign_public_listing", "access", "short", "sales_call_only", detail=det)
        elif ss.get("yes"):
            add(eid, "campaign_public_listing", "access", "meets", "self_serve_listed", detail=det)
        else:
            add(eid, "campaign_public_listing", "access", "neutral", None, detail=det)
        if any(r.get("rate_usd_per_gpu_hour") is not None for r in crows):
            add(eid, "campaign_public_listing", "transparency", "meets", "pricing_public", detail=det)

    # ---- status page / incidents
    sname = STATUS_NAME.get(slug)
    sp = (inp.get("status_pages") or {}).get(sname) if sname else None
    inc = (inp.get("incidents") or {}).get(slug)
    status_state = "unknown"           # none | present | unknown
    status_api = None
    if sp:
        plat = (sp.get("platform") or "").lower()
        if plat.startswith("none") or plat.startswith("trust-center") or plat.startswith("statiq (dead"):
            status_state = "none"
        elif plat.startswith("unknown"):
            status_state = "unknown"
        else:
            status_state = "present"
            status_api = sp.get("api_summary_ok")
    # manifest JSON status API overrides an older 'none' finding
    for e in inp.get("manifest", {}).get(slug, []):
        if e["kind"].startswith("status") and e["http"] == 200 and e["file"] and str(e["file"]).endswith(".json"):
            try:
                d = jload(e["file"])
                if isinstance(d, dict) and d.get("incidents"):
                    status_state, status_api = "present", True
                    add("surf:%s:%s" % (slug, Path(e["file"]).name), "surface", "transparency", "meets", "status_api_json",
                        detail=e["url"])
            except (OSError, ValueError):
                pass
    if inc is not None and status_state != "present":
        status_state = "present"
    if sp:
        eid = "status:%s" % sname
        if status_state == "none":
            det = "status-pages.json platform=%r (retrieved %s)" % (sp.get("platform"), "2026-09-23")
            add(eid, "status", "reliability", "short", "no_status_history", detail=det)
            add(eid, "status", "transparency", "short", "no_status_history", detail=det)
            for e in inp.get("manifest", {}).get(slug, []):
                if e["kind"].startswith("status") and (e["http"] in (0, 404) or e["curl_error"]):
                    add("surf:%s:%s" % (slug, Path(e["file"]).name if e["file"] else e["kind"]), "surface", "reliability",
                        "short", "no_status_history", detail="status URL %s http=%s %s" % (e["url"], e["http"], e["curl_error"] or ""))
        elif status_state == "present":
            add(eid, "status", "reliability", "neutral", None, detail="platform=%s api_summary_ok=%s" % (sp.get("platform"), sp.get("api_summary_ok")))
            if status_api:
                add(eid, "status", "transparency", "meets", "status_api", detail="platform=%s" % sp.get("platform"))
            else:
                add(eid, "status", "transparency", "neutral", None, detail="platform=%s api_summary_ok=%s (non-Atlassian probe failure is not proof of no API)" % (sp.get("platform"), sp.get("api_summary_ok")))
        else:
            add(eid, "status", "reliability", "neutral", None, detail="status page platform unknown: %s" % sp.get("platform"))

    inc_facts = {}
    if inc is not None:
        eid = "incident:%s" % INCIDENT_FILE[slug]
        incs = [i for i in inc.get("incidents", []) if not i.get("is_maintenance")]
        we = dt.date.fromisoformat(inc.get("coverage_end") or AS_OF)
        ws = we - dt.timedelta(days=WINDOW_DAYS)

        def d_of(i):
            return dt.date.fromisoformat(i["started_utc"][:10])
        inwin = [i for i in incs if ws <= d_of(i) <= we]
        oldest = min((d_of(i) for i in incs), default=None)
        cs = inc.get("coverage_start")
        covered = bool((cs and dt.date.fromisoformat(cs) <= ws) or (oldest and oldest <= ws))
        sev = collections.Counter(i.get("severity") for i in inwin)
        inc_facts = {"window_start": ws.isoformat(), "window_end": we.isoformat(), "incidents_total_all": len(incs),
                     "incidents_in_window": len(inwin), "major_critical_in_window": sev.get("major", 0) + sev.get("critical", 0),
                     "critical_in_window": sev.get("critical", 0), "major_in_window": sev.get("major", 0),
                     "minor_in_window": sev.get("minor", 0), "severity_none_in_window": sev.get("none", 0),
                     "window_covered": covered, "coverage_start": cs, "coverage_end": inc.get("coverage_end"),
                     "no_incidents_reported_unverifiable": len(incs) == 0,
                     "severity_unclassified": bool(inwin) and sev.get("none", 0) == len(inwin)}
        add(eid, "incident", "reliability", "neutral", None,
            detail="%s incidents in window (major/critical %d); coverage %s..%s" % (
                len(inwin), inc_facts["major_critical_in_window"], cs, inc.get("coverage_end")))
        add(eid, "incident", "transparency", "meets", "status_history_reachable", detail="incident file present") if inc_facts["window_covered"] else None

    # ---- price
    price = inp.get("price") or {}
    pkey = PRICE_KEY.get(slug)
    pos = price_position(price, pkey) if pkey else None
    price_facts = {}
    if pos:
        gpu, med, pct, n, ent = pos
        eid = "price:%s:%s:2026-07" % (pkey, gpu)
        price_facts = {"gpu": gpu, "july_median_usd_gpu_hr": med, "percentile_in_market": None if pct is None else round(pct, 1),
                       "market_providers": n, "thin_market": n < 10, "rows_kept": ent["rows_kept"], "rows_dropped_artefact": ent["rows_dropped_artefact"],
                       "source": "OpenComputePrices on_demand, July 2026, provider-median"}
        lst = sorted({r["rate_usd_per_gpu_hour"] for r in crows if r.get("gpu") == gpu and r.get("rate_usd_per_gpu_hour") is not None})
        if lst:
            price_facts["public_listing_rates_usd_gpu_hr"] = lst
            price_facts["listing_disagrees_with_feed"] = bool(med and (max(lst) > 1.25 * med or min(lst) < med / 1.25))
        if pct is not None and pct > PRICE_BAND_PERCENTILE:
            add(eid, "price", "pricing", "short", "above_price_band",
                detail="%s median $%.2f/GPU-hr = P%.0f of %d providers (band <= P%d)" % (gpu, med, pct, n, PRICE_BAND_PERCENTILE))
        elif pct is not None:
            add(eid, "price", "pricing", "meets", "in_price_band",
                detail="%s median $%.2f/GPU-hr = P%.0f of %d providers" % (gpu, med, pct, n))
    # ---- synthesis
    dims = {d: new_dim() for d in DIMENSIONS}
    for d in DIMENSIONS:
        items = dimev[d]
        ids = []
        for eid, _p, _l in items:
            if eid not in ids:
                ids.append(eid)
        dims[d]["evidence_ids"] = ids
        dims[d]["evidence_count"] = len(ids)

    def shortfalls(d):
        by = collections.OrderedDict()
        for eid, pol, lab in dimev[d]:
            if pol == "short" and lab:
                by.setdefault(lab, [])
                if eid not in by[lab]:
                    by[lab].append(eid)
        return by

    # access
    D = dims["access"]
    sf = shortfalls("access")
    pos_e = [e for e, p, _ in dimev["access"] if p == "meets"]
    D["facts"] = {"self_serve_pricing_surface": surf["pricing_public"], "positive_ids": pos_e}
    # security: attestation supersession (newer self-stated surface mention beats older review "no attestation")
    D2 = dims["security"]
    sf2 = shortfalls("security")
    D2["facts"] = {"attestation_evidence_ids": [e for e, p, l in dimev["security"] if p == "meets" and l in ("attestation_held", "attestation_mentioned_on_provider_page")],
                   "trust_page": surf["trust_page"]}
    if "no_soc2" in sf2 and surf["attest_mentioned"]:
        D2["superseded"].append({"label": "no_soc2", "evidence_ids": sf2.pop("no_soc2"),
                                 "superseded_by": surf["attest_mentioned"],
                                 "why": "review dated 2025-11-06; provider's own trust page (fetched %s) states an attestation; self-stated, not independently verified" % AS_OF})
    # reliability
    D3 = dims["reliability"]
    sf3 = shortfalls("reliability")
    D3["facts"] = {"status_state": status_state, "status_api": status_api, "incident_file": INCIDENT_FILE.get(slug) if inc is not None else None, **inc_facts}
    # pricing
    D4 = dims["pricing"]
    sf4 = shortfalls("pricing")
    D4["facts"] = price_facts
    # transparency facets
    D5 = dims["transparency"]
    sf5 = shortfalls("transparency")
    if "undisclosed_provider" in sf4:          # facet reference; same claim ids (not a new fact)
        sf5["undisclosed_provider"] = list(sf4["undisclosed_provider"])
        for eid in sf4["undisclosed_provider"]:
            if eid not in D5["evidence_ids"]:
                D5["evidence_ids"].append(eid)
        D5["evidence_count"] = len(D5["evidence_ids"])
    tp = [p for _, p, _l in dimev["transparency"] if p == "meets"]
    labs_t = {l for _, p, l in dimev["transparency"] if p == "meets"}
    D5["facts"] = {"status_api": bool(status_api) if status_state == "present" else None if status_state == "unknown" else False,
                   "pricing_public": ("pricing_public" in labs_t) or None,
                   "docs_public": ("docs_public" in labs_t) or None,
                   "provider_disclosed": True if "provider_disclosed" in labs_t else (False if "undisclosed_provider" in sf5 else None),
                   "note": "facets overlap access/reliability/pricing; see distance_excluding_transparency"}

    # delivery
    D6 = dims["delivery"]
    sf6 = shortfalls("delivery")
    pos6 = [e for e, p, _ in dimev["delivery"] if p == "meets"]
    neg6 = [e for e, p, _ in dimev["delivery"] if p == "neg_unlabeled"]
    D6["facts"] = {"praise_ids": pos6, "criticism_unlabeled_ids": neg6,
                   "topic_counts": {"criticism": sum(1 for eid in D6["evidence_ids"] if claim_by_id.get(eid, {}).get("topic") == "criticism"),
                                    "praise": sum(1 for eid in D6["evidence_ids"] if claim_by_id.get(eid, {}).get("topic") == "praise")}}

    def finish(D, sfd, meets_ok, unknown_note=None):
        if sfd:
            D["status"] = "SHORT"
            D["shortfalls"] = [{"label": l, "evidence_ids": ids,
                                "initial_marked_ids": [i for i in ids if INITIAL.search(ev.get(i, {}).get("quote", ""))]}
                               for l, ids in sfd.items()]
        elif meets_ok:
            D["status"] = "MEETS"
        else:
            D["status"] = "UNKNOWN"
            D["note"] = unknown_note

    finish(dims["access"], sf, bool(pos_e), "no positive access evidence and no shortfall" if not pos_e else None)
    finish(dims["delivery"], sf6, bool(pos6) and len(neg6) < len(pos6),
           "mixed: %d unlabeled criticism vs %d praise" % (len(neg6), len(pos6)) if pos6 and len(neg6) >= len(pos6) else "no praise-side delivery evidence")
    att_pos = [e for e, p, l in dimev["security"] if p == "meets" and l in ("attestation_held", "attestation_mentioned_on_provider_page")]
    finish(dims["security"], sf2, bool(att_pos), "no attestation evidence held or refuted" if not att_pos else None)
    # reliability
    if sf3:
        finish(dims["reliability"], sf3, False)
    else:
        ok = bool(inc is not None and inc_facts.get("window_covered") and not inc_facts.get("no_incidents_reported_unverifiable")
                  and inc_facts.get("incidents_in_window", 0) > 0 and not inc_facts.get("severity_unclassified"))
        note = None
        if inc is not None and inc_facts.get("no_incidents_reported_unverifiable"):
            note = "no incidents reported; unverifiable (an empty page does not show absence of outages)"
        elif inc is not None and not inc_facts.get("window_covered"):
            note = "history does not demonstrably cover the 180-day window; counts are lower bounds"
        elif inc is not None and inc_facts.get("severity_unclassified"):
            note = "incidents carry no severity; major/critical count not derivable"
        elif inc is None:
            note = "no incident history captured"
        finish(dims["reliability"], sf3, ok, note)
    # pricing
    pct = price_facts.get("percentile_in_market")
    pm = any(p == "meets" and l == "in_price_band" for _, p, l in dimev["pricing"])
    price_praise = any(l == "price_praise" for _, p, l in dimev["pricing"])
    finish(dims["pricing"], sf4, pm or (pct is None and price_praise),
           "no price percentile (fewer than %d July on-demand rows or not in feed)" % MIN_PRICE_ROWS)
    # transparency
    f = D5["facts"]
    pos_count = sum(1 for k in ("status_api", "pricing_public", "docs_public", "provider_disclosed") if f.get(k) is True)
    neg_any = bool(sf5)
    finish(dims["transparency"], sf5, pos_count >= 3 and not neg_any, "%d of 4 transparency facets positive" % pos_count)

    # evidence records for output
    all_ids = []
    for d in DIMENSIONS:
        for eid in dims[d]["evidence_ids"]:
            if eid not in all_ids:
                all_ids.append(eid)
    evidence = []
    for eid in all_ids:
        rec = ev.get(eid)
        if rec is None:
            continue
        evidence.append(rec)
    n_short = sum(1 for d in DIMENSIONS if dims[d]["status"] == "SHORT")
    n_unknown = sum(1 for d in DIMENSIONS if dims[d]["status"] == "UNKNOWN")
    short_labels = sorted({s["label"] for d in DIMENSIONS for s in dims[d]["shortfalls"]})
    n_short_core = sum(1 for d in DIMENSIONS if d != "transparency" and dims[d]["status"] == "SHORT")
    row = {
        "slug": slug,
        "provider": hdr.get("provider") or slug,
        "as_of": AS_OF,
        "method": METHOD_VERSION,
        "evidence_count": len(evidence),
        "claims_on_review_page": len(claims),
        "distance_to_floor": n_short,
        "unknown_count": n_unknown,
        "distance_excluding_transparency": n_short_core,
        "short_dimensions": [d for d in DIMENSIONS if dims[d]["status"] == "SHORT"],
        "unknown_dimensions": [d for d in DIMENSIONS if dims[d]["status"] == "UNKNOWN"],
        "short_labels": short_labels,
        "dimensions": dims,
        "imported_context": {
            "clustermax_2_0_page_tier": tier.get("tier") or hdr.get("tier_on_page"),
            "clustermax_3_0_medal": tier.get("tier_3_0"),
            "note": "imported context; never an input to any dimension score",
        },
        "evidence_public_only": all(e["kind"] in PUBLIC_KINDS for e in evidence),
        "evidence": evidence,
    }
    if slug in DISCLOSURES:
        row["disclosure"] = DISCLOSURES[slug]
    return row


# ---------------------------------------------------------------- driver
def sort_key(r):
    return (r["distance_to_floor"], r["unknown_count"], r["provider"].lower())


def run(refresh_prices=False, out=HERE):
    inp = load_inputs()
    if refresh_prices:
        inp["price"] = load_prices(refresh=True)
    inp["manifest"] = {s: manifest_entries(s) for s in inp["headers"]}
    rows = [rate_provider(s, inp) for s in sorted(inp["headers"])]
    rows.sort(key=sort_key)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "RATINGS.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n")
    (out / "RATINGS.md").write_text(render_md(rows, inp), encoding="utf-8", newline="\n")
    return rows


MEDAL_ORDER = ["Platinum", "Gold", "Silver", "Bronze", "Participation Ribbon", "Underperforming", "Unavailable", "NOT IN 3.0 TABLE"]


def contingency(rows, filt=None):
    tab = {m: collections.Counter() for m in MEDAL_ORDER}
    for r in rows:
        if filt and not filt(r):
            continue
        m = r["imported_context"]["clustermax_3_0_medal"]
        tab.setdefault(m, collections.Counter())[r["distance_to_floor"]] += 1
    return tab


def md_contingency(tab):
    ds = list(range(0, 7))
    lines = ["| 3.0 medal | " + " | ".join("d=%d" % d for d in ds) + " | n | mean d |", "|---|" + "---|" * (len(ds) + 2)]
    for m in MEDAL_ORDER:
        c = tab.get(m, collections.Counter())
        n = sum(c.values())
        mean = "%.2f" % (sum(d * k for d, k in c.items()) / n) if n else "-"
        lines.append("| %s | " % m + " | ".join(str(c.get(d, 0)) for d in ds) + " | %d | %s |" % (n, mean))
    return "\n".join(lines)


def short_cell(d):
    return {"MEETS": "M", "SHORT": "**S**", "UNKNOWN": "?"}[d]


def render_md(rows, inp):
    L = []
    w = L.append
    w("# RATINGS: desk-tier rating of ClusterMAX-reviewed providers against the floor")
    w("")
    w("As of %s. Method `%s`. %d providers. Generated by `rate.py`; row-level evidence is in `RATINGS.jsonl`." % (AS_OF, METHOD_VERSION, len(rows)))
    w("")
    w("## How to read this")
    w("")
    w("- Each of six dimensions is **M**EETS, **S**HORT or **?** (UNKNOWN). `distance` = number of SHORT dimensions (0 to 6). `unk` = number of UNKNOWN dimensions, reported separately and never counted as SHORT. A row with distance 0 and many `?` is a thin row, not a passing row.")
    w("- `ev` = distinct evidence items behind the row (review sentences that bore on a dimension, provider surfaces, status/incident files, price rows). `claims` = all sentences on the review page. Rows with `ev` under 3 are marked with `†`.")
    w("- Sorted by distance ascending, then unknown ascending, then name. The top of the table is nearest the floor with the fewest gaps in evidence; a distance-0 row near the bottom of its group is mostly unknown.")
    w("- The ClusterMAX 2.0 page tier and 3.0 medal columns are imported context only. No score reads them.")
    w("- Review sentences are ClusterMAX 2.0 text (published 2025-11-06, 4 pages carry an April 2026 update). Provider surfaces were fetched 2026-09-29, status/incident files 2026-09-23 to 2026-09-29, prices are July 2026. Where a newer self-stated provider surface conflicts with an older review sentence, the row shows the review sentence under `superseded`; the surface statement is self-stated, not independently verified.")
    w("- A SHORT names a documented shortfall label and its evidence ids. It is a desk finding, not a verdict about cause, and does not replace the per-shop counter (`hot-aisle/campaign/shop-eval/counter`) or the diagnose rubric: those measure a machine, this reads documents.")
    w("- Failure of the reviewers to obtain test access is recorded as evidence but is not scored SHORT (it mixes provider friction with reviewer scope). Scored access shortfalls are `sales_call_only`, `access_weeks`, `account_gate`.")
    w("- `floor.json` item ids are bound afterwards (`FLOOR_BINDING` in `rate.py`; every label currently maps to none).")
    w("")
    w("### Dimensions and rules")
    w("")
    w("| dimension | SHORT when | MEETS when | labels |")
    w("|---|---|---|---|")
    w("| access | a review sentence shows a form/phone/invitation-only path, a KYC/quota/approval gate, or a wait of weeks; or a campaign listing row says sales-only with no self-serve row | a self-serve pricing page with dollar figures was fetched, or the campaign listing marks self-serve, or a positive access sentence; and no SHORT | sales_call_only, access_weeks, account_gate |")
    w("| delivery | a review sentence says health checks, monitoring, shared storage are absent, or Slurm/K8s is absent or did not work | at least one positive sentence on Slurm/K8s/health/monitoring/storage/network, more praise than unlabeled criticism, no SHORT | no_health_checks, no_monitoring, no_shared_storage, slurm_k8s_not_working, no_slurm_k8s_offering |")
    w("| security | review says no SOC 2/ISO attestation (unless superseded by the provider's own newer trust page), old driver/toolkit/CVE, no RBAC/SSO, or tenant-isolation gap | attestation held per review or self-stated on a provider trust page that names the provider; no SHORT | no_soc2, old_driver_cve, no_rbac, tenant_isolation_gap |")
    w("| reliability | no public status page (status-pages.json platform none, trust-center only, or dead) or reviewer-reported reliability complaints | incident history demonstrably covers the 180-day window, it has non-maintenance incidents with severities, and no SHORT. Zero incidents = unverifiable, UNKNOWN. Counts of major/critical incidents per 180 days are reported, no threshold is set | no_status_history, reliability_complaints |")
    w("| pricing | July 2026 on-demand median for H100 (else MI300X) above P%d of the market's provider medians; billing during outage; undisclosed underlying provider | median at or below P%d (or, with no percentile, a positive price sentence); no SHORT | above_price_band, billing_during_outage, undisclosed_provider |" % (PRICE_BAND_PERCENTILE, PRICE_BAND_PERCENTILE))
    w("| transparency | a facet is affirmatively negative: no public status page, undisclosed provider | at least 3 of 4 facets positive (status API, pricing public, provider disclosed, docs public) and none negative | mirrors labels above |")
    w("")
    w("Transparency facets repeat facts already scored under access, reliability and pricing, as specified. `distance_excluding_transparency` (in the jsonl) removes that overlap.")
    w("")
    w("Price notes: source is OpenComputePrices `latest-data` (2026-07-29), on-demand, per provider median, providers with at least %d July rows. July rows above %.0fx a provider's own June median were dropped as scraper artefacts (for example a $100.00 H100 row for one provider); dropped counts are in each row." % (MIN_PRICE_ROWS, ARTEFACT_FACTOR))
    w("")
    w("## Table")
    w("")
    hdr = "| # | provider | dist | unk | ev | claims | acc | del | sec | rel | prc | trn | SHORT labels | 2.0 page | 3.0 medal |"
    w(hdr)
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        d = r["dimensions"]
        thin = "†" if r["evidence_count"] < 3 else ""
        w("| %d | %s%s | %d | %d | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            i, r["provider"], thin, r["distance_to_floor"], r["unknown_count"], r["evidence_count"], r["claims_on_review_page"],
            *[short_cell(d[x]["status"]) for x in DIMENSIONS],
            ", ".join(r["short_labels"]) or "-", r["imported_context"]["clustermax_2_0_page_tier"],
            r["imported_context"]["clustermax_3_0_medal"]))
    w("")
    w("† evidence_count under 3.")
    w("")
    w("## Per-provider blocks")
    w("")
    for r in rows:
        w("### %s (`%s`)" % (r["provider"], r["slug"]))
        w("")
        w("distance %d, unknown %d, evidence %d (of %d review sentences). 2.0 page: %s. 3.0 medal: %s." % (
            r["distance_to_floor"], r["unknown_count"], r["evidence_count"], r["claims_on_review_page"],
            r["imported_context"]["clustermax_2_0_page_tier"], r["imported_context"]["clustermax_3_0_medal"]))
        if r.get("disclosure"):
            w("")
            w("**Disclosure.** " + r["disclosure"])
        w("")
        any_short = False
        for dname in DIMENSIONS:
            D = r["dimensions"][dname]
            for s in D["shortfalls"]:
                any_short = True
                w("- SHORT %s / `%s`: %s" % (dname, s["label"], ", ".join("`%s`" % x for x in s["evidence_ids"])))
            for s in D["superseded"]:
                w("- superseded %s / `%s`: %s replaced by %s. %s" % (dname, s["label"], ", ".join("`%s`" % x for x in s["evidence_ids"]), "`%s`" % s["superseded_by"], s["why"]))
        if not any_short:
            w("- No SHORT dimension.")
        unk = []
        for dname in r["unknown_dimensions"]:
            n = r["dimensions"][dname]["note"]
            unk.append("%s%s" % (dname, " (%s)" % n if n else ""))
        if unk:
            w("- UNKNOWN: " + "; ".join(unk))
        rel = r["dimensions"]["reliability"]["facts"]
        if rel.get("incident_file"):
            w("- Reliability facts: %s incidents in %s..%s, major/critical %s, window covered %s%s." % (
                rel.get("incidents_in_window"), rel.get("window_start"), rel.get("window_end"), rel.get("major_critical_in_window"),
                rel.get("window_covered"), ", no incidents reported: unverifiable" if rel.get("no_incidents_reported_unverifiable") else ""))
        pf = r["dimensions"]["pricing"]["facts"]
        if pf.get("gpu"):
            w("- Price: %s July 2026 on-demand median $%.2f/GPU-hr, P%s of %d providers." % (pf["gpu"], pf["july_median_usd_gpu_hr"], pf["percentile_in_market"], pf["market_providers"]))
        w("")
    w("## Distance to floor against the 3.0 medal")
    w("")
    w("Description only. The 3.0 medal was published 2026-09-23 from a paywalled methodology; this rating is a desk reading of 2025-11 review text plus 2026 public surfaces. The two are not independent samples of one construct, the desk tier has unscored UNKNOWNs, and rows differ widely in evidence. Nothing below validates either measure.")
    w("")
    w("All %d providers (columns = distance to floor, counts of providers):" % len(rows))
    w("")
    w(md_contingency(contingency(rows)))
    w("")
    w("Providers with evidence_count of at least 5 and at most 2 UNKNOWN dimensions:")
    w("")
    w(md_contingency(contingency(rows, lambda r: r["evidence_count"] >= 5 and r["unknown_count"] <= 2)))
    w("")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-prices", action="store_true", help="re-stream the 954 MB price feed")
    ap.add_argument("--out", default=str(HERE))
    a = ap.parse_args(argv)
    rows = run(refresh_prices=a.refresh_prices, out=a.out)
    print("rows:", len(rows), "out:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
