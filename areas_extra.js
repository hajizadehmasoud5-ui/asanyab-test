window.A=[...new Set([...(window.A||[]),"شیلنگ آباد"])];

window.addEventListener('DOMContentLoaded',()=>{
  if(!document.querySelector('.directory')) return;
  const loadEnhance=()=>{
    const s=document.createElement('script');
    s.src='directory-enhance.js?v=2';
    document.body.appendChild(s);
  };
  if(window.AlanBiz){loadEnhance();return;}
  const c=document.createElement('script');
  c.src='business-categories.js?v=2';
  c.onload=loadEnhance;
  document.body.appendChild(c);
});