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
const AHVAZ_BBOX='31.15,48.50,31.47,48.88';
const OVERPASS_ENDPOINTS=['https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter'];

fs.mkdirSync(path.dirname(DB_PATH),{recursive:true});
const db=new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.exec(`
CREATE TABLE IF NOT EXISTS businesses(
 id TEXT PRIMARY KEY,name TEXT NOT NULL,top TEXT NOT NULL,sub TEXT NOT NULL,city TEXT NOT NULL DEFAULT 'اهواز',area TEXT NOT NULL,address TEXT NOT NULL,phone TEXT DEFAULT '',instagram TEXT DEFAULT '',website TEXT DEFAULT '',lat REAL,lng REAL,source TEXT NOT NULL DEFAULT 'manual',source_ref TEXT DEFAULT '',status TEXT NOT NULL DEFAULT 'approved',created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_business_city ON businesses(city);
CREATE INDEX IF NOT EXISTS idx_business_area ON businesses(area);
CREATE INDEX IF NOT EXISTS idx_business_top_sub ON businesses(top,sub);
CREATE TABLE IF NOT EXISTS osm_businesses(
 source_ref TEXT PRIMARY KEY,name TEXT NOT NULL,top TEXT NOT NULL,sub TEXT NOT NULL,city TEXT NOT NULL DEFAULT 'اهواز',area TEXT DEFAULT '',address TEXT DEFAULT '',phone TEXT DEFAULT '',website TEXT DEFAULT '',lat REAL NOT NULL,lng REAL NOT NULL,osm_tags TEXT DEFAULT '{}',imported_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_osm_city ON osm_businesses(city);
CREATE INDEX IF NOT EXISTS idx_osm_top_sub ON osm_businesses(top,sub);
CREATE TABLE IF NOT EXISTS submissions(
 id TEXT PRIMARY KEY,name TEXT NOT NULL,top TEXT NOT NULL,sub TEXT NOT NULL,city TEXT NOT NULL DEFAULT 'اهواز',area TEXT NOT NULL,address TEXT NOT NULL,phone TEXT DEFAULT '',instagram TEXT DEFAULT '',website TEXT DEFAULT '',lat REAL NOT NULL,lng REAL NOT NULL,claimed_status TEXT DEFAULT 'unknown',review_status TEXT NOT NULL DEFAULT 'pending',submitted_at INTEGER NOT NULL,reviewed_at INTEGER,review_note TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_submission_review ON submissions(review_status,submitted_at);
`);

const app=express();
app.set('trust proxy',1);
app.use(helmet({crossOriginResourcePolicy:false}));
app.use(cors({origin(origin,cb){if(!origin||ORIGINS.includes(origin))return cb(null,true);return cb(new Error('origin_not_allowed'))}}));
app.use(express.json({limit:'128kb'}));
const submitLimiter=rateLimit({windowMs:60*60*1000,limit:15,standardHeaders:true,legacyHeaders:false});
const osmLimiter=rateLimit({windowMs:60*60*1000,limit:30,standardHeaders:true,legacyHeaders:false});

function clean(x,max=300){return String(x??'').replace(/[\u0000-\u001f]/g,' ').replace(/\s+/g,' ').trim().slice(0,max)}
function norm(x){return clean(x,500).replace(/ي/g,'ی').replace(/ك/g,'ک').toLowerCase()}
function id(prefix){return prefix+'_'+Date.now().toString(36)+'_'+crypto.randomBytes(4).toString('hex')}
function safeTokenMatch(a,b){if(!a||!b)return false;const aa=Buffer.from(a),bb=Buffer.from(b);return aa.length===bb.length&&crypto.timingSafeEqual(aa,bb)}
function requireAdmin(req,res,next){const t=String(req.headers.authorization||'').replace(/^Bearer\s+/i,'');if(!safeTokenMatch(t,ADMIN_TOKEN))return res.status(401).json({error:'admin_unauthorized'});next()}
function validCoords(lat,lng){return Number.isFinite(lat)&&Number.isFinite(lng)&&lat>=29&&lat<=33&&lng>=46&&lng<=51}
function publicRow(r){return {id:r.id,name:r.name,top:r.top,sub:r.sub,city:r.city,area:r.area,address:r.address,phone:r.phone,instagram:r.instagram,website:r.website,lat:r.lat,lng:r.lng,source:r.source,sourceRef:r.source_ref,status:r.status,createdAt:r.created_at}}
function publicOsmRow(r){return {id:'osm_'+r.source_ref.replace(/[^a-zA-Z0-9]/g,'_'),name:r.name,top:r.top,sub:r.sub,city:r.city,area:r.area,address:r.address,phone:r.phone,instagram:'',website:r.website,lat:r.lat,lng:r.lng,source:'osm',sourceRef:r.source_ref,status:'approved',createdAt:r.imported_at}}

const OSM_CATALOG={
 food:{restaurant:['["amenity"="restaurant"]'],fastfood:['["amenity"="fast_food"]'],cafe:['["amenity"="cafe"]'],juice:['["amenity"="ice_cream"]','["shop"="ice_cream"]'],catering:['["amenity"="food_court"]']},
 grocery:{produce:['["shop"="greengrocer"]'],bakery:['["shop"="bakery"]'],pastry:['["shop"="confectionery"]','["shop"="pastry"]'],protein:['["shop"="butcher"]','["shop"="seafood"]'],dairy:['["shop"="dairy"]'],supermarket:['["shop"="supermarket"]','["shop"="convenience"]'],nuts:['["shop"="nuts"]']},
 health:{dentist:['["amenity"="dentist"]','["healthcare"="dentist"]'],dental_specialist:['["healthcare"="dentist"]'],general_doctor:['["amenity"="doctors"]','["healthcare"="doctor"]'],specialist_doctor:['["healthcare"="doctor"]'],clinic:['["amenity"="clinic"]','["healthcare"="clinic"]'],hospital:['["amenity"="hospital"]'],pharmacy:['["amenity"="pharmacy"]'],lab:['["healthcare"="laboratory"]'],imaging:['["healthcare"="diagnostics"]'],physio:['["healthcare"="physiotherapist"]'],psychology:['["healthcare"="psychotherapist"]','["office"="psychologist"]'],optometry:['["shop"="optician"]'],hearing:['["healthcare"="audiologist"]']},
 beauty:{barber:['["shop"="hairdresser"]'],salon:['["shop"="hairdresser"]'],beauty_clinic:['["healthcare"="clinic"]["healthcare:speciality"~"dermatology|plastic_surgery"]','["shop"="beauty"]'],nail:['["shop"="beauty"]'],spa:['["leisure"="spa"]','["shop"="massage"]']},
 auto:{mechanic:['["shop"="car_repair"]'],tire:['["shop"="tyres"]'],carwash:['["amenity"="car_wash"]'],oil:['["shop"="car_repair"]'],parts:['["shop"="car_parts"]'],body:['["shop"="car_repair"]'],battery:['["shop"="car_parts"]'],motorcycle:['["shop"="motorcycle"]']},
 home:{electrician:['["craft"="electrician"]'],plumber:['["craft"="plumber"]'],ac:['["craft"="hvac"]'],appliance:['["shop"="appliance"]'],cleaning:['["craft"="cleaning"]'],carpentry:['["craft"="carpenter"]'],locksmith:['["craft"="locksmith"]'],moving:['["office"="moving_company"]']},
 retail:{clothing:['["shop"="clothes"]'],shoes:['["shop"="shoes"]'],mobile:['["shop"="mobile_phone"]'],computer:['["shop"="computer"]'],cosmetics:['["shop"="cosmetics"]'],home_goods:['["shop"="houseware"]'],jewelry:['["shop"="jewelry"]'],book:['["shop"="books"]','["shop"="stationery"]']},
 education:{school:['["amenity"="school"]','["amenity"="training"]'],language:['["amenity"="language_school"]'],tutoring:['["amenity"="training"]'],computer:['["amenity"="training"]'],art:['["amenity"="music_school"]','["amenity"="arts_centre"]'],driving:['["amenity"="driving_school"]']},
 fitness:{gym:['["leisure"="fitness_centre"]'],pool:['["leisure"="swimming_pool"]'],sports_school:['["leisure"="sports_centre"]'],game:['["leisure"="amusement_arcade"]'],cinema:['["amenity"="cinema"]']},
 professional:{lawyer:['["office"="lawyer"]'],accounting:['["office"="accountant"]'],insurance:['["office"="insurance"]'],realestate:['["office"="estate_agent"]'],printing:['["shop"="copyshop"]','["craft"="printer"]'],photography:['["shop"="photo"]'],it:['["office"="it"]']},
 travel:{hotel:['["tourism"="hotel"]'],guesthouse:['["tourism"="guest_house"]'],travel_agency:['["shop"="travel_agency"]'],rental:['["amenity"="car_rental"]']},
 pet:{vet:['["amenity"="veterinary"]'],petshop:['["shop"="pet"]']}
};

function osmFilters(top,sub){return OSM_CATALOG?.[top]?.[sub]||[]}
function osmAddress(tags){const parts=[tags['addr:province'],tags['addr:city'],tags['addr:district'],tags['addr:suburb'],tags['addr:street'],tags['addr:housenumber']].map(x=>clean(x,100)).filter(Boolean);return [...new Set(parts)].join('، ')}
function osmArea(tags){return clean(tags['addr:neighbourhood']||tags['addr:suburb']||tags['addr:district']||'',120)}
function osmName(tags){return clean(tags.name||tags['name:fa']||tags['name:en']||'',140)}
function osmPhone(tags){return clean(tags.phone||tags['contact:phone']||'',60)}
function osmWebsite(tags){return clean(tags.website||tags['contact:website']||'',220)}
function osmItem(el,top,sub){const tags=el.tags||{},lat=Number(el.lat??el.center?.lat),lng=Number(el.lon??el.center?.lon);return {sourceRef:`${el.type}/${el.id}`,name:osmName(tags),top,sub,city:'اهواز',area:osmArea(tags),address:osmAddress(tags),phone:osmPhone(tags),website:osmWebsite(tags),lat,lng,tags}}
async function overpassFetch(query){let lastErr=null;for(const endpoint of OVERPASS_ENDPOINTS){try{const ctl=new AbortController();const timer=setTimeout(()=>ctl.abort(),25000);const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8','Accept':'application/json','User-Agent':'AlanOffer-Ahvaz-Pilot/1.0'},body:new URLSearchParams({data:query}),signal:ctl.signal});clearTimeout(timer);if(!r.ok)throw new Error('overpass_'+r.status);const body=await r.json();return body}catch(e){lastErr=e}}throw lastErr||new Error('overpass_unreachable')}

app.get('/api/health',(req,res)=>res.json({ok:true,service:'alanoffer-backend',db:true,osmImport:true,neshanSearch:!!NESHAN_API_KEY,time:new Date().toISOString()}));

app.get('/api/businesses',(req,res)=>{
 const q=norm(req.query.q||''),city=clean(req.query.city||'اهواز',80),area=norm(req.query.area||''),top=clean(req.query.top||'',80),sub=clean(req.query.sub||'',80);const limit=Math.min(Math.max(Number(req.query.limit)||100,1),500);
 let ownSql=`SELECT * FROM businesses WHERE status='approved' AND city=?`,ownArgs=[city];if(top){ownSql+=' AND top=?';ownArgs.push(top)}if(sub){ownSql+=' AND sub=?';ownArgs.push(sub)}
 let osmSql=`SELECT * FROM osm_businesses WHERE city=?`,osmArgs=[city];if(top){osmSql+=' AND top=?';osmArgs.push(top)}if(sub){osmSql+=' AND sub=?';osmArgs.push(sub)}
 const own=db.prepare(ownSql+' ORDER BY updated_at DESC LIMIT 1500').all(...ownArgs).map(publicRow);
 const ownKeys=new Set(own.map(r=>norm(r.name)+'|'+norm(r.area)));
 const osm=db.prepare(osmSql+' ORDER BY imported_at DESC LIMIT 1500').all(...osmArgs).map(publicOsmRow).filter(r=>!ownKeys.has(norm(r.name)+'|'+norm(r.area)));
 const rows=own.concat(osm).filter(r=>{const text=norm([r.name,r.area,r.address,r.top,r.sub].join(' '));return(!q||text.includes(q))&&(!area||norm(r.area).includes(area)||norm(r.address).includes(area))}).slice(0,limit);
 res.json({items:rows,count:rows.length,attribution:osm.some(x=>rows.includes(x))?'© OpenStreetMap contributors · ODbL':''});
});

app.post('/api/submissions',submitLimiter,(req,res)=>{
 const b=req.body||{};const name=clean(b.name,140),top=clean(b.top,60),sub=clean(b.sub,60),city=clean(b.city||'اهواز',80),area=clean(b.area,120),address=clean(b.address,350),phone=clean(b.phone,60),instagram=clean(b.instagram,100),website=clean(b.website,220),claimed=clean(b.status||'unknown',30),lat=Number(b.lat),lng=Number(b.lng);
 if(!name||!top||!sub||!area||!address||!validCoords(lat,lng))return res.status(400).json({error:'invalid_business_submission'});
 const duplicate=db.prepare(`SELECT id FROM businesses WHERE city=? AND lower(name)=lower(?) AND area=? LIMIT 1`).get(city,name,area);if(duplicate)return res.status(409).json({error:'business_already_exists',id:duplicate.id});
 const sid=id('s'),now=Date.now();db.prepare(`INSERT INTO submissions(id,name,top,sub,city,area,address,phone,instagram,website,lat,lng,claimed_status,review_status,submitted_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)`).run(sid,name,top,sub,city,area,address,phone,instagram,website,lat,lng,claimed,now);res.status(202).json({ok:true,id:sid,status:'pending'});
});

app.get('/api/admin/submissions',requireAdmin,(req,res)=>{const status=clean(req.query.status||'pending',30);const rows=db.prepare(`SELECT * FROM submissions WHERE review_status=? ORDER BY submitted_at ASC LIMIT 500`).all(status);res.json({items:rows,count:rows.length})});
app.post('/api/admin/submissions/:id/approve',requireAdmin,(req,res)=>{const s=db.prepare(`SELECT * FROM submissions WHERE id=?`).get(req.params.id);if(!s)return res.status(404).json({error:'submission_not_found'});if(s.review_status!=='pending')return res.status(409).json({error:'submission_already_reviewed'});const bid=id('b'),now=Date.now();db.transaction(()=>{db.prepare(`INSERT INTO businesses(id,name,top,sub,city,area,address,phone,instagram,website,lat,lng,source,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)`).run(bid,s.name,s.top,s.sub,s.city,s.area,s.address,s.phone,s.instagram,s.website,s.lat,s.lng,'user',now,now);db.prepare(`UPDATE submissions SET review_status='approved',reviewed_at=? WHERE id=?`).run(now,s.id)})();res.json({ok:true,businessId:bid})});
app.post('/api/admin/submissions/:id/reject',requireAdmin,(req,res)=>{const note=clean(req.body?.note||'',250),now=Date.now();const r=db.prepare(`UPDATE submissions SET review_status='rejected',reviewed_at=?,review_note=? WHERE id=? AND review_status='pending'`).run(now,note,req.params.id);if(!r.changes)return res.status(404).json({error:'pending_submission_not_found'});res.json({ok:true})});

app.post('/api/admin/businesses',requireAdmin,(req,res)=>{const b=req.body||{},name=clean(b.name,140),top=clean(b.top,60),sub=clean(b.sub,60),city=clean(b.city||'اهواز',80),area=clean(b.area,120),address=clean(b.address,350),phone=clean(b.phone,60),instagram=clean(b.instagram,100),website=clean(b.website,220),source=clean(b.source||'admin',50),sourceRef=clean(b.sourceRef||'',180),lat=Number(b.lat),lng=Number(b.lng);if(!name||!top||!sub||!area||!address)return res.status(400).json({error:'invalid_business'});const bid=id('b'),now=Date.now();db.prepare(`INSERT INTO businesses(id,name,top,sub,city,area,address,phone,instagram,website,lat,lng,source,source_ref,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)`).run(bid,name,top,sub,city,area,address,phone,instagram,website,Number.isFinite(lat)?lat:null,Number.isFinite(lng)?lng:null,source,sourceRef,now,now);res.status(201).json({ok:true,id:bid})});

app.get('/api/admin/osm/catalog',requireAdmin,(req,res)=>{res.json({catalog:Object.fromEntries(Object.entries(OSM_CATALOG).map(([top,subs])=>[top,Object.keys(subs)]))})});
app.get('/api/admin/osm/search',requireAdmin,osmLimiter,async(req,res)=>{
 const top=clean(req.query.top,60),sub=clean(req.query.sub,60),filters=osmFilters(top,sub);if(!filters.length)return res.status(400).json({error:'unsupported_osm_category'});
 const clauses=filters.map(f=>`nwr${f}(${AHVAZ_BBOX});`).join('\n');const query=`[out:json][timeout:20];(\n${clauses}\n);out center tags 500;`;
 try{const body=await overpassFetch(query);const seen=new Set();const items=(body.elements||[]).map(x=>osmItem(x,top,sub)).filter(x=>x.name&&validCoords(x.lat,x.lng)).filter(x=>{if(seen.has(x.sourceRef))return false;seen.add(x.sourceRef);return true}).slice(0,500);const existing=new Set(db.prepare(`SELECT source_ref FROM osm_businesses WHERE top=? AND sub=?`).all(top,sub).map(x=>x.source_ref));res.json({items:items.map(x=>({...x,alreadyImported:existing.has(x.sourceRef)})),count:items.length,source:'OpenStreetMap',license:'ODbL 1.0',attribution:'© OpenStreetMap contributors'})}catch(e){console.error(e);res.status(502).json({error:'overpass_unreachable'})}
});
app.post('/api/admin/osm/import',requireAdmin,(req,res)=>{
 const b=req.body||{},sourceRef=clean(b.sourceRef,100),name=clean(b.name,140),top=clean(b.top,60),sub=clean(b.sub,60),area=clean(b.area,120),address=clean(b.address,350),phone=clean(b.phone,60),website=clean(b.website,220),lat=Number(b.lat),lng=Number(b.lng),tags=(b.tags&&typeof b.tags==='object')?b.tags:{};
 if(!/^((node|way|relation)\/\d+)$/.test(sourceRef)||!name||!top||!sub||!validCoords(lat,lng))return res.status(400).json({error:'invalid_osm_import'});
 const now=Date.now();db.prepare(`INSERT INTO osm_businesses(source_ref,name,top,sub,city,area,address,phone,website,lat,lng,osm_tags,imported_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_ref) DO UPDATE SET name=excluded.name,top=excluded.top,sub=excluded.sub,area=excluded.area,address=excluded.address,phone=excluded.phone,website=excluded.website,lat=excluded.lat,lng=excluded.lng,osm_tags=excluded.osm_tags,imported_at=excluded.imported_at`).run(sourceRef,name,top,sub,'اهواز',area,address,phone,website,lat,lng,JSON.stringify(tags).slice(0,12000),now);res.status(201).json({ok:true,sourceRef})
});

app.get('/api/neshan/search',async(req,res)=>{if(!NESHAN_API_KEY)return res.status(503).json({error:'neshan_search_not_configured'});const term=clean(req.query.term,120),lat=Number(req.query.lat),lng=Number(req.query.lng);if(!term||!Number.isFinite(lat)||!Number.isFinite(lng))return res.status(400).json({error:'term_lat_lng_required'});try{const u=new URL('https://api.neshan.org/v1/search');u.searchParams.set('term',term);u.searchParams.set('lat',String(lat));u.searchParams.set('lng',String(lng));const r=await fetch(u,{headers:{'Api-Key':NESHAN_API_KEY,'Accept':'application/json'}});const body=await r.json().catch(()=>({}));if(!r.ok)return res.status(502).json({error:'neshan_error',status:r.status,detail:body});const items=(body.items||[]).map((x,i)=>({id:x.id||x.poiHash||('neshan_'+i),title:x.title||'',address:x.address||'',neighbourhood:x.neighbourhood||'',region:x.region||'',type:x.type||'',category:x.category||'',lat:Number(x.location?.y),lng:Number(x.location?.x),raw:x}));res.json({count:items.length,items})}catch(e){res.status(502).json({error:'neshan_unreachable'})}});

app.use((err,req,res,next)=>{console.error(err);res.status(500).json({error:'server_error'})});
app.listen(PORT,'0.0.0.0',()=>console.log(`AlanOffer backend on :${PORT}`));
