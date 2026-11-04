const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const sourceDir = process.argv[2];
assert.ok(sourceDir, 'pass the prepared openwrt-daede directory');
const source = fs.readFileSync(path.join(sourceDir,
  'luci-app-daede/htdocs/luci-static/resources/view/daede/backend.js'), 'utf8');

// Stub only router RPC I/O; execute the actual upstream module and promises.
function harness(options = {}) {
  const calls = [];
  const rpc = { declare: () => () => Promise.resolve({}) };
  const io = {
    stat: async () => ({}),
    write: async () => {},
    exec: async (command, args) => {
      if (command === '/bin/pidof' && options.pidError)
        throw new Error('process status RPC failed');
      if (command === '/bin/pidof')
        return { code: options.running === args[0] ? 0 : 1 };
      const call = [command, ...args].join(' ');
      calls.push(call);
      return { code: call === options.fail ? 1 : 0, stderr: 'fixture RPC failure' };
    }
  };
  const uci = { set: () => {}, load: async () => {}, get: () => 'daed' };
  const module = new Function('fs', 'rpc', 'uci', 'baseclass', 'L', source)(
    io, rpc, uci, { extend: value => value },
    { resolveDefault: (promise, fallback) => promise.catch(() => fallback) });
  return { module, calls };
}

async function testSwitch(name) {
  const { module, calls } = harness();
  await module.setActiveBackend(name);
  const selected = calls.indexOf(`/sbin/uci set daede.config.active_backend=${name}`);
  for (const backend of ['dae', 'daed']) {
    for (const command of [`/sbin/uci set ${backend}.config.enabled=0`,
      `/sbin/uci commit ${backend}`, `/etc/init.d/${backend} disable`]) {
      assert.ok(calls.indexOf(command) >= 0 && calls.indexOf(command) < selected,
        `${command} must persist before selecting ${name}`);
    }
  }
}

async function testFailures() {
  const brokenStatus = harness({ pidError: true });
  await assert.rejects(brokenStatus.module.setActiveBackend('daed'), /RPC failed/);
  assert.equal(brokenStatus.calls.length, 0);
  for (const running of ['dae', 'daed']) {
    const { module, calls } = harness({ running });
    await assert.rejects(module.setActiveBackend('daed'), /stop/i);
    assert.equal(calls.length, 0, 'running backend must not be modified');
  }
  for (const fail of ['/sbin/uci commit dae', '/etc/init.d/daed disable',
    '/sbin/uci commit daede']) {
    const { module, calls } = harness({ fail });
    await assert.rejects(module.setActiveBackend('daed'), /fixture RPC failure/);
    if (fail !== '/sbin/uci commit daede')
      assert.ok(!calls.some(call => call.includes('daede.config.active_backend=')));
  }
  const { module, calls } = harness();
  await assert.rejects(module.setActiveBackend('invalid'), /invalid backend/);
  assert.equal(calls.length, 0);
}

(async () => {
  await testSwitch('dae');
  await testSwitch('daed');
  await testFailures();
  console.log('daede switching persists exclusions and exposes RPC failures');
})().catch(error => { console.error(error); process.exitCode = 1; });
