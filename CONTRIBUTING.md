# Contributing to RetailOps

This repository uses a lightweight, PR-based workflow for the six-person team.

## Branches

- `main`: stable release baseline. Do not push directly.
- `develop`: integration branch and GitHub default branch. Do not push directly.
- `feature/<task-slug>`, `fix/<task-slug>`, `chore/<task-slug>`: short-lived working branches, created from current `develop`.

Create a working branch:

```powershell
git fetch origin
git switch develop
git pull --ff-only origin develop
git switch -c feature/<task-slug>
```

Do not develop new work on an already merged feature branch.

## Pull requests

1. Make scoped changes based on the approved SRS and assigned task.
2. Run relevant local tests; disclose any checks not run.
3. Push the working branch; open a PR into `develop`.
4. Wait for CI to pass and obtain a review before merge.
5. The Tech Lead coordinates merges. Use a merge commit when preserving meaningful task commits is useful; otherwise squash is acceptable.
6. Delete short-lived remote branches after merging when no longer needed.

A green CI run is a minimum gate, not proof that every requirement or security property is correct. Review authentication/authorization, SQL safety, transaction boundaries, concurrency, idempotency, migrations, and untrusted AI tool inputs according to the change.

Never commit `.env`, secrets, production credentials, real customer data, or generated local databases.

## Release to main

Open a PR `develop` -> `main` only when the complete target commit is suitable for a stable release. This is **not** required at the end of every Sprint.

Before release, verify scope and approved requirements, CI, end-to-end behavior, security and data integrity, migration safety, and deployment/rollback readiness. Tag the release on `main` only after merging and validating it. Do not merge `develop` merely because one completed feature is working while other merged work is unstable.

## Enforcement and platform limitations

Apply branch rulesets for `main` and `develop` when the GitHub plan supports enforcing them on this private repository. Prefer required PRs, one review from another team member, and required `Backend / Ruff + unit` and `Backend / MySQL integration` checks when applicable.

Until rulesets are verified as enforced, the above are team conventions, not technical controls. Repository owners must monitor direct pushes. Avoid requiring backend-only checks for frontend-only PRs until CI coverage is broadened or path-aware checks are deliberately implemented.
