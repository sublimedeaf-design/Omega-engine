# OMEGA external generation pulse

This is a **liveness transport only**. It has no source, evidence, signing, release,
or distribution authority.

## Why it exists

The canonical generation state machine is
`.github/workflows/omega-generation-reconciler.yml`. GitHub schedules are a
fallback, not the sole wake authority. A tiny Cloudflare Worker can independently
dispatch that reconciler every five minutes. QStash can call the same Worker every
ten minutes with bounded retries, providing an independent durable delivery path.

The Worker never receives `OMEGA_BOOTSTRAP_TOKEN`, the Android keystore, or any
private-repository credential. It only holds a fine-grained token scoped to
`sublimedeaf-design/Omega-engine` with the minimum permissions needed to read
workflow-run state and dispatch the Generation Reconciler.

## Required Worker secrets

- `OMEGA_CONTROL_DISPATCH_TOKEN`: fine-grained GitHub token for the public
  control repository only; Actions read/write and repository metadata/read are
  sufficient.
- `OMEGA_CONTROL_KEY`: random bearer secret used only to authenticate the
  external `POST /pulse` endpoint.

Health is public at `GET /healthz`; pulse is accepted only at `POST /pulse`.

## Cloudflare cadence

`wrangler.toml` configures `*/5 * * * *`. The Worker performs only bounded
GitHub API I/O and deduplicates queued/in-progress Generation Reconciler runs.

## QStash backstop

Configure these locally or in a secret-bearing deployment runner:

- `QSTASH_TOKEN`
- `OMEGA_PULSE_URL=https://<worker>.workers.dev/pulse`
- `OMEGA_CONTROL_KEY`
- optional `QSTASH_URL` (defaults to the EU/global QStash endpoint)

Then run:

```bash
bash bootstrap/omega/qstash/create-schedule.sh
```

The fixed schedule id `omega-generation-pulse-v1` makes the operation
idempotent: re-running it updates the existing schedule. Default cadence is ten
minutes with three retries. At 144 scheduled deliveries/day, even complete
three-retry failure consumes at most 576 delivery attempts/day, below the
current QStash Free allowance of 1,000 messages/day.

## Authority invariant

```text
QStash / Cloudflare
        ↓
wake or dispatch only
        ↓
OMEGA Generation Reconciler
        ↓
existing exact-SHA / epoch / signer / evidence authorities
```

External pulse infrastructure may improve liveness but may never certify PASS,
change the canonical signer, promote evidence, or release an APK.
