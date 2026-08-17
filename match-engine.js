(function (global) {
  'use strict';

  const VERSION = '0.1.0';
  const WAIT_KEY = 'alanoffer_waiting_v1';

  const CATEGORIES = {
    restaurant: {
      label: 'رستوران و فست‌فود',
      fields: [
        { key: 'foodType', label: 'چه غذایی؟', type: 'select', options: ['فرقی ندارد','برگر','پیتزا','کباب و ایرانی','سوخاری','ساندویچ','فلافل و سمبوسه','دریایی','صبحانه'] },
        { key: 'mode', label: 'چطور می‌خواهی؟', type: 'select', options: ['فرقی ندارد','حضوری','ارسال'] },
        { key: 'people', label: 'چند نفر؟', type: 'number', min: 1, max: 20, placeholder: '2' },
        { key: 'timeWindow', label: 'چه زمانی؟', type: 'select', options: ['هر زمان','الان تا ۲ ساعت','امروز','امشب','فردا'] }
      ]
    },
    cafe: {
      label: 'کافه',
      fields: [
        { key: 'itemType', label: 'بیشتر دنبال چی هستی؟', type: 'select', options: ['فرقی ندارد','قهوه','نوشیدنی سرد','صبحانه','کیک و دسر','غذا'] },
        { key: 'people', label: 'چند نفر؟', type: 'number', min: 1, max: 20, placeholder: '2' },
        { key: 'timeWindow', label: 'چه زمانی؟', type: 'select', options: ['هر زمان','الان تا ۲ ساعت','امروز','امشب','فردا'] }
      ]
    },
    produce: {
      label: 'میوه و تره‌بار',
      fields: [
        { key: 'product', label: 'چه محصولی؟', type: 'text', placeholder: 'مثلاً موز، هندوانه، گوجه' },
        { key: 'mode', label: 'تحویل', type: 'select', options: ['فرقی ندارد','حضوری','ارسال'] },
        { key: 'quantity', label: 'حدود مقدار', type: 'text', placeholder: 'مثلاً ۵ کیلو' }
      ]
    },
    dairy: {
      label: 'لبنیات',
      fields: [
        { key: 'product', label: 'چه محصولی؟', type: 'text', placeholder: 'مثلاً شیر، ماست، پنیر' },
        { key: 'mode', label: 'تحویل', type: 'select', options: ['فرقی ندارد','حضوری','ارسال'] },
        { key: 'quantity', label: 'حدود مقدار', type: 'text', placeholder: 'مثلاً ۳ عدد' }
      ]
    },
    service: {
      label: 'خدمات و نوبت',
      fields: [
        { key: 'serviceType', label: 'چه خدمتی؟', type: 'text', placeholder: 'مثلاً کوتاهی مو، جرم‌گیری، کارواش' },
        { key: 'timeWindow', label: 'چه زمانی؟', type: 'select', options: ['هر زمان','امروز','امشب','فردا','این هفته'] },
        { key: 'acceptCancellation', label: 'اگر نوبت کنسل‌شده پیدا شد؟', type: 'select', options: ['بله خبرم کن','فقط آفر عادی'] }
      ]
    },
    clothing: {
      label: 'لباس و پوشاک',
      fields: [
        { key: 'audience', label: 'برای چه کسی؟', type: 'select', options: ['فرقی ندارد','زنانه','مردانه','بچگانه'] },
        { key: 'itemType', label: 'چه لباسی؟', type: 'text', placeholder: 'مثلاً شلوار، مانتو، کفش' },
        { key: 'size', label: 'سایز', type: 'text', placeholder: 'مثلاً L یا 42' },
        { key: 'brand', label: 'برند (اختیاری)', type: 'text', placeholder: 'اگر مهم است' }
      ]
    }
  };

  const LABEL_TO_KEY = Object.fromEntries(Object.entries(CATEGORIES).map(([k,v]) => [v.label, k]));
  LABEL_TO_KEY['خدمات و نوبت'] = 'service';
  LABEL_TO_KEY['میوه و تره‌بار'] = 'produce';
  LABEL_TO_KEY['لبنیاتی'] = 'dairy';
  LABEL_TO_KEY['لبنیات'] = 'dairy';

  function normalizeText(x) {
    return String(x || '').replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/‌/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function categoryKey(value) {
    if (!value) return '';
    if (CATEGORIES[value]) return value;
    return LABEL_TO_KEY[value] || '';
  }

  function discountPercent(offer) {
    const oldP = Number(offer.old ?? offer.price ?? 0);
    const newP = Number(offer.newp ?? offer.offerPrice ?? offer.finalPrice ?? 0);
    if (!oldP || newP >= oldP) return 0;
    return Math.round(((oldP - newP) / oldP) * 100);
  }

  function getOfferPrice(offer) {
    return Number(offer.newp ?? offer.offerPrice ?? offer.finalPrice ?? offer.price ?? 0);
  }

  function getMeta(obj) {
    return obj && typeof obj.meta === 'object' && obj.meta ? obj.meta : {};
  }

  function textCompatible(wanted, offered) {
    const w = normalizeText(wanted), o = normalizeText(offered);
    if (!w || !o || w === 'فرقی ندارد' || w === 'هر زمان') return true;
    return o.includes(w) || w.includes(o);
  }

  function categorySpecificScore(request, offer) {
    const rk = categoryKey(request.category || request.cat), r = request.meta || {}, o = getMeta(offer);
    let earned = 0, total = 0;
    const compare = (key, weight, aliases=[]) => {
      const rv = r[key];
      if (!rv || rv === 'فرقی ندارد' || rv === 'هر زمان') return;
      total += weight;
      let ov = o[key];
      if (!ov) for (const a of aliases) if (o[a]) { ov = o[a]; break; }
      if (textCompatible(rv, ov || offer.title || offer.product || '')) earned += weight;
    };

    if (rk === 'restaurant') {
      compare('foodType', 12, ['itemType']); compare('mode', 5); compare('timeWindow', 5);
      if (r.people) { total += 3; const cap = Number(o.people || o.capacity || offer.qty || 0); if (!cap || cap >= Number(r.people)) earned += 3; }
    } else if (rk === 'cafe') {
      compare('itemType', 12, ['foodType']); compare('timeWindow', 5);
      if (r.people) { total += 3; const cap = Number(o.people || o.capacity || offer.qty || 0); if (!cap || cap >= Number(r.people)) earned += 3; }
    } else if (rk === 'produce' || rk === 'dairy') {
      compare('product', 14); compare('mode', 6);
    } else if (rk === 'service') {
      compare('serviceType', 14, ['product']); compare('timeWindow', 6);
      if (r.acceptCancellation === 'بله خبرم کن') { total += 5; const reason = normalizeText(offer.reason); if (reason.includes('کنسل') || reason.includes('خالی') || normalizeText(o.offerType).includes('کنسل')) earned += 5; }
    } else if (rk === 'clothing') {
      compare('audience', 5); compare('itemType', 10, ['product']); compare('size', 5); compare('brand', 5);
    }
    return { earned, total };
  }

  function score(request, offer) {
    const reqCat = categoryKey(request.category || request.cat), offCat = categoryKey(offer.category || offer.cat);
    if (!reqCat || !offCat || reqCat !== offCat) return { score: 0, matched: false, reasons: ['دسته متفاوت است'] };

    let points = 45;
    const reasons = ['دسته مناسب'];
    const reqArea = normalizeText(request.area), offArea = normalizeText(offer.area);
    if (!reqArea || reqArea === 'همه محله‌ها') points += 10;
    else if (reqArea === offArea) { points += 20; reasons.push('همان محله'); }

    const maxPrice = Number(request.maxPrice || 0), offerPrice = getOfferPrice(offer);
    if (maxPrice > 0) {
      if (offerPrice > 0 && offerPrice <= maxPrice) { points += 15; reasons.push('داخل بودجه'); }
      else if (offerPrice > maxPrice) points -= 20;
    } else points += 7;

    const minDiscount = Number(request.minDiscount || 0), dp = discountPercent(offer);
    if (minDiscount > 0) {
      if (dp >= minDiscount) { points += 10; reasons.push('تخفیف کافی'); }
      else points -= 12;
    } else points += 5;

    const spec = categorySpecificScore(request, offer);
    if (spec.total) {
      const normalized = Math.round((spec.earned / spec.total) * 20);
      points += normalized;
      if (normalized >= 12) reasons.push('جزئیات نزدیک به خواسته‌ات');
    } else points += 8;

    if (Number(offer.end || 0) && Number(offer.end) <= Date.now()) points = 0;
    if (Number(offer.qty || 1) <= 0) points = 0;
    points = Math.max(0, Math.min(100, Math.round(points)));
    return { score: points, matched: points >= 60, reasons, discount: dp };
  }

  function findMatches(request, offers, limit = 20) {
    return (offers || []).map(offer => ({ offer, ...score(request, offer) })).filter(x => x.matched).sort((a,b) => b.score - a.score).slice(0, limit);
  }

  function requestId() { return 'w_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2,7); }

  function readWaiting() {
    let list = [];
    try { list = JSON.parse(localStorage.getItem(WAIT_KEY) || '[]'); } catch (e) {}
    const now = Date.now();
    list = Array.isArray(list) ? list.filter(x => !x.expiresAt || x.expiresAt > now) : [];
    localStorage.setItem(WAIT_KEY, JSON.stringify(list));
    return list;
  }

  function saveWaiting(request) {
    const list = readWaiting(), durationHours = Number(request.durationHours || 24);
    const saved = {
      id: request.id || requestId(), city: 'اهواز', category: categoryKey(request.category || request.cat), area: request.area || '',
      maxPrice: Number(request.maxPrice || 0), minDiscount: Number(request.minDiscount || 0), meta: request.meta || {},
      createdAt: request.createdAt || Date.now(), expiresAt: request.expiresAt || (Date.now() + durationHours * 3600000)
    };
    localStorage.setItem(WAIT_KEY, JSON.stringify([saved, ...list.filter(x => x.id !== saved.id)].slice(0, 30)));
    return saved;
  }

  function removeWaiting(id) {
    const next = readWaiting().filter(x => x.id !== id);
    localStorage.setItem(WAIT_KEY, JSON.stringify(next));
    return next;
  }

  function labelForCategory(key) { return CATEGORIES[categoryKey(key)]?.label || key || ''; }

  function bestRequestForOffer(offer, requests = readWaiting()) {
    let best = null;
    requests.forEach(r => { const result = score(r, offer); if (result.matched && (!best || result.score > best.score)) best = { request: r, ...result }; });
    return best;
  }

  global.AlanMatch = { VERSION, WAIT_KEY, CATEGORIES, categoryKey, labelForCategory, discountPercent, score, findMatches, readWaiting, saveWaiting, removeWaiting, bestRequestForOffer, normalizeText };
})(window);
