# ISP monitoring

VPN dashboard URLs:

- https://speedtest.levizitting.com:8443
- https://smokeping.levizitting.com:8443

Connect to Headscale/Tailscale and trust the existing `levizitting-ca`. Private DNS maps both names to the on-premises LZ nodes. The dedicated `ispprivate` Traefik entrypoint uses port 8443; there are no app routes on public-facing ports 80/443. Neither the public edge nor Cloudflare Tunnel forwards to this port. Network policies also prevent other pods from directly reaching the app services, except the speed-test scheduler.

A dedicated oauth2-proxy authenticates both dashboards against ZITADEL and permits `me@levizitting.com`. Its callback is on the speedtest hostname. The existing Dex-backed proxy is unchanged. Speedtest Tracker's guest dashboard is enabled only behind this gate; administration still requires the local account `me@levizitting.com`. The initial password and application key are in OpenBao at `applications/isp-monitoring/runtime`.

## Measurement and budget

One CronJob starts at 00:00 and 12:00 UTC. Each job chooses a fresh delay of 0–10 hours, then requests one test through the internal API. This leaves about two hours between windows. No automatic POST or Job retries are enabled, and missed windows are not replayed after five minutes. A cluster outage can therefore mean fewer than two tests that day. Keep the built-in speed-test schedule disabled and account for any manually triggered tests separately.

At 500 Mbps down, two daily tests might consume about 41 GB/month with 50 Mbps upload, or 75 GB/month with symmetric upload, assuming ten seconds per direction. These are estimates, not enforced caps. Check actual `data.download.bytes` plus `data.upload.bytes` in results and adjust the schedule if needed. Tests intentionally have no CPU limit so throttling does not cap measured throughput. Run these pods on the on-premises cluster without VPN exit-node routing.

SmokePing sends twelve small pings per target every minute, spaced five seconds apart. It compares the local workload gateway with Cloudflare, Google, and Quad9. The three external targets consume roughly 0.26 GB/month before link-layer overhead. Retention is 90 days at minute resolution plus hourly summaries for a year. Tracker retains individual results for 90 days. Grafana is not required.

Application memory requests total 352 MiB, plus 16 MiB while the scheduling job is waiting or running. Limits allow bursts, particularly during speed tests. Storage is two 2 GiB Longhorn volumes.

## Secrets and backup

The `isp_monitoring` module in `infra-app-config` owns the ZITADEL client/access grant and OpenBao runtime, OIDC, and backup secrets. External Secrets imports them here. On startup, Tracker installs a hashed, run-only API token for the scheduler after its database migrations. No cluster API permissions are needed by the applications or scheduler.

K8up backs up SmokePing's RRD volume and a consistent online SQLite snapshot daily to the existing B2 bucket under `isp-monitoring`. To restore Tracker, stop its deployment and restore `database.sqlite` from the backup tar into the root of its config volume; preserve the original OpenBao application key. Restore SmokePing's `/data` volume while its deployment is stopped. Configuration is rebuilt from Git.

Changing SmokePing database step/ping/archive settings requires migrating or recreating existing RRD files. Changing the initial admin password in OpenBao does not reset an already-created Tracker account; use its password-reset command instead.
