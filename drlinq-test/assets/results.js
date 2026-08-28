import { searchProviders } from './api.js?v=1.0.1';
import {
  buildPageUrl,
  dedupeProviders,
  escapeHtml,
  isCallablePhone,
  phoneHref,
  searchParamsFromLocation,
  toPersianNumber,
  verificationState,
} from './core.js?v=1.0.1';

const $ = (id) => document.getElementById(id);
const filters = searchParamsFromLocation();
const resultList = $('resultList');
const loadMore = $('loadMore');
const pageSize = 24;
let rawItems = [];
let offset = 0;
let total = 0;
let hasMore = false;
let totalIsExact = true;
let loading = false;

function filterParams(overrides = {}) {
  return {
    service: filters.service,
    province: filters.province,
    city: filters.city,
    insurer: filters.insurer,
    ...overrides,
  };
}

function renderSummary() {
  const values = [
    filters.need || filters.service,
    filters.city,
    filters.province,
    filters.insurer || 'آزاد / بدون فیلتر بیمه',
  ].filter(Boolean);
  $('summaryChips').innerHTML = values.map((value) => `<span class="summary-chip">${escapeHtml(value)}</span>`).join('');
  const editParams = filterParams({ need: filters.need });
  $('editSearch').href = buildPageUrl('index.html', editParams);
  $('newSearch').href = window.DRLINQ_CONFIG.BASE_PATH;
  $('pageTitle').textContent = filters.city ? `مراکز درمانی در ${filters.city}` : 'مراکز درمانی مطابق جست‌وجوی شما';
}

function providerCard(item) {
  const verification = verificationState(item.sources);
  const insurers = (item.insurers || []).slice(0, 3);
  const address = item.address || [item.province, item.city, item.district].filter(Boolean).join('، ') || 'آدرس در این رکورد ثبت نشده';
  const detailUrl = buildPageUrl('provider.html', {
    id: item.id,
    location_id: item.location_id,
    ...filterParams({ need: filters.need }),
  });
  try {
    sessionStorage.setItem(`drlinq:provider:${item.id}:${item.location_id || ''}`, JSON.stringify(item));
  } catch {}
  const call = isCallablePhone(item.phone)
    ? `<a class="call-button" href="tel:${phoneHref(item.phone)}" aria-label="تماس با ${escapeHtml(item.name)}">تماس</a>`
    : '';
  const matchParts = [filters.service && `خدمت ${filters.service}`, filters.city && `شهر ${filters.city}`, filters.insurer && `بیمه ${filters.insurer}`].filter(Boolean);
  return `
    <article class="provider-card">
      <div class="provider-card-head">
        <div>
          <h2>${escapeHtml(item.name || 'مرکز درمانی')}</h2>
          <div class="badges">
            <span class="badge ${verification.tone}">${escapeHtml(verification.label)}</span>
            ${item.provider_type ? `<span class="badge">${escapeHtml(item.provider_type)}</span>` : ''}
            ${insurers.map((value) => `<span class="badge insurance">${escapeHtml(value)}</span>`).join('')}
            ${(item.insurers || []).length > 3 ? `<span class="badge">+${toPersianNumber(item.insurers.length - 3)} بیمه</span>` : ''}
          </div>
        </div>
      </div>
      <p class="provider-address">⌖ ${escapeHtml(address)}</p>
      <div class="match-line">مطابق با ${escapeHtml(matchParts.join('، '))}</div>
      <div class="provider-card-actions">
        <a class="primary-button" href="${detailUrl}">مشاهده جزئیات</a>
        ${call}
      </div>
    </article>`;
}

function renderResults() {
  const rows = dedupeProviders(rawItems);
  resultList.innerHTML = rows.map(providerCard).join('');
  $('resultStatus').textContent = totalIsExact
    ? `${toPersianNumber(total)} رکورد منطبق در بانک پیدا شد؛ موارد تکراری در نمایش ادغام می‌شوند.`
    : `${toPersianNumber(rows.length)} مرکز منطبق تا اینجا نمایش داده شده؛ تعداد نهایی از API فعلی در دسترس نیست.`;
  loadMore.hidden = !hasMore;
}

function emptyState() {
  const removeInsurance = filters.insurer
    ? `<a class="secondary-button" href="${buildPageUrl('results.html', filterParams({ need: filters.need, insurer: '' }))}">جست‌وجو بدون بیمه</a>`
    : '';
  const wholeProvince = filters.city
    ? `<a class="secondary-button" href="${buildPageUrl('results.html', filterParams({ need: filters.need, city: '' }))}">جست‌وجو در کل استان</a>`
    : '';
  resultList.innerHTML = `
    <div class="state-card">
      <div class="state-icon">⌕</div>
      <h2>برای این ترکیب، رکورد منطبق پیدا نشد</h2>
      <p>پوشش بانک هنوز کامل نیست. برای دیدن گزینه‌های واقعی بیشتر فقط یک محدودیت را تغییر بده؛ نتیجه‌ای ساخته یا حدس زده نمی‌شود.</p>
      <div class="state-actions">${removeInsurance}${wholeProvince}<a class="primary-button" href="${buildPageUrl('index.html', filterParams({ need: filters.need }))}">ویرایش کامل جست‌وجو</a></div>
    </div>`;
  $('resultStatus').textContent = 'نتیجه‌ای در پوشش فعلی بانک ثبت نشده است.';
  loadMore.hidden = true;
}

function errorState() {
  resultList.innerHTML = `
    <div class="state-card">
      <div class="state-icon">!</div>
      <h2>دریافت نتایج انجام نشد</h2>
      <p>اطلاعات ساختگی نمایش داده نمی‌شود. چند لحظه دیگر دوباره تلاش کن.</p>
      <div class="state-actions"><button id="retryButton" class="primary-button" type="button">تلاش دوباره</button></div>
    </div>`;
  $('resultStatus').textContent = 'ارتباط با بانک مراکز برقرار نشد.';
  $('retryButton').addEventListener('click', () => load(true));
  loadMore.hidden = true;
}

async function load(reset = false) {
  if (loading) return;
  loading = true;
  if (reset) {
    offset = 0;
    rawItems = [];
    total = 0;
    hasMore = false;
    totalIsExact = true;
    resultList.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  }
  loadMore.disabled = true;
  loadMore.textContent = 'در حال دریافت…';
  try {
    const data = await searchProviders({ ...filterParams(), limit: pageSize, offset });
    total = data.total || 0;
    rawItems.push(...(data.items || []));
    offset += data.items?.length || 0;
    hasMore = data.has_more ?? rawItems.length < total;
    totalIsExact = data.total_is_exact !== false;
    if (!rawItems.length) emptyState();
    else renderResults();
  } catch {
    if (!rawItems.length) errorState();
  } finally {
    loading = false;
    loadMore.disabled = false;
    loadMore.textContent = 'نمایش مراکز بیشتر';
  }
}

loadMore.addEventListener('click', () => load());
renderSummary();

if (!filters.service || !filters.province) {
  window.location.replace(buildPageUrl('index.html'));
} else {
  load(true);
}
