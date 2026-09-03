import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const base = (process.env.DRLINQ_TEST_BASE || '').replace(/\/$/, '');
const doctorCode = process.env.DRLINQ_E2E_DOCTOR_CODE || '';
assert.ok(base.startsWith('https://'), 'DRLINQ_TEST_BASE must be HTTPS');
assert.ok(doctorCode.length >= 20, 'doctor E2E code is missing');

const png = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
);
const testRun = new Date().toISOString().replace(/[:.]/g, '-');
const patientName = `بیمار تست E2E ${testRun}`;
const doctorNote = `یادداشت تست پایدار ${testRun}`;
const browser = await chromium.launch({ headless: true });

try {
  const patientContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    userAgent: 'Mozilla/5.0 (Linux; Android 14; DrLinq-E2E) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36',
  });
  const patient = await patientContext.newPage();
  const patientErrors = [];
  patient.on('pageerror', error => patientErrors.push(error.message));
  await patient.goto(`${base}/implant-intake.html`, { waitUntil: 'networkidle' });

  await patient.locator('[data-problem="دندان از دست رفته دارم"]').click();
  await patient.locator('[data-count="۱ دندان"]').click();
  await patient.locator('#next').click();

  await patient.locator('[data-jaw="upper"]').click();
  await patient.locator('[data-part-upper="سمت راست"]').click();
  await patient.locator('[data-tooth="16"]').click();
  await patient.locator('#next').click();

  await patient.locator('[data-med="diabetes"]').click();
  await patient.locator('#diseaseText').fill('دیابت کنترل‌شده برای تست');
  await patient.locator('#medText').fill('متفورمین');
  await patient.locator('#next').click();

  await patient.locator('#file-opg').setInputFiles({ name: 'test-opg.png', mimeType: 'image/png', buffer: png });
  await patient.locator('[data-record-status="cbct|الان در دسترسم نیست"]').click();
  await patient.locator('#next').click();

  await patient.locator('#gallery-front').setInputFiles({ name: 'test-front.png', mimeType: 'image/png', buffer: png });
  for (const slot of ['upper', 'lower', 'right', 'left']) {
    await patient.locator(`[data-photo-skip="${slot}"]`).click();
  }
  await patient.locator('#next').click();

  await patient.locator('[data-suggested-question]').first().click();
  await patient.locator('[data-custom-question]').click();
  await patient.locator('#question').fill('آیا برای این کیس پیوند استخوان لازم است؟');
  await patient.locator('#name').fill(patientName);
  await patient.locator('#mobile').fill('09121234567');
  await patient.locator('#city').fill('اهواز');
  await patient.locator('#next').click();

  await patient.locator('#consent').check();
  await patient.locator('#next').click();
  await patient.getByText('پرونده شما ثبت شد').waitFor({ timeout: 30_000 });
  const caseId = (await patient.locator('[data-case-id]').textContent()).trim();
  assert.match(caseId, /^IMP-\d{8}-[0-9A-F]{6}$/);
  assert.deepEqual(patientErrors, [], `patient page errors: ${patientErrors.join('; ')}`);

  const saved = await patient.evaluate(() => JSON.parse(localStorage.getItem('drlinq_implant_pilot_v5')));
  const duplicatePayload = {
    submission_key: saved.submissionKey,
    name: saved.name,
    mobile: saved.mobile,
    city: saved.city,
    problem: saved.problem,
    missingCount: saved.missingCount,
    jaws: saved.jaws,
    jawParts: saved.jawParts,
    teeth: saved.teeth,
    medical: saved.medical,
    diseaseText: saved.diseaseText,
    medText: saved.medText,
    suggestedQuestions: saved.suggestedQuestions,
    question: saved.question,
    records: saved.records,
    photos: saved.photos,
    consent: saved.consent,
  };
  const duplicate = await patientContext.request.post(`${base}/implant-api/cases`, {
    multipart: { payload: JSON.stringify(duplicatePayload) },
  });
  assert.equal(duplicate.ok(), true);
  const duplicateData = await duplicate.json();
  assert.equal(duplicateData.created, false);
  assert.equal(duplicateData.case_id, caseId);
  await patientContext.close();

  const doctorContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const doctor = await doctorContext.newPage();
  const doctorErrors = [];
  doctor.on('pageerror', error => doctorErrors.push(error.message));
  await doctor.goto(`${base}/implant-doctor.html`, { waitUntil: 'networkidle' });
  await doctor.locator('#accessCode').fill(doctorCode);
  await doctor.locator('#loginForm button[type="submit"]').click();
  await doctor.getByRole('heading', { name: 'پرونده‌های ایمپلنت' }).waitFor();

  const row = doctor.locator(`[data-case-row="${caseId}"]`);
  await row.waitFor();
  assert.match(await row.textContent(), new RegExp(patientName));
  await row.locator('[data-open-case]').click();
  await doctor.getByRole('heading', { name: patientName }).waitFor();
  await doctor.locator('[data-file-slot="opg"] img[data-zoom-image]').waitFor({ timeout: 20_000 });
  await doctor.locator('[data-file-slot="front"] img[data-zoom-image]').waitFor({ timeout: 20_000 });
  assert.equal(await doctor.locator('[data-file-slot="cbct"]').textContent().then(text => text.includes('ارسال نشده')), true);
  for (const image of await doctor.locator('img[data-zoom-image]').all()) {
    assert.equal(await image.evaluate(element => element.complete && element.naturalWidth > 0), true);
  }
  await doctor.locator('[data-file-slot="opg"] img').click();
  await doctor.locator('#lightbox:not(.hidden)').waitFor();
  await doctor.locator('#lightbox button').click();

  await doctor.locator('#reviewStatus').selectOption('ready_for_consult');
  await doctor.locator('#doctorNote').fill(doctorNote);
  await doctor.locator('#saveReview').click();
  await doctor.getByText('ذخیره شد.').waitFor();

  await doctor.reload({ waitUntil: 'networkidle' });
  await doctor.getByRole('heading', { name: 'پرونده‌های ایمپلنت' }).waitFor();
  await doctor.locator(`[data-case-row="${caseId}"] [data-open-case]`).click();
  await doctor.getByRole('heading', { name: patientName }).waitFor();
  assert.equal(await doctor.locator('#reviewStatus').inputValue(), 'ready_for_consult');
  assert.equal(await doctor.locator('#doctorNote').inputValue(), doctorNote);
  assert.deepEqual(doctorErrors, [], `doctor page errors: ${doctorErrors.join('; ')}`);
  await doctorContext.close();

  console.log(JSON.stringify({
    result: 'PASS',
    case_id: caseId,
    patient_mobile_viewport: '390x844',
    doctor_desktop_viewport: '1440x1000',
    duplicate_prevented: true,
    opg_opened: true,
    intraoral_opened: true,
    review_persisted_after_refresh: true,
  }));
} finally {
  await browser.close();
}
