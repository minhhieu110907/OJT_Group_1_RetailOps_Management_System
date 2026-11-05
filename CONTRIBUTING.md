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

## Commit message convention (required)

Every **new, manually authored commit** must follow Conventional Commits and
include a **real, traceable task ID**:

```text
<type>(<scope>): <short imperative description> [<TASK-ID>]
```

Examples:

```text
feat(frontend): initialize React and Axios integration [T3C98D1]
fix(inventory): prevent negative stock under concurrency [<assigned-task-id>]
test(sales): cover repeated cancellation requests [<assigned-task-id>]
ci(frontend): require lint and production build [<assigned-task-id>]
docs(git): document commit message policy [OPS-001]
```

- **Required types:** `feat`, `fix`, `refactor`, `test`, `docs`, `ci`,
  `chore`, or `perf`.
- **Scope:** use the affected module or area, such as `auth`, `product`,
  `inventory`, `sales`, `purchasing`, `frontend`, `backend`, `db`, or `git`.
- **Description:** short English imperative describing the change, not "update",
  "done", or "fix bug" without context.
- **Task ID:** use the exact identifier from the assigned learning/backlog task,
  such as `T3C98D1`. For internal maintenance, create and document a real
  team-tracked task ID first (e.g., `OPS-001` for this Git policy change).
  Never invent a course/task ID or reuse an unrelated ID just to pass review.
- If a task has not been assigned an ID, obtain or register one **before
  committing**. The requirement also applies to documentation, refactors, and CI.
- One commit may contain multiple logically related changes for the same task.
  Prefer small, scoped commits over mixing unrelated tasks.

Example command:

```powershell
git commit -m "feat(frontend): initialize React and Axios integration [T3C98D1]"
```

The PR title should also contain the relevant task ID. When squash-merging,
preserve it in the resulting commit title. For GitHub-generated merge commits,
record the task ID in the PR title and constituent authored commits; a
generated "Merge pull request #..." subject is not required to follow this
template. Older commits made before this policy are grandfathered.

**Review policy:** Reviewers should request corrections when new authored
commit messages lack a task ID. This is currently a documented team convention,
not an automatically enforced commitlint rule.

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
