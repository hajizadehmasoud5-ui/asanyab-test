(function () {
  const inTestPath = window.location.pathname.startsWith('/drlinq-test');
  const inIsolatedVpsTest = inTestPath && window.location.hostname === 'n8n.drlinq.ir';
  window.DRLINQ_CONFIG = Object.freeze({
    APP_NAME: 'DrLinq',
    BRAND_NAME: 'دکتر لینک',
    DOMAIN: 'drlinq.ir',
    LOGO: 'دکتر لینک',
    PRIMARY_LOCALE: 'fa-IR',
    BASE_PATH: inTestPath ? '/drlinq-test/' : '/',
    API_BASE: inIsolatedVpsTest ? '/drlinq-test/api' : 'https://n8n.drlinq.ir/bank',
  });
})();
