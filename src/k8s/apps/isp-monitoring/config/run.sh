#!/bin/sh
set -eu

# One attempt in each UTC half-day. A ten-hour jitter leaves at least
# two hours between windows, apart from small Kubernetes start delays.
random=$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')
delay=$((random % 36000))
echo "Speed test scheduled in ${delay} seconds"
sleep "$delay"

# Do not retry an ambiguous POST: the first request may have queued a test.
exec curl --fail-with-body --silent --show-error \
  --connect-timeout 10 --max-time 30 \
  --request POST \
  --header "Authorization: Bearer ${SCHEDULER_API_TOKEN}" \
  --header 'Accept: application/json' \
  http://speedtest/api/v1/speedtests/run
