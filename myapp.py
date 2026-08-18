from __future__ import annotations
import json, os, re, shutil, subprocess, threading, time, uuid
from pathlib import Path
import requests
from flask import Flask, jsonify, render_template_string, request, send_file
from werkzeug.utils import secure_filename

ROOT=Path(__file__).resolve().parent
DATA_ROOT=Path(os.environ.get('DATA_ROOT', str(ROOT/'data'))); DATA_ROOT.mkdir(parents=True,exist_ok=True)
app=Flask(__name__); app.config['MAX_CONTENT_LENGTH']=120*1024*1024
from alanoffer_blueprint import create_alanoffer_blueprint
app.register_blueprint(create_alanoffer_blueprint(DATA_ROOT))
AVALAI_BASE_URL=os.environ.get('AVALAI_BASE_URL','https://api.avalai.ir/v1').rstrip('/')
AVALAI_MODEL=os.environ.get('AVALAI_MODEL','gpt-5.4-mini')
LIPSYNC_API_URL=os.environ.get('LIPSYNC_API_URL','').strip(); LIPSYNC_API_TOKEN=os.environ.get('LIPSYNC_API_TOKEN','').strip(); LIPSYNC_COMMAND=os.environ.get('LIPSYNC_COMMAND','').strip()
JOBS={}; LOCK=threading.Lock()
VIDEO_MODES=[('doctor_avatar','ویدیو با چهره و صدای پزشک',True),('visual_story','ویدیوی تصویری از صفر',False),('reuse_video','ساخت ویدیوی جدید از ویدیوی قبلی',False),('doctor_broll','پزشک + تصاویر کمکی',False),('voiceover','ویدیوی آموزشی با نریشن',False),('photo_video','ساخت ویدیو از عکس پزشک',False),('long_to_reels','تبدیل ویدیوی بلند به چند ریلز',False)]

PAGE='''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><title>استودیوی هوشمند تولید ویدیو</title><style>
:root{--p:#5b46f5;--n:#111a43;--bg:#f5f7fc;--ok:#119c63;--bad:#cf4040;--mut:#747d91}*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:Tahoma,Arial,sans-serif;color:#18203b}.wrap{max-width:760px;margin:auto;padding:12px 10px 70px}.card,.hero{background:#fff;border-radius:22px;padding:17px;margin:12px 0;box-shadow:0 5px 22px #28345a12}.hero{background:linear-gradient(135deg,#fff,#eef3ff)}h1{font-size:24px;margin:0 0 8px;color:var(--n)}h2{font-size:19px;margin:0 0 12px}.sub,.msg{font-size:13px;color:var(--mut);line-height:1.9}.status{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.pill{padding:6px 9px;border-radius:99px;background:#eef1f7;font-size:12px}.pill.ok{background:#e5f8ef;color:#087549}.pill.warn{background:#fff1d6;color:#8a5a00}.modes{display:grid;grid-template-columns:1fr 1fr;gap:8px}.mode{border:1px solid #e2e7f0;border-radius:15px;padding:11px;min-height:78px}.mode.active{border:2px solid var(--p);background:#f5f2ff}.mode.off{opacity:.5}.num{display:inline-grid;place-items:center;width:27px;height:27px;border-radius:8px;background:#15a9b4;color:#fff;font-weight:bold;margin-left:5px}.steps{display:flex;gap:5px;overflow:auto;margin:10px 0}.step{padding:8px 10px;border-radius:11px;background:#edf0f6;color:#687087;white-space:nowrap;font-size:12px;font-weight:bold}.step.on{background:var(--p);color:#fff}.panel{display:none}.panel.on{display:block}label{display:block;margin:11px 0 6px;font-weight:bold;font-size:13px}input,textarea,select{width:100%;padding:12px;border:1px solid #dce2ec;border-radius:12px;background:#fff;font:inherit}textarea{min-height:112px;line-height:1.9}.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.btn{width:100%;border:0;border-radius:13px;padding:13px;margin-top:11px;background:var(--p);color:white;font:inherit;font-weight:bold;cursor:pointer}.btn:disabled{opacity:.45;cursor:not-allowed;filter:grayscale(.25)}.btn.sec{background:#eef1f7;color:#27304b}.btn.ok{background:var(--ok)}.btn.bad{background:var(--bad)}.preview{width:100%;max-height:470px;object-fit:contain;border-radius:15px;background:#0b1022;margin-top:9px}.hidden{display:none}.scene{border:1px solid #e1e6ef;border-radius:15px;padding:10px;margin:9px 0}.sceneTop{display:flex;justify-content:space-between}.actions{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px}.actions .btn{font-size:12px;padding:9px 5px}.progress{height:9px;background:#e7eaf1;border-radius:99px;overflow:hidden;margin-top:9px}.progress div{height:100%;background:linear-gradient(90deg,var(--p),#16b1bb);width:0}.download{display:block;text-align:center;text-decoration:none;background:#142044;color:#fff;border-radius:13px;padding:13px;margin-top:9px;font-weight:bold}.legacy{border:1px dashed #c7cfdf}.nav2{display:grid;grid-template-columns:1fr 1fr;gap:8px}.choiceRow{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}.choice{border:1px solid #dce2ec;background:#fff;color:#27304b;border-radius:13px;padding:12px;font:inherit;font-weight:bold}.choice.on{border:2px solid var(--p);background:#f5f2ff;color:#3e2bd6}.summaryBox{background:#f7f8fc;border:1px solid #e3e7ef;border-radius:13px;padding:11px;margin:10px 0}.summaryText{white-space:pre-wrap;line-height:1.9;font-size:13px;max-height:150px;overflow:auto}.step{cursor:pointer}.step.locked{opacity:.45;cursor:not-allowed}#wizard{scroll-margin-top:12px}@media(max-width:560px){.modes,.grid{grid-template-columns:1fr}h1{font-size:21px}}
</style></head><body><div class="wrap"><div class="hero"><h1>استودیوی هوشمند تولید ویدیو برای درمانگران</h1><div class="sub">نسخه ارتقایافته روی همان مسیر Cloudiva — مدل ۱ فعال</div><div class="status"><span id="ff" class="pill">FFmpeg…</span><span id="av" class="pill">AvalAI…</span><span id="ls" class="pill">Lip-sync…</span></div></div>
<div class="card"><h2>۷ مدل اصلی تولید ویدیو</h2><div class="modes">{% for key,title,active in modes %}{% if active %}<a href="#wizard" class="mode active" style="cursor:pointer;text-decoration:none;color:inherit;display:block"><span class="num">{{loop.index}}</span><b>{{title}}</b><div class="sub">برای شروع لمس کن</div></a>{% else %}<div class="mode off"><span class="num">{{loop.index}}</span><b>{{title}}</b><div class="sub">بعداً اضافه می‌شود</div></div>{% endif %}{% endfor %}</div>{% if modes[0][2] %}<a class="btn" href="#wizard" style="display:block;text-align:center;text-decoration:none">شروع مدل ۱</a>{% endif %}</div>
<div class="card" id="wizard"><h2>مدل ۱ — چهره و صدای پزشک</h2><div class="steps"><span class="step on" data-s="1" onclick="go(1)">۱ محتوا</span><span class="step locked" data-s="2" onclick="go(2)">۲ چهره</span><span class="step locked" data-s="3" onclick="go(3)">۳ صدا</span><span class="step locked" data-s="4" onclick="go(4)">۴ سکانس‌ها</span><span class="step locked" data-s="5" onclick="go(5)">۵ خروجی</span></div>
<div class="panel on" id="p1">
<label>نام پروژه</label><input id="name" value="Darmanjo_Model1_Test">
<label>روش آماده‌سازی متن</label>
<div class="choiceRow"><button type="button" id="chooseCustom" class="choice on" onclick="setScriptMode('custom')">متن خودم</button><button type="button" id="chooseAI" class="choice" onclick="setScriptMode('generate')">ساخت با AI</button></div><input id="sm" type="hidden" value="custom">
<div id="aiFields" class="hidden"><label>موضوع</label><input id="topic" placeholder="مثلاً چرا قیمت ایمپلنت متفاوت است؟"><div class="grid"><div><label>هدف</label><select id="goal"><option>جذب بیمار</option><option>آموزش</option><option>اعتمادسازی</option></select></div><div><label>مدت هدف</label><select id="duration"><option>30</option><option>45</option><option>60</option><option>15</option></select></div></div><button type="button" class="btn sec" id="genBtn" onclick="generateScript()">ساخت سناریو با AI</button></div>
<div id="customFields"><div class="grid"><div><label>هدف</label><select id="goalCustom"><option>جذب بیمار</option><option>آموزش</option><option>اعتمادسازی</option></select></div><div><label>مدت هدف</label><select id="durationCustom"><option>30</option><option>45</option><option>60</option><option>15</option></select></div></div></div>
<label>متن نهایی ویدیو</label><textarea id="script" placeholder="متن دقیق چیزی که قرار است پزشک بگوید…"></textarea>
<button class="btn" id="contentNext" onclick="confirmContent()" disabled>تأیید متن و مرحله بعد</button><div id="m1" class="msg">تا وقتی متن نهایی تأیید نشود، مرحله بعد باز نمی‌شود.</div></div>

<div class="panel" id="p2"><div class="summaryBox"><b>متن تأییدشده</b><div id="scriptPreview2" class="summaryText"></div></div><label>عکس پزشک</label><input id="photo" type="file" accept="image/*"><img id="phPrev" class="preview hidden"><div class="nav2"><button class="btn sec" onclick="go(1)">مرحله قبل</button><button class="btn" id="photoNext" onclick="step2()">آپلود عکس و مرحله بعد</button></div><div id="m2" class="msg"></div></div>

<div class="panel" id="p3"><div class="summaryBox"><b>متن تأییدشده برای خواندن</b><div id="scriptPreview3" class="summaryText"></div></div><label>فایل صوتی پزشک</label><input id="voice" type="file" accept="audio/*"><label>زیرنویس</label><select id="submode"><option value="off">خاموش</option><option value="script_exact">دقیقاً همین متن تأییدشده را خوانده‌ام</option><option value="transcript">متن دقیق فایل صوتی را وارد می‌کنم</option></select><textarea id="transcript" placeholder="فقط در حالت متن دقیق…"></textarea><label><input id="fit" type="checkbox" style="width:auto"> اگر اختلاف کم بود، صدا به مدت هدف Fit شود</label><div class="nav2"><button class="btn sec" onclick="go(2)">مرحله قبل</button><button class="btn" onclick="step3()">بهبود صدا و ساخت سکانس‌ها</button></div><audio id="clean" controls class="hidden" style="width:100%;margin-top:10px"></audio><div id="m3" class="msg"></div></div>

<div class="panel" id="p4"><div class="sub">تقسیم بر اساس مکث واقعی صدا؛ معمولاً ۴ تا ۸ ثانیه. هر کلیپ مستقل ساخته می‌شود.</div><div id="scenes"></div><button class="btn" onclick="renderAll()">ساخت همه سکانس‌ها</button><div class="progress"><div id="bar"></div></div><div id="m4" class="msg"></div><div class="nav2"><button class="btn sec" onclick="go(3)">مرحله قبل</button><button class="btn ok" id="outputNext" onclick="go(5)" disabled>خروجی نهایی</button></div><div class="msg" id="sceneGateMsg">برای رفتن به خروجی، همه سکانس‌ها باید ساخته و تأیید شوند.</div></div>

<div class="panel" id="p5"><button class="btn sec" onclick="go(4)">مرحله قبل</button><button class="btn" onclick="compose()">مونتاژ نهایی</button><video id="final" class="preview hidden" controls playsinline></video><a id="dl" class="download hidden">دانلود MP4</a><a id="pack" class="download hidden" style="background:#606b82">دانلود پکیج پروژه</a><div id="m5" class="msg"></div></div></div></div>
<div class="card legacy"><h2>تست ۵ ثانیه‌ای Lip-sync</h2><div class="sub">همان تست قبلی حفظ شده تا موتور اختصاصی را جداگانه کنترل کنیم.</div><input id="lph" type="file" accept="image/*"><br><br><input id="lvo" type="file" accept="audio/*"><button class="btn sec" onclick="legacy()">اجرای تست ۵ ثانیه‌ای</button><video id="lv" class="preview hidden" controls playsinline></video><div id="lm" class="msg"></div></div></div>
<script>
let pid=null,timer=null;
const E=(id)=>document.getElementById(id);
const state={content:false,photo:false,voice:false,scenes:false};
function M(id,t,c=''){let e=E(id);if(!e)return;e.textContent=t;e.style.color=c==='bad'?'#c33':c==='ok'?'#087549':''}
function canOpen(n){if(n<=1)return true;if(n===2)return state.content;if(n===3)return state.content&&state.photo;if(n===4)return state.content&&state.photo&&state.voice;if(n===5)return state.content&&state.photo&&state.voice&&state.scenes;return false}
function gateText(n){return n===2?'ابتدا متن نهایی را تأیید کن.':n===3?'ابتدا عکس پزشک را ثبت کن.':n===4?'ابتدا فایل صوتی را ثبت و پردازش کن.':n===5?'ابتدا همه سکانس‌ها را بساز و تأیید کن.':'این مرحله هنوز باز نشده است.'}
function updateSteps(){document.querySelectorAll('.step').forEach(x=>{let n=+x.dataset.s;x.classList.toggle('locked',!canOpen(n))});if(E('outputNext'))E('outputNext').disabled=!state.scenes}
function go(n){if(!canOpen(n)){let current=document.querySelector('.panel.on');let mid=current?current.querySelector('.msg'):null;if(mid)M(mid.id,gateText(n),'bad');return false}document.querySelectorAll('.panel').forEach(x=>x.classList.remove('on'));E('p'+n).classList.add('on');document.querySelectorAll('.step').forEach(x=>x.classList.toggle('on',+x.dataset.s===n));updateSteps();setTimeout(()=>E('wizard').scrollIntoView({behavior:'smooth',block:'start'}),30);return true}
function setScriptMode(mode){E('sm').value=mode;E('chooseCustom').classList.toggle('on',mode==='custom');E('chooseAI').classList.toggle('on',mode==='generate');E('aiFields').classList.toggle('hidden',mode!=='generate');E('customFields').classList.toggle('hidden',mode!=='custom');invalidateContent('روش متن تغییر کرد؛ متن نهایی را دوباره تأیید کن.')}
function currentGoal(){return E('sm').value==='generate'?E('goal').value:E('goalCustom').value}
function currentDuration(){return E('sm').value==='generate'?E('duration').value:E('durationCustom').value}
function syncContentButton(){E('contentNext').disabled=!E('script').value.trim()}
function invalidateContent(msg=''){if(state.content||state.photo||state.voice||state.scenes){state.content=false;state.photo=false;state.voice=false;state.scenes=false;pid=null;updateSteps();if(msg)M('m1',msg,'bad')}syncContentButton()}
async function A(u,o={}){let r=await fetch(u,o),d;try{d=await r.json()}catch{d={error:await r.text()}}if(!r.ok)throw Error(d.error||'خطای سرور');return d}
async function status(){try{let d=await A('/api/status');E('ff').textContent=d.ffmpeg?'FFmpeg آماده':'FFmpeg پیدا نشد';E('ff').className='pill '+(d.ffmpeg?'ok':'warn');E('av').textContent=d.avalai?'AvalAI متصل':'AvalAI بدون کلید';E('av').className='pill '+(d.avalai?'ok':'warn');E('ls').textContent=d.lipsync.label;E('ls').className='pill '+(d.lipsync.ready?'ok':'warn')}catch{}}
async function createProject(){let f=new FormData();f.append('name',E('name').value.trim()||'Darmanjo_Model1');f.append('topic',E('topic')?E('topic').value:'');f.append('goal',currentGoal());f.append('duration',currentDuration());return await A('/api/projects',{method:'POST',body:f})}
async function generateScript(){let topic=E('topic').value.trim();if(!topic)return M('m1','برای ساخت با AI اول موضوع را وارد کن.','bad');M('m1','در حال ساخت سناریو با AI…');E('genBtn').disabled=true;try{let p=await createProject();let s=new FormData();s.append('mode','generate');s.append('topic',topic);s.append('custom_script','');let d=await A(`/api/projects/${p.project_id}/script`,{method:'POST',body:s});E('script').value=d.full_script||'';syncContentButton();M('m1','سناریو ساخته شد. متن را بخوان/ویرایش کن و بعد «تأیید متن و مرحله بعد» را بزن.','ok')}catch(e){M('m1',e.message,'bad')}finally{E('genBtn').disabled=false}}
async function confirmContent(){let text=E('script').value.trim();if(!text)return M('m1','متن نهایی خالی است. متن خودت را وارد کن یا با AI بساز.','bad');M('m1','در حال ثبت متن نهایی…');try{let p=await createProject();pid=p.project_id;let s=new FormData();s.append('mode','custom');s.append('topic',E('topic')?E('topic').value:'');s.append('custom_script',text);await A(`/api/projects/${pid}/script`,{method:'POST',body:s});state.content=true;state.photo=false;state.voice=false;state.scenes=false;E('scriptPreview2').textContent=text;E('scriptPreview3').textContent=text;updateSteps();M('m1','متن نهایی تأیید شد.','ok');go(2)}catch(e){M('m1',e.message,'bad')}}
E('script').addEventListener('input',()=>{if(state.content)invalidateContent('متن تغییر کرد؛ برای جلوگیری از اشتباه، مراحل بعد قفل شدند. دوباره متن را تأیید کن.');else syncContentButton()});
['name','topic','goal','duration','goalCustom','durationCustom'].forEach(id=>{let el=E(id);if(el)el.addEventListener('change',()=>{if(state.content)invalidateContent('تنظیمات محتوا تغییر کرد؛ دوباره متن نهایی را تأیید کن.')})});
E('photo').onchange=()=>{const p=E('photo');if(p.files[0]){E('phPrev').src=URL.createObjectURL(p.files[0]);E('phPrev').classList.remove('hidden')}if(state.photo){state.photo=false;state.voice=false;state.scenes=false;updateSteps();M('m2','عکس تغییر کرد؛ دوباره آپلودش کن.','bad')}};
async function step2(){if(!state.content||!pid)return M('m2','ابتدا مرحله محتوا را کامل کن.','bad');const p=E('photo');if(!p.files[0])return M('m2','عکس لازم است.','bad');let f=new FormData();f.append('file',p.files[0]);M('m2','در حال آپلود عکس…');try{await A(`/api/projects/${pid}/photo`,{method:'POST',body:f});state.photo=true;state.voice=false;state.scenes=false;updateSteps();M('m2','عکس ثبت شد.','ok');go(3)}catch(e){M('m2',e.message,'bad')}}
E('voice').addEventListener('change',()=>{if(state.voice){state.voice=false;state.scenes=false;updateSteps();M('m3','فایل صدا تغییر کرد؛ دوباره پردازش کن.','bad')}});
async function step3(){if(!state.photo||!pid)return M('m3','ابتدا عکس پزشک را ثبت کن.','bad');const v=E('voice');if(!v.files[0])return M('m3','صدا لازم است.','bad');M('m3','پاکسازی صدا و تشخیص مکث‌ها…');let f=new FormData();f.append('file',v.files[0]);f.append('subtitle_mode',E('submode').value);f.append('voice_transcript',E('transcript').value);f.append('fit_duration',E('fit').checked?'1':'0');try{let d=await A(`/api/projects/${pid}/voice`,{method:'POST',body:f});E('clean').src=d.clean_url;E('clean').classList.remove('hidden');draw(d.scenes);state.voice=true;state.scenes=false;updateSteps();M('m3',`${d.scenes.length} سکانس آماده ساخت شد.`,'ok');go(4)}catch(e){M('m3',e.message,'bad')}}
function updateSceneGate(a){let all=Array.isArray(a)&&a.length>0&&a.every(s=>s.video&&s.approved);state.scenes=all;E('outputNext').disabled=!all;M('sceneGateMsg',all?'همه سکانس‌ها ساخته و تأیید شدند؛ خروجی باز شد.':'برای رفتن به خروجی، همه سکانس‌ها باید ساخته و تأیید شوند.',all?'ok':'');updateSteps()}
function draw(a){const box=E('scenes');box.innerHTML='';a.forEach(s=>{let x=document.createElement('div');x.className='scene';x.innerHTML=`<div class="sceneTop"><b>${s.scene_id} — ${Number(s.audio_duration||0).toFixed(1)} ثانیه</b><small>${s.approved?'تأیید':s.video?'ساخته شده':'در انتظار'}</small></div><div class="sub">${s.text||'بدون زیرنویس'}</div>${s.url?`<video class="preview" controls playsinline src="${s.url}?v=${Date.now()}"></video>`:''}<div class="actions"><button class="btn sec" onclick="one('${s.scene_id}')">${s.video?'بازسازی':'ساخت'}</button><button class="btn ok" ${s.video?'':'disabled'} onclick="okScene('${s.scene_id}')">تأیید</button><button class="btn bad" ${s.video?'':'disabled'} onclick="noScene('${s.scene_id}')">رد</button></div>`;box.appendChild(x)});updateSceneGate(a)}
async function refresh(){let d=await A(`/api/projects/${pid}/scenes`);draw(d.scenes);return d.scenes}
async function one(s){M('m4',s+' در حال ساخت…');try{await A(`/api/projects/${pid}/scenes/${s}/render`,{method:'POST'});await refresh();M('m4',s+' آماده شد؛ برای ادامه آن را تأیید کن.','ok')}catch(e){M('m4',e.message,'bad')}}
async function okScene(s){try{await A(`/api/projects/${pid}/scenes/${s}/approve`,{method:'POST'});await refresh()}catch(e){M('m4',e.message,'bad')}}
async function noScene(s){try{await A(`/api/projects/${pid}/scenes/${s}/reject`,{method:'POST'});await refresh();M('m4','سکانس رد شد؛ آن را بازسازی کن.','bad')}catch(e){M('m4',e.message,'bad')}}
async function renderAll(){if(!state.voice||!pid)return M('m4','ابتدا مرحله صدا را کامل کن.','bad');M('m4','ساخت همه سکانس‌ها شروع شد…');try{let d=await A(`/api/projects/${pid}/build-job`,{method:'POST'});timer=setInterval(async()=>{try{let j=await A('/api/build-jobs/'+d.job_id);E('bar').style.width=(j.progress||0)+'%';M('m4',j.message,j.status==='failed'?'bad':'');if(['completed','failed'].includes(j.status)){clearInterval(timer);timer=null;await refresh();if(j.status==='completed')M('m4','سکانس‌ها ساخته شدند. هر سکانس را ببین و تأیید کن.','ok')}}catch(e){clearInterval(timer);timer=null;M('m4',e.message,'bad')}},1800)}catch(e){M('m4',e.message,'bad')}}
async function compose(){if(!state.scenes)return M('m5','همه سکانس‌ها باید ساخته و تأیید شوند.','bad');M('m5','مونتاژ…');try{let d=await A(`/api/projects/${pid}/compose`,{method:'POST'});E('final').src=d.final_url+'?v='+Date.now();E('final').classList.remove('hidden');E('dl').href=d.final_url;E('dl').classList.remove('hidden');E('pack').href=d.package_url;E('pack').classList.remove('hidden');M('m5',`آماده — ${d.qc.width||''}×${d.qc.height||''} / ${Number(d.qc.duration||0).toFixed(1)} ثانیه`,'ok')}catch(e){M('m5',e.message,'bad')}}
async function legacy(){const ph=E('lph'),vo=E('lvo');if(!ph.files[0]||!vo.files[0])return M('lm','عکس و صدا لازم‌اند','bad');let f=new FormData();f.append('photo',ph.files[0]);f.append('voice',vo.files[0]);M('lm','در حال تست…');try{let d=await A('/api/legacy-5s',{method:'POST',body:f});E('lv').src=d.url+'?v='+Date.now();E('lv').classList.remove('hidden');M('lm',d.message,'ok')}catch(e){M('lm',e.message,'bad')}}
setScriptMode('custom');syncContentButton();updateSteps();status();
</script></body></html>'''

def pdir(pid):
    if not re.fullmatch(r'[A-Za-z0-9_-]{4,80}',pid or ''): raise ValueError('شناسه نامعتبر')
    p=DATA_ROOT/pid;p.mkdir(parents=True,exist_ok=True);return p

def load_meta(pid):
    p=pdir(pid)/'meta.json'
    if not p.exists(): raise FileNotFoundError('پروژه پیدا نشد')
    return json.loads(p.read_text(encoding='utf-8'))

def save_meta(pid,d):
    p=pdir(pid)/'meta.json';c=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'project_id':pid};c.update(d);c['updated_at']=time.time();p.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8');return c

def run(cmd,check=True):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if check and p.returncode!=0: raise RuntimeError((p.stderr or p.stdout or 'command failed')[-1200:])
    return p

def ffok(): return bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))
def probe(path):
    d=json.loads(run(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height,r_frame_rate,codec_type','-of','json',str(path)]).stdout or '{}');o={'duration':float((d.get('format')or{}).get('duration')or 0)}
    for s in d.get('streams')or[]:
        if s.get('codec_type')=='video':o.update(width=s.get('width'),height=s.get('height'),fps=s.get('r_frame_rate'))
    return o

def enhance(src,dst):
    if not ffok(): shutil.copy2(src,dst);return
    filt='highpass=f=70,lowpass=f=15000,afftdn=nf=-25,acompressor=threshold=-18dB:ratio=2.2:attack=20:release=180,loudnorm=I=-16:TP=-1.5:LRA=8'
    run(['ffmpeg','-y','-i',str(src),'-vn','-af',filt,'-ar','48000','-ac','1',str(dst)])
def fit_audio(src,dst,target,enabled):
    dur=probe(src)['duration'] if ffok() else target
    if not enabled or not dur or not target or abs(dur-target)/target>.15: shutil.copy2(src,dst);return {'applied':False,'source_duration':dur,'final_duration':dur}
    fac=dur/target;run(['ffmpeg','-y','-i',str(src),'-vn','-af',f'atempo={fac:.8f}','-ar','48000','-ac','1',str(dst)]);return {'applied':True,'source_duration':dur,'final_duration':probe(dst)['duration'],'factor':fac}
def pauses(audio):
    if not ffok(): return []
    p=run(['ffmpeg','-hide_banner','-i',str(audio),'-af','silencedetect=noise=-38dB:d=0.28','-f','null','-'],False);t=(p.stderr or '')+'\n'+(p.stdout or '');a=[float(x) for x in re.findall(r'silence_start:\s*([0-9.]+)',t)];b=[float(x) for x in re.findall(r'silence_end:\s*([0-9.]+)',t)];return [(x+y)/2 for x,y in zip(a,b) if y>x]
def spans(audio,target=5.3,minlen=3.2,maxlen=8.0):
    total=probe(audio)['duration'] if ffok() else 5.;ps=[x for x in pauses(audio) if .4<x<total-.25];bounds=[0.];cur=0.
    while total-cur>maxlen:
        c=[x for x in ps if cur+minlen<=x<=cur+maxlen];cut=min(c,key=lambda x:abs((x-cur)-target)) if c else min(total,cur+target)
        if cut-cur<.5:break
        bounds.append(cut);cur=cut
    bounds.append(total)
    if len(bounds)>=3 and bounds[-1]-bounds[-2]<2.2 and bounds[-1]-bounds[-3]<=maxlen+1:bounds.pop(-2)
    return [(round(bounds[i],3),round(bounds[i+1]-bounds[i],3)) for i in range(len(bounds)-1)]
def splittext(text,count,durs):
    text=re.sub(r'\s+',' ',(text or '').strip())
    if not text:return ['']*count
    w=text.split();tot=sum(durs)or count;out=[];pos=0
    for i in range(count):
        if i==count-1:out.append(' '.join(w[pos:]));break
        take=min(max(1,len(w)-pos-(count-i-1)),max(1,round(len(w)*durs[i]/tot)));out.append(' '.join(w[pos:pos+take]));pos+=take
    return (out+['']*count)[:count]
def build_scenes(pid,audio,text):
    sp=spans(audio);caps=splittext(text,len(sp),[d for _,d in sp]) if text else ['']*len(sp);a=[]
    for i,((st,du),cap) in enumerate(zip(sp,caps),1):a.append({'scene_id':f'sc_{i:02d}','order':i,'audio_start':st,'audio_duration':du,'text':cap,'video':'','approved':False,'generation':0})
    (pdir(pid)/'scenes.json').write_text(json.dumps(a,ensure_ascii=False,indent=2),encoding='utf-8');return a
def scenes(pid):
    p=pdir(pid)/'scenes.json';return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
def save_scenes(pid,a):(pdir(pid)/'scenes.json').write_text(json.dumps(a,ensure_ascii=False,indent=2),encoding='utf-8')
def segment(full,start,dur,out):run(['ffmpeg','-y','-ss',str(start),'-t',str(dur),'-i',str(full),'-vn','-ar','48000','-ac','1',str(out)]) if ffok() else shutil.copy2(full,out)
def normalize(src,dst,dur):run(['ffmpeg','-y','-i',str(src),'-vf','scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p','-t',str(dur),'-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-b:a','160k','-movflags','+faststart',str(dst)])
def local_motion(photo,audio,dur,out):
    if not ffok():raise RuntimeError('FFmpeg روی سرور پیدا نشد')
    fr=max(1,int(dur*30));vf="scale=1200:2134:force_original_aspect_ratio=increase,crop=1200:2134,zoompan=z='min(zoom+0.00045,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=1080x1920:fps=30,format=yuv420p"%fr;run(['ffmpeg','-y','-loop','1','-i',str(photo),'-i',str(audio),'-vf',vf,'-t',str(dur),'-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-b:a','160k','-shortest','-movflags','+faststart',str(out)])
def lstatus():
    if LIPSYNC_API_URL:return {'ready':True,'mode':'api','label':'Lip-sync API متصل'}
    if LIPSYNC_COMMAND:return {'ready':True,'mode':'command','label':'موتور Lip-sync محلی متصل'}
    return {'ready':False,'mode':'fallback','label':'Lip-sync فعلاً fallback'}
def lip_api(photo,audio,out,dur):
    h={'Authorization':'Bearer '+LIPSYNC_API_TOKEN} if LIPSYNC_API_TOKEN else {}
    with photo.open('rb') as im,audio.open('rb') as au:r=requests.post(LIPSYNC_API_URL,headers=h,files={'image':im,'audio':au},data={'duration':str(dur),'format':'mp4'},timeout=900)
    if not r.ok:raise RuntimeError(f'Lip-sync API {r.status_code}: {r.text[:250]}')
    if 'video' in r.headers.get('content-type','') or 'octet-stream' in r.headers.get('content-type',''):out.write_bytes(r.content);return
    d=r.json();u=d.get('url')or d.get('video_url')or d.get('output_url');rr=requests.get(u,timeout=300);rr.raise_for_status();out.write_bytes(rr.content)
def lip_cmd(photo,audio,out,dur):
    c=LIPSYNC_COMMAND.format(image=str(photo),audio=str(audio),output=str(out),duration=str(dur));p=subprocess.run(c,shell=True,capture_output=True,text=True,timeout=900)
    if p.returncode!=0 or not out.exists():raise RuntimeError((p.stderr or p.stdout or 'Lip-sync failed')[-800:])
def avatar(photo,audio,dur,out):
    raw=out.with_name(out.stem+'_raw.mp4');st=lstatus()
    if st['mode']=='api':lip_api(photo,audio,raw,dur)
    elif st['mode']=='command':lip_cmd(photo,audio,raw,dur)
    else:local_motion(photo,audio,dur,raw)
    normalize(raw,out,dur);raw.unlink(missing_ok=True)
def render_scene(pid,sid):
    m=load_meta(pid);a=scenes(pid);s=next((x for x in a if x['scene_id']==sid),None)
    if not s:raise KeyError(sid)
    p=pdir(pid);au=p/f'{sid}_audio.wav';segment(Path(m['voice_final']),s['audio_start'],s['audio_duration'],au);out=p/f"{sid}_g{s.get('generation',0)+1}.mp4";avatar(Path(m['photo']),au,s['audio_duration'],out);s['video']=str(out);s['generation']=s.get('generation',0)+1;s['approved']=False;save_scenes(pid,a);return s
def public(pid,s):
    d=dict(s)
    if d.get('video'):d['url']=f"/api/projects/{pid}/file/{Path(d['video']).name}"
    return d
def compose_file(pid):
    a=sorted(scenes(pid),key=lambda x:x['order'])
    if not a or any(not x.get('video') for x in a):raise RuntimeError('همه سکانس‌ها ساخته نشده‌اند')
    p=pdir(pid);lst=p/'concat.txt';lst.write_text('\n'.join("file '"+Path(x['video']).name+"'" for x in a),encoding='utf-8');out=p/'final_reel.mp4';run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(lst),'-c','copy',str(out)],False)
    if not out.exists() or out.stat().st_size<1000:
        ins=[]
        for x in a:ins+=['-i',x['video']]
        fc=''.join(f'[{i}:v][{i}:a]' for i in range(len(a)))+f'concat=n={len(a)}:v=1:a=1[v][a]';run(['ffmpeg','-y',*ins,'-filter_complex',fc,'-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-b:a','160k','-movflags','+faststart',str(out)])
    qc=probe(out);save_meta(pid,{'final_video':str(out),'qc':qc,'status':'completed'});z=Path(shutil.make_archive(str(p.parent/(pid+'_package')),'zip',root_dir=p));return out,qc,z
def akey():return os.environ.get('AVALAI_API_KEY','').strip()
def gen_script(topic,duration,goal):
    if not akey():return {'full_script':topic.strip() or 'موضوع را وارد کنید','source':'fallback'}
    sy='تو سناریونویس سختگیر محتوای کوتاه پزشکی هستی. فقط JSON با کلید full_script بده. فارسی محاوره‌ای، بدون ادعای پزشکی یا قیمت ساختگی، هوک کوتاه، بدنه روشن و CTA طبیعی.';us=f'موضوع: {topic}\nهدف: {goal}\nمدت: حدود {duration} ثانیه.';r=requests.post(AVALAI_BASE_URL+'/chat/completions',headers={'Authorization':'Bearer '+akey(),'Content-Type':'application/json'},json={'model':AVALAI_MODEL,'messages':[{'role':'system','content':sy},{'role':'user','content':us}],'temperature':.4,'response_format':{'type':'json_object'}},timeout=90)
    if not r.ok:raise RuntimeError(f'AvalAI {r.status_code}: {r.text[:220]}')
    c=r.json()['choices'][0]['message']['content']
    try:d=json.loads(c)
    except:d={'full_script':c}
    return {'full_script':str(d.get('full_script')or '').strip(),'source':'avalai'}
def save_job(j):
    with LOCK:JOBS[j['job_id']]=dict(j)
def update_job(jid,**kw):
    with LOCK:j=dict(JOBS.get(jid)or{});j.update(kw);JOBS[jid]=j;return j
def worker(jid,pid):
    try:
        a=scenes(pid);n=max(1,len(a));update_job(jid,status='rendering',progress=2,message='ساخت سکانس‌ها شروع شد')
        for i,s in enumerate(a,1):
            cur=next(x for x in scenes(pid) if x['scene_id']==s['scene_id'])
            if not cur.get('video'):render_scene(pid,s['scene_id'])
            update_job(jid,progress=int(5+78*i/n),message=f'سکانس {i} از {n} آماده شد')
        update_job(jid,status='composing',progress=90,message='مونتاژ');out,qc,z=compose_file(pid);update_job(jid,status='completed',progress=100,message='خروجی آماده شد',final_url=f'/api/projects/{pid}/file/{out.name}',package_url=f'/api/projects/{pid}/file/{z.name}',qc=qc)
    except Exception as e:update_job(jid,status='failed',progress=100,message=str(e),error=type(e).__name__)

@app.after_request
def no_cache(resp):
    resp.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma']='no-cache'
    resp.headers['Expires']='0'
    return resp

@app.get('/')
def home():return render_template_string(PAGE,modes=VIDEO_MODES)
@app.get('/health')
def health():return jsonify(ok=True,time=time.time())
@app.get('/api/status')
def status():return jsonify(ok=True,ffmpeg=ffok(),avalai=bool(akey()),lipsync=lstatus())
@app.post('/api/projects')
def create():
    pid='p_'+uuid.uuid4().hex[:14];d={'project_id':pid,'name':request.form.get('name')or pid,'topic':request.form.get('topic','').strip(),'goal':request.form.get('goal','جذب بیمار'),'duration':int(request.form.get('duration') or 30),'created_at':time.time(),'status':'created'};save_meta(pid,d);return jsonify(d)
@app.post('/api/projects/<pid>/script')
def script_api(pid):
    m=load_meta(pid);mode=request.form.get('mode','custom');custom=request.form.get('custom_script','').strip();topic=request.form.get('topic','').strip()or m.get('topic','')
    if mode=='custom':
        if not custom:return jsonify(error='سناریو را وارد کن'),400
        d={'full_script':custom,'source':'custom'}
    else:d=gen_script(topic,int(m.get('duration',30)),m.get('goal','جذب بیمار'))
    save_meta(pid,{'script':d['full_script'],'script_source':d['source'],'status':'script_ready'});return jsonify(d)
@app.post('/api/projects/<pid>/photo')
def photo_api(pid):
    load_meta(pid);f=request.files.get('file')
    if not f:return jsonify(error='عکس لازم است'),400
    ext=Path(secure_filename(f.filename or 'photo.jpg')).suffix.lower()or'.jpg';dest=pdir(pid)/('photo'+ext);f.save(dest);save_meta(pid,{'photo':str(dest),'status':'photo_ready'});return jsonify(url=f'/api/projects/{pid}/file/{dest.name}')
@app.post('/api/projects/<pid>/voice')
def voice_api(pid):
    m=load_meta(pid);f=request.files.get('file')
    if not f:return jsonify(error='صدا لازم است'),400
    ext=Path(secure_filename(f.filename or 'voice.m4a')).suffix.lower()or'.m4a';raw=pdir(pid)/('voice_raw'+ext);f.save(raw);clean=pdir(pid)/'voice_clean.wav';enhance(raw,clean);final=pdir(pid)/'voice_final.wav';fi=fit_audio(clean,final,float(m.get('duration',30)),request.form.get('fit_duration')=='1');sm=request.form.get('subtitle_mode','off');exact=''
    if sm=='script_exact':exact=m.get('script','')
    elif sm=='transcript':
        exact=request.form.get('voice_transcript','').strip()
        if not exact:return jsonify(error='متن دقیق فایل صدا را وارد کن'),400
    else:sm='off'
    a=build_scenes(pid,final,exact if sm!='off' else '');save_meta(pid,{'voice_raw':str(raw),'voice_clean':str(clean),'voice_final':str(final),'subtitle_mode':sm,'fit':fi,'status':'voice_ready'});return jsonify(clean_url=f'/api/projects/{pid}/file/{final.name}',scenes=[public(pid,x) for x in a],fit=fi)
@app.get('/api/projects/<pid>/scenes')
def scenes_api(pid):load_meta(pid);return jsonify(scenes=[public(pid,x) for x in scenes(pid)])
@app.post('/api/projects/<pid>/scenes/<sid>/render')
def render_api(pid,sid):
    try:return jsonify(public(pid,render_scene(pid,sid)))
    except Exception as e:return jsonify(error=str(e)),400
@app.post('/api/projects/<pid>/scenes/<sid>/approve')
def approve_api(pid,sid):
    a=scenes(pid);s=next((x for x in a if x['scene_id']==sid),None)
    if not s:return jsonify(error='سکانس پیدا نشد'),404
    s['approved']=True;save_scenes(pid,a);return jsonify(public(pid,s))
@app.post('/api/projects/<pid>/scenes/<sid>/reject')
def reject_api(pid,sid):
    a=scenes(pid);s=next((x for x in a if x['scene_id']==sid),None)
    if not s:return jsonify(error='سکانس پیدا نشد'),404
    s['approved']=False;save_scenes(pid,a);return jsonify(public(pid,s))
@app.post('/api/projects/<pid>/build-job')
def build_api(pid):
    m=load_meta(pid)
    if not m.get('photo')or not m.get('voice_final'):return jsonify(error='عکس و صدا لازم است'),400
    jid='j_'+uuid.uuid4().hex[:12];j={'job_id':jid,'project_id':pid,'status':'queued','progress':0,'message':'در صف'};save_job(j);threading.Thread(target=worker,args=(jid,pid),daemon=True).start();return jsonify(j)
@app.get('/api/build-jobs/<jid>')
def job_api(jid):
    with LOCK:j=dict(JOBS.get(jid)or{})
    if not j:return jsonify(error='Job پیدا نشد'),404
    return jsonify(j)
@app.post('/api/projects/<pid>/compose')
def compose_api(pid):
    try:o,q,z=compose_file(pid);return jsonify(final_url=f'/api/projects/{pid}/file/{o.name}',package_url=f'/api/projects/{pid}/file/{z.name}',qc=q)
    except Exception as e:return jsonify(error=str(e)),400
@app.get('/api/projects/<pid>/file/<name>')
def file_api(pid,name):
    name=Path(name).name;p=pdir(pid);t=p/name
    if not t.exists() and name==pid+'_package.zip':t=p.parent/name
    if not t.exists():return jsonify(error='فایل پیدا نشد'),404
    return send_file(t,as_attachment=False)
@app.post('/api/legacy-5s')
def legacy_api():
    ph=request.files.get('photo');vo=request.files.get('voice')
    if not ph or not vo:return jsonify(error='عکس و صدا لازم‌اند'),400
    pid='legacy_'+uuid.uuid4().hex[:10];p=pdir(pid);pext=Path(secure_filename(ph.filename or 'photo.jpg')).suffix or '.jpg';vext=Path(secure_filename(vo.filename or 'voice.m4a')).suffix or '.m4a';photo=p/('photo'+pext);voice=p/('voice'+vext);ph.save(photo);vo.save(voice);cl=p/'voice_clean.wav';enhance(voice,cl);du=min(5.,probe(cl)['duration']) if ffok() else 5.;sh=p/'voice_short.wav';segment(cl,0,du,sh);out=p/'legacy_5s.mp4';avatar(photo,sh,du,out);st=lstatus();return jsonify(url=f'/api/projects/{pid}/file/{out.name}',message='تست با موتور Lip-sync انجام شد' if st['ready'] else 'تست با fallback انجام شد؛ موتور Lip-sync هنوز وصل نیست',renderer=st)
if __name__=='__main__':app.run(host='0.0.0.0',port=3000)
