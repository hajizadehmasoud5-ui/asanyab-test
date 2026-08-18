window.A=[...new Set([...(window.A||[]),"شیلنگ آباد"])];

window.addEventListener('DOMContentLoaded',()=>{
  if(!document.querySelector('.directory')) return;
  const load=(src)=>new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=src;s.onload=resolve;s.onerror=reject;document.body.appendChild(s)});
  (async()=>{
    try{
      if(!window.AlanBiz) await load('business-categories.js?v=3');
      if(!window.AlanMapProvider) await load('map-provider.js?v=1');
      await load('directory-enhance.js?v=3');
    }catch(e){console.error('AlanOffer directory enhancement failed',e)}
  })();
});