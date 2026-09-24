# OMEGA public bootstrap control

This public repository contains no OMEGA private source, data or credentials.

The scheduled workflow only needs one repository secret named
`OMEGA_CODESPACE_LIFECYCLE_TOKEN`. The token must be able to list the user's
Codespaces and start an existing Codespace. The script never creates, stops,
deletes or renames a Codespace and never prints credential material.

Target selection is deterministic: repository `sublimedeaf-design/Omega-engines`,
prefer ref `main`, then the most recently used existing Codespace. GitHub API
state is verified after any start request; a 409 is not treated as recovery proof
without a subsequent available/running state.
