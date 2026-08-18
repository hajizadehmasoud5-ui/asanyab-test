(function(global){
  'use strict';
  const KEY='alanoffer_map_config_v1';
  const DEFAULT={provider:'neshan',neshanWebKey:'',style:'dreamy'};
  let readyPromise=null;
  function read(){try{return {...DEFAULT,...JSON.parse(localStorage.getItem(KEY)||'{}')}}catch(e){return {...DEFAULT}}}
  function save(cfg){localStorage.setItem(KEY,JSON.stringify({...read(),...cfg}));readyPromise=null;return read()}
  function loadCss(id,href){return new Promise(resolve=>{if(document.getElementById(id))return resolve();const l=document.createElement('link');l.id=id;l.rel='stylesheet';l.href=href;l.onload=resolve;l.onerror=resolve;document.head.appendChild(l)})}
  function loadScript(id,src){return new Promise((resolve,reject)=>{if(document.getElementById(id)){if(global.L)return resolve();const old=document.getElementById(id);old.addEventListener('load',resolve,{once:true});return}const s=document.createElement('script');s.id=id;s.src=src;s.onload=resolve;s.onerror=reject;document.head.appendChild(s)})}
  async function ensure(){const cfg=read();if(global.L)return {provider:cfg.provider==='neshan'&&cfg.neshanWebKey?'neshan':'osm',cfg};if(cfg.provider==='neshan'&&cfg.neshanWebKey){await loadCss('alan-neshan-css','https://static.neshan.org/sdk/leaflet/v1.9.4/neshan-sdk/v1.0.8/index.css');await loadScript('alan-neshan-js','https://static.neshan.org/sdk/leaflet/v1.9.4/neshan-sdk/v1.0.8/index.js');return {provider:'neshan',cfg}}await loadCss('alan-leaflet-css','https://unpkg.com/leaflet@1.9.4/dist/leaflet.css');await loadScript('alan-leaflet-js','https://unpkg.com/leaflet@1.9.4/dist/leaflet.js');return {provider:'osm',cfg}}
  function ready(){if(!readyPromise)readyPromise=ensure();return readyPromise}
  async function create(id,opts={}){const state=await ready();const center=opts.center||[31.3183,48.6706],zoom=opts.zoom||13;let map;if(state.provider==='neshan'){map=new L.Map(id,{key:state.cfg.neshanWebKey,maptype:state.cfg.style||'dreamy',center,zoom})}else{map=L.map(id,{zoomControl:true}).setView(center,zoom);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map)}return {map,provider:state.provider,cfg:state.cfg}}
  function neshanPoint(lat,lng){return `https://nshn.ir/?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`}
  function neshanRoute(origin,destination,vehicle='d'){const o=`${origin[0]},${origin[1]}`,d=`${destination[0]},${destination[1]}`;return `https://nshn.ir?origin=${encodeURIComponent(o)}&destination=${encodeURIComponent(d)}&vehicle=${encodeURIComponent(vehicle)}`}
  function label(){const c=read();return c.provider==='neshan'&&c.neshanWebKey?'نشان':'OpenStreetMap (پشتیبان)'}
  global.AlanMapProvider={read,save,ready,create,label,neshanPoint,neshanRoute,hasNeshan:()=>!!read().neshanWebKey};
})(window);