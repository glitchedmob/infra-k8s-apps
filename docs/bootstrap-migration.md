# Bootstrap ownership migration

Existing clusters must use three separately reviewed phases. A branch is not evidence that its checkpoint has happened. Do not collapse this series into one automated rollout. Keep transfer and cleanup draft until their preceding checkpoints are observed.

## Preparation

The current bootstrap-config owner keeps all existing resources. Every moving identity has temporary `argocd.argoproj.io/sync-options: Prune=false`. This includes the DNS gateway ConfigMap, StatefulSet and both Services, not only its ExternalSecret. The future bootstrap-ingress-config and bootstrap-aws-config children point to empty, stable directories and allow an empty sync. Existing foundation and issuer waves stay unchanged during preparation.

Cert-manager's controller uses `extraArgs: [--acme-http01-solver-nameservers=1.1.1.1:53,1.0.0.1:53]`. This is the HTTP01 self-check resolver override supported by the v1.21.2 operator chart and controller, not the DNS01 resolver flag. Public certificate issuance must not resolve the issuer through LZ's private split DNS before the tailnet DNS gateway can start. Allow outbound UDP/TCP 53 to these public resolvers and public ACME HTTP traffic. The public OIDC hook separately uses these resolvers with normal TLS verification.

Before transfer, observe a successful preparation reconcile. Inspect every moving identity in `tests/bootstrap-inventory.json` for live Prune=false and confirm both empty children reconciled. Record resource UIDs, target Secret UIDs, ownerReferences and Argo tracking annotations without reading Secret data. Confirm the cert-manager controller argument is live. Stop if any resource or protection is missing.

## Transfer

Transfer retains protection while adopting existing resources under their new owners:

- bootstrap-ingress-config, wave -4, path `src/k8s/platform/configuration-ingress`, health-gated. Its namespace-local `kube-system/bootstrap-aws-ssm` SecretStore is wave 0. Only `kube-system/cloudflared-token` and `kube-system/crowdsec-bouncer-key` ExternalSecrets are wave 1. Their names, targets, remote SSM paths, one-hour refresh and `creationPolicy: Owner` stay unchanged. Their store reference changes to this static store.
- bootstrap-config, wave -3, retains admission expansion, ingress HelmChartConfig, middleware, certificate/CA prerequisites, trust bundle and CoreDNS split configuration. It has no ESO resources or DNS gateway workload.
- k8s-oidc, wave -2, must be Synced and Healthy with a successful PostSync public discovery/JWKS hook matching its current input fingerprint.
- bootstrap-aws-config, wave -1, adopts JWT stores, cache readers and splits, Traefik tailnet auth, DNS gateway auth and all DNS gateway resources. Reader ServiceAccounts/RBAC are wave -2 inside this child, stores 0, direct ExternalSecrets 1 and cache splits 2. Gateway resources sync after its auth ExternalSecret at wave 2. Existing services follow.

The static store uses ParameterStore in us-east-2 and only `auth.secretRef` to `kube-system/bootstrap-aws-credentials`, keys `access-key-id` and `secret-access-key`. It remains static and continuously reconciled after bootstrap; credentials never pass through ESO or the normal cache. The bootstrap IAM reader can read only `/vm-workloads/lz/infra-vm-workloads/cloudflare-tunnel-token` and `/vm-workloads/lz/infra-vm-workloads/crowdsec-traefik-bouncer-key`. It has no Headscale access. All other AWS stores remain JWT authenticated.

Moving the gateway breaks the cycle between its JWT-backed auth key and public issuer readiness. CoreDNS still forwards private zones to its fixed Service IP, but neither public check nor HTTP01 self-check uses that split DNS. Foundation owns a Traefik HelmChartConfig, not the generated Deployment. Do not wait for full Traefik pod readiness before the issuer. Missing tailnet auth can leave the Tailscale container and pod NotReady while Traefik and Cloudflared start. The tunnel's origin is localhost, not a readiness-filtered Traefik Service. Keep Tailscale probes unchanged; public success says nothing about tailnet health.

Before cleanup, compare recorded resource and target Secret UIDs and ownerReferences. Confirm new Argo tracking, actual Ready conditions for the static store and both early ExternalSecrets, current fingerprint-bound public hook success, JWT store/ExternalSecret Ready conditions, gateway readiness and unchanged ingress availability. A Synced parent alone is insufficient. Do not delete or recreate an ExternalSecret or target Secret, force replacement, or enable shared-resource rejection. Preserve `Owner`, not `Merge`.

## Cold bootstrap and rollout order

Land/apply AWS-core's dedicated `lz-k3s-bootstrap-reader` user and exact-path inline policy first. No runtime role or trust changes are part of this redesign. The operator provisions access keys outside Terraform and stores them as SecureString outside state/Git at `/vm-workloads/lz/infra-vm-workloads/bootstrap-aws/access-key-id` and `/vm-workloads/lz/infra-vm-workloads/bootstrap-aws/secret-access-key`. Do not print key values or put them in command arguments, outputs or logs.

Use the coordinated VM bootstrap revision. Its create-only helper reads these parameters with explicit us-east-2/decryption and seeds only `kube-system/bootstrap-aws-credentials` for ingress. A complete Secret is untouched; an incomplete Secret fails rather than mixing credentials. Existing ingress target Secrets remain for ESO adoption. VM preparation installs AWS runtime and the early admission mirror before ESO's ServiceAccount; keep that mirror identical to Kubernetes admission expansion, including its existing policy coverage.

Then install Argo/operators and apply platform. Wait for the early static store and both ExternalSecrets before foundation certificate/CA prerequisites. Do not wait for foundation first, a DNS gateway StatefulSet, or whole Traefik readiness. Next wait for the current public issuer hook, then JWT AWS configuration conditions and gateway readiness, then apps. The preparation branch retains legacy waves for migration safety and is not the cold-bootstrap revision. Healthy legacy reruns remain supported; old main does not support cold recovery under this contract.

ESO v2.11.0 with `creationPolicy: Owner` can adopt a preexisting Secret without a conflicting controller owner; conflicting ownership must stop the rollout. Seeds have no Argo tracking or controller ownerReference. Offline checks cannot prove live UID preservation or controller adoption. A real empty-cluster bootstrap and isolated controller adoption check remain outstanding.

## Cleanup, rotation and recovery

Remove protection only from the reviewed transferred identities after adoption. Require all three configuration Applications Synced and Healthy. The static store keeps reconciling, and pruning resumes in cleanup. Never automate merging across checkpoints.

For rotation, stage a new operator-managed key pair in the SecureString parameters, then update the credential Secret through an approved secret-handling procedure without exposing data. The create-only Ansible helper does not rotate an existing complete Secret. Observe static store and both ExternalSecrets Ready, successful refresh and public ingress before revoking the old key. Never delete target Secrets to trigger refresh. Both credential fields must come from the same key pair.

If reconciliation or adoption fails, keep Prune=false and stop. Repair credentials, permissions, conditions or tracking without deletion. Incomplete credential seeding requires operator repair, not automatic replacement. A failed public hook is not an AWS authentication probe; inspect public DNS, ACME TLS, tunnel and discovery/JWKS separately, then retry the input-bound hook. Do not weaken Tailscale probes or add a whole-pod foundation gate.

To restore an old owner, first protect the new owner's moving resources, confirm protection is live, then restore their original desired paths and remove them from the new desired tree. Restore the original JWT store references if moving ingress ExternalSecrets back. Confirm unchanged UIDs and old tracking before removing protection. Do not blindly revert cleanup or prune to force adoption.

Offline tests render each phase with `kubectl kustomize` and compare identities and runtime specs against contract fixtures. The ingress store-reference change and new static store are intentional; gateway workloads and target identities stay unchanged.
