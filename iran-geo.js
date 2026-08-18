/* AlanOffer Iran geography loader
   Province/city data: masterking32/iran-states-cities-districts (MIT), snapshot 2025-01-18.
   Neighborhood suggestions: OpenStreetMap/Overpass (ODbL). Manual neighborhood entry is always available.
*/
(()=>{'use strict';
const CITY_URL='https://raw.githubusercontent.com/masterking32/iran-states-cities-districts/ef80f5bab604ece1cb5fa35da4d2f169f79f2ead/2025-01-18/cities_sorted.json';
const OVERPASS=['https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter'];
const PROVINCES=[
[1,'آذربایجان شرقی'],[2,'آذربایجان غربی'],[3,'اردبیل'],[4,'اصفهان'],[5,'البرز'],[6,'ایلام'],[7,'بوشهر'],[8,'تهران'],[16,'چهارمحال و بختیاری'],[17,'خراسان جنوبی'],[18,'خراسان رضوی'],[19,'خراسان شمالی'],[20,'خوزستان'],[21,'زنجان'],[22,'سمنان'],[23,'سیستان و بلوچستان'],[24,'فارس'],[25,'قزوین'],[26,'قم'],[27,'کردستان'],[28,'کرمان'],[29,'کرمانشاه'],[30,'کهگیلویه و بویراحمد'],[31,'گلستان'],[32,'گیلان'],[33,'لرستان'],[34,'مازندران'],[35,'مرکزی'],[36,'هرمزگان'],[37,'همدان'],[38,'یزد']
];
const AHWAZ=Array.isArray(window.A)?window.A.filter(x=>x&&x!=='سایر اهواز'):[];
let cities=[];const areaCache=new Map();
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
function opt(value,label){return `<option value="${esc(value)}">${esc(label)}</option>`}
function norm(s){return String(s||'').replace(/ي/g,'ی').replace(/ك/g,'ک').replace(/‌/g,' ').replace(/\s+/g,' ').trim()}
async function json(url,timeout=9000){const c=new AbortController();const t=setTimeout(()=>c.abort(),timeout);try{const r=await fetch(url,{signal:c.signal,cache:'force-cache'});if(!r.ok)throw new Error('http_'+r.status);return await r.json()}finally{clearTimeout(t)}}
function hav(a,b,c,d){const R=6371,p=Math.PI/180,dp=(c-a)*p,dl=(d-b)*p,x=Math.sin(dp/2)**2+Math.cos(a*p)*Math.cos(c*p)*Math.sin(dl/2)**2;return 2*R*Math.asin(Math.sqrt(x))}
function cityName(x){return norm(x?.name)}
function dedupeCity(rows){const m=new Map();for(const x of rows){const n=cityName(x);if(!n)continue;const old=m.get(n);if(!old||(!old.lat&&x.lat)||(!old.is_county&&x.is_county))m.set(n,x)}return [...m.values()].sort((a,b)=>cityName(a).localeCompare(cityName(b),'fa'))}
async function loadCities(){if(cities.length)return cities;const raw=await json(CITY_URL,12000);cities=dedupeCity(Object.values(raw||{}));return cities}
async function overpassAreas(city){const lat=Number(city.lat),lon=Number(city.lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return[];const radius=['تهران','مشهد','اصفهان','شیراز','تبریز','کرج','اهواز'].includes(cityName(city))?26000:16000;const q=`[out:json][timeout:12];(node["place"~"neighbourhood|suburb|quarter"](around:${radius},${lat},${lon});way["place"~"neighbourhood|suburb|quarter"](around:${radius},${lat},${lon});relation["place"~"neighbourhood|suburb|quarter"](around:${radius},${lat},${lon}););out center tags;`;
let last=null;for(const ep of OVERPASS){try{const u=ep+'?data='+encodeURIComponent(q);const body=await json(u,14000);const names=[];for(const el of body.elements||[]){const t=el.tags||{},name=norm(t['name:fa']||t.name);if(!name)continue;const p=el.center||el;const y=Number(p.lat),x=Number(p.lon);if(Number.isFinite(y)&&Number.isFinite(x)&&hav(lat,lon,y,x)<=radius/1000)names.push(name)}return [...new Set(names)].sort((a,b)=>a.localeCompare(b,'fa'))}catch(e){last=e}}throw last||new Error('overpass')}
async function areasFor(city){const name=cityName(city);if(name==='اهواز'&&AHWAZ.length)return AHWAZ;const key=String(city.id||name);if(areaCache.has(key))return areaCache.get(key);try{const a=await overpassAreas(city);areaCache.set(key,a);return a}catch{areaCache.set(key,[]);return[]}}
function mount(cfg={}){const p=document.getElementById(cfg.provinceId||'province'),c=document.getElementById(cfg.cityId||'city'),a=document.getElementById(cfg.areaId||'area'),mc=document.getElementById(cfg.manualCityId||'manualCity'),ma=document.getElementById(cfg.manualAreaId||'manualArea'),st=document.getElementById(cfg.statusId||'geoStatus');if(!p||!c||!a||!mc||!ma)return null;
const changed=()=>{if(typeof cfg.onChange==='function')cfg.onChange()};
p.innerHTML=opt('','انتخاب استان')+PROVINCES.map(x=>opt(x[0],x[1])).join('');
c.innerHTML=opt('','اول استان را انتخاب کن');c.disabled=true;a.innerHTML=opt('','اول شهر را انتخاب کن');a.disabled=true;mc.style.display='none';ma.style.display='none';
function status(t){if(st){st.textContent=t||'';st.style.display=t?'block':'none'}}
function selectedCity(){const id=c.value;if(id==='__manual__')return null;return cities.find(x=>String(x.id)===String(id))||null}
function cityValue(){if(c.value==='__manual__')return norm(mc.value);const x=selectedCity();return cityName(x)}
function provinceValue(){const x=PROVINCES.find(x=>String(x[0])===String(p.value));return x?x[1]:''}
function areaValue(){return a.value==='__manual__'?norm(ma.value):norm(a.value)}
p.addEventListener('change',async()=>{changed();mc.value='';ma.value='';mc.style.display='none';ma.style.display='none';a.innerHTML=opt('','اول شهر را انتخاب کن');a.disabled=true;c.disabled=true;c.innerHTML=opt('','در حال آماده‌سازی شهرها...');if(!p.value){c.innerHTML=opt('','اول استان را انتخاب کن');return}status('');try{await loadCities();const rows=cities.filter(x=>String(x.province_id)===String(p.value));c.innerHTML=opt('','انتخاب شهر')+rows.map(x=>opt(x.id,cityName(x))).join('')+opt('__manual__','شهر من در فهرست نیست');c.disabled=false}catch{c.innerHTML=opt('__manual__','نام شهر را خودم وارد می‌کنم');c.disabled=false;status('فهرست شهرها باز نشد؛ نام شهر را وارد کن.')}});
c.addEventListener('change',async()=>{changed();ma.value='';ma.style.display='none';a.disabled=true;a.innerHTML=opt('','در حال آماده‌سازی محله‌ها...');if(!c.value){mc.style.display='none';a.innerHTML=opt('','اول شهر را انتخاب کن');return}if(c.value==='__manual__'){mc.style.display='block';a.innerHTML=opt('__manual__','نام محله را وارد می‌کنم');a.value='__manual__';a.disabled=false;ma.style.display='block';status('');return}mc.style.display='none';const city=selectedCity();const list=city?await areasFor(city):[];a.innerHTML=opt('','انتخاب محله / منطقه')+list.map(x=>opt(x,x)).join('')+opt('__manual__','محله من در فهرست نیست');a.disabled=false;status(list.length?'':'محله را خودت وارد کن؛ فهرست این شهر هنوز کامل نیست.');if(!list.length){a.value='__manual__';ma.style.display='block'}});
a.addEventListener('change',()=>{changed();ma.style.display=a.value==='__manual__'?'block':'none';if(a.value!=='__manual__')ma.value=''});mc.addEventListener('input',changed);ma.addEventListener('input',changed);
return{provinceValue,cityValue,areaValue,selectedCity};}
window.AlanGeo={mount,PROVINCES};
})();