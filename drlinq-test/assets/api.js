const config = window.DRLINQ_CONFIG;

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function apiGet(path, params = {}, { signal } = {}) {
  const url = new URL(`${config.API_BASE}${path}`, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      url.searchParams.set(key, String(value));
    }
  });
  const response = await fetch(url, {
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new ApiError(`HTTP ${response.status}`, response.status);
  return response.json();
}

export const getFilters = (province = '', city = '', options = {}) => apiGet('/filters', { province, city }, options);
export const getMarketplaceMeta = (options = {}) => apiGet('/marketplace/meta', {}, options);

export async function searchProviders(filters, options = {}) {
  try {
    return await apiGet('/marketplace/providers', filters, options);
  } catch (error) {
    if (error.status !== 404) throw error;
    const legacy = await apiGet('/providers', filters, options);
    const items = (legacy.items || []).map((item) => ({
      ...item,
      location_id: item.location_id || '',
      insurers: Array.isArray(item.insurers) ? item.insurers : (item.insurer ? [item.insurer] : []),
      services: Array.isArray(item.services) ? item.services : (filters.service ? [filters.service] : []),
      sources: Array.isArray(item.sources) ? item.sources : [],
    }));
    const limit = Number(filters.limit || legacy.limit || items.length || 1);
    const offset = Number(filters.offset || legacy.offset || 0);
    const legacyTotal = Number(legacy.total);
    const hasExactTotal = legacy.total !== null && legacy.total !== undefined && Number.isFinite(legacyTotal) && legacyTotal >= 0;
    return {
      items,
      total: hasExactTotal ? legacyTotal : offset + items.length,
      has_more: hasExactTotal ? offset + items.length < legacyTotal : items.length === limit,
      total_is_exact: hasExactTotal,
      limit,
      offset,
      legacy: true,
    };
  }
}

export async function getProvider(id, locationId = '', filters = {}, options = {}) {
  try {
    return await apiGet(`/marketplace/providers/${encodeURIComponent(id)}`, { location_id: locationId }, options);
  } catch (error) {
    if (error.status !== 404) throw error;
    const result = await searchProviders({ ...filters, limit: 100, offset: 0 }, options);
    const item = result.items.find((candidate) => candidate.id === id && (!locationId || !candidate.location_id || candidate.location_id === locationId));
    if (!item) throw error;
    return {
      id: item.id,
      name: item.name,
      provider_type: item.provider_type,
      medical_license_no: item.medical_license_no,
      phone: item.phone,
      website: item.website,
      services: item.services || [],
      locations: [{
        location_id: item.location_id || '',
        province: item.province,
        city: item.city,
        district: item.district,
        address: item.address,
        latitude: item.latitude,
        longitude: item.longitude,
        phone: item.phone,
        insurers: item.insurers || [],
        sources: item.sources || [],
      }],
    };
  }
}
