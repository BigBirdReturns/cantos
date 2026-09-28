# Independent Cantos qualification

Run from the repository root:

```
node research-desk/cantos/tests/native_contract.cjs
python -B research-desk/cantos/tests/seed_contract.py
node research-desk/cantos/tests/adversarial.cjs
python -B research-desk/cantos/build.py --out /path/to/candidate --check
python -B research-desk/cantos/tests/qualify.py --artifact /path/to/candidate/cantos.html --out /path/to/results
```

The browser harness uses the already-installed Python Playwright and Chromium. It starts an ephemeral loopback-only HTTP server, navigates actual URLs and file URIs, and shuts down the browser and server. It writes screenshots, a result with the tested HTML hash, and a sample exported packet containing explicitly labeled test reviews. Keep these outputs outside the source/distributable directory.

Native synthetic fixtures prove journal/accounting behavior only; seed tests check actual retained Run3 input identities. The browser journey uses the real final seed and UI. The adversarial test specifically catches failures occurring after native packet verification during construction of the bridge view; both journal and public view must remain intact. No GPU, generated-code grading, provider action, model, account or network service is invoked.

Passing checks do not authenticate reviewers or historical source claims. Qualification applies to tested artifact bytes; rebuild and rerun when product source changes.
