#!/usr/bin/with-contenv bash
set -e

# Keep the image's existing Laravel maintenance cron entry.
entry='* * * * * /usr/bin/php /opt/isp-monitoring/scheduler.php >> /config/log/isp-scheduler.log 2>&1'
grep -Fqx "$entry" /etc/crontabs/abc || printf '%s\n' "$entry" >> /etc/crontabs/abc
