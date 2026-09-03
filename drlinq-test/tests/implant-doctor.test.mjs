import assert from 'node:assert/strict';
import fs from 'node:fs';

const patient = fs.readFileSync(new URL('../implant-intake.html', import.meta.url), 'utf8');
const doctor = fs.readFileSync(new URL('../implant-doctor.html', import.meta.url), 'utf8');

for (const [name, html] of [['patient', patient], ['doctor', doctor]]) {
  const scripts = [...html.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)].map(match => match[1]);
  assert.equal(scripts.length, 1, `${name} must have exactly one inline app script`);
  assert.doesNotThrow(() => new Function(scripts[0]), `${name} inline JavaScript must parse`);
}

assert.match(patient, /new FormData\(\)/);
assert.match(patient, /implant-api/);
assert.match(patient, /submission_key/);
assert.match(patient, /پرونده شما ثبت شد/);
assert.match(patient, /12\*1024\*1024/);
assert.doesNotMatch(patient, /class="mouthchart"/, 'legacy CBCT asset must not replace the live tooth controls');
assert.match(doctor, /Authorization/);
assert.match(doctor, /sessionStorage/);
assert.match(doctor, /ready_for_consult/);
assert.match(doctor, /data-file-slot/);
assert.match(doctor, /ذخیره وضعیت و یادداشت/);

console.log('implant patient/doctor integration shell: PASS');
