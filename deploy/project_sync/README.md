# Gavrik project maintenance update

Shared registry loader and singleton maintenance worker. Current Windows installation is independent of GitHub permissions: it reports project state and preserves dirty worktrees. Remote auto-merge is request-driven, restricted to configured repositories, requires a full commit SHA, nonempty successful CI checks and native GitHub merge rules. Failed, skipped, missing and stale-head checks block execution. No deployment command is executed by this worker version.

Run tests:
python -m unittest discover -s tests -v

The registry, account authentication and release deployment scope are configured on each host. Do not commit .env, tokens, sessions, client files or runtime databases. The Windows registry loader defaults to C:/Users/HP/gavrik/support/project-sync/projects.json; GAVRIK_PROJECTS_FILE overrides it. A Unix host resolves support/project-sync relative to its bot root.

CI workflow is provided as a template only. GitHub Workflows permission and the owner's workflow approval are still outstanding. Native repository auto-merge is currently disabled. CLI GitHub authentication failed in the Codex sandbox; it was subsequently verified successfully under the actual HP service account. Until these dependencies are resolved, reports explicitly mark remote actions blocked.

Current scope: catalogue coordination and gated auto-merge requests. Full server deployment, release upload, and cross-host synchronization have not been verified.
