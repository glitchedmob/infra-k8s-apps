# LZ Traefik AppSec

CrowdSec runs in the `crowdsec` namespace. Its node agents acquire the **unsampled**
Traefik container logs from `kube-system`; Alloy's Loki sampling does not affect
these agents. The AppSec service inspects requests through a Traefik plugin on
`websecure`. The `web` entry point, including cert-manager HTTP-01, is not
protected by this middleware.

The bouncer is deliberately in `appsec` mode. It blocks requests matching the
AppSec rules, but **does not enforce LAPI IP decisions**. Direct HTTPS arrives
through the shared public edge's TCP/SNI passthrough, which does not preserve
the visitor IP. A ban derived from those requests could block the edge rather
than the attacker. Tunnel traffic also needs a verified client-IP chain. The
header-stripping middleware ensures the plugin uses the socket peer instead of
an attacker-provided IP header. Do not change to `stream` until the edge sends
PROXY protocol, the cluster trusts only that edge, the tunnel client-IP path
is validated, and the resulting Traefik log and plugin IPs have been checked
on **both** ingress paths.

## Secret before deployment

Create a random bouncer key as an AWS SSM `SecureString` at
`/vm-workloads/lz/infra-vm-workloads/crowdsec-traefik-bouncer-key` in
`us-east-2` **before merging**. Use the existing External Secrets IAM-readable
prefix. Do not commit the value. External Secrets copies it into a
`kube-system/crowdsec-bouncer-key` Secret, mounted into Traefik as a file.
The plugin requires a key even in `appsec` mode, but it does not query LAPI
or enforce LAPI decisions in this mode. When switching to `stream`, also
configure LAPI with the same `BOUNCER_KEY_traefik` key. A missing parameter
prevents the new Traefik pods from starting.

For example, with appropriate AWS credentials:

```sh
aws ssm put-parameter --region us-east-2 --name /vm-workloads/lz/infra-vm-workloads/crowdsec-traefik-bouncer-key --type SecureString --value "$(openssl rand -hex 32)" --no-overwrite
```

## Check after sync

```sh
kubectl -n crowdsec get pods,svc
kubectl -n kube-system get externalsecret crowdsec-bouncer-key
kubectl -n crowdsec exec deploy/crowdsec-appsec -- cscli metrics show appsec
kubectl -n crowdsec exec ds/crowdsec-agent -- cscli metrics show acquisition
```

Check a normal route on each ingress path and a harmless AppSec test path
such as `/.env`; the latter should return 403. Confirm legitimate uploads,
OAuth callbacks and cert-manager HTTP-01 renewals still work. Watch for AppSec
unavailability: the middleware fails open when the AppSec service cannot be
reached, to avoid taking all HTTPS ingresses down. A WAF rule returning an
error blocks the request. Pin changes to the chart and plugin versions and
check their compatibility with the k3s-managed Traefik chart on upgrades.
