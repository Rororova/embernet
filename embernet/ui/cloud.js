'use strict';
const $ = id => document.getElementById(id);
const headers = () => ({'Content-Type':'application/json', Authorization:'Bearer '+code});
let code = new URLSearchParams(location.hash.slice(1)).get('control') || sessionStorage.getItem('embernet-control') || '';
let controller=false, base='', socket=null, state=null, noticeTimer, connecting=false;
let lastPongAt=0;
let cameraDirty=false, cameraRequest=null, lastDataAt=0, lastFrameAt=0;
let previewRGB='', previewIR='', frameChain=Promise.resolve();
const frameTimes=[];
if(location.hash.includes('control=')) history.replaceState(null,'',location.pathname+location.search);
const text=(tag,value,cls)=>{const element=document.createElement(tag);element.textContent=value;if(cls)element.className=cls;return element;};
function notice(message){$('notice').textContent=message;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('notice').textContent='',6500);}
async function request(path,options={},remote=false){
  const response=await fetch((remote?base:'')+path,{...options,headers:headers()});
  if(!response.ok){let detail;try{detail=(await response.json()).detail;}catch{detail='The server is unavailable';}throw Error(typeof detail==='string'?detail:'Check the report values and try again');}
  return response.json();
}
function controls(){
  const connected=socket?.readyState===WebSocket.OPEN;
  document.querySelectorAll('.control').forEach(element=>element.disabled=!controller||!connected);
  $('ignite').disabled=!controller||!connected||!state?.camera||!lastFrameAt||performance.now()-lastFrameAt>2500||!!pendingFire;
  if(!controller||!connected)setIgnite(false);
  $('role').textContent=controller?'Controller':'Spectator';$('unlock').hidden=controller;
  $('access-note').textContent=controller?'Your code controls this shared room. Share the watch link for spectators.':'Anyone with the watch link can observe.';
}
async function authorize(){try{controller=(await request('/api/auth')).control;if(controller)sessionStorage.setItem('embernet-control',code);controls();await poll();}catch(error){notice(error.message);}}
$('unlock').addEventListener('submit',async event=>{event.preventDefault();code=$('code').value.trim();await authorize();if(!controller)notice('That control code was not accepted.');});
$('share').onclick=async()=>{try{await navigator.clipboard.writeText(location.origin+location.pathname);notice('Watch link copied. The control code stays private.');}catch{notice('Copy this page’s address to share the watch link.');}};
async function command(value,showQueued=true){
  const payload={...value,request_id:value.request_id||crypto.randomUUID()};
  for(let attempt=0;attempt<3;attempt++){
    try{const result=await controlRequest(payload);if(showQueued)notice('Action queued · '+result.sequence);return result;}
    catch(error){if(attempt===2){notice(error.message);return false;}cameraSocket?.close();await new Promise(resolve=>setTimeout(resolve,300));}
  }
}
$('start').onclick=async()=>{const button=$('start');button.disabled=true;button.textContent='Starting…';try{const session=await request('/api/start?world='+encodeURIComponent($('world').value),{method:'POST'});connect(session.url);button.hidden=true;$('phase').textContent='Starting Isaac and PX4…';}catch(error){notice(error.message);button.textContent='Start';button.disabled=false;}};
function applyView(){if(!state?.camera)return;command({...state.camera,action:'camera',camera:$('quick-view').value,drone:$('camera-drone').value,interactive:false});}
$('quick-view').onchange=applyView;$('camera-drone').onchange=applyView;
$('panels').onclick=()=>{const drawer=$('drawer');drawer.hidden=!drawer.hidden;$('panels').setAttribute('aria-expanded',String(!drawer.hidden));};
let igniting=false,pendingFire=null,placementTimer=null;
function setIgnite(on){igniting=on;drag=null;$('ignite').setAttribute('aria-pressed',String(on));$('ignite').textContent=on?'Cancel fire placement':'Add fire';$('ignite-hint').hidden=!on;$('viewport').classList.toggle('igniting',on);}
$('ignite').onclick=()=>{setIgnite(!igniting);if(igniting)notice('Click the city to place a fire. Size and Heat set its properties.');};
addEventListener('keydown',event=>{if(event.key==='Escape')setIgnite(false);});
function finishFire(message,success){
  if(!pendingFire)return;
  clearTimeout(pendingFire.timer);pendingFire=null;
  $('fire-placement').classList.toggle('placed',success);
  clearTimeout(placementTimer);placementTimer=setTimeout(()=>$('fire-placement').hidden=true,success?3000:0);
  if(success)setIgnite(false);
  notice(message);controls();
}
function fireResult(currentState){
  if(!pendingFire)return;
  const result=(currentState.command_results||[]).find(value=>value.request_id===pendingFire.request_id);
  if(result)finishFire(result.result,!result.result.startsWith('rejected:'));
}
async function placeFire(event){
  if(pendingFire||$('ignite').disabled)return;
  const box=viewport.getBoundingClientRect(),scale=Math.min(box.width/960,box.height/540),width=960*scale,height=540*scale;
  const u=(event.clientX-box.left-(box.width-width)/2)/width,v=(event.clientY-box.top-(box.height-height)/2)/height;
  if(u<0||u>1||v<0||v>1){notice('Click inside the live picture, on the ground or a building.');return;}
  const request_id=crypto.randomUUID(),marker=$('fire-placement');
  clearTimeout(placementTimer);marker.hidden=false;marker.classList.remove('placed');
  marker.style.left=(event.clientX-box.left)+'px';marker.style.top=(event.clientY-box.top)+'px';
  pendingFire={request_id,timer:setTimeout(()=>{finishFire('Fire placement not confirmed. Check World truth before retrying.',false);setIgnite(false);},20000)};
  pendingOrbit=null;controls();notice('Placing fire…');
  const result=await command({action:'ignite',request_id,u,v,radius:+$('ignite-radius').value,severity:+$('ignite-severity').value/100},false);
  if(pendingFire?.request_id!==request_id)return;
  if(!result){finishFire('Fire placement not confirmed. Check the connection and World truth before retrying.',false);return;}
  fireResult(state);
}
$('severity').oninput=()=>{$('severity-output').value=$('severity').value+'%';};
$('kind').onchange=()=>{$('altitude').value=$('kind').value==='person'?0:1;};
$('report-form').onsubmit=event=>{event.preventDefault();command({action:'incident',kind:$('kind').value,x:+$('east').value,y:+$('north').value,z:+$('altitude').value,severity:+$('severity').value/100,radius:+$('radius').value});};
$('pause').onclick=()=>command({action:state?.paused?'resume':'pause'});
$('stop').onclick=()=>{if(confirm('End this shared session for everyone?'))command({action:'stop'});};
$('mesh').onclick=()=>{const drone=$('mesh-drone').value,current=state?.drones.find(item=>item.id===drone);command({action:'mesh',drone,enabled:current?.connected===false});};
$('mesh-drone').onchange=()=>updateMeshButton();
function updateMeshButton(){const current=state?.drones.find(item=>item.id===$('mesh-drone').value);$('mesh').textContent=current?.connected===false?'Reconnect link':'Isolate link';}

const incidentRows=new Map();
function renderLedger(currentState){
  const ledger=$('incidents'),reports=currentState.incidents.filter(item=>item.status!=='merged');
  $('report-count').textContent=reports.length+(reports.length===1?' incident':' incidents');
  if(!reports.length&&!incidentRows.size){if(!ledger.querySelector('p'))ledger.append(text('p','No aircraft has detected anything yet.','muted'));return;}
  if(!incidentRows.size)ledger.replaceChildren();
  const current=new Set(reports.map(item=>item.id));
  for(const [id,row] of incidentRows){if(!current.has(id)){row.remove();incidentRows.delete(id);}}
  for(const incident of reports){
    let row=incidentRows.get(incident.id);
    if(!row){row=text('div','','incident');row.append(text('strong',''),text('p','','muted'));ledger.append(row);incidentRows.set(incident.id,row);}
    row.querySelector('strong').textContent=`${incident.kind==='person'?'Possible survivor':'Fire'} · ${incident.id} · ${incident.status}`;
    const age=currentState.time-incident.observed_at;
    row.querySelector('p').textContent=`${age>35?'stale':Math.round(age)+' s old'} · known by ${incident.known_by.length} · committed ${incident.committed.join(' ')||'none'} · capacity ${incident.capacity.toFixed(1)} · seen by ${incident.source}${incident.deferred_reason?' · '+incident.deferred_reason:''}`;
  }
}
function renderWorld(world){
  const target=$('world-fires');if(!world)return;target.replaceChildren();
  for(const fire of world.fires){const row=text('div','','incident');row.append(text('strong',`${fire.id} · ${fire.contained_at===null?Math.round(fire.fraction*100)+'% remaining':fire.manual?'manually cleared':'contained by virtual work'}`));if(fire.contained_at===null){const button=text('button','Clear manually (not autonomous)','control');button.onclick=()=>command({action:'resolve',incident_id:fire.id});row.append(button);}target.append(row);}
  for(const subject of world.subjects)target.append(text('p',`${subject.id} · ${subject.escalated_at===null?'awaiting verification':'verified by '+subject.escalated_by+' · ground rescue requested'}`,'muted'));
}
function refreshCamera(camera){
  if(!camera||document.activeElement===$('quick-view')||document.activeElement===$('camera-drone'))return;
  $('camera-drone').value=camera.drone;$('quick-view').value=camera.camera;
}
let meshFleet='';
const svgNode=(tag,attributes)=>{const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attributes))node.setAttribute(key,value);return node;};
function buildMesh(ids){
  const graph=$('mesh-graph');graph.replaceChildren();
  const place=ids.map((_,index)=>{const angle=-Math.PI/2+2*Math.PI*index/ids.length;return [180+135*Math.cos(angle),85+58*Math.sin(angle)];});
  ids.forEach((a,i)=>ids.forEach((b,j)=>{if(j>i)graph.append(svgNode('line',{id:'link-'+a+'-'+b,x1:place[i][0],y1:place[i][1],x2:place[j][0],y2:place[j][1]}));}));
  ids.forEach((id,i)=>{const group=svgNode('g',{id:'node-'+id});group.append(svgNode('circle',{cx:place[i][0],cy:place[i][1],r:19}));const label=svgNode('text',{x:place[i][0],y:place[i][1]+5});label.textContent=id;group.append(label);graph.append(group);});
  meshFleet=ids.join();
}
function syncFleet(ids){
  for(const select of [$('camera-drone'),$('mesh-drone')]){if([...select.options].map(o=>o.value).join()===ids.join())continue;const value=select.value;select.replaceChildren(...ids.map(id=>new Option(id,id)));select.value=ids.includes(value)?value:ids[0];}
}
function renderMesh(mesh,ids){
  if(!mesh)return;
  if(ids.length&&ids.join()!==meshFleet)buildMesh(ids);
  let active=0;
  for(const link of mesh.links){
    if(link.active)active++;
    const id=[link.a,link.b].sort().join('-'),line=$('link-'+id);
    if(line){line.classList.toggle('inactive',!link.active);line.classList.toggle('active-traffic',link.queued>0);line.setAttribute('data-distance',link.distance+' m');}
  }
  for(const id of ids)$('node-'+id)?.classList.toggle('isolated',mesh.isolated.includes(id));
  $('mesh-summary').textContent=mesh.isolated.length?`${mesh.isolated.join(', ')} isolated · ${active}/${mesh.links.length} links up`:`${active}/${mesh.links.length} links up · ${mesh.queued} packets in transit`;
  const activity=$('mesh-activity');activity.replaceChildren();
  if(!mesh.traffic.length)activity.append(text('li','Waiting for packet traffic.'));
  for(const packet of mesh.traffic.slice(-6).reverse()){const item=document.createElement('li');item.append(text('time',packet.time.toFixed(1)+'s'),document.createTextNode(`${packet.sender} → ${packet.receiver} · ${packet.kind} · ${packet.status}`));activity.append(item);}
}
function freshness(){
  const connected=socket?.readyState===WebSocket.OPEN,now=performance.now();
  if(state?.drones.length&&lastDataAt){const age=Math.max(0,Math.floor((now-lastDataAt)/1000));$('data-status').textContent=`${connected&&age<3?'Measured telemetry':'Last received telemetry'} · ${state.time.toFixed(1)} s · ${age} s ago`;}
  else $('data-status').textContent='Waiting for measured aircraft state';
  if(lastFrameAt&&now-lastFrameAt>2500){$('feed-label').textContent=`Last received frame · ${Math.floor((now-lastFrameAt)/1000)} s ago`;$('feed-status').textContent=connected?'Camera stream delayed':'Stream disconnected';}
  controls();
}
setInterval(freshness,1000);
function render(currentState){
  if(!state||currentState.time!==state.time||currentState.frame!==state.frame)lastDataAt=performance.now();
  state=currentState;$('phase').textContent=currentState.phase;$('simtime').textContent=currentState.time.toFixed(1)+' s';$('remaining').textContent=Math.ceil(currentState.remaining_seconds)+' s';$('radio').textContent=currentState.radio?`${currentState.radio.delivered} / ${currentState.radio.lost}`:'—';$('pause').textContent=currentState.paused?'Resume':'Pause';
  const list=$('aircraft');list.replaceChildren();if(!currentState.drones.length)list.append(text('p','Booting PX4 aircraft…','muted'));
  for(const drone of currentState.drones){const row=text('div','','aircraft-row'),top=text('div','','aircraft-top'),name=text('strong',drone.id);name.style.color=drone.color||'';top.append(name,text('span',`${drone.position[2].toFixed(1)} m · capacity ${drone.capacity?.toFixed(1)??'—'} · ${drone.connected?'mesh':'isolated'}`));row.append(top,text('div',`${drone.armed?(drone.offboard?'PX4 offboard':'PX4 armed'):'PX4 preflight'} · ${drone.task}${drone.incident_id?' · '+drone.incident_id:''}${drone.working?' · working '+drone.working:''}`,'aircraft-reason'),text('div',drone.reason,'aircraft-reason'));list.append(row);}
  const fleet=currentState.drones.map(drone=>drone.id);if(fleet.length)syncFleet(fleet);
  renderLedger(currentState);renderWorld(currentState.world);renderMesh(currentState.mesh,fleet);
  const log=$('events');log.replaceChildren();const decisions=currentState.decisions||[];if(!decisions.length)log.append(text('li','Waiting for a mission decision.'));for(const event of decisions.slice(-10).reverse()){const item=document.createElement('li');item.append(text('time',event.time.toFixed(1)+'s'),document.createTextNode(`${event.drone} · ${event.text}${event.incident?' · '+event.incident:''}`));log.append(item);}
  const wild=currentState?.scene?.world==='wildland',labels={mission:'Mission',overview:wild?'Forest':'Overview',bird:'Bird’s-eye',fire:'Fire',follow:'Follow',onboard:'Onboard'};for(const option of $('quick-view').options)option.textContent=labels[option.value];
  $('world').value=wild?'wildland':'city';$('world').disabled=true;$('world').title='Choose a world before starting a session';
  refreshCamera(currentState.camera);updateMeshButton();fireResult(currentState);controls();
}
let videoDecoder=null,videoConfig=null,videoNeedsKey=true,forceJPEG=false;
const videoCanvas=document.createElement('canvas');videoCanvas.width=960;videoCanvas.height=540;videoCanvas.hidden=true;videoCanvas.setAttribute('aria-label','Live Isaac Sim city RGB video');videoCanvas.setAttribute('role','img');videoCanvas.style.cssText='position:absolute;inset:0;width:100%;height:100%;object-fit:contain;pointer-events:none';$('feed').insertAdjacentElement('afterend',videoCanvas);
function rgbFrameReceived(){const now=performance.now();lastFrameAt=now;frameTimes.push(now);while(frameTimes.length>30)frameTimes.shift();if(frameTimes.length>1)$('stream-status').textContent=`${((frameTimes.length-1)/((frameTimes.at(-1)-frameTimes[0])/1000)).toFixed(1)} RGB fps received`;}
function configureVideo(config){
  videoConfig={codec:config.codec,optimizeForLatency:true,hardwareAcceleration:'prefer-hardware'};
  if(videoDecoder&&videoDecoder.state!=='closed')videoDecoder.close();
  videoDecoder=new VideoDecoder({output:frame=>{try{videoCanvas.getContext('2d',{alpha:false}).drawImage(frame,0,0,960,540);videoCanvas.hidden=false;$('feed').style.opacity='0';$('feed').setAttribute('aria-hidden','true');rgbFrameReceived();$('feed-label').textContent='LIVE · Isaac / PhysX · RGB';$('feed-status').textContent='RTX hardware video · low-delay stream';}finally{frame.close();}},error:()=>{videoNeedsKey=true;notice('Video recovering at the next key frame');}});
  videoDecoder.configure(videoConfig);videoNeedsKey=true;
}
function decodeVideo(buffer){
  if(!videoDecoder||!videoConfig)return;
  const header=new DataView(buffer),key=header.getUint8(1)===1;
  if(videoDecoder.state==='closed'){configureVideo(videoConfig);}
  if(videoDecoder.state!=='configured'||videoDecoder.decodeQueueSize>2){videoDecoder.reset();videoDecoder.configure(videoConfig);videoNeedsKey=true;}
  if(videoNeedsKey&&!key)return;
  videoNeedsKey=false;videoDecoder.decode(new EncodedVideoChunk({type:key?'key':'delta',timestamp:Number(header.getBigUint64(2)),data:new Uint8Array(buffer,10)}));
}
function sensorFrame(channel,buffer){
  const blob=new Blob([buffer],{type:'image/jpeg'}),url=URL.createObjectURL(blob),now=performance.now();
  lastFrameAt=now;
  if(channel===0){frameTimes.push(now);while(frameTimes.length>30)frameTimes.shift();
    if(frameTimes.length>1){const fps=(frameTimes.length-1)/((frameTimes.at(-1)-frameTimes[0])/1000);$('stream-status').textContent=`${fps.toFixed(1)} RGB fps received`;}}
  if(channel===0){videoCanvas.hidden=true;$('feed').style.opacity='1';$('feed').removeAttribute('aria-hidden');if(previewRGB)URL.revokeObjectURL(previewRGB);previewRGB=url;$('feed').src=url;$('feed').alt='Live Isaac Sim city RGB camera';$('feed-label').textContent='LIVE · Isaac / PhysX · RGB';$('feed-status').textContent='RTX renderer · latest frames, no playback queue';}
  else if(channel===1){$('ir-view').hidden=false;if(previewIR)URL.revokeObjectURL(previewIR);previewIR=url;$('ir-feed').src=url;}
}
function connect(url){
  const target=(url||location.origin).replace(/\/$/,'');if(socket&&base===target&&socket.readyState<2)return;base=target;if(socket)socket.close();if(cameraSocket){cameraSocket.close();cameraSocket=null;controlAuthenticated=false;}
  socket=new WebSocket(target.replace(/^http/,'ws')+'/ws'+(typeof VideoDecoder!=='undefined'&&!forceJPEG?'?video=h264':''));socket.binaryType='blob';
  socket.onopen=()=>{if(controller)ensureControl().catch(error=>notice(error.message));lastPongAt=performance.now();connecting=false;$('waiting').hidden=true;$('feed-label').textContent='Starting Isaac · recorded preview';$('feed-status').textContent='Connected · waiting for first frame';controls();};
  socket.onmessage=event=>{
    if(typeof event.data==='string'){const message=JSON.parse(event.data);if(message.type==='pong'){lastPongAt=performance.now();return;}if(message.type==='video_config'){try{configureVideo(message);}catch{forceJPEG=true;notice('Hardware video unsupported; using JPEG preview');socket.close();socket=null;connect(base);}return;}if(message.type==='video_error'){notice('Video encoder unavailable; reconnecting JPEG preview');forceJPEG=true;socket.close();socket=null;connect(base);return;}render(message);return;}
    frameChain=frameChain.then(()=>event.data.arrayBuffer()).then(buffer=>{const channel=new Uint8Array(buffer,0,1)[0];if(channel===2)decodeVideo(buffer);else sensorFrame(channel,buffer.slice(1));}).catch(()=>{});
  };
  socket.onclose=event=>{controls();$('remaining').textContent='—';if(event.code===1013)notice(event.reason);$('feed-label').textContent='Last received frame · disconnected';$('feed-status').textContent='Stream disconnected';$('phase').textContent='Session ended or reconnecting';};
  socket.onerror=()=>{if(!connecting){connecting=true;$('feed-status').textContent='Isaac is warming up; reconnecting…';}};
}
async function poll(){try{const session=await request('/api/session');if(session.active){$('start').hidden=true;connect(session.url);}else{$('start').hidden=!controller||!session.has_ticket;$('start').disabled=false;$('start').textContent='Start';$('phase').textContent=session.has_ticket?(controller?'Ready to launch':'Waiting for a controller to start'):'Session offline · host renewal needed';
    $('waiting-title').textContent=session.has_ticket?'Simulation is ready to launch':'Simulation is offline';
    $('waiting-help').textContent=controller?(session.has_ticket?'Select Start shared swarm above. Isaac and PX4 may take a few minutes to start.':'The previous session ended. Prepare a new session to launch again.'):(session.has_ticket?'Unlock with your control code to launch. Spectators can watch after a controller starts the shared swarm.':'Waiting for the controller to prepare and start a shared session.');}}catch{$('phase').textContent='Host unavailable';}}
authorize();setInterval(poll,8000);

// Direct camera input uses one persistent socket and replaces pending drag samples.
let cameraSocket=null,controlAuthenticated=false,controlConnecting=null,drag=null,orbit=null,pendingOrbit=null,lastOrbitSend=0;
const pendingControls=new Map();
const viewport=$('feed');
viewport.draggable=false;viewport.style.touchAction='none';
function ensureControl(){
  if(controlAuthenticated&&cameraSocket?.readyState===WebSocket.OPEN)return Promise.resolve();
  if(controlConnecting)return controlConnecting;
  controlConnecting=new Promise((resolve,reject)=>{
    const ws=new WebSocket(base.replace(/^http/,'ws')+'/ws/control');cameraSocket=ws;
    const timer=setTimeout(()=>{ws.close();reject(Error('Control connection timed out'));},30000);
    ws.onopen=()=>ws.send(JSON.stringify({code}));
    ws.onmessage=event=>{const message=JSON.parse(event.data);
      if(message.type==='authenticated'){clearTimeout(timer);controlAuthenticated=true;controlConnecting=null;resolve();sendOrbit();}
      const pending=pendingControls.get(message.request_id);
      if(pending){clearTimeout(pending.timer);pendingControls.delete(message.request_id);if(message.type==='control_ack')pending.resolve(message);else pending.reject(Error(message.detail||'Control rejected'));}
    };
    ws.onerror=()=>{};
    ws.onclose=()=>{clearTimeout(timer);if(cameraSocket===ws){controlAuthenticated=false;controlConnecting=null;}reject(Error('Control connection closed'));for(const pending of pendingControls.values()){clearTimeout(pending.timer);pending.reject(Error('Control connection closed'));}pendingControls.clear();};
  });
  return controlConnecting;
}
async function controlRequest(payload){
  await ensureControl();
  return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pendingControls.delete(payload.request_id);reject(Error('Control acknowledgement timed out'));},6000);pendingControls.set(payload.request_id,{resolve,reject,timer});cameraSocket.send(JSON.stringify(payload));});
}
setInterval(()=>{if(controlAuthenticated&&cameraSocket?.readyState===WebSocket.OPEN)cameraSocket.send(JSON.stringify({type:'ping',nonce:performance.now()}));},5000);
function sendOrbit(){
  if(!pendingOrbit||!controller)return;
  if(!controlAuthenticated||cameraSocket?.readyState!==WebSocket.OPEN){ensureControl().catch(()=>{});return;}
  cameraSocket.send(JSON.stringify({...pendingOrbit,action:'camera'}));pendingOrbit=null;
}
function queueOrbit(){pendingOrbit={...orbit,interactive:true};}
setInterval(()=>{if(performance.now()-lastOrbitSend>=50&&pendingOrbit){sendOrbit();lastOrbitSend=performance.now();}},25);
viewport.addEventListener('contextmenu',event=>event.preventDefault());
viewport.addEventListener('pointerdown',event=>{
  if(!controller||socket?.readyState!==WebSocket.OPEN||!state?.camera||event.button!==0&&event.button!==2)return;
  event.preventDefault();
  if(igniting){
    if(event.button!==0||pendingFire)return;
    viewport.setPointerCapture(event.pointerId);
    drag={x:event.clientX,y:event.clientY,fire:true,moved:false};return;
  }
  viewport.setPointerCapture(event.pointerId);
  orbit={...state.camera};
  if(!orbit.interactive){
    const presets={fire:[-59,16,51],overview:[-49,34,255],bird:[-90,80,235],mission:[-72,22,60]};
    const preset=presets[orbit.camera];
    if(preset)[orbit.yaw,orbit.pitch,orbit.distance]=preset;
    if(orbit.camera==='onboard')orbit.camera='follow';
    orbit.pan_x=0;orbit.pan_y=0;
  }
  drag={x:event.clientX,y:event.clientY,pan:event.button===2||event.shiftKey};
});
viewport.addEventListener('pointermove',event=>{
  if(!drag)return;
  if(drag.fire){if(Math.hypot(event.clientX-drag.x,event.clientY-drag.y)>6)drag.moved=true;return;}
  const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
  drag.x=event.clientX;drag.y=event.clientY;
  if(drag.pan){const yaw=orbit.yaw*Math.PI/180,scale=orbit.distance*.002;
    orbit.pan_x=Math.max(-200,Math.min(200,orbit.pan_x+(-dx*Math.sin(yaw)+dy*Math.cos(yaw))*scale));
    orbit.pan_y=Math.max(-200,Math.min(200,orbit.pan_y+(dx*Math.cos(yaw)+dy*Math.sin(yaw))*scale));
  }else{orbit.yaw=((orbit.yaw-dx*.25+540)%360)-180;orbit.pitch=Math.max(5,Math.min(80,orbit.pitch+dy*.2));}
  queueOrbit();
});
viewport.addEventListener('pointerup',event=>{const click=drag;drag=null;if(igniting&&click?.fire&&!click.moved)placeFire(event);});
for(const name of ['pointercancel','lostpointercapture'])viewport.addEventListener(name,()=>{drag=null;});
viewport.addEventListener('wheel',event=>{
  if(!controller||!state?.camera||igniting||pendingFire)return;
  event.preventDefault();
  orbit={...state.camera};if(!orbit.interactive){const p={fire:[-59,16,51],overview:[-49,34,255],bird:[-90,80,235],mission:[-72,22,60]}[orbit.camera];if(p)[orbit.yaw,orbit.pitch,orbit.distance]=p;if(orbit.camera==='onboard')orbit.camera='follow';orbit.pan_x=0;orbit.pan_y=0;}
  orbit.distance=Math.max(2,Math.min(600,orbit.distance*Math.exp(event.deltaY*.001)));
  queueOrbit();
},{passive:false});

setInterval(()=>{if(socket?.readyState===WebSocket.OPEN){if(performance.now()-lastPongAt>15000){$('feed-status').textContent='Connection heartbeat lost';socket.close();return;}socket.send(JSON.stringify({type:'ping',nonce:performance.now()}));}},5000);
