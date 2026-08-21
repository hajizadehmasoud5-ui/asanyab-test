const CACHE='drlinq-specialist-v2';
const SHELL=['/shahmoradi-panel.html','/activate-shahmoradi.html','/specialist-app.webmanifest','/specialist-icon.svg'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',event=>{
  const u=new URL(event.request.url);
  if(u.pathname.startsWith('/api/')) return;
  if(event.request.method!=='GET') return;
  event.respondWith(fetch(event.request).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(event.request,copy));return r}).catch(()=>caches.match(event.request).then(r=>r||caches.match('/shahmoradi-panel.html'))));
});
self.addEventListener('push',event=>{
  let data={};
  try{data=event.data?event.data.json():{}}catch(_){data={body:event.data?event.data.text():''}}
  const title=data.title||'دکتر لینک';
  const options={
    body:data.body||'ارجاع جدید برای شما ثبت شد.',
    icon:'/specialist-icon.svg',
    badge:'/specialist-icon.svg',
    tag:data.tag||'drlinq-referral',
    renotify:true,
    vibrate:[180,80,180],
    data:{url:data.url||'/shahmoradi-panel.html'}
  };
  event.waitUntil(self.registration.showNotification(title,options));
});
self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const target=new URL((event.notification.data&&event.notification.data.url)||'/shahmoradi-panel.html',self.location.origin).href;
  event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{
    for(const client of list){if(client.url===target&&'focus' in client)return client.focus()}
    return clients.openWindow?clients.openWindow(target):undefined;
  }));
});
