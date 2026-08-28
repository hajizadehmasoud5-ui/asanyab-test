(function () {
  const inTestPath = window.location.pathname.startsWith('/drlinq-test');
  const inIsolatedVpsTest = inTestPath && window.location.hostname === 'n8n.drlinq.ir';
  const readOnlyApi = 'https://n8n.drlinq.ir/drlinq-test/api';
  window.DRLINQ_CONFIG = Object.freeze({
    APP_NAME: 'DrLinq',
    BRAND_NAME: 'دکتر لینک',
    DOMAIN: 'drlinq.ir',
    LOGO: 'دکتر لینک',
    PRIMARY_LOCALE: 'fa-IR',
    BASE_PATH: inTestPath ? '/drlinq-test/' : '/',
    API_BASE: inIsolatedVpsTest ? '/drlinq-test/api' : readOnlyApi,
  });
})();
