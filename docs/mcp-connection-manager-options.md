# Multi-user MCP connection manager options

Research checked 2026-10-02 UTC. No deployments, credential collection or food-log writes.

## What we are comparing

The original task is to connect ChatGPT to SparkyFitness through an OAuth gateway. Discussion clarified that we should also explore a shared web application where multiple users can manage upstream credentials. ToolHive is still an option, not a selected deployment.

Keep these separate:

1. Operators or permitted users register an upstream URL and authentication requirements.
2. Each user supplies their own static API key/header or authorizes their own upstream OAuth account.
3. ChatGPT authenticates the user to the gateway with OAuth and calls a stable MCP endpoint.
4. The gateway selects only that user's credential when calling an upstream.

An admin UI, per-user OAuth support, or a Kubernetes Secret reference alone does not prove that the personal static-key workflow exists. Arbitrary user-entered URLs also create an SSRF/credential-exfiltration risk; an approved shared catalog can provide self-service credentials without permitting unrestricted destinations.

## Shortlist

Star counts and latest releases came from GitHub's API. Stars are adoption signals, not assurances of security or feature maturity. Exact ChatGPT + Zitadel + Sparky compatibility remains untested for every candidate.

| Project | Stars | Checked release | User-owned static credentials in UI | Zitadel path | Assessment |
| --- | ---: | --- | --- | --- | --- |
| MCPHub, samanhappy/mcphub | 2,488 | v1.0.44 | Explicit Credentials page and per-user header/env bindings | Generic OIDC through Better Auth, PostgreSQL required | First candidate to test for the exact workflow. Personal credentials are a recent feature. |
| Obot, obot-platform/obot | 1,082 | v0.26.1 | User-supplied sensitive headers and per-user vMCP connection configuration | No generic OIDC/Zitadel provider documented in the checked provider list | Strong UI/catalog option, but identity integration and edition limits matter. |
| IBM ContextForge | 4,557 | v1.0.11 | Admin gateway-auth UI confirmed; personal static-key binding UI not confirmed | Generic OIDC documented | Keep as a secondary candidate. Per-user OAuth does not settle the static-key question. |
| ToolHive | 2,230 | v0.51.4 | Not in the proposed OSS Kubernetes workflow; URL/auth configured via CRDs and Secrets | Embedded OAuth server with upstream OIDC | Keep for centrally managed infrastructure. A self-service portal would be additional work or a separate product. |

MCPHub, ContextForge and ToolHive report Apache-2.0 licenses. Obot reports MIT, but its application editions still impose user/device limits and gate some providers.

## MCPHub

The tagged documentation and UI code directly cover the required static-key workflow:

- Owner/admin adds a server URL through the web Server form.
- Advanced configuration declares personal credential slots. HTTP servers use header slots, such as `Authorization` or `X-API-Key`.
- Users enter or replace their values in **Credentials** or from a server card.
- Users can manage only their own bindings; the normal credential-list API does not return secret values.
- For Authorization, the user supplies the complete value, including `Bearer `.
- Missing personal credentials fail rather than falling back to an organization key.
- Stored bindings use AES-256-GCM with server and username included as authenticated associated data. Database mode stores ciphertext in `credential_bindings`.
- Personal HTTP clients are isolated per user.

For Sparky, the shared definition would have URL `https://sparky.levizitting.com/mcp` and a personal `Authorization` header slot. Alice and Bob would each enter `Bearer <their-own-Sparky-key>` in their Credentials page.

Public MCP routes include `/mcp`, `/mcp/<server>` and `/mcp/<group>`. MCPHub has its own OAuth authorization server, PKCE, protected-resource metadata and dynamic registration. Generic OIDC login can use Zitadel discovery via Better Auth. The tagged OAuth controller bridges Better Auth session cookies into the OAuth consent flow, so these are not merely two disconnected login mechanisms. This is source evidence, not a successful ChatGPT integration test.

Operational caveats:

- PostgreSQL is required for Better Auth/OIDC login; file-only mode is insufficient.
- Set stable credential-encryption, JWT and session secrets and back them up separately from ciphertext.
- Local permissions are admin/non-admin, with server/group visibility. This is not a rich enterprise role system.
- Personal-credential support was added on September 9, 2026 in PR #1129. It has only weeks of public history at this check.
- Recent releases contain OAuth and protocol fixes. Session-dependent modern tools require sticky routing; start a trial with one replica and a read-only mock backend.
- Shared upstream OAuth and a personal credential template cannot be combined on the same server definition according to the tagged guide. Do not assume its general upstream OAuth mode is a per-user OAuth vault.

Security: published advisories include cross-user access, OAuth PKCE/client-authentication failures, log IDOR and executable overwrite. The patched versions listed in the inspected MCPHub advisories are at or below v1.0.41. v1.0.44 is beyond those versions, but still needs negative authorization, secret-redaction and dependency checks. Do not enable skip-auth or give non-admin users unrestricted executable-server deployment.

Sources:

- [Personal credentials, v1.0.44](https://github.com/samanhappy/mcphub/blob/v1.0.44/docs/features/per-user-credentials.mdx)
- [Authentication and generic OIDC, v1.0.44](https://github.com/samanhappy/mcphub/blob/v1.0.44/docs/features/authentication.mdx)
- [Server form](https://github.com/samanhappy/mcphub/blob/v1.0.44/frontend/src/components/ServerForm.tsx)
- [OAuth consent controller](https://github.com/samanhappy/mcphub/blob/v1.0.44/src/controllers/oauthServerController.ts)
- [Personal credentials introduction](https://github.com/samanhappy/mcphub/pull/1129)
- [Security advisories](https://github.com/samanhappy/mcphub/security/advisories)

## Obot

The checked release has an admin server/catalog UI and per-user connection configuration:

- Add a Remote server/catalog entry and enter the upstream URL in the UI.
- Define an `Authorization` header as **User-Supplied**, mark it **Sensitive**, and configure the prefix `Bearer `.
- Create a shared virtual MCP and set the header's configuration policy to **Provided at connection**.
- Each connecting user supplies their own value, stored with that user's vMCP instance.
- The connection URL is `/mcp-connect/<vmcp-id>` and uses Streamable HTTP.
- Admins publish shared vMCPs and grant access through profiles. Users can also assemble owner-only personal vMCPs from catalog entries they are allowed to use.
- User-provided headers are isolated without requiring a separate hosted workload for each user.

This is a genuine documented personal-header workflow, not an inference from OAuth support.

Caveats:

- Default and free registered Community editions are capped at 100 users and 100 devices. Enterprise removes those limits.
- Local, GitHub and Google login are included without registration. Entra, Okta, JumpCloud and Auth0 require free Community registration or Enterprise.
- The checked auth-provider guide does not list a generic OIDC or Zitadel provider. Do not assume Auth0 support can simply be pointed at Zitadel. A supported integration or custom provider needs investigation if Zitadel is required.
- Credential encryption is disabled by default until an encryption provider is configured.
- v0.26.1 introduces transitional vMCP behavior and is recommended only for new installations, not upgrades from existing deployments. vMCP definitions/profile configuration are not directly GitOps-managed in that release.
- Do not grant users hosted-code deployment permissions merely to let them configure a remote API key.

Security clarification: GHSA-6fwv-3h4c-37j9 has no patched version in its GitHub advisory field, but the v0.26.0 release notes explicitly say it was fixed in v0.25.0. The v0.26.1 `checkUI` implementation only permits the actual UI fallback handler, addressing the reported route-prefix mechanism. Verify with a denied-user runtime test rather than treating the empty advisory field as proof of an unfixed current release.

Sources:

- [vMCP policies and per-user instances](https://github.com/obot-platform/obot/blob/v0.26.1/docs/versioned_docs/version-v0.26.0/functionality/virtual-mcps.md)
- [Remote header configuration UI](https://github.com/obot-platform/obot/blob/v0.26.1/ui/user/src/lib/components/mcp/RemoteRuntimeForm.svelte)
- [Auth providers](https://github.com/obot-platform/obot/blob/v0.26.1/docs/versioned_docs/version-v0.26.0/configuration/auth-providers.md)
- [Edition limits](https://github.com/obot-platform/obot/blob/v0.26.1/docs/versioned_docs/version-v0.26.0/enterprise/overview.md)
- [Encryption requirement](https://docs.obot.ai/concepts/mcp-hosting/)
- [v0.26.0 security notes](https://github.com/obot-platform/obot/releases/tag/v0.26.0)
- [v0.26.1 upgrade warning](https://github.com/obot-platform/obot/releases/tag/v0.26.1)

## ContextForge and ToolHive

ContextForge has a UI for registering gateways and configuring upstream auth. Tagged OAuth documentation confirms encrypted tokens stored per gateway/user, but also lists lifecycle UI gaps. A self-service personal static-Bearer binding page for a shared upstream has not been established. Private user-owned gateway registrations might provide another workflow, but that needs verification. Do not mark this requirement supported solely because OAuth tokens are user-scoped.

ToolHive remains useful if operators can own server definitions and credential provisioning. Its native upstream OIDC token mechanisms can support multiple users, but the proposed static-Bearer configuration is a Kubernetes Secret reference, not a per-user dashboard. Building a portal on top would mean owning credential authorization and lifecycle code ourselves. That is a poor shortcut when the task asks for a proven implementation.

Sources:

- [ContextForge OAuth implementation and known gaps](https://github.com/IBM/mcp-context-forge/blob/v1.0.11/docs/docs/architecture/oauth-design.md)
- [ContextForge generic OIDC](https://github.com/IBM/mcp-context-forge/blob/v1.0.11/docs/docs/manage/sso.md)
- [ToolHive auth configuration types](https://github.com/stacklok/toolhive/blob/v0.51.4/cmd/thv-operator/api/v1beta1/mcpexternalauthconfig_types.go)

## Other options screened

- AnythingMCP markets a dashboard and encrypted credentials, but its Community page says three active users and Business-only self-hosted SSO. Do not pick it for many-user Zitadel access based on the headline "free self-hosted" claim. This is vendor documentation, not a verified runtime assessment.
- MSPStack's gateway describes `/admin` and `/me` self-service, but has eight GitHub stars at this check. It does not meet the original adoption preference as well as the shortlist.
- LibreChat has user-supplied MCP credentials, but is principally a chat client. That does not establish a public OAuth MCP gateway endpoint for ChatGPT.

## Recommended next experiment

Test MCPHub first for the exact workflow and keep Obot as the second trial if local login or another supported IdP is acceptable. Keep ToolHive on the infrastructure-managed track. No final product selection yet.

Use a mock upstream and two test users before any real health data:

1. Configure a single shared upstream URL in the UI.
2. Bind different Alice/Bob Authorization values and verify the mock sees only the caller's value.
3. Confirm a user cannot read, update, delete or invoke another user's connection through any route, including groups and direct tools/call.
4. Delete Alice's credential; Alice must fail, Bob must continue working.
5. Test Zitadel login, ChatGPT OAuth consent and resource/audience validation together.
6. Verify missing/wrong/expired tokens fail, and disabled tools cannot execute.
7. Restart and verify credentials, clients, refresh state and encryption material survive.
8. Confirm logs, exports and UI responses do not disclose secrets.
9. Only then connect a dedicated Sparky key and run read-only diary calls. Food writes remain a separate approved step.

Before expanding beyond a trusted small group, settle whether users may register arbitrary URLs or only bind credentials to approved upstreams, whether local passwords are acceptable, and the expected user count.
