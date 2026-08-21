const UPSTREAM='https://python-0jatcc.cldv.dev/alanoffer/api/referral';
const KNOWN={
  'dr-shahmoradi-endodontist':{name:'دکتر محسن شاهمرادی',clinicName:'مطب دکتر محسن شاهمرادی',city:'اهواز',phone:'',slug:'dr-shahmoradi-endodontist'}
};

async function ensureSpecialist(slug){
  const spec=KNOWN[slug];
  if(!spec)return;
  let r=await fetch(`${UPSTREAM}/c/${encodeURIComponent(slug)}`,{cache:'no-store'});
  if(r.status!==404)return;
  await fetch(`${UPSTREAM}/specialists/register`,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(spec)
  });
}

export default {
  async fetch(request,env){
    const url=new URL(request.url);
    if(url.pathname.startsWith('/api/referral/')){
      const suffix=url.pathname.slice('/api/referral'.length);
      const m=suffix.match(/^\/c\/([^/]+)(?:\/submit)?$/);
      if(m){
        try{await ensureSpecialist(decodeURIComponent(m[1]));}catch(_e){}
      }
      const upstream=new URL(UPSTREAM+suffix);
      upstream.search=url.search;
      const init={method:request.method,headers:new Headers(request.headers),redirect:'manual'};
      init.headers.delete('host');
      init.headers.delete('origin');
      init.headers.delete('referer');
      if(request.method!=='GET'&&request.method!=='HEAD')init.body=request.body;
      const resp=await fetch(upstream.toString(),init);
      const headers=new Headers(resp.headers);
      headers.set('Cache-Control','no-store');
      return new Response(resp.body,{status:resp.status,statusText:resp.statusText,headers});
    }

    const asset=await env.ASSETS.fetch(request);
    const type=asset.headers.get('content-type')||'';
    if(type.includes('text/html')){
      let html=await asset.text();
      html=html.split(UPSTREAM).join('/api/referral');
      const headers=new Headers(asset.headers);
      headers.set('Cache-Control','no-store');
      headers.delete('content-length');
      return new Response(html,{status:asset.status,statusText:asset.statusText,headers});
    }
    return asset;
  }
};
