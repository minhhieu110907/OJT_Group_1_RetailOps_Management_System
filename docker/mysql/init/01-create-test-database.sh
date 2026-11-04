#!/usr/bin/env bash
set -euo pipefail

identifier_pattern='^[A-Za-z0-9_]+$'
if [[ ! "${MYSQL_TEST_DATABASE}" =~ ${identifier_pattern} ]]; then
    echo "MYSQL_TEST_DATABASE must contain only letters, numbers, and underscores" >&2
    exit 1
fi
if [[ ! "${MYSQL_USER}" =~ ${identifier_pattern} ]]; then
    echo "MYSQL_USER must contain only letters, numbers, and underscores" >&2
    exit 1
fi
if [[ ! "${MYSQL_TEST_USER}" =~ ${identifier_pattern} ]]; then
    echo "MYSQL_TEST_USER must contain only letters, numbers, and underscores" >&2
    exit 1
fi
if [[ "${MYSQL_TEST_DATABASE}" == "${MYSQL_DATABASE}" ]]; then
    echo "MYSQL_TEST_DATABASE must differ from MYSQL_DATABASE" >&2
    exit 1
fi
if [[ "${MYSQL_TEST_USER}" == "${MYSQL_USER}" ]]; then
    echo "MYSQL_TEST_USER must differ from MYSQL_USER" >&2
    exit 1
fi
case "${MYSQL_TEST_USER,,}" in
    root|mysql.sys|mysql.session|mysql.infoschema)
        echo "MYSQL_TEST_USER must not be an administrative MySQL account" >&2
        exit 1
        ;;
esac

test_password_escaped=${MYSQL_TEST_PASSWORD//\\/\\\\}
test_password_escaped=${test_password_escaped//\'/\'\'}

development_test_privileges=$(
    MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql \
        --protocol=socket \
        --user=root \
        --batch \
        --skip-column-names \
        --execute="SELECT COALESCE(
                       GROUP_CONCAT(PRIVILEGE_TYPE ORDER BY PRIVILEGE_TYPE SEPARATOR ', '),
                       ''
                   )
                   FROM information_schema.schema_privileges
                   WHERE grantee = \"'${MYSQL_USER}'@'%'\"
                     AND table_schema = '${MYSQL_TEST_DATABASE}'"
)
if [[ -n "${development_test_privileges}" ]]; then
    MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql \
        --protocol=socket \
        --user=root \
        --execute="REVOKE ${development_test_privileges}
                   ON \`${MYSQL_TEST_DATABASE}\`.* FROM '${MYSQL_USER}'@'%'"
fi

MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql --protocol=socket --user=root <<SQL
CREATE DATABASE IF NOT EXISTS \`${MYSQL_TEST_DATABASE}\`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
DROP USER IF EXISTS '${MYSQL_TEST_USER}'@'%';
CREATE USER '${MYSQL_TEST_USER}'@'%' IDENTIFIED BY '${test_password_escaped}';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES
  ON \`${MYSQL_TEST_DATABASE}\`.* TO '${MYSQL_TEST_USER}'@'%';
SQL
