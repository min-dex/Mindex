import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import os from 'node:os';
import net from 'node:net';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

// No connection URL or production credentials are accepted by this harness.
export async function openWorshipTestDb({ requirePostgres = false } = {}) {
  const require = createRequire(path.resolve(process.env.PGLITE_ROOT || '.', 'package.json'));
  if (requirePostgres && process.env.WORSHIP_TEST_ENGINE !== 'postgres') {
    // Role/permission/lock semantics are not reproduced by PGlite; the documented
    // verification runs on a real PostgreSQL 17.6 (see docs/worship-atomic-*-check.md).
    console.log('SKIP requires WORSHIP_TEST_ENGINE=postgres (PostgreSQL 17.6) with embedded-postgres17/pg installed under PGLITE_ROOT; PGlite cannot model this test.');
    process.exit(0);
  }
  if (process.env.WORSHIP_TEST_ENGINE !== 'postgres') {
    let pglite;
    try { pglite = require.resolve('@electric-sql/pglite'); } catch {
      // Opt-in engine: it is not a project dependency, so skip instead of failing.
      console.log('SKIP @electric-sql/pglite not found. Install it in a temporary directory and set PGLITE_ROOT to run this test.');
      process.exit(0);
    }
    const { PGlite } = await import(pathToFileURL(pglite));
    return new PGlite();
  }
  const packageName = process.env.WORSHIP_TEST_PG_VERSION === '17.6' ? 'embedded-postgres17' : 'embedded-postgres';
  try { require.resolve(packageName); require.resolve('pg'); } catch {
    console.log(`SKIP ${packageName} and pg are not installed under PGLITE_ROOT; install them in a temporary directory to run this test.`);
    process.exit(0);
  }
  const { default: EmbeddedPostgres } = await import(pathToFileURL(require.resolve(packageName)));
  const { default: pg } = await import(pathToFileURL(require.resolve('pg')));
  const listener = net.createServer();
  await new Promise((resolve, reject) => { listener.once('error', reject); listener.listen(0, '127.0.0.1', resolve); });
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'mindex-pg-test-'));
  const password = randomUUID();
  const server = new EmbeddedPostgres({ databaseDir:path.join(dir,'db'), port,
    user:'postgres', password, authMethod:'scram-sha-256', persistent:false,
    postgresFlags:['-h','127.0.0.1','-k',dir], onLog:()=>{}, onError:()=>{} });
  const clients = new Set();
  const close = async () => {
    for (const client of clients) await client.end().catch(()=>{});
    await server.stop();
    await fs.rm(dir,{recursive:true,force:true});
  };
  const connect = async (database = 'postgres') => {
    const client = new pg.Client({host:'127.0.0.1',port,user:'postgres',password,database,
      connectionTimeoutMillis:5000,statement_timeout:10000});
    await client.connect(); clients.add(client);
    return client;
  };
  try {
    await server.initialise(); await server.start();
    const client = await connect();
    console.log('PostgreSQL:',(await client.query('show server_version')).rows[0].server_version);
    const restoreBackup = async () => {
      if (!process.env.WORSHIP_TEST_PG_BIN) throw new Error('WORSHIP_TEST_PG_BIN_REQUIRED');
      const run = promisify(execFile);
      const file = path.join(dir,'backup.dump');
      // Credentials always refer to this freshly created loopback-only cluster.
      const connection = ['--host=127.0.0.1',`--port=${port}`,'--username=postgres','--no-password'];
      const options = {env:{...process.env,PGPASSWORD:password},timeout:60000,maxBuffer:1024*1024};
      await run(path.join(process.env.WORSHIP_TEST_PG_BIN,'pg_dump'),
        [...connection,'--format=custom','--dbname=postgres',`--file=${file}`],options);
      await client.query('create database restored_backup template template0');
      await run(path.join(process.env.WORSHIP_TEST_PG_BIN,'pg_restore'),
        [...connection,'--exit-on-error','--single-transaction','--dbname=restored_backup',file],options);
      const restored = await connect('restored_backup');
      return {exec:sql=>restored.query(sql),query:(...args)=>restored.query(...args)};
    };
    return {exec:sql=>client.query(sql),query:(...args)=>client.query(...args),connect,restoreBackup,close};
  } catch(error) { await close(); throw error; }
}
