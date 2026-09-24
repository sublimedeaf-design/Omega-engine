# OMEGA public bootstrap control

This public repository contains no OMEGA private source, data or credentials.

The scheduled workflow only needs one Actions repository secret named
`OMEGA_BOOTSTRAP_TOKEN`. The token must be able to list/start the existing
Omega-engines Codespace, read the five private federation peers, write commit
statuses, and write the Omega-engines Codespaces repository secret.

After every wake attempt the workflow uses GitHub CLI to store the same value,
encrypted, as the private Omega-engines Codespaces secret
`OMEGA_FEDERATION_PAT`. This is the shortest bootstrap path; the token can be
split into separate least-privilege lifecycle/federation tokens after recovery. The script never creates, stops,
deletes or renames a Codespace and never prints credential material.

Target selection is deterministic: repository `sublimedeaf-design/Omega-engines`,
prefer ref `main`, then the most recently used existing Codespace. GitHub API
state is verified after any start request; a 409 is not treated as recovery proof
without a subsequent available/running state.


Secret activation verification is performed by the scheduled/push bootstrap workflow; no secret value is logged.

SSH recovery is provided by the devcontainer sshd feature; the normal bootstrap remains non-destructive and converges the existing Codespace to available before remote runner repair.
