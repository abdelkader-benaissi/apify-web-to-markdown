# Backup of abdou_009/apify-web-to-markdown before web2md replacement
- Taken: 2026-10-20 (before any replacement work)
- Live actor: id IRAJEB9NOAik6toOe, source type GIT_REPO (this repo), version 0.0, latest build 0.0.2 (buildId yIrFRf8YftpXIfu1f, finished 2026-10-13)
- Live pricing (from actor-live-2026-10-20.json pricingInfos): PAY_PER_EVENT —
  page-converted $0.003 (primary event, "Page converted"),
  apify-actor-start $0.00005, apify-default-dataset-item $0.00001.
  Platform usage paid by user; price-change notifications NOT suppressed.
- Input schema + README snapshotted alongside (input-schema.json, README-live.md, pricing-pay-per-event.json)
- Recent run inputs: only 2 runs are visible to the scoped run-only API token
  (both carry the schema-default input: urls="https://example.com" as a single
  newline-string, includeImages=true, maxChars=20000). Public stats show 7 runs
  in 30 days; the remaining runs (other users) are not readable with a
  restricted token — platform permission boundary, noted not worked around.
  The input SHAPE those runs prove: urls is a newline-separated STRING,
  includeImages boolean, maxChars integer. Backward-compat must accept it.
- This branch (legacy-v1) is committed locally; it has NOT been pushed to
  GitHub (push needs the owner's GitHub credentials).
