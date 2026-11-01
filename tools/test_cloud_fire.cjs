// Exercise the actual UI event handlers without requiring an Isaac GPU session.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function room(width=1600,height=900){
  const nodes=new Map(),sent=[];
  const node=id=>{
    if(nodes.has(id))return nodes.get(id);
    const classes=new Set(),listeners=new Map();
    const element={id,style:{},hidden:false,disabled:false,value:'',textContent:'',attributes:{},listeners,
      classList:{toggle(name,on){if(on)classes.add(name);else classes.delete(name);},remove(name){classes.delete(name);}},
      setAttribute(name,value){this.attributes[name]=value;},removeAttribute(name){delete this.attributes[name];},
      addEventListener(name,handler){listeners.set(name,handler);},insertAdjacentElement(){},setPointerCapture(){},
      getBoundingClientRect(){return {left:0,top:0,width,height};}};
    nodes.set(id,element);return element;
  };
  const context=vm.createContext({document:{getElementById:node,createElement:()=>node('canvas'),querySelectorAll:()=>[node('ignite')]},
    location:{hash:'',origin:'http://test',pathname:'/'},history:{replaceState(){}},sessionStorage:{getItem:()=>''},
    URLSearchParams,URL,performance:{now:()=>1000},crypto:{randomUUID:()=>String(sent.length+1)},
    WebSocket:{OPEN:1},fetch:()=>new Promise(()=>{}),addEventListener(){},setInterval(){},setTimeout(){return 1;},clearTimeout(){},
  });
  vm.runInContext(fs.readFileSync('embernet/ui/cloud.js','utf8'),context);
  context.capture=value=>{sent.push(value);return {sequence:sent.length};};
  vm.runInContext("controller=true;socket={readyState:1};state={camera:{}};lastFrameAt=1000;controlRequest=async value=>capture(value);controls();",context);
  node('ignite-radius').value='4';node('ignite-severity').value='60';
  const event=(x,y,button=0)=>({clientX:x,clientY:y,button,pointerId:1,preventDefault(){}});
  return {context,node,sent,event,
    run:code=>vm.runInContext(code,context),
    press:(type,x,y,button=0)=>node('feed').listeners.get(type)(event(x,y,button)),
    arm:()=>node('ignite').onclick(),
    settle:()=>new Promise(resolve=>setImmediate(resolve)),
  };
}

(async()=>{
  const city=room();city.arm();city.press('pointerdown',800,450);city.press('pointerup',800,450);await city.settle();
  assert.equal(city.sent.length,1);
  assert.deepEqual(JSON.parse(JSON.stringify(city.sent[0])),{action:'ignite',request_id:'1',u:.5,v:.5,radius:4,severity:.6});
  assert.equal(city.node('ignite').disabled,true,'only one fire may be pending');
  city.press('pointerdown',900,500);city.press('pointerup',900,500);await city.settle();assert.equal(city.sent.length,1);
  assert.equal(city.node('fire-placement').hidden,false);
  city.run("fireResult({command_results:[{request_id:'unrelated',result:'world fire F01'}]})");
  assert.equal(city.run('pendingFire!==null'),true,'another operator result must not confirm this click');
  city.run("fireResult({command_results:[{request_id:'1',result:'world fire F03 ignited at 120, 90'}]})");
  assert.equal(city.run('igniting'),false);
  assert.equal(city.node('ignite').textContent,'Add fire');
  assert.match(city.node('notice').textContent,/F03/);

  const phone=room(400,800);phone.arm();phone.press('pointerdown',200,100);phone.press('pointerup',200,100);await phone.settle();
  assert.equal(phone.sent.length,0,'black letterbox borders are not picture coordinates');
  phone.press('pointerdown',100,400);phone.press('pointerup',100,400);await phone.settle();
  assert.equal(phone.sent[0].u,.25);assert.equal(phone.sent[0].v,.5);
  phone.run("fireResult({command_results:[{request_id:'1',result:'rejected: click on ground inside the mission area'}]})");
  assert.equal(phone.run('igniting'),true,'a rejected location leaves placement mode available');
  assert.equal(phone.node('ignite').disabled,false);
  assert.match(phone.node('notice').textContent,/rejected/);

  const gestures=room();gestures.arm();gestures.press('pointerdown',500,400);gestures.press('pointermove',530,400);gestures.press('pointerup',530,400);
  gestures.press('pointerdown',500,400,2);gestures.press('pointerup',500,400,2);await gestures.settle();
  assert.equal(gestures.sent.length,0,'dragging or right-clicking cannot ignite');
  gestures.press('pointerdown',500,400);gestures.press('pointercancel',500,400);gestures.press('pointerup',500,400);await gestures.settle();assert.equal(gestures.sent.length,0);
  gestures.run('lastFrameAt=-2000;controls()');assert.equal(gestures.node('ignite').disabled,true);
  gestures.press('pointerdown',500,400);gestures.press('pointerup',500,400);await gestures.settle();assert.equal(gestures.sent.length,0,'stale previews cannot be used to place fires');
  gestures.run('socket.readyState=3;controls()');assert.equal(gestures.run('igniting'),false);
  console.log('Cloud fire UI checks passed: placement, letterboxing, confirmation/rejection, duplicates, gestures, stale/offline guards.');
})().catch(error=>{console.error(error);process.exitCode=1;});
