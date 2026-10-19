// Blitz4 Socket.IO diagnostic. Independent of Nex, no betting or ingestion.
// Run locally or as a temporary diagnostic command only; not the web service.
const io = require('socket.io-client');
const url = process.env.BLITZ_SOCKET_URL || 'https://api-v2.blitz4.casino';
const path = process.env.BLITZ_SOCKET_PATH || '/replication/';
const durationMs = Math.min(120000, Math.max(5000, Number(process.env.PROBE_DURATION_MS || 30000)));
const log = (event, details={}) => console.log(JSON.stringify({at:new Date().toISOString(),event,...details}));
let received=0, connected=false, errors=0;
const socket = io(url, {path, transports:['websocket'], reconnection:false, timeout:10000, autoConnect:false});
socket.on('connect',()=>{connected=true;log('CONNECTED',{transport:socket.io.engine.transport.name});});
socket.on('connect_error',e=>{errors++;log('CONNECT_ERROR',{message:String(e.message).slice(0,180)});});
socket.on('disconnect',reason=>log('DISCONNECTED',{reason}));
const original=socket.onevent;
socket.onevent=function(packet){
  received++;
  const eventName=Array.isArray(packet.data)?String(packet.data[0]):'unknown';
  log('EVENT_NAME',{name:eventName,count:received}); // Names only: no tokens or raw payloads.
  return original.call(this,packet);
};
log('START',{host:url,path,duration_seconds:durationMs/1000});
socket.connect();
setTimeout(()=>{
  log('SUMMARY',{connected,received,errors});
  socket.disconnect();
  process.exit(connected?0:2);
},durationMs);
