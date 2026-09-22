#!/usr/bin/with-contenv bash
set -e
exec s6-setuidgid abc php /opt/isp-monitoring/init-scheduler.php
