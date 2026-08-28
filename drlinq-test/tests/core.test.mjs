import test from 'node:test';
import assert from 'node:assert/strict';

global.window = {
  DRLINQ_CONFIG: { BASE_PATH: '/drlinq-test/' },
  location: { origin: 'https://n8n.drlinq.ir', search: '' },
};

const core = await import('../assets/core.js');

test('normalizes Persian and Arabic keyboard variants', () => {
  assert.equal(core.normalizeText('  بيمه‌ دانا  '), 'بیمه دانا');
});

test('maps everyday dental language to the bank service', () => {
  assert.equal(core.resolveService('دندونم درد می‌کنه'), 'دندانپزشکی');
  assert.equal(core.resolveService('عصب کشی'), 'دندانپزشکی');
});

test('maps common diagnostics and imaging language', () => {
  assert.equal(core.resolveService('آزمایش خون'), 'آزمایشگاه');
  assert.equal(core.resolveService('ام آر آی'), 'رادیولوژی');
});

test('accepts a small typo in a known service', () => {
  assert.equal(core.resolveService('فیزوتراپی'), 'فیزیوتراپی');
});

test('uses an exact real API service when it is not curated', () => {
  assert.equal(core.resolveService('قلب و عروق', ['قلب و عروق']), 'قلب و عروق');
});

test('deduplicates provider rows while merging insurer evidence', () => {
  const rows = core.dedupeProviders([
    { id: '1', name: 'کلینیک آریانا', address: 'زیتون', phone: '0613818', insurers: ['بیمه آسیا'], services: ['دندانپزشکی'], sources: [] },
    { id: '2', name: 'کلينيک آريانا', address: 'زیتون', phone: '0613818', insurers: ['بیمه البرز'], services: ['دندانپزشکی'], sources: [] },
  ]);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].insurers.sort(), ['بیمه آسیا', 'بیمه البرز'].sort());
});

test('never marks an unsourced provider as verified', () => {
  assert.equal(core.verificationState([]).key, 'unverified');
  assert.equal(core.verificationState([{ source_type: 'secondary' }]).key, 'sourced');
  assert.equal(core.verificationState([{ source_type: 'official' }]).key, 'official');
});

test('shows known provider types in Persian', () => {
  assert.equal(core.providerTypeLabel('dentistry'), 'دندانپزشکی');
  assert.equal(core.providerTypeLabel('laboratory'), 'آزمایشگاه');
  assert.equal(core.providerTypeLabel('نوع ثبت‌شده'), 'نوع ثبت‌شده');
});

test('does not repeat the insurance prefix', () => {
  assert.equal(core.insurerFilterLabel('بیمه البرز'), 'بیمه البرز');
  assert.equal(core.insurerFilterLabel('البرز'), 'بیمه البرز');
});

test('creates a safe telephone link only from phone characters', () => {
  assert.equal(core.phoneHref('061-33337474'), '06133337474');
  assert.equal(core.isCallablePhone('ناموجود'), false);
});

test('builds links inside the isolated test path', () => {
  assert.equal(core.buildPageUrl('results.html', { city: 'اهواز' }), '/drlinq-test/results.html?city=%D8%A7%D9%87%D9%88%D8%A7%D8%B2');
});
