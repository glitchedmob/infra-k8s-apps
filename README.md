# infra-k8s-apps

Holds the Kubernetes manifests for base infrastructure and applications deployed to the LZ k3s cluster via Argo CD.

## Scope
- Owns: Kubernetes desired state for bootstrap components and app workloads in the LZ k3s cluster.

## Structure
- `src/k8s/bootstrap/`: Argo CD projects and platform operators required before their custom resources.
- `src/k8s/platform/`: Cluster configuration, storage, identity, observability, and shared services.
- `src/k8s/apps/`: The primary set of applications deployed to the cluster.

Applications can use either of these layouts:

- Flat applications place `kustomization.yaml` directly under `src/k8s/apps/<app>/`.
- Applications with overlays place shared resources under `src/k8s/apps/<app>/base/` and each deployable environment in a sibling directory containing its own `kustomization.yaml`.

The application generator discovers top-level Kustomizations and nested overlay Kustomizations, excluding directories named `base`. An overlay application must not have a Kustomization at its application root.

## Public ingress model
- Public DNS hostnames (for example `hello-nginx.levizitting.com`) resolve to the public edge node.
- The edge cluster forwards `*.levizitting.com` traffic to internal LZ k3s nodes.
- HTTPS is SNI passthrough at the edge, so TLS terminates on the destination workload cluster ingress.
- This repo defines destination ingresses/services; edge entry and forwarding rules are owned by [`glitchedmob/infra-public-edge`](https://github.com/glitchedmob/infra-public-edge).

## Application backups

- K8up uses `src/k8s/platform/services/backup-base/` for shared Backblaze scheduling and retention.
- OpenBao uses logical Raft snapshots and a least-privilege Kubernetes auth role managed by `infra-app-config`.
- OpenBao restores the latest snapshot only when all three current PVCs are empty; otherwise recovery makes no changes.
- A newly initialized or successfully queried repository with no snapshots permits first-time initialization. Missing credentials, invalid credentials, existing-repository password errors, and network errors fail closed.
