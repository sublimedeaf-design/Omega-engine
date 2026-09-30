# Archived OMEGA public control-plane workflows

The unified product authority is `sublimedeaf-design/Sublimej`.

All former OMEGA public control-plane workflows are archived here as donor/reference code.
They must not run as a parallel scheduler, release authority, signer authority, or Android
product pipeline.

The sole active workflow left under `.github/workflows/` is
`sublimej-external-apk-verifier.yml`. It is verifier-only: it may read the exact current
private SublimeJ source, run the canonical verifier/build, and publish evidence/status. It
does not own product source, release promotion, signing identity, or distribution.
