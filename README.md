# infra-k8s-apps

Holds the Kubernetes manifests for base infrastructure and applications deployed to the LZ k3s cluster.

## Scope
- Owns: Kubernetes desired state for bootstrap components and app workloads in the LZ k3s cluster.

## Structure
- `src/k8s/flux/`: Flux Kustomizations that define reconciliation order.
- `src/k8s/bootstrap/`: Base cluster components and cluster-level configuration.
- `src/k8s/apps/`: Application manifests deployed to the cluster.

## Public ingress model
- Public DNS hostnames (for example `hello-nginx.levizitting.com`) resolve to the public edge node.
- The edge cluster forwards `*.levizitting.com` traffic to internal LZ k3s nodes.
- HTTPS is SNI passthrough at the edge, so TLS terminates on the destination workload cluster ingress.
- This repo defines destination ingresses/services; edge entry and forwarding rules are owned by [`glitchedmob/infra-public-edge`](https://github.com/glitchedmob/infra-public-edge).
