(()=>{
'use strict';
const LINK_KEY='drlinq_implant_secure_case_v1';
const originalFetch=window.fetch.bind(window);
function saveSecureLink(data){
  if(!data||data.created!==true||!data.case_id||!data.patient_access_token)return;
  const url=new URL('implant-case.html',window.location.href);
  url.hash=new URLSearchParams({case:data.case_id,token:data.patient_access_token}).toString();
  localStorage.setItem(LINK_KEY,JSON.stringify({case_id:data.case_id,url:url.href}));
}
window.fetch=async(...args)=>{
  const response=await originalFetch(...args);
  try{
    const input=args[0];
    const url=typeof input==='string'?input:(input&&input.url)||'';
    const method=String((args[1]&&args[1].method)||(input&&input.method)||'GET').toUpperCase();
    if(method==='POST'&&/implant-api\/cases(?:\?|$)/.test(url))saveSecureLink(await response.clone().json());
  }catch{}
  return response;
};
function readSaved(){
  try{return JSON.parse(localStorage.getItem(LINK_KEY)||'null')}catch{return null}
}
async function copyText(value,button){
  try{
    await navigator.clipboard.writeText(value);
  }catch{
    const input=document.createElement('textarea');input.value=value;input.setAttribute('readonly','');input.style.position='fixed';input.style.opacity='0';document.body.appendChild(input);input.select();document.execCommand('copy');input.remove();
  }
  const old=button.textContent;button.textContent='لینک کپی شد';setTimeout(()=>button.textContent=old,1800);
}
function enhance(){
  const caseNode=document.querySelector('[data-case-id]');
  if(!caseNode||document.querySelector('[data-secure-case-url]'))return;
  const saved=readSaved(),caseId=(caseNode.textContent||'').trim();
  if(!saved||saved.case_id!==caseId||!saved.url)return;
  const box=document.createElement('div');
  box.className='notice';
  box.setAttribute('data-secure-case-url','');
  box.innerHTML='<b style="display:block;margin-bottom:6px">لینک امن پیگیری پرونده</b><div style="font-size:13px;line-height:1.9">این لینک را نگه دارید. فقط با همین لینک می‌توان پاسخ پزشک را دید.</div><a data-open-secure-case style="display:block;margin:10px 0;color:#087d59;font-weight:850;overflow-wrap:anywhere" rel="noreferrer">باز کردن صفحه پیگیری پرونده</a><button type="button" data-copy-secure-case class="btn secondary" style="width:100%;min-height:48px">کپی لینک امن</button>';
  const anchor=box.querySelector('[data-open-secure-case]');anchor.href=saved.url;
  box.querySelector('[data-copy-secure-case]').onclick=event=>copyText(saved.url,event.currentTarget);
  const done=caseNode.closest('.done');(done||caseNode).insertAdjacentElement('afterend',box);
}
new MutationObserver(enhance).observe(document.documentElement,{childList:true,subtree:true});
enhance();
})();
