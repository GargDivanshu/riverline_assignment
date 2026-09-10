// Development/verification fallback only. The submission runtime uses real Postgres.
import { PGlite } from '@electric-sql/pglite';
import { PGLiteSocketServer } from '@electric-sql/pglite-socket';
import { mkdirSync } from 'node:fs';

mkdirSync('.local', { recursive: true });
const db = await PGlite.create('.local/dev-postgres');
const server = new PGLiteSocketServer({ db, host: '127.0.0.1', port: 15432 });
await server.start();
console.log('Local development database listening on 127.0.0.1:15432. Not for production.');
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, async () => {
  await server.stop();
  await db.close();
  process.exit(0);
});
