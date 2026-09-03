(()=>{
'use strict';
const TOKEN_KEY='drlinq_implant_doctor_session';
const API='implant-api';
const statusText=document.createElement('span');
function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
function fmtTime(value){if(!value)return 'هنوز منتشر نشده';try{return new Intl.DateTimeFormat('fa-IR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value))}catch{return value}}
async function api(path,options={}){
  const headers=new Headers(options.headers||{}),token=sessionStorage.getItem(TOKEN_KEY)||'';
  if(token)headers.set('Authorization',`Bearer ${token}`);
  const response=await fetch(`${API}${path}`,{...options,headers,cache:'no-store'});
  if(!response.ok){let detail='خطا در ارتباط با سرور';try{detail=(await response.json()).detail||detail}catch{}throw new Error(detail)}
  return response;
}
function currentCaseId(){return (document.querySelector('.detail-code')?.textContent||'').trim()}
function setMessage(text,error=false){const el=document.getElementById('patientResponseMessage');if(!el)return;el.textContent=text;el.style.color=error?'#b42318':'#087d59'}
function updatePublished(value){const el=document.getElementById('responsePublishedAt');if(el)el.textContent=fmtTime(value)}
async function loadPatientResponse(caseId){
  try{
    const data=await (await api(`/cases/${encodeURIComponent(caseId)}/patient-response`)).json();
    const response=document.getElementById('patientResponse'),required=document.getElementById('moreInfoRequired'),message=document.getElementById('moreInfoMessage');
    if(!response||!required||!message)return;
    response.value=data.patient_response_draft||'';required.checked=Boolean(data.more_info_required_draft);message.value=data.more_info_message_draft||'';message.disabled=!required.checked;updatePublished(data.response_published_at);
  }catch(err){setMessage(`دریافت پاسخ ذخیره‌شده انجام نشد: ${err.message}`,true)}
}
async function savePatientResponse(publish){
  const caseId=currentCaseId(),save=document.getElementById('savePatientResponse'),pub=document.getElementById('publishPatientResponse');
  if(!caseId)return;save.disabled=true;pub.disabled=true;setMessage(publish?'در حال انتشار…':'در حال ذخیره…');
  try{
    const payload={patient_response:document.getElementById('patientResponse').value,more_info_required:document.getElementById('moreInfoRequired').checked,more_info_message:document.getElementById('moreInfoMessage').value,publish};
    const data=await (await api(`/cases/${encodeURIComponent(caseId)}/patient-response`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})).json();
    updatePublished(data.response_published_at);setMessage(publish?'پاسخ برای بیمار منتشر شد.':'پاسخ به‌صورت پیش‌نویس ذخیره شد.');
  }catch(err){setMessage(`ذخیره نشد: ${err.message}`,true)}finally{save.disabled=false;pub.disabled=false}
}
function install(){
  const note=document.getElementById('doctorNote');if(!note||document.getElementById('patientResponsePanel'))return;
  const noteLabel=document.querySelector('label[for="doctorNote"]');if(noteLabel)noteLabel.textContent='یادداشت داخلی پزشک (فقط پزشک)';
  note.placeholder='این یادداشت فقط در پنل پزشک می‌ماند و به بیمار نمایش داده نمی‌شود.';
  const section=note.closest('section');if(!section)return;
  section.insertAdjacentHTML('afterend',`<section id="patientResponsePanel" class="section full"><h2>پاسخ به بیمار</h2><p class="muted" style="margin-top:-6px">این بخش از یادداشت داخلی جداست. فقط نسخه منتشرشده در لینک امن بیمار دیده می‌شود.</p><label class="label" for="patientResponse">پاسخ قابل‌نمایش به بیمار</label><textarea id="patientResponse" class="textarea" placeholder="پاسخ ساده و قابل‌فهم برای بیمار را اینجا بنویسید."></textarea><label class="consent" style="margin-top:14px"><input id="moreInfoRequired" type="checkbox"><span>اطلاعات یا تصویر بیشتری لازم است</span></label><label class="label" for="moreInfoMessage" style="margin-top:12px">پیام درخواست اطلاعات بیشتر</label><textarea id="moreInfoMessage" class="textarea" style="min-height:90px" placeholder="مثلاً: لطفاً OPG جدید یا عکس سمت چپ را ارسال کنید." disabled></textarea><div class="facts" style="margin-top:14px"><div class="fact"><b>زمان آخرین انتشار</b><span id="responsePublishedAt">هنوز منتشر نشده</span></div></div><div class="save-row" style="flex-wrap:wrap"><button id="savePatientResponse" class="btn secondary" type="button">ذخیره پیش‌نویس</button><button id="publishPatientResponse" class="btn primary" type="button">ذخیره و انتشار پاسخ</button><span id="patientResponseMessage" class="save-message"></span></div></section>`);
  document.getElementById('moreInfoRequired').onchange=event=>{document.getElementById('moreInfoMessage').disabled=!event.currentTarget.checked};
  document.getElementById('savePatientResponse').onclick=()=>savePatientResponse(false);
  document.getElementById('publishPatientResponse').onclick=()=>savePatientResponse(true);
  const caseId=currentCaseId();if(caseId)loadPatientResponse(caseId);
}
new MutationObserver(install).observe(document.documentElement,{childList:true,subtree:true});
install();
})();
