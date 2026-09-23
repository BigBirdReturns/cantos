# Availability ledger

One JSON line per observation of whether a provider would sell a given GPU SKU, in a given region, at a given moment. Every provisioning attempt the campaign makes writes here, including failures. This is the raw material for the availability heatmap: provider × SKU × region × hour. Nobody publishes this from the buyer's side.

Fields: `ts` (UTC), `provider`, `region`, `sku`, `gpus`, `method` (`console-plan-list` | `console-create` | `tui-provision-list` | `api` | `prior-session-note`), `outcome` (`available` | `out_of_capacity` | `out_of_stock` | `create_failed`), `provisioned`, and optional `count`, `time_to_ssh_s`, `note`.

Seeded 2026-09-23 from the first campaign. Times before 19:00 UTC are approximate to a few minutes. Probing on a schedule needs provider API tokens (DigitalOcean, Hot Aisle), which the operator holds. The admin TUI rate-limits repeated logins.
