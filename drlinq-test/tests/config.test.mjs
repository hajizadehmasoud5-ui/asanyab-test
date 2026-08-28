import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../assets/config.js', import.meta.url), 'utf8');

function loadConfig(hostname, pathname) {
  const context = { window: { location: { hostname, pathname } } };
  vm.runInNewContext(source, context);
  return context.window.DRLINQ_CONFIG;
}

test('production uses root links and the isolated read-only API', () => {
  const config = loadConfig('drlinq.ir', '/');
  assert.equal(config.BASE_PATH, '/');
  assert.equal(config.API_BASE, 'https://n8n.drlinq.ir/drlinq-test/api');
});

test('isolated test uses same-origin API routing', () => {
  const config = loadConfig('n8n.drlinq.ir', '/drlinq-test/');
  assert.equal(config.BASE_PATH, '/drlinq-test/');
  assert.equal(config.API_BASE, '/drlinq-test/api');
});
