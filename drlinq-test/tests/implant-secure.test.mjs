import assert from 'node:assert/strict';
import fs from 'node:fs';

const intakeAddon = fs.readFileSync(new URL('../implant-intake-secure.js', import.meta.url), 'utf8');
const doctorAddon = fs.readFileSync(new URL('../implant-doctor-patient.js', import.meta.url), 'utf8');
const patientCase = fs.readFileSync(new URL('../implant-case.html', import.meta.url), 'utf8');
const containerfile = fs.readFileSync(new URL('../Containerfile', import.meta.url), 'utf8');

assert.doesNotThrow(() => new Function(intakeAddon), 'intake secure addon must parse');
assert.doesNotThrow(() => new Function(doctorAddon), 'doctor patient-response addon must parse');
const inlineScripts = [...patientCase.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)].map(match => match[1]);
assert.equal(inlineScripts.length, 1);
assert.doesNotThrow(() => new Function(inlineScripts[0]), 'patient case inline script must parse');
assert.match(intakeAddon, /patient_access_token/);
assert.match(intakeAddon, /data-secure-case-url/);
assert.match(doctorAddon, /یادداشت داخلی پزشک/);
assert.match(doctorAddon, /patient-response/);
assert.match(doctorAddon, /responsePublishedAt/);
assert.match(patientCase, /data-patient-response/);
assert.match(patientCase, /پرونده شما در حال بررسی است/);
assert.doesNotMatch(patientCase, /doctor_note/);
assert.match(containerfile, /implant-intake-secure\.js/);
assert.match(containerfile, /implant-doctor-patient\.js/);

console.log('implant secure doctor-to-patient shell: PASS');
