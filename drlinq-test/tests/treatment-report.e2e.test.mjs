import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright-core';

const port = 4179;
let server;
let browser;

test.before(async () => {
  server = spawn('python3', ['-m', 'http.server', String(port), '--bind', '127.0.0.1'], { cwd: new URL('..', import.meta.url).pathname, stdio: 'ignore' });
  await new Promise(resolve => setTimeout(resolve, 500));
  browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
});
test.after(async () => { await browser?.close(); server?.kill(); });

test('doctor publishes a token-protected report without leaking internal notes', { timeout: 45000 }, async () => {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(3000);
  const report = { id:'e2e-case',doctorToken:'d'.repeat(64),patientToken:'p'.repeat(64),status:'review',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),publishedAt:null,intake:{name:'بیمار تست',mobile:'09120000000',city:'اهواز',problem:'یک دندان از دست رفته',location:'دندان ۲۱'},overallSummary:'',internalNote:'',nextStep:'رزرو معاینه',offer:null,items:[] };
  await page.addInitScript(value => localStorage.getItem('drlinq_treatment_reports_v1') || localStorage.setItem('drlinq_treatment_reports_v1', JSON.stringify([value])), report);

  await page.goto(`http://127.0.0.1:${port}/patient-report.html?case=e2e-case&token=${report.patientToken}`);
  await page.getByText('پرونده شما در حال بررسی است.').waitFor();

  await page.goto(`http://127.0.0.1:${port}/doctor-report.html?case=e2e-case&token=${report.doctorToken}`);
  await page.getByRole('button', { name: '+ افزودن درمان' }).click();
  await page.getByRole('button', { name: '+ افزودن درمان' }).click();
  assert.equal(await page.locator('[data-item]').count(), 2);
  await page.locator('[data-remove]').last().click();
  assert.equal(await page.locator('[data-item]').count(), 1);
  const item = page.locator('[data-item]').first();
  await item.locator('[data-k="area"]').fill('دندان ۲۱');
  await item.locator('[data-k="treatmentId"]').selectOption('implant');
  await item.locator('[data-k="patientExplanation"]').fill('جایگزینی دندان از دست‌رفته با پایه ایمپلنت');
  await item.locator('[data-k="priority"]').selectOption('high');
  await item.locator('[data-k="condition"]').fill('پس از معاینه و بررسی CBCT');
  await item.locator('[data-k="priceMin"]').fill('25000000');
  await item.locator('[data-k="priceMax"]').fill('45000000');
  await item.locator('[data-k="internalNote"]').fill('ITEM SECRET 9341');
  await page.locator('#summary').fill('یک ناحیه برای درمان ایمپلنت بررسی شده است.');
  await page.locator('#internalNote').fill('OVERALL SECRET 7812');
  await page.locator('#offer').selectOption('discount');
  await page.locator('#offerDescription').fill('۱۰ درصد تخفیف پس از تأیید طرح درمان');
  await page.getByRole('button', { name: 'Save Draft' }).click();
  await page.reload();
  await page.getByText('دندان ۲۱').waitFor();
  const bypass = await context.newPage();
  await bypass.goto(`http://127.0.0.1:${port}/patient-report.html?case=e2e-case&token=${report.patientToken}&preview=1`);
  await bypass.getByText('پرونده شما در حال بررسی است.').waitFor();
  await bypass.close();
  await page.getByRole('button', { name: 'Publish' }).click();
  await page.getByText('گزارش منتشر شده است.').waitFor();

  await page.goto(`http://127.0.0.1:${port}/patient-report.html?case=e2e-case&token=${report.patientToken}`);
  await page.getByText('گزارش درمان شما').waitFor();
  assert.match(await page.locator('body').innerText(), /۲۵٬۰۰۰٬۰۰۰ تومان تا ۴۵٬۰۰۰٬۰۰۰ تومان/);
  assert.match(await page.locator('body').innerText(), /۱۰ درصد تخفیف/);
  assert.equal((await page.locator('body').innerText()).includes('SECRET'), false);

  await page.goto(`http://127.0.0.1:${port}/patient-report.html?case=e2e-case&token=wrong`);
  await page.getByText('لینک امن معتبر نیست').waitFor();
  await context.close();
});
