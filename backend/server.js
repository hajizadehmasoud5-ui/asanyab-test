import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import {rateLimit} from 'express-rate-limit';
import Database from 'better-sqlite3';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const __dirname=path.dirname(fileURLToPath(import.meta.url));
const PORT=Number(process.env.PORT||8787);
const DB_PATH=process.env.DB_PATH||path.join(__dirname,'data','alanoffer.db');
const ADMIN_TOKEN=String(process.env.ADMIN_TOKEN||'');
const NESHAN_API_KEY=String(process.env.NESHAN_API_KEY||'');
const ORIGINS=String(process.env.CORS_ORIGINS||'https://hajizadehmasoud5-ui.github.io').split(',').map(x=>x.trim()).filter(Boolean);
fs.mkdirSync(path.dirname(DB_PATH),{recursive:true});
const db=new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.exec(`
CREATE TABLE IF NOT EXISTS businesses(
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 top TEXT NOT NULL,
 sub TEXT NOT NULL,
 city TEXT NOT NULL DEFAULT 'اهواز',
 area TEXT NOT NULL,
 address TEXT NOT NULL,
 phone TEXT DEFAULT '',
 instagram TEXT DEFAULT '',
 website TEXT DEFAULT '',
 lat REAL,
 lng REAL,
 source TEXT NOT NULL DEFAULT 'manual',
 source_ref TEXT DEFAULT '',
 status TEXT NOT NULL DEFAULT 'approved',
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_business_city ON businesses(city);
CREATE INDEX IF NOT EXISTS idx_business_area ON businesses(area);
CREATE INDEX IF NOT EXISTS idx_business_top_sub ON businesses(top,sub);
CREATE TABLE IF NOT EXISTS submissions(
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 top TEXT NOT NULL,
 sub TEXT NOT NULL,
 city TEXT NOT NULL DEFAULT 'اهواز',
 area TEXT NOT NULL,
 address TEXT NOT NULL,
 phone TEXT DEFAULT '',
 instagram TEXT DEFAULT '',
 website TEXT DEFAULT '',
 lat REAL NOT NULL,
 lng REAL NOT NULL,
 claimed_status TEXT DEFAULT 'unknown',
 review_status TEXT NOT NULL DEFAULT 'pending',
 submitted_at INTEGER NOT NULL,
 reviewed_at INTEGER,
 review_note TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_submission_review ON submissions(review_status,submitted_at);
`);

const app=express();
app.set('trust proxy',1);
app.use(helmet({crossOriginResourcePolicy:false}));
app.use(cors({origin(origin,cb){if(!origin||ORIGINS.includes(origin))return cb(null,true);return cb(new Error('origin_not_allowed'))}}));
app.use(express.json({limit:'128kb'}));
const submitLimiter=rateLimit({windowMs:60*60*1000,limit:15,standardHeaders:true,legacyHeaders:false});

function clean(x,max=300){return String(x??'').replace(/[\u0000-\u001f]/g,' ').replace(/\s+/g,' ').trim().slice(0,max)}
function norm(x){return clean(x,500).replace(/ي/g,'ی').replace(/ك/g,'ک').toLowerCase()}
function id(prefix){return prefix+'_'+Date.now().toString(36)+'_'+crypto.randomBytes(4).toString('hex')}
function publicRow(r){return {id:r.id,name:r.name,top:r.top,sub:r.sub,city:r.city,area:r.area,address:r.address,phone:r.phone,instagram:r.instagram,website:r.website,lat:r.lat,lng:r.lng,source:r.source,sourceRef:r.source_ref,status:r.status,createdAt:r.created_at}}
function requireAdmin(req,res,next){const t=String(req.headers.authorization||'').replace(/^Bearer\s+/i,'');if(!ADMIN_TOKEN||!crypto.timingSafeEqual(Buffer.from(t),Buffer.from(ADMIN_TOKEN))){return res.status(401).json({error:'admin_unauthorized'})}next()}
function validCoords(lat,lng){return Number.isFinite(lat)&&Number.isFinite(lng)&&lat>=29&&lat<=33&&lng>=46&&lng<=51}

app.get('/api/health',(req,res)=>res.json({ok:true,service:'alanoffer-backend',db:true,neshanSearch:!!NESHAN_API_KEY,time:new Date().toISOString()}));

app.get('/api/businesses',(req,res)=>{
 const q=norm(req.query.q||''),city=clean(req.query.city||'اهواز',80),area=norm(req.query.area||''),top=clean(req.query.top||'',80),sub=clean(req.query.sub||'',80);
 const limit=Math.min(Math.max(Number(req.query.limit)||100,1),500);
 let sql=`SELECT * FROM businesses WHERE status='approved' AND city=?`,args=[city];
 if(top){sql+=' AND top=?';args.push(top)} if(sub){sql+=' AND sub=?';args.push(sub)}
 const rows=db.prepare(sql+' ORDER BY updated_at DESC LIMIT 1000').all(...args).filter(r=>{const text=norm([r.name,r.area,r.address,r.top,r.sub].join(' '));return(!q||text.includes(q))&&(!area||norm(r.area).includes(area)||norm(r.address).includes(area))}).slice(0,limit);
 res.json({items:rows.map(publicRow),count:rows.length});
});

app.post('/api/submissions',submitLimiter,(req,res)=>{
 const b=req.body||{};const name=clean(b.name,140),top=clean(b.top,60),sub=clean(b.sub,60),city=clean(b.city||'اهواز',80),area=clean(b.area,120),address=clean(b.address,350),phone=clean(b.phone,60),instagram=clean(b.instagram,100),website=clean(b.website,220),claimed=clean(b.status||'unknown',30);const lat=Number(b.lat),lng=Number(b.lng);
 if(!name||!top||!sub||!area||!address||!validCoords(lat,lng))return res.status(400).json({error:'invalid_business_submission'});
 const duplicate=db.prepare(`SELECT id FROM businesses WHERE city=? AND lower(name)=lower(?) AND area=? LIMIT 1`).get(city,name,area);if(duplicate)return res.status(409).json({error:'business_already_exists',id:duplicate.id});
 const sid=id('s'),now=Date.now();db.prepare(`INSERT INTO submissions(id,name,top,sub,city,area,address,phone,instagram,website,lat,lng,claimed_status,review_status,submitted_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)`).run(sid,name,top,sub,city,area,address,phone,instagram,website,lat,lng,claimed,now);
 res.status(202).json({ok:true,id:sid,status:'pending'});
});

app.get('/api/admin/submissions',requireAdmin,(req,res)=>{const status=clean(req.query.status||'pending',30);const rows=db.prepare(`SELECT * FROM submissions WHERE review_status=? ORDER BY submitted_at ASC LIMIT 500`).all(status);res.json({items:rows,count:rows.length})});

app.post('/api/admin/submissions/:id/approve',requireAdmin,(req,res)=>{
 const s=db.prepare(`SELECT * FROM submissions WHERE id=?`).get(req.params.id);if(!s)return res.status(404).json({error:'submission_not_found'});if(s.review_status!=='pending')return res.status(409).json({error:'submission_already_reviewed'});
 const bid=id('b'),now=Date.now();const tx=db.transaction(()=>{db.prepare(`INSERT INTO businesses(id,name,top,sub,city,area,address,phone,instagram,website,lat,lng,source,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)`).run(bid,s.name,s.top,s.sub,s.city,s.area,s.address,s.phone,s.instagram,s.website,s.lat,s.lng,'user',now,now);db.prepare(`UPDATE submissions SET review_status='approved',reviewed_at=? WHERE id=?`).run(now,s.id)});tx();res.json({ok:true,businessId:bid});
});
app.post('/api/admin/submissions/:id/reject',requireAdmin,(req,res)=>{const note=clean(req.body?.note||'',250),now=Date.now();const r=db.prepare(`UPDATE submissions SET review_status='rejected',reviewed_at=?,review_note=? WHERE id=? AND review_status='pending'`).run(now,note,req.params.id);if(!r.changes)return res.status(404).json({error:'pending_submission_not_found'});res.json({ok:true})});

app.post('/api/admin/businesses',requireAdmin,(req,res)=>{
 const b=req.body||{},name=clean(b.name,140),top=clean(b.top,60),sub=clean(b.sub,60),city=clean(b.city||'اهواز',80),area=clean(b.area,120),address=clean(b.address,350),phone=clean(b.phone,60),instagram=clean(b.instagram,100),website=clean(b.website,220),source=clean(b.source||'admin',50),sourceRef=clean(b.sourceRef||'',180),lat=Number(b.lat),lng=Number(b.lng);if(!name||!top||!sub||!area||!address)return res.status(400).json({error:'invalid_business'});const bid=id('b'),now=Date.now();db.prepare(`INSERT INTO businesses(id,name,top,sub,city,area,address,phone,instagram,website,lat,lng,source,source_ref,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)`).run(bid,name,top,sub,city,area,address,phone,instagram,website,Number.isFinite(lat)?lat:null,Number.isFinite(lng)?lng:null,source,sourceRef,now,now);res.status(201).json({ok:true,id:bid})
});

app.get('/api/neshan/search',async(req,res)=>{
 if(!NESHAN_API_KEY)return res.status(503).json({error:'neshan_search_not_configured'});const term=clean(req.query.term,120),lat=Number(req.query.lat),lng=Number(req.query.lng);if(!term||!Number.isFinite(lat)||!Number.isFinite(lng))return res.status(400).json({error:'term_lat_lng_required'});
 try{const u=new URL('https://api.neshan.org/v1/search');u.searchParams.set('term',term);u.searchParams.set('lat',String(lat));u.searchParams.set('lng',String(lng));const r=await fetch(u,{headers:{'Api-Key':NESHAN_API_KEY,'Accept':'application/json'}});const body=await r.json().catch(()=>({}));if(!r.ok)return res.status(502).json({error:'neshan_error',status:r.status,detail:body});const items=(body.items||[]).map((x,i)=>({id:x.id||x.poiHash||('neshan_'+i),title:x.title||'',address:x.address||'',neighbourhood:x.neighbourhood||'',region:x.region||'',type:x.type||'',category:x.category||'',lat:Number(x.location?.y),lng:Number(x.location?.x),raw:x}));res.json({count:items.length,items})}catch(e){res.status(502).json({error:'neshan_unreachable'})}
});

app.use((err,req,res,next)=>{console.error(err);res.status(500).json({error:'server_error'})});
app.listen(PORT,'0.0.0.0',()=>console.log(`AlanOffer backend on :${PORT}`));
