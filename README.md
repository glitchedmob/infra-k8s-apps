# infra-k8s-apps

Holds the Kubernetes manifests for base infrastructure and applications deployed to the LZ k3s cluster via Argo CD.

## Scope
- Owns: Kubernetes desired state for bootstrap components and app workloads in the LZ k3s cluster.

## Structure
- `src/k8s/bootstrap/`: Argo CD projects and platform operators required before their custom resources.
- `src/k8s/platform/`: Cluster configuration, storage, identity, observability, and shared services.
- `src/k8s/apps/`: The primary set of applications deployed to the cluster.

## Public ingress model
- Public DNS hostnames (for example `hello-nginx.levizitting.com`) resolve to the public edge node.
- The edge cluster forwards `*.levizitting.com` traffic to internal LZ k3s nodes.
- HTTPS is SNI passthrough at the edge, so TLS terminates on the destination workload cluster ingress.
- This repo defines destination ingresses/services; edge entry and forwarding rules are owned by [`glitchedmob/infra-public-edge`](https://github.com/glitchedmob/infra-public-edge).
