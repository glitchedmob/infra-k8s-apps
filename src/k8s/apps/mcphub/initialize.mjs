import '/app/node_modules/reflect-metadata/Reflect.js';
import { readFile } from 'node:fs/promises';

// Do not allow upstream's generated-password/signing-secret/key-file fallback.
const required = [
  'DB_URL', 'JWT_SECRET', 'BETTER_AUTH_SECRET',
  'MCPHUB_CREDENTIAL_ENCRYPTION_KEY', 'ADMIN_PASSWORD',
  'OIDC_CLIENT_ID', 'OIDC_CLIENT_SECRET',
];
for (const name of required) {
  if (!process.env[name]?.trim()) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
}
const key = process.env.MCPHUB_CREDENTIAL_ENCRYPTION_KEY.trim();
if (!/^[A-Za-z0-9+/]{43}=$/.test(key) || Buffer.from(key, 'base64').length !== 32) {
  throw new Error('MCPHUB_CREDENTIAL_ENCRYPTION_KEY must be 32 bytes encoded as base64');
}

const seed = JSON.parse(await readFile('/bootstrap/mcp_settings.json', 'utf8'));
let connection;
let exitCode = 1;
try {
  // Dynamic import follows reflect-metadata registration. This initializes the
  // DB and selects DB-backed DAOs before applying the trial system configuration.
  const { initializeDatabaseMode } = await import('/app/dist/utils/migration.js');
  connection = await import('/app/dist/db/connection.js');
  if (!(await initializeDatabaseMode())) {
    throw new Error('Database initialization failed; refusing to start MCPHub');
  }
  const { getSystemConfigDao } = await import('/app/dist/dao/DaoFactory.js');
  // v1.0.44's file migration omits activityLog. The seed alone is NOT enough.
  // Reapply only systemConfig on every startup, not users/servers/bindings.
  const updated = await getSystemConfigDao().update(seed.systemConfig);
  if (updated.activityLog?.storeToolPayload !== false) {
    throw new Error('Tool payload logging baseline was not applied');
  }
  exitCode = 0;
} catch {
  // Upstream initialization reports its own errors; never print environment data.
  console.error('MCPHub trial initialization failed; refusing to start');
} finally {
  if (connection) {
    try {
      const dataSource = connection.getAppDataSource();
      if (dataSource.isInitialized) await dataSource.destroy();
    } catch {
      console.error('MCPHub trial database cleanup failed');
      exitCode = 1;
    }
  }
}
// Upstream imports can keep handles alive. Exit only after awaiting the update
// and closing the main data source; sh -ec will not boot index.js on failure.
process.exit(exitCode);
