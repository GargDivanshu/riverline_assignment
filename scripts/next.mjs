import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';

if (existsSync('.env')) process.loadEnvFile('.env');
const action = process.argv[2];
if (!['dev', 'build'].includes(action)) throw new Error('Use dev or build.');
const args = ['node_modules/next/dist/bin/next', action, 'apps/web'];
if (action === 'dev') args.push('--hostname', '127.0.0.1');
const child = spawn(process.execPath, args, { stdio: 'inherit', env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' } });
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => child.kill(signal));
child.on('exit', code => process.exit(code ?? 1));
