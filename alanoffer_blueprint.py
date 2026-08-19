from __future__ import annotations
import json, os, re, secrets, sqlite3, time
from pathlib import Path
from typing import Any
from flask import Blueprint, jsonify, request

VERSION='0.4.0'
FLOW=[
 ('service','چه خدمت یا درمانی می‌خوای؟','مثلاً ایمپلنت، ترمیم چند دندان، لیزر پوست یا فیزیوتراپی زانو',[],False),
 ('city','در کدوم شهر دنبال درمانگر می‌گردی؟','فعلاً فقط مراکز استان‌ها پوشش داده می‌شن.',[],False),
 ('priorities','برای انتخاب درمانگر، کدوم چیزها برات مهم‌تره؟ حداکثر دو مورد.','دو مورد رو انتخاب کن یا خودت بنویس.',['قیمت بهتر','کیفیت','سرعت','اقساط','نزدیکی'],True),
 ('case_size','حجم کارت تقریباً چقدره؟','مثلاً ۱ ایمپلنت، ۵ دندان یا ۱۰ جلسه؛ اگر نمی‌دونی بنویس «نمی‌دانم».',['یک مورد','۲ تا ۳ مورد','۴ مورد یا بیشتر','نمی‌دانم'],False),
 ('wait','تا کی می‌تونی برای پیدا شدن گزینه مناسب صبر کنی؟','',['امروز','تا ۳ روز','تا یک هفته','عجله ندارم'],False),
 ('contact','برای خبر دادن، شماره موبایل یا واتساپت رو بفرست.','فقط برای پیگیری همین درخواست استفاده می‌شه.',[],False),
]
CAPITALS={'اراک','اردبیل','ارومیه','اصفهان','اهواز','ایلام','بجنورد','بندرعباس','بوشهر','بیرجند','تبریز','تهران','خرم آباد','خرم‌آباد','رشت','زاهدان','زنجان','ساری','سمنان','سنندج','شهرکرد','شیراز','قزوین','قم','کرج','کرمان','کرمانشاه','گرگان','مشهد','همدان','یاسوج','یزد'}
REQ_STATUS={'needs_provider_search','outreach','provider_interested','offered','completed','closed_no_match','cancelled'}
PROV_STATUS={'candidate','contacted','interested','rejected','no_reply','selected'}

def create_alanoffer_blueprint(data_root:str|Path)->Blueprint:
    bp=Blueprint('alanoffer',__name__,url_prefix='/alanoffer')
    root=Path(data_root)/'alanoffer'; root.mkdir(parents=True,exist_ok=True)
    db=Path(os.environ.get('ALANOFFER_DB_PATH',str(root/'alanoffer.db'))); db.parent.mkdir(parents=True,exist_ok=True)
    token=os.environ.get('DRLINQ_ADMIN_TOKEN') or os.environ.get('ALANOFFER_ADMIN_TOKEN') or ''
    origins={x.strip() for x in os.environ.get('ALANOFFER_CORS_ORIGINS','https://hajizadehmasoud5-ui.github.io,https://drlinq.ir,https://www.drlinq.ir').split(',') if x.strip()}
    def con():
        c=sqlite3.connect(str(db),timeout=20); c.row_factory=sqlite3.Row; c.execute('PRAGMA journal_mode=WAL'); return c
    def clean(v:Any,n=300): return re.sub(r'\s+',' ',re.sub(r'[\x00-\x1f]+',' ',str(v or ''))).strip()[:n]
    def norm(v:Any): return clean(v,800).replace('ي','ی').replace('ك','ک').replace('‌',' ').lower()
    def nid(p): return f'{p}_{int(time.time()*1000)}_{secrets.token_hex(5)}'
    def digits(v): return str(v or '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789'))
    def valid_phone(v): return 10<=len(re.sub(r'\D+','',digits(v)))<=15
    def supported_city(v): return norm(v) in {norm(x) for x in CAPITALS}
    def init():
        with con() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS chat_sessions(id TEXT PRIMARY KEY,data_json TEXT NOT NULL DEFAULT '{}',ready INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS chat_records(id TEXT PRIMARY KEY,session_id TEXT NOT NULL UNIQUE,role TEXT NOT NULL DEFAULT 'buyer',payload_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'needs_provider_search',created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL DEFAULT 0,admin_note TEXT NOT NULL DEFAULT '');
            CREATE INDEX IF NOT EXISTS idx_records_status ON chat_records(status,created_at);
            CREATE TABLE IF NOT EXISTS providers(id TEXT PRIMARY KEY,name TEXT NOT NULL,city TEXT NOT NULL DEFAULT '',service_tags TEXT NOT NULL DEFAULT '',whatsapp TEXT NOT NULL DEFAULT '',instagram TEXT NOT NULL DEFAULT '',source TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',accepted_count INTEGER NOT NULL DEFAULT 0,rejected_count INTEGER NOT NULL DEFAULT 0,no_reply_count INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_providers_city ON providers(city);
            CREATE TABLE IF NOT EXISTS request_providers(id TEXT PRIMARY KEY,request_id TEXT NOT NULL,provider_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'candidate',channel TEXT NOT NULL DEFAULT 'whatsapp',note TEXT NOT NULL DEFAULT '',created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,UNIQUE(request_id,provider_id));
            CREATE INDEX IF NOT EXISTS idx_request_providers ON request_providers(request_id);
            ''')
            cols={r['name'] for r in c.execute('PRAGMA table_info(chat_records)')}
            if 'updated_at' not in cols: c.execute('ALTER TABLE chat_records ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0')
            if 'admin_note' not in cols: c.execute("ALTER TABLE chat_records ADD COLUMN admin_note TEXT NOT NULL DEFAULT ''")
            c.execute('UPDATE chat_records SET updated_at=created_at WHERE updated_at=0')
    init()
    def q(data):
        for key,question,hint,options,multi in FLOW:
            if not clean(data.get(key),700):
                data['_awaiting']=key
                return {'reply':question+('\n'+hint if hint else ''),'field':key,'options':options,'multi':multi}
        data.pop('_awaiting',None); return None
    def load(sid):
        with con() as c: r=c.execute('SELECT data_json,ready FROM chat_sessions WHERE id=?',(sid,)).fetchone()
        if not r:return None
        try:d=json.loads(r['data_json'] or '{}'); d=d if isinstance(d,dict) else {}
        except:d={}
        return d,bool(r['ready'])
    def save_session(sid,data,ready=False):
        with con() as c:c.execute('UPDATE chat_sessions SET data_json=?,ready=?,updated_at=? WHERE id=?',(json.dumps(data,ensure_ascii=False),int(ready),int(time.time()*1000),sid))
    def summary(d):return f"{clean(d.get('service'),120)} | {clean(d.get('city'),70)} | اولویت: {clean(d.get('priorities'),120)} | حجم: {clean(d.get('case_size'),100)} | مهلت: {clean(d.get('wait'),80)}"
    def parse(s):
        try:x=json.loads(s or '{}'); return x if isinstance(x,dict) else {}
        except:return {}
    def save_record(sid,d):
        now=int(time.time()*1000)
        with con() as c:
            r=c.execute('SELECT id FROM chat_records WHERE session_id=?',(sid,)).fetchone()
            if r:return r['id']
            rid=nid('req'); c.execute('INSERT INTO chat_records(id,session_id,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',(rid,sid,json.dumps({k:v for k,v in d.items() if not k.startswith('_')},ensure_ascii=False),'needs_provider_search',now,now)); return rid
    def outreach(p):return f"سلام. از طرف دکترلینک یک متقاضی واقعی داریم.\nدرخواست: {clean(p.get('service'),160)}\nشهر: {clean(p.get('city'),80)}\nحجم تقریبی: {clean(p.get('case_size'),100)}\nاولویت بیمار: {clean(p.get('priorities'),120)}\nزمان انتظار: {clean(p.get('wait'),80)}\nاگر تمایل به بررسی این درخواست دارید، فقط «بله» پاسخ دهید."
    def guard():
        if not token:return jsonify(error='admin_token_not_configured'),503
        if not secrets.compare_digest(request.headers.get('X-Admin-Token',''),token):return jsonify(error='unauthorized'),401
        return None
    @bp.after_request
    def cors(resp):
        o=request.headers.get('Origin','')
        if o in origins:
            resp.headers['Access-Control-Allow-Origin']=o; resp.headers['Vary']='Origin'; resp.headers['Access-Control-Allow-Headers']='Content-Type, X-Admin-Token'; resp.headers['Access-Control-Allow-Methods']='GET, POST, OPTIONS'
        resp.headers['Cache-Control']='no-store'; return resp
    @bp.route('/api/<path:_p>',methods=['OPTIONS'])
    def opt(_p):return ('',204)
    @bp.get('/api/health')
    @bp.get('/api/chat/health')
    def health():
        with con() as c:
            nr=c.execute('SELECT COUNT(*) n FROM chat_records').fetchone()['n']; np=c.execute('SELECT COUNT(*) n FROM providers').fetchone()['n']
        return jsonify(ok=True,service='drlinq-demand-matching',version=VERSION,mode='demand-first-mvp',coverage='iran-province-capitals',requests=nr,providers=np,adminConfigured=bool(token))
    @bp.post('/api/chat/start')
    def start():
        sid=nid('cs'); now=int(time.time()*1000); data={}
        with con() as c:
            c.execute('DELETE FROM chat_sessions WHERE updated_at<?',(now-30*24*3600*1000,)); c.execute("INSERT INTO chat_sessions(id,data_json,ready,created_at,updated_at) VALUES(?, '{}',0,?,?)",(sid,now,now))
        z=q(data); save_session(sid,data); return jsonify(ok=True,sessionId=sid,role='buyer',ready=False,**z)
    @bp.post('/api/chat/message')
    def message():
        b=request.get_json(silent=True) or {}; sid=clean(b.get('sessionId'),120); text=clean(b.get('text'),1200)
        if not sid or not text:return jsonify(error='missing_session_or_text'),400
        loaded=load(sid)
        if not loaded:return jsonify(error='session_not_found'),404
        data,ready=loaded
        if ready:
            with con() as c:r=c.execute('SELECT id,status FROM chat_records WHERE session_id=?',(sid,)).fetchone()
            return jsonify(ok=True,ready=True,requestId=r['id'] if r else None,status=r['status'] if r else 'needs_provider_search',reply='این درخواست قبلاً ثبت شده. برای درخواست جدید «درخواست تازه» رو بزن.',summary=summary(data))
        key=clean(data.get('_awaiting'),40)
        if key=='contact' and not valid_phone(text):return jsonify(ok=True,ready=False,reply='یک شماره موبایل یا واتساپ معتبر بفرست؛ فقط شماره کافیه.',field='contact',options=[],multi=False)
        if key=='city' and not supported_city(text):return jsonify(ok=True,ready=False,reply='فعلاً فقط مراکز استان‌ها رو پوشش می‌دیم. اسم مرکز استان رو بنویس؛ مثلاً اهواز، شیراز یا تهران.',field='city',options=[],multi=False)
        if key:data[key]=text; data.pop('_awaiting',None)
        z=q(data)
        if z:save_session(sid,data); return jsonify(ok=True,sessionId=sid,role='buyer',ready=False,**z)
        rid=save_record(sid,data); save_session(sid,data,True)
        return jsonify(ok=True,sessionId=sid,role='buyer',ready=True,requestId=rid,status='needs_provider_search',summary=summary(data),reply='درخواستت ثبت شد. بر اساس شهر، نوع درمان و اولویت‌هات سراغ درمانگرهای مناسب می‌ریم. اگر درمانگری برای بررسی درخواستت اعلام آمادگی کرد، بهت خبر می‌دیم.',field=None,options=[],multi=False)
    @bp.get('/api/request/<rid>')
    def status(rid):
        with con() as c:r=c.execute('SELECT id,payload_json,status,created_at,updated_at FROM chat_records WHERE id=?',(clean(rid,120),)).fetchone()
        if not r:return jsonify(error='not_found'),404
        p=parse(r['payload_json']); p.pop('contact',None); return jsonify(ok=True,id=r['id'],status=r['status'],createdAt=r['created_at'],updatedAt=r['updated_at'],request=p)
    @bp.get('/api/admin/requests')
    def admin_requests():
        x=guard()
        if x:return x
        with con() as c:
            rows=c.execute("SELECT * FROM chat_records WHERE role='buyer' ORDER BY created_at DESC LIMIT 200").fetchall(); out=[]
            for r in rows:
                p=parse(r['payload_json']); links=c.execute('SELECT rp.*,p.name,p.whatsapp,p.instagram FROM request_providers rp JOIN providers p ON p.id=rp.provider_id WHERE rp.request_id=? ORDER BY rp.created_at DESC',(r['id'],)).fetchall()
                out.append({'id':r['id'],'status':r['status'],'createdAt':r['created_at'],'updatedAt':r['updated_at'],'adminNote':r['admin_note'],'payload':p,'outreachText':outreach(p),'providers':[dict(a) for a in links]})
        return jsonify(ok=True,requests=out)
    @bp.post('/api/admin/requests/<rid>/status')
    def admin_status(rid):
        x=guard()
        if x:return x
        b=request.get_json(silent=True) or {}; s=clean(b.get('status'),60); note=clean(b.get('note'),1000)
        if s not in REQ_STATUS:return jsonify(error='invalid_status'),400
        with con() as c:
            cur=c.execute('UPDATE chat_records SET status=?,admin_note=?,updated_at=? WHERE id=?',(s,note,int(time.time()*1000),clean(rid,120)))
            if not cur.rowcount:return jsonify(error='not_found'),404
        return jsonify(ok=True,status=s)
    def get_provider(b,reqp):
        name=clean(b.get('name'),160); wa=clean(b.get('whatsapp'),80); ig=clean(b.get('instagram'),120).lstrip('@')
        if not name or (not wa and not ig):return None
        city=clean(reqp.get('city'),80); tags=clean(reqp.get('service'),200); now=int(time.time()*1000)
        with con() as c:
            r=c.execute('SELECT id FROM providers WHERE (whatsapp<>\'\' AND whatsapp=?) OR (instagram<>\'\' AND instagram=?) LIMIT 1',(wa,ig)).fetchone()
            if r:
                pid=r['id']; c.execute('UPDATE providers SET name=?,city=?,service_tags=?,whatsapp=?,instagram=?,source=?,notes=?,updated_at=? WHERE id=?',(name,city,tags,wa,ig,clean(b.get('source'),120) or 'demand-search',clean(b.get('notes'),500),now,pid)); return pid
            pid=nid('prv'); c.execute('INSERT INTO providers(id,name,city,service_tags,whatsapp,instagram,source,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(pid,name,city,tags,wa,ig,clean(b.get('source'),120) or 'demand-search',clean(b.get('notes'),500),now,now)); return pid
    @bp.post('/api/admin/requests/<rid>/providers')
    def add_provider(rid):
        x=guard()
        if x:return x
        b=request.get_json(silent=True) or {}; rr=clean(rid,120)
        with con() as c:r=c.execute('SELECT payload_json FROM chat_records WHERE id=?',(rr,)).fetchone()
        if not r:return jsonify(error='request_not_found'),404
        pid=get_provider(b,parse(r['payload_json']))
        if not pid:return jsonify(error='provider_name_and_contact_required'),400
        now=int(time.time()*1000); channel='whatsapp' if clean(b.get('whatsapp'),80) else 'instagram'
        with con() as c:
            old=c.execute('SELECT id FROM request_providers WHERE request_id=? AND provider_id=?',(rr,pid)).fetchone()
            if old:link=old['id']
            else:
                link=nid('lnk'); c.execute('INSERT INTO request_providers(id,request_id,provider_id,status,channel,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(link,rr,pid,'candidate',channel,'',now,now))
            c.execute("UPDATE chat_records SET status='outreach',updated_at=? WHERE id=? AND status='needs_provider_search'",(now,rr))
        return jsonify(ok=True,providerId=pid,linkId=link)
    @bp.post('/api/admin/requests/<rid>/providers/<pid>/status')
    def provider_status(rid,pid):
        x=guard()
        if x:return x
        b=request.get_json(silent=True) or {}; s=clean(b.get('status'),40); note=clean(b.get('note'),700); rr=clean(rid,120); pp=clean(pid,120)
        if s not in PROV_STATUS:return jsonify(error='invalid_provider_status'),400
        now=int(time.time()*1000)
        with con() as c:
            old=c.execute('SELECT status FROM request_providers WHERE request_id=? AND provider_id=?',(rr,pp)).fetchone()
            if not old:return jsonify(error='link_not_found'),404
            c.execute('UPDATE request_providers SET status=?,note=?,updated_at=? WHERE request_id=? AND provider_id=?',(s,note,now,rr,pp))
            if old['status']!=s:
                if s=='interested':c.execute('UPDATE providers SET accepted_count=accepted_count+1,updated_at=? WHERE id=?',(now,pp)); c.execute("UPDATE chat_records SET status='provider_interested',updated_at=? WHERE id=?",(now,rr))
                elif s=='rejected':c.execute('UPDATE providers SET rejected_count=rejected_count+1,updated_at=? WHERE id=?',(now,pp))
                elif s=='no_reply':c.execute('UPDATE providers SET no_reply_count=no_reply_count+1,updated_at=? WHERE id=?',(now,pp))
                elif s=='selected':c.execute("UPDATE chat_records SET status='offered',updated_at=? WHERE id=?",(now,rr))
        return jsonify(ok=True,status=s)
    return bp
