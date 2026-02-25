#!/usr/bin/env node

/*
Usage:
  node scripts/actual/get_transactions.js 2026-02-01 2026-02-29

Required env (.env supported):
  ACTUAL_DATA_DIR=.actual-cache
  ACTUAL_SERVER_URL=http://localhost:5006
  ACTUAL_PASSWORD=...
  ACTUAL_SYNC_ID=...

Optional:
  ACTUAL_BUDGET_ENCRYPTION_PASSWORD=...
  ACTUAL_ACCOUNT_IDS=acc1,acc2   # if omitted, script tries api.getAccounts()

Install deps:
  npm install @actual-app/api dotenv
*/

const api = require('@actual-app/api');
const path = require('path');
const fs = require('fs');

require('dotenv').config({ path: path.resolve(__dirname, '..', '..', '.env'), quiet: true });

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const JSON_SENTINEL = '__LEDGERMIND_ACTUAL_JSON__:';

// Reserve stdout for a single machine-readable payload line.
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

function parseArgs() {
  const start = process.argv[2];
  const end = process.argv[3];
  const isoDateRe = /^\d{4}-\d{2}-\d{2}$/;
  if (!start || !end || !isoDateRe.test(start) || !isoDateRe.test(end)) {
    throw new Error('Usage: node scripts/actual/get_transactions.js YYYY-MM-DD YYYY-MM-DD');
  }
  return { start, end };
}

async function resolveAccountIds() {
  const envAccountIds = process.env.ACTUAL_ACCOUNT_IDS;
  if (envAccountIds) {
    return envAccountIds.split(',').map((s) => s.trim()).filter(Boolean);
  }

  if (typeof api.getAccounts === 'function') {
    const accounts = await api.getAccounts();
    return (accounts || []).map((a) => a.id).filter(Boolean);
  }

  throw new Error('No account IDs available. Set ACTUAL_ACCOUNT_IDS or use an API version with getAccounts().');
}

async function getAllTransactions(accountIds, start, end) {
  const rows = [];
  for (const accountId of accountIds) {
    const txns = await api.getTransactions(accountId, start, end);
    for (const txn of txns || []) {
      rows.push({ accountId, ...txn });
    }
  }
  return rows;
}

async function main() {
  const { start, end } = parseArgs();
  console.error(`[actual] node execPath=${process.execPath} version=${process.version}`);

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

    const accountIds = await resolveAccountIds();
    console.error(`[actual] accounts count=${accountIds.length}`);
    console.error(`[actual] getTransactions start=${start} end=${end}`);

    const transactions = await getAllTransactions(accountIds, start, end);
    process.stdout.write(`${JSON_SENTINEL}${JSON.stringify(transactions)}\n`);
  } finally {
    console.error('[actual] shutdown');
    await api.shutdown();
  }
}

main().catch((err) => {
  console.error('[actual] error:', err && err.stack ? err.stack : err);
  process.exitCode = 1;
});
