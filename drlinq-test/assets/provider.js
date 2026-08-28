import { getProvider } from './api.js?v=1.0.1';
import {
  buildPageUrl,
  displayDate,
  escapeHtml,
  isCallablePhone,
  phoneHref,
  safeExternalUrl,
  searchParamsFromLocation,
  verificationState,
} from './core.js?v=1.0.1';

const root = document.getElementById('detailRoot');
const query = new URLSearchParams(window.location.search);
const id = query.get('id') || '';
const locationId = query.get('location_id') || '';
const search = searchParamsFromLocation();

function resultsUrl() {
  const params = { ...search };
  return search.service && search.province ? buildPageUrl('results.html', params) : buildPageUrl('index.html');
}

function sourceItem(source) {
  const url = safeExternalUrl(source.url);
  const date = displayDate(source.last_verified_at || source.last_seen_at);
  const type = source.source_type === 'official' ? 'منبع رسمی' : 'منبع ثبت‌شده';
  return `
    <div class="source-item">
      <strong>${escapeHtml(source.name || 'منبع اطلاعات')}</strong>
      <small>${escapeHtml(type)}${date ? ` · آخرین ثبت/بررسی: ${escapeHtml(date)}` : ''}</small>
      ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">مشاهده منبع</a>` : ''}
    </div>`;
}

function render(data) {
  const location = data.locations?.[0] || {};
  const sources = location.sources || [];
  const verification = verificationState(sources);
  const address = location.address || [location.province, location.city, location.district].filter(Boolean).join('، ') || 'در این رکورد ثبت نشده';
  const phone = location.phone || data.phone || '';
  const website = safeExternalUrl(data.website);
  const insurers = location.insurers || [];
  document.title = `${data.name || 'مرکز درمانی'} | دکتر لینک`;

  root.innerHTML = `
    <section class="detail-hero">
      <a class="back-link" href="${resultsUrl()}">→ بازگشت به نتایج</a>
      <div class="badges"><span class="badge ${verification.tone}">${escapeHtml(verification.label)}</span>${data.provider_type ? `<span class="badge">${escapeHtml(data.provider_type)}</span>` : ''}</div>
      <h1>${escapeHtml(data.name || 'مرکز درمانی')}</h1>
      <p>${escapeHtml([location.district, location.city, location.province].filter(Boolean).join('، '))}</p>
      <div class="detail-actions">
        ${isCallablePhone(phone) ? `<a class="call-button" href="tel:${phoneHref(phone)}">تماس با مرکز</a>` : ''}
        ${website ? `<a class="secondary-button" href="${escapeHtml(website)}" target="_blank" rel="noopener noreferrer">وب‌سایت مرکز</a>` : ''}
      </div>
    </section>

    <div class="detail-grid">
      <div>
        <section class="detail-card">
          <h2>اطلاعات مرکز</h2>
          <dl class="fact-list">
            <div class="fact"><dt>آدرس</dt><dd>${escapeHtml(address)}</dd></div>
            <div class="fact"><dt>تلفن</dt><dd>${phone ? escapeHtml(phone) : 'در این رکورد ثبت نشده'}</dd></div>
            <div class="fact"><dt>نوع مرکز</dt><dd>${escapeHtml(data.provider_type || 'در این رکورد ثبت نشده')}</dd></div>
            ${data.medical_license_no ? `<div class="fact"><dt>شماره مجوز</dt><dd>${escapeHtml(data.medical_license_no)}</dd></div>` : ''}
          </dl>
        </section>
        <section class="detail-card">
          <h2>خدمات ثبت‌شده</h2>
          <div class="badges">${(data.services || []).length ? data.services.map((value) => `<span class="badge">${escapeHtml(value)}</span>`).join('') : '<span class="badge muted">خدمت تفصیلی در این رکورد ثبت نشده</span>'}</div>
        </section>
        <section class="detail-card">
          <h2>بیمه‌های ثبت‌شده</h2>
          <div class="badges">${insurers.length ? insurers.map((value) => `<span class="badge insurance">${escapeHtml(value)}</span>`).join('') : '<span class="badge muted">رابطه بیمه‌ای در این رکورد ثبت نشده</span>'}</div>
        </section>
      </div>

      <aside>
        <section class="detail-card">
          <h2>منبع و اعتبار اطلاعات</h2>
          <div class="source-list">${sources.length ? sources.map(sourceItem).join('') : '<div class="source-item"><strong>منبع قابل نمایش ثبت نشده</strong><small>این رکورد نیازمند بازبینی مجدد است.</small></div>'}</div>
        </section>
        <section class="side-card">
          <h2>قبل از حرکت تماس بگیر</h2>
          <p>پذیرش بیمه، ارائهٔ خدمت و ساعت فعالیت ممکن است تغییر کند. دکتر لینک نوبت خالی یا قیمت را در این مرحله نمایش نمی‌دهد.</p>
        </section>
      </aside>
    </div>`;
}

function renderError(notFound = false) {
  root.innerHTML = `
    <div class="state-card">
      <div class="state-icon">!</div>
      <h2>${notFound ? 'این رکورد پیدا نشد' : 'دریافت اطلاعات انجام نشد'}</h2>
      <p>${notFound ? 'ممکن است رکورد حذف یا ادغام شده باشد.' : 'چند لحظه دیگر دوباره تلاش کن؛ اطلاعات ساختگی نمایش داده نمی‌شود.'}</p>
      <div class="state-actions"><a class="primary-button" href="${resultsUrl()}">بازگشت به نتایج</a>${notFound ? '' : '<button id="retryButton" class="secondary-button" type="button">تلاش دوباره</button>'}</div>
    </div>`;
  document.getElementById('retryButton')?.addEventListener('click', load);
}

async function load() {
  if (!id) {
    renderError(true);
    return;
  }
  try {
    const cached = JSON.parse(sessionStorage.getItem(`drlinq:provider:${id}:${locationId}`) || 'null');
    if (cached) {
      render({
        ...cached,
        services: cached.services || [],
        locations: [{
          location_id: cached.location_id || '',
          province: cached.province,
          city: cached.city,
          district: cached.district,
          address: cached.address,
          latitude: cached.latitude,
          longitude: cached.longitude,
          phone: cached.phone,
          insurers: cached.insurers || [],
          sources: cached.sources || [],
        }],
      });
      return;
    }
  } catch {}
  try {
    render(await getProvider(id, locationId, {
      service: search.service,
      insurer: search.insurer,
      province: search.province,
      city: search.city,
      district: search.district,
    }));
  } catch (error) {
    renderError(error.status === 404);
  }
}

load();
