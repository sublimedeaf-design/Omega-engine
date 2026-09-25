# OMEGA failproof control plane

This directory contains one provider-neutral reconcile engine and thin adapters for GitHub-hosted control, Cloudflare Workers, Deno Deploy, and Render cron jobs.

The engine has deliberately narrow authority. It can read the private main SHA, existing validation statuses and compare metadata; move only `omega-external-validation` and `omega-external-validation-android`; publish `omega/control-plane/ref-sync`; and append non-sensitive dispatch timestamps to public helper issue #2. It cannot merge, release, sign, mutate main, change models, or publish predictive evidence.

Required secret: `OMEGA_GITHUB_TOKEN`, stored in the provider secret manager, never source control. Each deployment should use its own minimally scoped credential. Optional authenticated manual reconcile endpoints use a separate `OMEGA_CONTROL_KEY`.

Global policy is shared across providers: 15-minute stable-head delay, 15-minute dispatch cooldown, at most 2 external dispatches per rolling 24 hours and 6 per rolling 30 days. The public ledger makes these limits global instead of provider-local.

Cloudflare: deploy this directory with `wrangler.toml`; configure both secrets in Workers secrets. Deno: deploy `deno.ts` and configure secrets in project environment variables. Render: run `node control-plane/render.mjs` from a scheduled service with the token in Render environment variables.

A provider deployment is not counted as live until it has reconciled a current exact SHA and produced an attributable status/ledger entry.
