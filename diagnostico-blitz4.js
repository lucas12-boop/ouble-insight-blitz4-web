// Diagnostic-only Socket.IO listener for Blitz4. No betting, no ingestion.
// Run independently once verified; does not touch Nex/Trade MD.
const io=require('socket.io-client');
const url=process.env.BLITZ_SOCKET_URL || 'https://api-v2.blitz4.casino';
const path=process.env.BLITZ_SOCKET_PATH || '/replication/';
const socket=io(url,{path,transports:['websocket'],reconnection:true,timeout:15000,autoConnect:false});
let observed=0;
const log=(tag,data)=>console.log(JSON.stringify({at:new Date().toISOString(),tag,data}));
socket.on('connect',()=>log('CONNECTED',{id:socket.id}));
socket.on('disconnect',reason=>log('DISCONNECTED',{reason}));
socket.on('connect_error',err=>log('CONNECT_ERROR',{message:err.message}));
socket.onAny?.((name,...args)=>{ observed++; log('EVENT',{name,payloadType:typeof args[0],sample:JSON.stringify(args).slice(0,350)}); });
socket.connect();
setInterval(()=>log('HEARTBEAT',{connected:socket.connected,observed}),60000);
