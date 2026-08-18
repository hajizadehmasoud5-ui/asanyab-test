(function(){
  'use strict';
  const STORE='alanoffer_businesses_v1';
  const AHVAZ=[31.3183,48.6706];
  let map=null,markers=null;
  const style=document.createElement('style');
  style.textContent=`
  .directoryTitleActions{display:flex;gap:7px;align-items:center}.addBizBtn{background:#ff6a00;color:#fff;text-decoration:none;border-radius:11px;padding:9px 11px;font-size:10px;font-weight:900;white-space:nowrap}.dirGrid.full{grid-template-columns:1.2fr 1fr 1fr 1fr}.directoryMapBox{margin:12px 0 4px;border:1px solid #e7e7e7;border-radius:17px;overflow:hidden;background:#fafafa}.directoryMapHead{display:flex;justify-content:space-between;align-items:center;padding:10px 11px;background:#fafafa;border-bottom:1px solid #eee;font-size:10px;color:#666}.directoryMap{height:340px}.sourceTag{display:inline-block;background:#f2f2f2;color:#666;border-radius:999px;padding:3px 6px;font-size:8px;margin-right:4px}.mapBtn{display:inline-block;background:#111;color:#fff;text-decoration:none;border-radius:9px;padding:6px 8px;font-size:9px;margin-top:7px}.bizTopline{display:flex;justify-content:space-between;gap:8px;align-items:center}.healthPrompt{background:#fff7f1;border:1px solid #ffe0c8;border-radius:13px;padding:10px;font-size:10px;line-height:1.8;margin:10px 0}@media(max-width:780px){.dirGrid.full{grid-template-columns:1fr}.directoryMap{height:300px}.directoryTitle{align-items:flex-start}.directoryTitleActions{flex-direction:column;align-items:stretch}}
  `;
  document.head.appendChild(style);

  const css=document.createElement('link');css.rel='stylesheet';css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';document.head.appendChild(css);
  const js=document.createElement('script');js.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';js.onload=initMap;document.head.appendChild(js);

  function readLocal(){try{return JSON.parse(localStorage.getItem(STORE)||'[]')}catch(e){return []}}
  function legacyToObj(x){const p=AlanBiz.legacyPair(Number(x[1]));return{id:'legacy_'+norm(x[0])+'_'+norm(x[2]),name:x[0],top:p[0],sub:p[1],area:x[2]||'',address:x[3]||'',phone:x[4]||'',lat:null,lng:null,source:'legacy'}}
  function allBusinesses(){return DATA.map(legacyToObj).concat(readLocal())}
  function safe(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}

  const topSel=document.getElementById('cat');
  const dirGrid=document.querySelector('.dirGrid');
  topSel.innerHTML='<option value="">همه حوزه‌ها</option>'+AlanBiz.topOptions().map(x=>`<option value="${x.key}">${x.icon} ${x.label}</option>`).join('');
  const subSel=document.createElement('select');subSel.id='subcat';subSel.innerHTML='<option value="">همه زیردسته‌ها</option>';dirGrid.appendChild(subSel);dirGrid.classList.add('full');
  function renderSubFilter(){const top=topSel.value;subSel.innerHTML='<option value="">همه زیردسته‌ها</option>'+(top?AlanBiz.subOptions(top).map(x=>`<option value="${x.key}">${x.label}</option>`).join(''):'')}
  topSel.addEventListener('change',()=>{renderSubFilter();enhancedRender()});subSel.addEventListener('change',enhancedRender);

  const title=document.querySelector('.directoryTitle');
  const oldIcon=title.querySelector('span');if(oldIcon)oldIcon.remove();
  const actions=document.createElement('div');actions.className='directoryTitleActions';actions.innerHTML='<a class="addBizBtn" href="add-business.html">＋ افزودن کسب‌وکار</a><span>🔎</span>';title.appendChild(actions);

  const mapBox=document.createElement('div');mapBox.className='directoryMapBox';mapBox.innerHTML='<div class="directoryMapHead"><b>نقشه کسب‌وکارهای ثبت‌شده</b><span id="mapCount">۰ نقطه</span></div><div id="businessMap" class="directoryMap"></div>';
  document.querySelector('.dirPanel').insertBefore(mapBox,document.getElementById('count').nextSibling);
  const healthHint=document.createElement('div');healthHint.className='healthPrompt';healthHint.innerHTML='🩺 حوزه «پزشکی و سلامت» شامل دندانپزشکی، متخصصان دندانپزشکی، پزشک عمومی و متخصص، کلینیک، داروخانه، آزمایشگاه، تصویربرداری، فیزیوتراپی و چند زیرگروه دیگر است.';mapBox.before(healthHint);

  function initMap(){if(!window.L||map)return;map=L.map('businessMap').setView(AHVAZ,12.5);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);markers=L.layerGroup().addTo(map);enhancedRender();setTimeout(()=>map.invalidateSize(),100)}
  function refreshMap(list){if(!map||!markers)return;markers.clearLayers();const geo=list.filter(x=>Number.isFinite(Number(x.lat))&&Number.isFinite(Number(x.lng)));geo.forEach(x=>{L.marker([Number(x.lat),Number(x.lng)]).addTo(markers).bindPopup(`<b>${safe(x.name)}</b><br>${safe(AlanBiz.subLabel(x.top,x.sub))}<br>${safe(x.area)}<br>${safe(x.address)}`)});document.getElementById('mapCount').textContent=`${geo.length.toLocaleString('fa-IR')} نقطه`;if(geo.length===1)map.setView([Number(geo[0].lat),Number(geo[0].lng)],16);else if(geo.length>1){const b=L.latLngBounds(geo.map(x=>[Number(x.lat),Number(x.lng)]));map.fitBounds(b.pad(.18),{maxZoom:15})}else map.setView(AHVAZ,12.5)}
  function neshanLink(x){return x.lat&&x.lng?`https://nshn.ir/?lat=${encodeURIComponent(x.lat)}&lng=${encodeURIComponent(x.lng)}`:''}
  function card(x){const src=x.source==='manual'?'<span class="sourceTag">ثبت‌شده در AlanOffer</span>':'<span class="sourceTag">بانک اولیه</span>';const mapLink=neshanLink(x);return `<div class="biz"><div class="bizTopline"><span class="tag">${safe(AlanBiz.subLabel(x.top,x.sub))}</span>${src}</div><h3>${safe(x.name)}</h3><div class="mini">📍 ${safe(x.area||'محله نامشخص')}<br>${safe(x.address||'آدرس هنوز تکمیل نشده')}${x.phone?`<br>☎ <a href="tel:${safe(x.phone)}">${safe(x.phone)}</a>`:''}</div>${mapLink?`<a class="mapBtn" target="_blank" rel="noopener" href="${mapLink}">مسیریابی با نشان</a>`:''}</div>`}
  function enhancedRender(){const qq=norm(q.value),aa=norm(area.value),top=topSel.value,sub=subSel.value;let r=allBusinesses().filter(x=>{const t=norm([x.name,x.area,x.address,AlanBiz.topLabel(x.top),AlanBiz.subLabel(x.top,x.sub)].join(' '));return(!qq||t.includes(qq))&&(!aa||t.includes(aa))&&(!top||x.top===top)&&(!sub||x.sub===sub)});count.textContent=`${r.length.toLocaleString('fa-IR')} نتیجه از ${allBusinesses().length.toLocaleString('fa-IR')} کسب‌وکار`;businesses.innerHTML=r.length?r.slice(0,60).map(card).join('')+(r.length>60?'<div class="biz"><div class="mini">۶۰ نتیجه اول نمایش داده شده؛ جست‌وجو را دقیق‌تر کن.</div></div>':''):'<div class="empty">در این دسته هنوز رکوردی ثبت نشده.<br><a class="addBizBtn" style="display:inline-block;margin-top:10px" href="add-business.html">اولین کسب‌وکار را اضافه کن</a></div>';refreshMap(r)}
  [q,area].forEach(el=>el.addEventListener('input',enhancedRender));
  renderSubFilter();enhancedRender();
  window.renderBusinesses=enhancedRender;
})();