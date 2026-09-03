import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';

const values = new Map();
global.localStorage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
global.crypto = webcrypto;
const reports = await import('../assets/treatment-report.js');

test('ships persistent treatment and offer libraries', () => {
  assert.deepEqual(reports.treatmentLibrary().map(x => x.id), ['restoration','root_canal','crown','extraction','scaling','implant','bone_graft','sinus_lift','periodontal_treatment','prosthesis']);
  assert.deepEqual(reports.offerLibrary().map(x => x.id), ['discount','gift','package']);
  assert.ok(values.has('drlinq_treatment_library_v1'));
  assert.ok(values.has('drlinq_offer_library_v1'));
});

test('creates separate strong doctor and patient tokens', () => {
  const item = reports.createCase({ name: 'بیمار تست' });
  assert.match(item.doctorToken, /^[a-f0-9]{64}$/);
  assert.match(item.patientToken, /^[a-f0-9]{64}$/);
  assert.notEqual(item.doctorToken, item.patientToken);
  assert.equal(reports.authorizeDoctor(item, item.doctorToken), true);
  assert.equal(reports.authorizePatient(item, item.doctorToken), false);
});

test('hides draft and strips every internal note from patient view', () => {
  const draft = reports.createCase({});
  draft.overallSummary = 'خلاصه';
  draft.internalNote = 'internal overall secret';
  draft.items = [{ id:'1',area:'21',treatmentId:'implant',treatmentLabel:'ایمپلنت',patientExplanation:'توضیح',priority:'high',priceMin:10,priceMax:20,condition:'CBCT',internalNote:'internal item secret' }];
  assert.equal(reports.patientView(draft), null);
  draft.status = 'published';
  const view = reports.patientView(draft);
  assert.equal(JSON.stringify(view).includes('secret'), false);
  assert.deepEqual(reports.totalEstimate(view.items), { min: 10, max: 20 });
});

test('validates required report data and price ranges', () => {
  assert.ok(reports.validateReport({ overallSummary:'', items:[] }).length >= 2);
  assert.deepEqual(reports.validateReport({ overallSummary:'آماده',items:[{area:'21',treatmentId:'implant',patientExplanation:'توضیح',priceMin:10,priceMax:20}]}), []);
});
