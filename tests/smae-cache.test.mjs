import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const scope = 'https://example.test/curso/smae/';
const worker = await readFile(new URL('../smae/sw.js', import.meta.url), 'utf8');

test('actualiza solo la caché propia y lee la guía vigente aun sin red', async () => {
  const stores = new Map();
  const listeners = new Map();
  const keys = name => [...stores.get(name).keys()].map(url => ({ url }));
  const caches = {
    async open(name) {
      if (!stores.has(name)) stores.set(name, new Map());
      const entries = stores.get(name);
      return {
        keys: async () => keys(name),
        addAll: async paths => paths.forEach(path => entries.set(new URL(path, scope).href, 'vigente')),
        match: async request => entries.get(request.url.split('?')[0]),
      };
    },
    async keys() { return [...stores.keys()]; },
    async delete(name) { return stores.delete(name); },
    async match(request, { cacheName } = {}) {
      for (const name of cacheName ? [cacheName] : stores.keys()) {
        const response = await (await this.open(name)).match(request);
        if (response) return response;
      }
    },
  };
  const help = scope + 'ayuda.html';
  const other = 'https://example.test/otra/ayuda.html';
  const ownPrevious = 'smae:' + encodeURIComponent(scope) + ':prueba-anterior';
  const otherVersion = 'smae:' + encodeURIComponent('https://example.test/otra/') + ':v0.6.12';
  stores.set(ownPrevious, new Map([[help, 'anterior']]));
  stores.set(otherVersion, new Map([[other, 'vigente de otra instalación']]));
  stores.set('otra-aplicacion', new Map([[help, 'ajena']]));
  stores.set('smae-v0.6.10', new Map([[help, 'anterior']]));
  stores.set('smae-v0.6.11', new Map([[help, 'anterior'], [other, 'compartida']]));
  const self = {
    registration: { scope },
    clients: { async claim() {} },
    addEventListener: (name, fn) => listeners.set(name, fn),
  };
  vm.runInNewContext(worker, {
    self, caches, URL, location: new URL(scope),
    fetch: async () => { throw new Error('offline'); },
  });
  for (const event of ['install', 'activate']) {
    let pending;
    listeners.get(event)({ waitUntil: promise => { pending = promise; } });
    await pending;
  }
  assert.equal(stores.get('otra-aplicacion')?.get(help), 'ajena');
  assert.equal(stores.has(ownPrevious), false);
  assert.equal(stores.get(otherVersion)?.get(other), 'vigente de otra instalación');
  assert.equal(stores.has('smae-v0.6.10'), false);
  assert.equal(stores.get('smae-v0.6.11')?.get(other), 'compartida');
  let reply;
  listeners.get('fetch')({
    request: { method: 'GET', url: help + '?unidad=1' },
    respondWith: promise => { reply = promise; },
  });
  assert.equal(await reply, 'vigente');
});
