(function () {
  const inTestPath = window.location.pathname.startsWith('/drlinq-test');
  window.DRLINQ_CONFIG = Object.freeze({
    APP_NAME: 'DrLinq',
    BRAND_NAME: 'دکتر لینک',
    DOMAIN: 'drlinq.ir',
    LOGO: 'دکتر لینک',
    PRIMARY_LOCALE: 'fa-IR',
    BASE_PATH: inTestPath ? '/drlinq-test/' : '/',
    API_BASE: 'https://n8n.drlinq.ir/bank',
  });
})();
