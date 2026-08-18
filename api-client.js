(function(global){
  'use strict';
  const CFG='alanoffer_api_config_v1';
  const LOCAL='alanoffer_businesses_v1';
  const DEFAULT={baseUrl:''};
  function readConfig(){try{return {...DEFAULT,...JSON.parse(localStorage.getItem(CFG)||'{}')}}catch(e){return {...DEFAULT}}}
  function saveConfig(cfg){const next={...readConfig(),...cfg};next.baseUrl=String(next.baseUrl||'').trim().replace(/\/+$/,'');localStorage.setItem(CFG,JSON.stringify(next));return next}
  function base(){return readConfig().baseUrl}
  function configured(){return !!base()}
  async function req(path,opts={}){if(!configured())throw new Error('backend_not_configured');const r=await fetch(base()+path,{...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})}});let body=null;try{body=await r.json()}catch(e){}if(!r.ok){const err=new Error(body?.error||('HTTP '+r.status));err.status=r.status;err.body=body;throw err}return body}
  function qs(obj){const p=new URLSearchParams();Object.entries(obj||{}).forEach(([k,v])=>{if(v!==undefined&&v!==null&&String(v)!=='')p.set(k,String(v))});const s=p.toString();return s?'?'+s:''}
  async function health(){return req('/api/health')}
  async function listBusinesses(filters={}){return req('/api/businesses'+qs(filters))}
  async function submitBusiness(rec){return req('/api/submissions',{method:'POST',body:JSON.stringify(rec)})}
  async function neshanSearch(params){return req('/api/neshan/search'+qs(params))}
  async function pending(token){return req('/api/admin/submissions?status=pending',{headers:{Authorization:'Bearer '+token}})}
  async function review(id,action,token){return req('/api/admin/submissions/'+encodeURIComponent(id)+'/'+action,{method:'POST',headers:{Authorization:'Bearer '+token}})}
  async function adminAddBusiness(rec,token){return req('/api/admin/businesses',{method:'POST',headers:{Authorization:'Bearer '+token},body:JSON.stringify(rec)})}
  async function osmCatalog(token){return req('/api/admin/osm/catalog',{headers:{Authorization:'Bearer '+token}})}
  async function osmSearch(top,sub,token){return req('/api/admin/osm/search'+qs({top,sub}),{headers:{Authorization:'Bearer '+token}})}
  async function osmImport(rec,token){return req('/api/admin/osm/import',{method:'POST',headers:{Authorization:'Bearer '+token},body:JSON.stringify(rec)})}
  function readLocal(){try{return JSON.parse(localStorage.getItem(LOCAL)||'[]')}catch(e){return []}}
  function saveLocal(rec){const list=readLocal();list.unshift(rec);localStorage.setItem(LOCAL,JSON.stringify(list.slice(0,1000)));return rec}
  global.AlanApi={readConfig,saveConfig,configured,health,listBusinesses,submitBusiness,neshanSearch,pending,review,adminAddBusiness,osmCatalog,osmSearch,osmImport,readLocal,saveLocal};
})(window);