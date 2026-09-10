import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';

if (existsSync('.env')) {
  console.log('.env already exists; left unchanged.');
} else {
  const config = readFileSync('.env.example', 'utf8')
    .replace('BETTER_AUTH_SECRET=', `BETTER_AUTH_SECRET=${randomBytes(32).toString('hex')}`)
    .replace('INTERNAL_API_SECRET=', `INTERNAL_API_SECRET=${randomBytes(32).toString('hex')}`);
  writeFileSync('.env', config, { mode: 0o600 });
  console.log('Created ignored .env with random local secrets. No keys printed.');
}
