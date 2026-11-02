# Crash and timeout recovery

1. Confirm bridge health and inspect the actual open project and expected operator paths. A running TD process/listening port does not prove a responsive bridge.
2. Inspect checkpoint indexes, actual saved project paths, timestamps, and relevant manifests before opening a candidate or rebuilding. Multiple agents can share one TD instance; filenames do not prove isolation.
3. For ambiguous `.toe`/`.tox` artifacts, use `toeexpand` from the installed TD build to inspect contents in a separate temporary directory. Discover its installation path rather than hardcoding a version.
4. Preserve the reopened state with a new unused save or checkpoint before restoring. Restore only the intended scope, then inspect operators, errors, parameter values, and output.
5. Save the verified recovery to a new version and confirm its actual filename. Report what survived, what was restored, and anything still unverified.

A timeout may occur after a mutation completed. Inspect before retrying. Never restart the serving WebServer DAT from its own connection.
