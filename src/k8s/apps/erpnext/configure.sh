#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /home/frappe/frappe-bench

# Serialize init containers sharing the site volume.
exec 9>sites/.erpnext-config.lock
flock -x 9

site_config="sites/$SITE_NAME/site_config.json"
if ! jq -e --slurpfile desired /settings/settings.json '
  .db_password == $desired[0].databasePassword and
  .encryption_key == $desired[0].encryptionKey
' "$site_config" >/dev/null; then
  echo "ERPNext site credentials differ from the managed settings." >&2
  exit 1
fi

# Native document import handles Frappe Password fields and their encryption.
if ! bench --site "$SITE_NAME" import-doc /settings/social-login.json >/dev/null 2>&1; then
  echo "Failed to import ERPNext login settings." >&2
  exit 1
fi

export MYSQL_PWD
MYSQL_PWD="$(jq -er .db_password "$site_config")"
if ! mariadb --host="$DB_HOST" --port="$DB_PORT" --user="$DB_NAME" \
  --database="$DB_NAME" < /bootstrap/settings.sql >/dev/null 2>&1; then
  echo "Failed to apply ERPNext signup settings." >&2
  exit 1
fi
unset MYSQL_PWD
bench --site "$SITE_NAME" clear-cache >/dev/null 2>&1
