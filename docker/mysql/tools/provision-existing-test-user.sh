#!/usr/bin/env bash
set -euo pipefail

if [[ "${CONFIRM_RETAILOPS_LOCAL_PROVISIONING:-}" != "retailops-local" ]]; then
    echo "Refusing to provision without explicit local-environment confirmation" >&2
    exit 1
fi

identifier_pattern='^[A-Za-z0-9_]+$'
if [[ ! "${MYSQL_DATABASE}" =~ ${identifier_pattern} ]]; then
    echo "MYSQL_DATABASE must contain only letters, numbers, and underscores" >&2
    exit 1
fi

MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql \
    --protocol=socket \
    --user=root \
    --batch \
    --skip-column-names \
    --execute="SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '${MYSQL_DATABASE}'" \
    | grep --fixed-strings --line-regexp "${MYSQL_DATABASE}" >/dev/null

exec bash /docker-entrypoint-initdb.d/01-create-test-database.sh
