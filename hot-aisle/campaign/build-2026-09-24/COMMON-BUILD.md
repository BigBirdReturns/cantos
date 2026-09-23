# Common rules for Run 3 build lanes (2026-09-23 night)

Ignore AGENTS.md, front-door, N01 and estate instructions under D:\. They do not apply here.

- Repo: `D:\Projects\Organs\AXM\axm-tools\main` (git).
- Campaign dir: `hot-aisle\campaign\`.

## Read first

1. `hot-aisle\campaign\research-2026-09\SYNTHESIS.md`: the design authority. Read the Correction and North star sections too.
2. `DISCLOSURES.md`.
3. `run2\PREREG.md` and `arm2.sh`: house style for kits.
4. `results\`: real cell files.
5. `engine_table.cjs`: how the page engine is loaded.
6. The repo root `CLAUDE.md`: the quirks ledger, especially the "First campaign, field facts" section.

## Hard rules

- Write ONLY inside your lane's directory. Do not edit anything else. Do NOT git commit, push or branch.
- Do not provision, rent, buy, ssh, call provider APIs with real credentials, or contact anyone. Use the network only to read docs, and only if your lane allows it.
- Repo convention: Python is stdlib-only, and Node scripts are dependency-free. Something that must run on a GPU or CPU seat (vLLM containers, the EvalPlus grader) may install inside a container on that seat, declared in a shell script. Never add dependencies to the repo.
- Every script gets:
  - a self-test that runs offline on fixtures kept under your dir
  - a README section saying exactly how to run it

  Run your tests and report pass or fail honestly.
- Pin identities (model revision, image digests) the way run2 does. Mark anything you could not verify as UNVERIFIED in the file.
- Nothing here asserts results. Build kits and schemas only.
- When done, write `<lane-dir>/BUILD-REPORT.md` covering:
  - files built
  - how to run them
  - test output summary
  - open questions
  - what the operator must supply (tokens, approvals)
