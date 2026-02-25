#!/usr/bin/env node

/*
Usage:
  ACTUAL_DATA_DIR=.actual-cache \
  ACTUAL_SERVER_URL=http://localhost:5006 \
  ACTUAL_PASSWORD=hunter2 \
  ACTUAL_SYNC_ID=1cfdbb80-6274-49bf-b0c2-737235a4c81f \
  node scripts/actual/get_budget_month.js 2026-01

Optional (if end-to-end encryption is enabled):
  ACTUAL_BUDGET_ENCRYPTION_PASSWORD=... node scripts/actual/get_budget_month.js 2026-01

Install dependency first (from repo root):
  npm install @actual-app/api dotenv
*/

const api = require('@actual-app/api');
const path = require('path');
const fs = require('fs');
require('dotenv').config({ path: path.resolve(__dirname, '..', '..', '.env'), quiet: true });
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const JSON_SENTINEL = '__LEDGERMIND_ACTUAL_JSON__:';

// Reserve stdout for the final machine-readable payload only.
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
  const month = process.argv[2];
  if (!month || !/^\d{4}-\d{2}$/.test(month)) {
    throw new Error('Usage: node scripts/actual/get_budget_month.js YYYY-MM');
  }
  return { month };
}

async function main() {
  const { month } = parseArgs();
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

    console.error(`[actual] getBudgetMonth month=${month}`);
    const budget = await api.getBudgetMonth(month);
    process.stdout.write(`${JSON_SENTINEL}${JSON.stringify(budget)}\n`);
  } finally {
    console.error('[actual] shutdown');
    await api.shutdown();
  }
}

main().catch((err) => {
  console.error('[actual] error:', err && err.stack ? err.stack : err);
  process.exitCode = 1;
});
