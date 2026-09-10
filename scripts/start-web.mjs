import { spawnSync, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';

if (existsSync('.env')) process.loadEnvFile('.env');

const migration = spawnSync(process.execPath, ['--import', 'tsx', 'apps/web/scripts/migrate.ts'], { stdio: 'inherit' });
if (migration.status !== 0) process.exit(migration.status ?? 1);
const server = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', 'apps/web', '--hostname', '0.0.0.0'], { stdio: 'inherit' });
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.kill(signal));
server.on('exit', code => process.exit(code ?? 1));
