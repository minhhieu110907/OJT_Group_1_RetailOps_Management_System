# RetailOps

## Local database and backend

Requirements: Docker Desktop with Compose, and `uv` for host-side tests.

1. Copy `.env.example` to `.env`.
2. Replace every `CHANGE_ME` value with independently generated local
   credentials. Do not reuse the example values or share a team-wide default.
   If the integration-test URL contains special password characters,
   URL-encode them.
3. Build and start MySQL and the backend:

   ```powershell
   docker compose up --build -d
   ```

MySQL is bound only to `127.0.0.1`; the backend is available at
`http://127.0.0.1:8000`. Compose waits for an authenticated MySQL `SELECT 1`
before starting the backend.

If port 3306 is already in use, change `MYSQL_HOST_PORT` in `.env` and change
the port in `RETAILOPS_TEST_DATABASE_URL` to the same value. For example, both
must use `13306`; changing only one leaves host-side tests pointed at the wrong
server.

MySQL initialization scripts run only when `/var/lib/mysql` is first created.
Changing `.env` later does not rotate existing MySQL passwords and does not
rerun the test-user provisioning script. For an existing verified local volume,
first confirm the Compose project and volume:

```powershell
docker volume inspect retailops_mysql_data --format '{{json .Labels}}'
docker compose ps
```

After confirming the volume belongs to the local `retailops` project, start
MySQL with the new environment and explicitly provision only the test user:

```powershell
docker compose up -d --wait mysql
docker compose exec `
  -e CONFIRM_RETAILOPS_LOCAL_PROVISIONING=retailops-local `
  mysql bash /usr/local/bin/provision-existing-test-user
```

This command requires the locally configured root credential at runtime; it is
not stored in source. It recreates only the dedicated test user and grants that
user schema-scoped test permissions. It also revokes any legacy development-user
grant on the test schema; it does not rotate the development user.

## Migrations

Apply reviewed migrations and inspect the current revision inside the backend
container:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

The Task 02 baseline creates only Alembic's version table. It does not create
RetailOps business tables.

MySQL DDL can cause implicit commits and Alembic reports it as
non-transactional. Every future business migration must be reviewed with an
explicit backup/recovery plan; do not assume a failed DDL migration rolls back
atomically.

Verify the entire migration chain on a uniquely named, temporary Compose
project and volume:

```powershell
.\scripts\verify-clean-migration.ps1
```

The script verifies the temporary volume's Compose project label before its
automatic cleanup. It never uses or resets the normal development/test volume.

## Tests

Task 01 unit/API tests do not require Docker or MySQL:

```powershell
cd backend
uv sync --locked
uv run pytest -m "not integration"
```

Integration tests require the dedicated database named by
`RETAILOPS_TEST_DATABASE_URL`. Start MySQL first, then run pytest with the root
`.env` loaded only for that process:

```powershell
cd backend
uv run dotenv -f ../.env run -- pytest -m integration
```

The integration suite accepts only `mysql+pymysql` URLs on `127.0.0.1` or
`localhost`, and requires exact matches for `MYSQL_TEST_DATABASE` and
`MYSQL_TEST_USER`. The test-only user must differ from the development user and
has no permission on the development schema. Missing or unsafe configuration
makes the integration command fail rather than skip.

## Stop and reset

Stop containers while retaining the named MySQL volume:

```powershell
docker compose down
```

Changing `.env` is not a credential rotation for an existing volume. Prefer an
explicit `ALTER USER` operational procedure when data must be retained.

Only when all local data is intentionally disposable, verify the exact Compose
project, volume labels, and data status before running the destructive reset:

```powershell
docker compose down -v
```

The `-v` command is destructive, is never run automatically by normal project
commands, and is not part of normal shutdown.
