# MCPHub trial

This runbook covers the MCPHub trial at `https://mcp.levizitting.com`. Test ChatGPT OAuth, Zitadel sign-in, and per-user credential isolation before connecting real health data.

## Deployment gate

`src/k8s/apps/application-set.yaml` discovers `src/k8s/apps/*/kustomization.yaml` from `main` and automatically syncs discovered apps. The new directory needs no root resource entry. Nothing on `feat/mcphub` is discovered until the normal promotion process exposes it on `main`. Do not promote this app before bootstrap and staging are approved. For staging, use an explicitly approved isolated target and GitOps revision, not a change to the shared ApplicationSet in this trial.

Before any deployment, the platform operator must:

- Confirm CNPG supports PostgreSQL `18.6-system-trixie`, the storage class can provision two 5Gi volumes, and required anti-affinity has two eligible nodes.
- Confirm External Secrets, Reloader, K8up, Traefik, cert-manager, and NetworkPolicy enforcement are installed. Policy labels must match actual Traefik and Sparky pods. Cluster CIDRs must fall inside the policy's blocked private/reserved ranges.
- Confirm public DNS and TLS issuance for `mcp.levizitting.com`. The app trusts one proxy hop. Keep access limited to Traefik and verify forwarded host/protocol handling with the actual proxy chain.
- Provision identity and secrets with `infra-app-config/src/tf/modules/mcphub`, following its existing two-phase Zitadel pattern. Apply the initial `bootstrap_oidc_client_secret = true` configuration, then set it to false and apply again without changing the OIDC secret version. This supplies the OpenBao role and properties below. Never put secret values in Git, shell history, tickets, screenshots, or application logs.
- Grant approved trial users the `access` role in the dedicated MCPHub Zitadel project. The confidential client uses `client_secret_post`, PKCE S256, and exact redirect URI `https://mcp.levizitting.com/api/auth/better/oauth2/callback/zitadel`. Request `openid email profile`. Google and GitHub clients are disabled. Zitadel grants do not make a user an MCPHub administrator.
- Verify the existing `aws-ssm` ClusterSecretStore can supply the existing B2 account ID/key paths and that K8up can write the `mcphub` repository prefix. Keep a separate protected copy of the OpenBao encryption/signing secrets.

| OpenBao KV path under `applications` | Property | Kubernetes destination |
| --- | --- | --- |
| `mcphub/runtime` | `jwtSecret` | `mcphub-runtime.JWT_SECRET` |
| `mcphub/runtime` | `betterAuthSecret` | `mcphub-runtime.BETTER_AUTH_SECRET` |
| `mcphub/runtime` | `credentialEncryptionKey` | `mcphub-runtime.MCPHUB_CREDENTIAL_ENCRYPTION_KEY` |
| `mcphub/runtime` | `adminPassword` | `mcphub-runtime.ADMIN_PASSWORD` |
| `mcphub/oidc` | `clientId` | `mcphub-runtime.OIDC_CLIENT_ID` |
| `mcphub/oidc` | `clientSecret` | `mcphub-runtime.OIDC_CLIENT_SECRET` |
| `mcphub/backup` | `resticPassword` | `mcphub-k8up-repo-password.password` |

The runtime Secret keys and `mcphub-db-app.uri` are required references. A missing Secret/key prevents container creation. Empty runtime values or an invalid encryption key fail initialization; there is no generated-password or ephemeral encryption-key fallback. Missing backup secrets block backup readiness, not app startup. Treat backup readiness as a deployment gate anyway.

CNPG creates `mcphub-db-app` and `mcphub-db-ca`. `DB_URL` uses the unmodified app `uri`. The pinned image contains `pg` 8.22.0, whose `sslmode=require` handling currently verifies certificates like `verify-full`. The app mounts `mcphub-db-ca/ca.crt` and uses `NODE_EXTRA_CA_CERTS` for both TypeORM and Better Auth. Verify the generated URI and server certificate hostnames in staging. Never use `NODE_TLS_REJECT_UNAUTHORIZED=0` or disable certificate checks to get bootstrap working. `pg_dump` separately uses `PGSSLMODE=require` as in Tandoor.

## Startup and baseline

The pinned digest runs one replica with `Recreate`, UID/GID 1000, a read-only root filesystem, no capabilities, no service account token, and writable `emptyDir` mounts only at `/app/data` and `/tmp`. It bypasses the image entrypoint's root-oriented npm/Docker setup and directly launches Node.

A hashed generated ConfigMap contains `mcp_settings.json` and `initialize.mjs`. Changes to either change the Deployment's volume reference and roll the pod. Reloader watches the runtime Secret, DB app Secret, and DB CA Secret.

The seed has no users or upstreams. Initialization imports reflect-metadata first, initializes database mode with a checked success result, then updates the database-backed system configuration before starting `dist/index.js`. It closes the data source and exits nonzero on failure. MCPHub's v1.0.44 file migration omits `activityLog`; the seed alone does **not** disable stored tool payloads. The DAO update applies `activityLog.storeToolPayload=false` on every startup and checks the returned setting. Confirm the stored setting and actual activity rows with mock traffic in staging, including the first boot when upstream's index initializes database mode again.

Startup reapplies the declared system settings, including authentication, base URL, OAuth state checks, payload storage, and disabled discovery/smart routing/compression. It does not reset existing users, upstream definitions, or personal credential bindings. UI edits to those baseline system settings are not durable across a restart. Changing or removing the seed does not delete existing upstreams in the database.

OAuth authorization-code and refresh-token grants, PKCE public clients, and unauthenticated dynamic client registration are enabled for the trial. Client ID metadata fetching is disabled. Public registration increases exposure to spam/abuse; verify request limits at the proxy and cleanup behavior before wider access. Global/group routing is enabled but bearer authentication is required. Do not create a system-wide bearer key as a workaround for per-user login or binding failures.

Startup/readiness probe `/health`. Liveness is TCP port 3000 so DB or upstream health failures alone do not repeatedly restart a running process. A health response is not proof of authorization or upstream correctness.

## Bootstrap login and mock isolation

Use the local `admin` login with the initial password held in OpenBao, not a password scraped from logs. On an empty DB, MCPHub consumes `ADMIN_PASSWORD` when creating the first administrator. Secret rotation does not change an existing user's password; change it through the authorized account workflow. Validate local break-glass login and logout before testing OIDC. Keep the local admin separate from trial user accounts.

Do not configure real Sparky credentials or any real upstream during bootstrap. First use a controlled mock MCP server with synthetic identities and harmless tools that return identity markers. Run it in a staging environment with a temporary, narrowly scoped policy allowance. The production trial policy does not allow arbitrary same-namespace mock ports. Do not weaken public/private egress rules for this test.

Create two non-admin users, Alice and Bob, and one shared mock definition with a required personal `Authorization` header slot. Bind different synthetic full `Bearer ...` header values. Use separate browser profiles and separate user-owned MCP tokens. Test both dashboard and MCP access paths, with concurrent sessions, before approving any real connection.

Required negative tests:

- Anonymous, invalid, expired, and revoked credentials cannot access protected dashboard APIs or MCP routes. Missing/mismatched OAuth state, invalid PKCE verifier, reused authorization codes, and unregistered redirect URIs must fail.
- OIDC-created users remain non-admin. An issuer grant or matching email must not link a trial user to the bootstrap admin. Email trust is explicitly disabled. Test account linking, logout, revoked Zitadel access, and reauthentication rather than assuming immediate revocation of all hub tokens.
- Alice receives only Alice's marker and Bob only Bob's marker under concurrent `tools/list` and `tools/call`, global, group, and server-specific routes. Caller-supplied usernames, another user's route names, forged headers, and reused session IDs must never choose another binding.
- A user with no binding fails closed. Replacing/deleting Alice's binding invalidates her runtime while Bob continues working. Idle recycling, pod restart, and DB-backed restore retain isolation. Deleting a user/server removes its binding; renaming a server requires rebinding.
- `/api/credentials` reveals slot metadata and configured status, not values. `/api/credentials/:name` can only replace/delete the current user's complete binding. Test attempts to name another user, incomplete/extra slots, non-visible servers, and system-wide bearer tokens. Check server detail/export APIs, error responses, and logs for disclosure of synthetic headers or mock tool payloads.
- Verify self-service pages such as Credentials and OAuth client management against non-admin RBAC. Check copied connection URLs, including user routes such as `/<username>/mcp`, against the pinned UI/API. Do not assume a URL grants access, or that possession of someone else's URL selects their identity. Confirm percent-encoding for email-style OIDC usernames.
- A token with OAuth `read` scope is **not** a permission guarantee. Test attempts to invoke every mock write tool, credentials API, settings API, and inaccessible server. Keep write tools disabled irrespective of requested scopes until authorization has been demonstrated and approved.
- Confirm activity records contain metadata only, including after fresh bootstrap and restart. Review other logs separately; this setting is not a general log redactor. Confirm blocked private/link-local/metadata destinations and non-Traefik ingress really fail under the installed CNI. Public HTTPS egress is not a hostname allowlist.

Record failures and stop the trial rather than substituting a shared key. Hosted ChatGPT OAuth/DCR compatibility and Zitadel sign-in are separate tests that still need runtime verification. Test them only after mock isolation passes and an operator approves external access. No hosted/deployed success is claimed here.

## Manual Sparky connection after approval

The repository's `src/k8s/apps/sparky/backend-service.yaml` declares service `sparky-server`, port 3010, with name/component selectors matching the backend Deployment. The internal Streamable HTTP URL is:

```text
http://sparky-server.sparky.svc.cluster.local:3010/mcp
```

The app egress rule and the scoped Sparky ingress rule allow only the `mcphub` namespace's `app.kubernetes.io/name=mcphub` pods on TCP 3010. They do not install an upstream definition or credentials. Verify service/endpoints and `/mcp` support in staging before using the URL. HTTP is confined to this internal path; do not publish it or treat NetworkPolicy as encryption.

After mock acceptance, an administrator may manually create a shared definition through the UI. This is an example of the declaration, not a seed to install automatically:

```json
{
  "type": "streamable-http",
  "url": "http://sparky-server.sparky.svc.cluster.local:3010/mcp",
  "owner": "admin",
  "visibility": "group",
  "sharedWithUsers": ["<approved-alice-username>", "<approved-bob-username>"],
  "enabled": false,
  "credentialTemplate": [
    {
      "target": "headers",
      "name": "Authorization",
      "label": "Full personal Sparky Bearer header"
    }
  ]
}
```

Validate the pinned UI's sharing fields before saving. Each approved user enters their own complete literal header value `Bearer <personal-sparky-api-key>` in Credentials, including the `Bearer ` prefix. Do not use a variable-expansion placeholder as the saved value. Do not add a static Authorization header, shared environment key, passthrough header, upstream OAuth credential, or organization-wide fallback. These are per-user bindings, not a shared-key proxy.

Leave the definition disabled until explicitly approved. Then disable every write tool and leave tool enablement pending review of the actual discovered catalog. Adding or enabling a server may connect/discover tools, so do not do it with real credentials before approval. Even ostensibly read-only tools may expose health data. Approve named users, named tools, and allowed operations before any real call. Keep real writes disabled throughout the trial unless separately authorized.

## Persistence, backup, and restore

There is no app PVC. The database stores users, settings, upstream definitions, OAuth clients/tokens, and encrypted credential bindings. `/app/data` is disposable seed/temp state in this DB-backed, externally keyed deployment. Do not enable file-backed persistence or stdio workflows that depend on its contents surviving a pod replacement.

The Tandoor-style K8up `PreBackupPod` dumps DB `mcphub` in custom format using the CNPG app password and SSL `require`, without owner/privilege entries. Its service account and pod do not mount a service account token. The schedule is `55 7 * * *`, with B2 prefix `mcphub`, OpenBao `mcphub/backup.resticPassword`, and the existing `aws-ssm` B2 credentials. The inherited retention is last 5, daily 14, weekly 4; check weekly and prune weekly schedules also come from backup-base.

A successful schedule resource is not proof of a recoverable backup. Verify the first completed dump and perform a restore to an isolated database before admitting real personal data. DB replicas are not backups. Monitor backup/check failures and B2 retention separately from app health.

Keep the external credential encryption key backed up separately from DB dumps. Restoring ciphertext without the original key makes bindings unreadable. Retain the original restic password and B2 access needed to retrieve dumps. Restore JWT/Better Auth signing secrets where existing sessions must remain valid, or deliberately rotate them and revoke sessions. Never generate a replacement encryption key over existing bindings as a repair.

On restore, isolate network access before launching the app: restored server definitions may resume real upstream connections. Restore the DB, original encryption key, and required runtime secrets; validate the system baseline and mock two-user isolation again. Prefer revoking restored OAuth tokens and rotating personal upstream credentials after a security incident. Confirm that grants, sharing, bindings, and disabled tools survive an ordinary restart without turning on real writes.

## Decommission and retention

Agree on a trial end date and personal-data retention before collecting any data. On shutdown, disable upstreams, revoke per-user MCP/OAuth tokens and upstream API keys, and remove Zitadel client access. Stop public routing and GitOps reconciliation through the approved workflow. Remove the MCPHub-specific Sparky ingress rule when removing the app.

Do not assume Argo pruning deletes CNPG volumes or B2 dumps. Inventory DB PVCs, dumps, activity metadata, OAuth data, OpenBao versions, and local exports. Retain only the approved data and document who owns deletion. Keep the original encryption/restic keys until all retained backups have expired or been deleted, then remove secrets and OpenBao role/policy. Verify B2 and storage retention explicitly before declaring the trial decommissioned.

## Local checks

These commands render locally and do not contact the API server:

```sh
kubectl kustomize src/k8s/apps/mcphub
kubectl kustomize src/k8s/apps/sparky
kubectl kustomize src/k8s/apps
git diff --check
```

The apps-root output is the ApplicationSet, not rendered child apps. Check the new app separately. Server-side validation, deployment, mock acceptance, restore acceptance, real credentials, and hosted client tests require separate approval.
