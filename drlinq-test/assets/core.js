export const SERVICE_CATALOG = [
  {
    value: 'دندانپزشکی',
    label: 'دندانپزشکی',
    hint: 'دندان‌درد، ترمیم، عصب‌کشی، روکش، ایمپلنت',
    aliases: ['دندان', 'دندون', 'دندان درد', 'دندون درد', 'پوسیدگی', 'پر کردن دندان', 'ترمیم دندان', 'عصب کشی', 'درمان ریشه', 'روکش', 'جرم گیری', 'ایمپلنت', 'ارتودنسی', 'کشیدن دندان'],
  },
  {
    value: 'آزمایشگاه',
    label: 'آزمایشگاه',
    hint: 'آزمایش خون، ژنتیک، پاتولوژی',
    aliases: ['آزمایش', 'ازمایش', 'آزمایش خون', 'تست خون', 'پاتولوژی', 'آزمایش ژنتیک', 'پی سی آر', 'pcr'],
  },
  {
    value: 'رادیولوژی',
    label: 'تصویربرداری',
    hint: 'رادیولوژی، سونوگرافی، MRI، CT',
    aliases: ['تصویربرداری', 'عکس برداری', 'عکسبرداری', 'رادیولوژی', 'سونوگرافی', 'ام آر آی', 'mri', 'سی تی اسکن', 'ct scan', 'ماموگرافی'],
  },
  {
    value: 'فیزیوتراپی',
    label: 'فیزیوتراپی و توانبخشی',
    hint: 'فیزیوتراپی، کاردرمانی، گفتاردرمانی',
    aliases: ['فیزیوتراپی', 'توانبخشی', 'کاردرمانی', 'گفتار درمانی', 'گفتاردرمانی', 'آب درمانی'],
  },
  {
    value: 'داروخانه',
    label: 'داروخانه',
    hint: 'داروخانه و خدمات دارویی',
    aliases: ['دارو', 'داروخانه', 'نسخه', 'داروخانه شبانه روزی'],
  },
  {
    value: 'پزشک عمومی',
    label: 'پزشک عمومی',
    hint: 'معاینه عمومی و خدمات پزشکی پایه',
    aliases: ['دکتر عمومی', 'پزشک عمومی', 'پزشک خانواده', 'معاینه عمومی', 'ویزیت عمومی'],
  },
  {
    value: 'درمانگاه',
    label: 'درمانگاه و کلینیک',
    hint: 'مرکز درمانی چندخدمتی',
    aliases: ['درمانگاه', 'کلینیک', 'مرکز درمانی', 'پلی کلینیک'],
  },
  {
    value: 'بیمارستان',
    label: 'بیمارستان',
    hint: 'خدمات بیمارستانی غیر اورژانسی',
    aliases: ['بیمارستان', 'بستری', 'مرکز بیمارستانی'],
  },
];

export function normalizeText(value = '') {
  return String(value)
    .toLowerCase()
    .replace(/[يى]/g, 'ی')
    .replace(/ك/g, 'ک')
    .replace(/ة/g, 'ه')
    .replace(/[‌‏‎]/g, ' ')
    .replace(/[ـًٌٍَُِّْ]/g, '')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function levenshtein(a, b) {
  const x = normalizeText(a);
  const y = normalizeText(b);
  if (!x) return y.length;
  if (!y) return x.length;
  const previous = Array.from({ length: y.length + 1 }, (_, index) => index);
  for (let i = 1; i <= x.length; i += 1) {
    let diagonal = previous[0];
    previous[0] = i;
    for (let j = 1; j <= y.length; j += 1) {
      const above = previous[j];
      previous[j] = Math.min(
        previous[j] + 1,
        previous[j - 1] + 1,
        diagonal + (x[i - 1] === y[j - 1] ? 0 : 1),
      );
      diagonal = above;
    }
  }
  return previous[y.length];
}

export function resolveService(input, apiServices = []) {
  const query = normalizeText(input);
  if (!query) return null;

  for (const item of SERVICE_CATALOG) {
    const terms = [item.value, item.label, ...item.aliases];
    const normalizedTerms = terms.map(normalizeText);
    if (normalizedTerms.includes(query)) return item.value;
    if (normalizedTerms.some((term) => term.length > 3 && (query.includes(term) || term.includes(query)))) {
      return item.value;
    }
  }

  const exactApi = apiServices.find((service) => normalizeText(service) === query);
  if (exactApi) return exactApi;

  const candidates = [
    ...SERVICE_CATALOG.flatMap((item) => [item.value, item.label, ...item.aliases].map((term) => ({ term, value: item.value }))),
    ...apiServices.map((term) => ({ term, value: term })),
  ];
  let best = null;
  for (const candidate of candidates) {
    const term = normalizeText(candidate.term);
    if (Math.abs(term.length - query.length) > 2) continue;
    const distance = levenshtein(query, term);
    if (distance <= 2 && (!best || distance < best.distance)) best = { ...candidate, distance };
  }
  return best?.value || input.trim();
}

export function buildPageUrl(page, params = {}) {
  const base = window.DRLINQ_CONFIG?.BASE_PATH || '/';
  const url = new URL(`${base}${page}`, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      url.searchParams.set(key, String(value));
    }
  });
  return `${url.pathname}${url.search}`;
}

export function searchParamsFromLocation(search = window.location.search) {
  const params = new URLSearchParams(search);
  return {
    need: params.get('need') || '',
    service: params.get('service') || '',
    insurer: params.get('insurer') || '',
    province: params.get('province') || '',
    city: params.get('city') || '',
    district: params.get('district') || '',
  };
}

export function normalizeProviderKey(item) {
  return [item.name, item.address, item.phone]
    .map(normalizeText)
    .filter(Boolean)
    .join('|');
}

export function dedupeProviders(items = []) {
  const map = new Map();
  for (const item of items) {
    const key = normalizeProviderKey(item) || `${item.id}|${item.location_id}`;
    if (!map.has(key)) {
      map.set(key, {
        ...item,
        insurers: new Set(item.insurers || []),
        services: new Set(item.services || []),
        sources: [...(item.sources || [])],
      });
      continue;
    }
    const current = map.get(key);
    (item.insurers || []).forEach((value) => current.insurers.add(value));
    (item.services || []).forEach((value) => current.services.add(value));
    for (const source of item.sources || []) {
      if (!current.sources.some((saved) => saved.url === source.url && saved.name === source.name)) current.sources.push(source);
    }
    if (!current.phone && item.phone) current.phone = item.phone;
    if (!current.district && item.district) current.district = item.district;
  }
  return [...map.values()].map((item) => ({
    ...item,
    insurers: [...item.insurers],
    services: [...item.services],
  }));
}

export function verificationState(sources = []) {
  if (sources.some((source) => source.source_type === 'official')) {
    return { key: 'official', label: 'منبع رسمی', tone: 'success' };
  }
  if (sources.length) return { key: 'sourced', label: 'دارای منبع', tone: 'info' };
  return { key: 'unverified', label: 'نیازمند بررسی مجدد', tone: 'muted' };
}

const PROVIDER_TYPE_LABELS = Object.freeze({
  dentistry: 'دندانپزشکی',
  laboratory: 'آزمایشگاه',
  radiology: 'تصویربرداری',
  physiotherapy: 'فیزیوتراپی',
  pharmacy: 'داروخانه',
  physician: 'پزشک',
  clinic: 'درمانگاه',
  hospital: 'بیمارستان',
  healthcare_provider: 'مرکز درمانی',
});

export function providerTypeLabel(value = '') {
  const type = String(value).trim();
  return PROVIDER_TYPE_LABELS[type.toLowerCase()] || type;
}

export function insurerFilterLabel(value = '') {
  const name = String(value).trim();
  if (!name) return '';
  return normalizeText(name).startsWith('بیمه ') ? name : `بیمه ${name}`;
}

export function phoneHref(phone = '') {
  const first = String(phone).split(/[،,;/]|\s+-\s+/)[0];
  const normalized = first.replace(/[^\d+]/g, '');
  return normalized.replace(/^00/, '+');
}

export function isCallablePhone(phone = '') {
  const length = phoneHref(phone).replace(/\D/g, '').length;
  return length >= 7 && length <= 15;
}

export function toPersianNumber(value) {
  return new Intl.NumberFormat('fa-IR').format(Number(value || 0));
}

export function displayDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('fa-IR', { year: 'numeric', month: 'long', day: 'numeric' }).format(date);
}

export function safeExternalUrl(value = '') {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

export function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}
