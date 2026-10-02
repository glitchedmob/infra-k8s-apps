# MCP OAuth gateway evaluation

Status: initial infrastructure-focused evaluation; no deployment or compatibility tests. The expanded comparison in [MCP connection manager options](mcp-connection-manager-options.md) supersedes the recommendation below after clarifying the multi-user credential UI requirement.
Checked 2026-10-02 UTC. No cluster changes or food-log writes made.

## Purpose

Todoist task `6hg6v9JpFFchqFx7`, "Find and deploy a proven MCP OAuth gateway", belongs to "Build eating habits that support sustainable weight loss".

The immediate goal is to connect ChatGPT to SparkyFitness for the October 1–3 food-logging trial. Manual logging should continue while the connector is being built. This task does not authorize entering the pending food log or inventing nutrition estimates.

Required capabilities:

- Self-hosted Kubernetes deployment.
- ChatGPT-facing OAuth with PKCE and MCP discovery metadata.
- Server-side API keys or Bearer tokens for multiple upstream MCP servers.
- Prefer existing Zitadel login.
- Restrict access to the owner of the stored Sparky credential.

## Recommendation

The initial proposal was to trial Stacklok ToolHive v0.51.4 with its embedded authorization server and Zitadel as the upstream OIDC provider. ToolHive remains an option for operator-managed connections, but does not supply the shared self-service static-credential portal now under consideration. Use a VirtualMCPServer for the public endpoint and an MCPServerEntry for Sparky, with a Secret-backed MCPExternalAuthConfig. The tagged Kubernetes guide documents direct remote entries, avoiding a separate proxy pod for each upstream.

This is a recommendation, not a claim that the exact ChatGPT/Zitadel/Sparky combination has passed an integration test. Stars indicate adoption, not security certification.

| Candidate | GitHub stars at check | Latest release | Assessment |
| --- | ---: | --- | --- |
| [ToolHive](https://github.com/stacklok/toolhive) | 2,230 | v0.51.4, September 27 | Best documented match for OIDC login brokering, MCP-specific token audiences, stored upstream credentials, and multi-server aggregation. Requires operator/CRDs and persistent OAuth state. |
| [agentgateway](https://github.com/agentgateway/agentgateway) | 5,125 | v1.5.0, August 27 | Good smaller resource-server proxy with MCP OAuth metadata, JWT validation and tool policies. Zitadel is not a documented tested provider. Direct integration needs special attention to audience binding; it does not solve that by merely enabling JWT validation. |
| [IBM ContextForge](https://github.com/IBM/mcp-context-forge) | 4,557 | v1.0.11, September 28 | Broad gateway/control-plane product with admin UI and stored upstream authentication. More application state and administration than this first connection needs. Not selected for the initial trial. |

All three repositories report Apache-2.0 licensing and recent activity. Release dates and star counts came from GitHub's API, not search-result summaries.

## Existing deployment

- Active kubectl context is `lz-k3s`.
- Argo CD application `sparky` is Synced and Healthy.
- Sparky frontend has two available replicas; backend has one.
- Configured Sparky server image is `codewithcj/sparkyfitness_server:v1.7.3`.
- An unauthenticated request to `https://sparky.levizitting.com/mcp` returns 401 and `Authentication required.` without an OAuth discovery challenge.
- Sparky's tagged documentation specifies Streamable HTTP at `/mcp`, authenticated by `Authorization: Bearer <API_KEY>`.
- Existing Zitadel issuer is `https://id.levizitting.com`. Live discovery advertises PKCE S256, but no dynamic-registration endpoint.
- ToolHive CRDs are not installed.
- Sparky's backend NetworkPolicy only permits frontend pods. Direct gateway-to-backend access will need a narrowly scoped rule.

## OAuth caveat

[Zitadel's current DCR documentation](https://zitadel.com/docs/guides/integrate/dynamic-client-registration) says dynamically registered clients share the `ZITADEL DCR` project audience. It accepts but ignores the RFC 8707 `resource` parameter when narrowing that audience.

Do not enable open registration and accept any Zitadel token as authorization to use the stored Sparky key. Direct agentgateway integration could use a dedicated, predefined OAuth application with explicit audience and subject/client checks, but needs an end-to-end compatibility test and documented treatment of resource binding.

ToolHive's tagged auth-server configuration explicitly validates requested resource URIs against `allowed_audiences`. Its embedded authorization server can broker upstream OIDC login and issue its own MCP-facing tokens. That avoids relying on Zitadel's shared DCR audience for the public MCP connection. Keep Zitadel's open DCR disabled.

## Proposed deployment

Proposed hostname, subject to approval: `mcp.levizitting.com`.

```text
ChatGPT
  -> HTTPS public MCP endpoint
  -> ToolHive VirtualMCPServer / embedded OAuth authorization server
       -> Zitadel for browser login
       -> server-side Sparky Bearer credential
       -> Sparky's internal /mcp endpoint
```

The exact public MCP path and upstream OAuth callback must come from the pinned ToolHive configuration before creating DNS, ingress and the Zitadel application.

Repository changes:

1. `infra-k8s-apps`: pin compatible ToolHive operator and CRD charts, runtime v0.51.4 and image digests; create an isolated gateway namespace, TLS ingress, health probes, resource limits and network policies.
2. `infra-app-config`: create a dedicated Zitadel OIDC application and least-privilege OpenBao policy/auth role for gateway secrets.
3. `infra-k8s-apps`: use External Secrets to load the Zitadel client secret, Sparky API key and persistent signing/encryption material. No credentials in Git, ConfigMaps, tool schemas or chat.
4. Configure persistent OAuth state. ToolHive defaults to memory; a restart must not discard client registrations and refresh-token state. Its tagged storage guide documents Redis support. Select and test persistence, encryption and backups before production use.
5. Add the Sparky entry and a food-tool allowlist. Restrict the authorized upstream Zitadel subject to the owner of the Sparky API key. Authentication alone is insufficient because a shared upstream key always acts as that key's owner.
6. `infra-dns`: add the approved public hostname through the existing edge route model.

Do not forward the ChatGPT access token to Sparky. Replace upstream Authorization with the Secret-backed Sparky Bearer key. Keep optional Sparky developer/admin tools disabled. Disable sensitive request/response-body logging.

## Security checks

Inspect published advisories and patched versions again at deployment time. A version pin is not a guarantee against unpublished vulnerabilities.

- ToolHive's published OAuth callback login-CSRF advisory [GHSA-2gjv-f568-6cxp](https://github.com/stacklok/toolhive/security/advisories/GHSA-2gjv-f568-6cxp) is fixed in 0.51.3.
- Its cross-principal MCP-session advisory [GHSA-hqg7-qjgg-q779](https://github.com/stacklok/toolhive/security/advisories/GHSA-hqg7-qjgg-q779) is fixed in 0.51.0.
- v0.51.4 is beyond the patched versions listed in the published ToolHive advisories inspected at this check. Recheck operator/chart dependencies separately.
- agentgateway's cross-route session/authorization advisory [GHSA-mvgg-jvj2-4frq](https://github.com/agentgateway/agentgateway/security/advisories/GHSA-mvgg-jvj2-4frq) is fixed in v1.4.0; cross-namespace route adoption [GHSA-g7j8-wp7h-wmgr](https://github.com/agentgateway/agentgateway/security/advisories/GHSA-g7j8-wp7h-wmgr) is fixed in v1.5.0.

Before marking the ticket complete:

- Unauthenticated MCP calls return an OAuth discovery challenge.
- Metadata, PKCE S256, exact callback allowlists and resource-specific audiences work with ChatGPT.
- Wrong issuer, audience, expired token and unauthorized Zitadel subject all fail closed.
- A second account cannot reuse the first account's session or access its Sparky key.
- Client-supplied Authorization cannot override the configured upstream key.
- `initialize`, `tools/list` and a read-only diary call work through ChatGPT.
- Tool restrictions cover enumeration and execution, not only hidden tool descriptions.
- A restart preserves OAuth state, signing keys and refresh behavior.
- Key rotation/revocation works and secrets do not appear in logs.
- A food-log write is tested only after explicit approval, with confirmed portions/date and no duplicate entry.

## Inputs needed

- Approval for the hostname and whether access is Levi-only initially.
- A dedicated Sparky API key created in Settings > Developer & Integrations > API Key Management. Store it through the existing secret-management workflow, not in chat. Confirm the associated account and privileges.
- Approval to install the operator/CRDs and apply the scoped identity, DNS and gateway changes.
- Browser access for the final ChatGPT connector OAuth test.

## Primary sources

- [ToolHive tagged Kubernetes guide](https://github.com/stacklok/toolhive/blob/v0.51.4/docs/operator/virtualmcpserver-kubernetes-guide.md)
- [ToolHive tagged auth-server configuration](https://github.com/stacklok/toolhive/blob/v0.51.4/pkg/authserver/config.go)
- [ToolHive tagged OAuth storage guide](https://github.com/stacklok/toolhive/blob/v0.51.4/docs/arch/11-auth-server-storage.md)
- [ToolHive tagged Bearer-secret example](https://github.com/stacklok/toolhive/blob/v0.51.4/examples/operator/external-auth/mcpremoteproxy_with_bearer_token.yaml)
- [agentgateway MCP authentication](https://agentgateway.dev/docs/standalone/latest/documentation/configuration/security/mcp-authn/)
- [OpenAI MCP authentication requirements](https://developers.openai.com/apps-sdk/build/auth/)
- [Sparky v1.7.3 MCP documentation](https://github.com/CodeWithCJ/SparkyFitness/blob/v1.7.3/docs/src/features/mcp-server.md)
