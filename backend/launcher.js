import http from 'node:http';
import {spawn} from 'node:child_process';

const BACKEND_PORT=8790;
const PUBLIC_PORTS=[80,8787,8080,3000];
let backendStatus='starting';
let lastExit=null;

const child=spawn(process.execPath,['server.js'],{
  cwd:process.cwd(),
  env:{...process.env,PORT:String(BACKEND_PORT)},
  stdio:['ignore','inherit','inherit']
});

child.on('spawn',()=>{backendStatus='running'});
child.on('exit',(code,signal)=>{backendStatus='exited';lastExit={code,signal,at:new Date().toISOString()};console.error('AlanOffer backend exited',lastExit)});
child.on('error',(err)=>{backendStatus='error';lastExit={message:err.message,at:new Date().toISOString()};console.error('AlanOffer backend spawn error',err)});

function proxy(req,res){
  if(req.url==='/gateway-health'){
    res.writeHead(200,{'content-type':'application/json; charset=utf-8'});
    res.end(JSON.stringify({ok:true,gateway:'alanoffer-cloudiva',backendStatus,lastExit,backendPort:BACKEND_PORT,publicPorts:PUBLIC_PORTS,time:new Date().toISOString()}));
    return;
  }
  const p=http.request({hostname:'127.0.0.1',port:BACKEND_PORT,path:req.url,method:req.method,headers:{...req.headers,host:`127.0.0.1:${BACKEND_PORT}`}},up=>{
    res.writeHead(up.statusCode||502,up.headers);
    up.pipe(res);
  });
  p.on('error',err=>{
    res.writeHead(503,{'content-type':'application/json; charset=utf-8','cache-control':'no-store'});
    res.end(JSON.stringify({ok:false,error:'backend_unavailable',backendStatus,lastExit,detail:err.message,time:new Date().toISOString()}));
  });
  req.pipe(p);
}

for(const port of PUBLIC_PORTS){
  const server=http.createServer(proxy);
  server.on('error',err=>console.error(`gateway port ${port} error`,err.message));
  server.listen(port,'0.0.0.0',()=>console.log(`AlanOffer gateway listening on ${port}`));
}
