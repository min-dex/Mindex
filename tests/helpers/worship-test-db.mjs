import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import os from 'node:os';
import net from 'node:net';
import { randomUUID } from 'node:crypto';

// No connection URL or production credentials are accepted by this harness.
export async function openWorshipTestDb() {
  const require = createRequire(path.resolve(process.env.PGLITE_ROOT || '.', 'package.json'));
  if (process.env.WORSHIP_TEST_ENGINE !== 'postgres') {
    const { PGlite } = await import(pathToFileURL(require.resolve('@electric-sql/pglite')));
    return new PGlite();
  }
  const packageName = process.env.WORSHIP_TEST_PG_VERSION === '17.6' ? 'embedded-postgres17' : 'embedded-postgres';
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
  const connect = async () => {
    const client = new pg.Client({host:'127.0.0.1',port,user:'postgres',password,database:'postgres',
      connectionTimeoutMillis:5000,statement_timeout:10000});
    await client.connect(); clients.add(client);
    return client;
  };
  try {
    await server.initialise(); await server.start();
    const client = await connect();
    console.log('PostgreSQL:',(await client.query('show server_version')).rows[0].server_version);
    return {exec:sql=>client.query(sql),query:(...args)=>client.query(...args),connect,close};
  } catch(error) { await close(); throw error; }
}
