import { getFilters } from './api.js?v=1.0.1';
import { SERVICE_CATALOG, buildPageUrl, resolveService, searchParamsFromLocation } from './core.js?v=1.0.1';

const $ = (id) => document.getElementById(id);
const need = $('need');
const province = $('province');
const city = $('city');
const insurer = $('insurer');
const form = $('searchForm');
const formStatus = $('formStatus');
const initial = searchParamsFromLocation();
let apiServices = [];

function replaceOptions(select, values, placeholder, selected = '') {
  select.innerHTML = '';
  const first = document.createElement('option');
  first.value = '';
  first.textContent = placeholder;
  select.appendChild(first);
  for (const value of values) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    option.selected = value === selected;
    select.appendChild(option);
  }
}

function populateSuggestions(services) {
  const datalist = $('serviceSuggestions');
  const unique = [...new Set([...SERVICE_CATALOG.map((item) => item.label), ...services])];
  datalist.innerHTML = unique.slice(0, 320).map((value) => `<option value="${value.replace(/"/g, '&quot;')}"></option>`).join('');
}

async function loadCities(selected = '') {
  city.disabled = true;
  replaceOptions(city, [], province.value ? 'در حال دریافت شهرها…' : 'ابتدا استان را انتخاب کن');
  if (!province.value) return;
  try {
    const data = await getFilters(province.value);
    replaceOptions(city, data.cities || [], 'انتخاب شهر', selected);
    city.disabled = false;
  } catch {
    replaceOptions(city, [], 'خطا در دریافت شهرها');
    formStatus.textContent = 'ارتباط با بانک موقتاً برقرار نشد. دوباره تلاش کن.';
  }
}

async function initialize() {
  need.value = initial.need || initial.service;
  formStatus.textContent = 'در حال اتصال به بانک مراکز…';
  try {
    const data = await getFilters();
    apiServices = data.services || [];
    replaceOptions(province, data.provinces || [], 'انتخاب استان', initial.province);
    replaceOptions(insurer, data.insurers || [], 'آزاد / بدون فیلتر بیمه', initial.insurer);
    populateSuggestions(apiServices);
    if (initial.province) await loadCities(initial.city);
    formStatus.textContent = 'بانک مراکز متصل است؛ شماره تماس یا اطلاعات پزشکی از تو نمی‌گیریم.';
  } catch {
    formStatus.textContent = 'اتصال به بانک برقرار نشد. اینترنت را بررسی و صفحه را تازه کن.';
  }
}

province.addEventListener('change', () => loadCities());

document.querySelectorAll('[data-service]').forEach((button) => {
  button.addEventListener('click', () => {
    need.value = button.dataset.service;
    document.querySelectorAll('[data-service]').forEach((item) => item.classList.toggle('is-active', item === button));
    need.focus();
  });
});

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const resolved = resolveService(need.value, apiServices);
  if (!resolved || !province.value || !city.value) {
    formStatus.textContent = 'خدمت، استان و شهر را کامل کن. بیمه اختیاری است.';
    if (!resolved) need.focus();
    else if (!province.value) province.focus();
    else city.focus();
    return;
  }
  const params = {
    need: need.value.trim(),
    service: resolved,
    province: province.value,
    city: city.value,
    insurer: insurer.value,
  };
  localStorage.setItem('drlinq:last-search', JSON.stringify(params));
  window.location.assign(buildPageUrl('results.html', params));
});

initialize();
