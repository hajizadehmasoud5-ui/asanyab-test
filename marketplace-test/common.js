(() => {
  const config = window.DRLINQ_CONFIG;
  document.querySelectorAll("[data-brand]").forEach((el) => { el.textContent = config.BRAND_NAME; });
  document.querySelectorAll("[data-app]").forEach((el) => { el.textContent = config.APP_NAME; });

  const money = (value) => value == null ? "—" : `${Number(value).toLocaleString("fa-IR")} تومان`;
  const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[char]);
  const api = async (path, options = {}) => {
    const response = await fetch(`${config.API_BASE}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) }
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "خطا در ارتباط با سامانه");
    return data;
  };
  const params = () => new URLSearchParams(location.search);
  const setMessage = (el, text, type = "info") => {
    el.className = `message ${type}`;
    el.textContent = text;
    el.hidden = false;
  };
  const matchCard = (match, selectable = false) => {
    const insurers = (match.insurers || []).slice(0, 3).map((x) => `<span class="chip">${escapeHtml(x)}</span>`).join("");
    const source = match.trust?.source_name || config.BRAND_NAME;
    const sourceView = match.trust?.source_url
      ? `<a href="${escapeHtml(match.trust.source_url)}" target="_blank" rel="noopener">${escapeHtml(source)}</a>`
      : escapeHtml(source);
    return `<article class="provider-card">
      <div class="provider-head">
        ${selectable ? `<input class="provider-check" type="checkbox" name="provider" value="${match.provider_id}" checked aria-label="انتخاب ${escapeHtml(match.provider_name)}">` : ""}
        <div><h3>${escapeHtml(match.provider_name)}</h3><p>${escapeHtml(match.provider_type || "مرکز درمانی")}</p></div>
        <span class="score">${Number(match.score || 0).toLocaleString("fa-IR")}% تطبیق</span>
      </div>
      <p class="location">${escapeHtml([match.province, match.city, match.district].filter(Boolean).join("، "))}</p>
      ${insurers ? `<div class="chips">${insurers}</div>` : ""}
      <div class="trust">✓ موجود در بانک درمانگران · منبع: ${sourceView}</div>
    </article>`;
  };
  window.DrLinq = { config, api, money, escapeHtml, params, setMessage, matchCard };
})();
