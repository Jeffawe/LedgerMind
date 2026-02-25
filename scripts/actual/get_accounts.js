#!/usr/bin/env node

/*
Usage:
  node scripts/actual/get_accounts.js

Required env (.env supported):
  ACTUAL_DATA_DIR=.actual-cache
  ACTUAL_SERVER_URL=http://localhost:5006
  ACTUAL_PASSWORD=...
  ACTUAL_SYNC_ID=...

Optional:
  ACTUAL_BUDGET_ENCRYPTION_PASSWORD=...

Install deps:
  npm install @actual-app/api dotenv
*/

const api = require('@actual-app/api');
const path = require('path');
const fs = require('fs');

require('dotenv').config({ path: path.resolve(__dirname, '..', '..', '.env'), quiet: true });

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const JSON_SENTINEL = '__LEDGERMIND_ACTUAL_JSON__:';

// Reserve stdout for one machine-readable payload.
console.log = (...args) => {
  process.stderr.write(`${args.map(String).join(' ')}\n`);
};

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    console.error(`[actual] cwd=${process.cwd()} dotenv_path=${path.resolve(__dirname, '..', '..', '.env')}`);
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

async function main() {
  const rawDataDir = requiredEnv('ACTUAL_DATA_DIR');
  const dataDir = path.isAbsolute(rawDataDir)
    ? rawDataDir
    : path.resolve(REPO_ROOT, rawDataDir);
  fs.mkdirSync(dataDir, { recursive: true });

  const serverURL = requiredEnv('ACTUAL_SERVER_URL');
  const password = requiredEnv('ACTUAL_PASSWORD');
  const syncId = requiredEnv('ACTUAL_SYNC_ID');
  const encryptionPassword = process.env.ACTUAL_BUDGET_ENCRYPTION_PASSWORD;

  console.error(`[actual] init server=${serverURL} dataDir=${dataDir}`);
  await api.init({ dataDir, serverURL, password });

  try {
    console.error(`[actual] downloadBudget syncId=${syncId}`);
    if (encryptionPassword) {
      await api.downloadBudget(syncId, { password: encryptionPassword });
    } else {
      await api.downloadBudget(syncId);
    }

    if (typeof api.getAccounts !== 'function') {
      throw new Error('This version of @actual-app/api does not expose getAccounts()');
    }

    console.error('[actual] getAccounts');
    const accounts = await api.getAccounts();
    process.stdout.write(`${JSON_SENTINEL}${JSON.stringify(accounts || [])}\n`);
  } finally {
    console.error('[actual] shutdown');
    await api.shutdown();
  }
}

main().catch((err) => {
  console.error('[actual] error:', err && err.stack ? err.stack : err);
  process.exitCode = 1;
});

