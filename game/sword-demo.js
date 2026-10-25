/** Three.js physical-space / synchronized opponent-view concept study. Owner: Adetola. */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { BEATS, DURATION, sample, smooth } from './sword-demo-timeline.js';

const stage = document.querySelector('#stage');
const preview = document.querySelector('#display-feed');
const ctx = preview.getContext('2d');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
stage.prepend(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color('#101815');
scene.fog = new THREE.Fog('#101815', 12, 27);
const camera = new THREE.PerspectiveCamera(42, 1, .1, 60);
camera.position.set(6, 5.5, 7.5);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 1, -.25);
controls.enableDamping = true;
controls.minDistance = 4;
controls.maxDistance = 16;
controls.maxPolarAngle = Math.PI * .47;
const ambient = new THREE.HemisphereLight('#e4f6dc', '#27342c', 2.2);
scene.add(ambient);
const light = new THREE.DirectionalLight('#ffedc3', 3.4);
light.position.set(-3, 7, 3);
light.castShadow = true;
light.shadow.mapSize.set(2048, 2048);
Object.assign(light.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6 });
scene.add(light);
const rim = new THREE.DirectionalLight('#78b8dc', 2.5);
rim.position.set(2, 3, -5);
scene.add(rim);

const material = (color, roughness = .7) => new THREE.MeshStandardMaterial({ color, roughness });
const gold = material('#dfbd71');
const dark = material('#1b2620');
const skin = material('#c6b79a');
function box(w, h, d, mat, x, y, z, parent = scene) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  mesh.position.set(x, y, z);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}
box(9, .15, 9, material('#202d25'), 0, -.1, -.3);
const grid = new THREE.GridHelper(9, 18, '#60705b', '#354337');
grid.position.y = -.017;
scene.add(grid);
// Illustrative separated movement lanes. Their dimensions are not calibrated gameplay thresholds.
function floorLane(x, color) {
  const points = [[-.67, -1.2], [.67, -1.2], [.67, 1.2], [-.67, 1.2], [-.67, -1.2]].map(([a,b]) => new THREE.Vector3(x+a,.012,1.1+b));
  scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({color})));
  const arrow = new THREE.ArrowHelper(new THREE.Vector3(0,0,-1),new THREE.Vector3(x,.025,.15),.65,color,.17,.13);
  scene.add(arrow);
}
floorLane(-1.05, '#c3a466');
floorLane(1.05, '#6897b1');

function label(text, color, width, height, x, y, z, parent = scene) {
  const canvas = document.createElement('canvas'); canvas.width=768; canvas.height=128;
  const c=canvas.getContext('2d');
  c.fillStyle=color; c.font='500 42px monospace';c.textAlign='center';c.textBaseline='middle';c.fillText(text,384,64);
  const texture=new THREE.CanvasTexture(canvas);
  const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,depthTest:false}));
  sprite.scale.set(width,height,1);sprite.position.set(x,y,z);parent.add(sprite);return sprite;
}
label('P1 / SWORD', '#e1c780', 1.5,.25,-1.05,2.3,1.25);
label('P2 / MAGE', '#8dc6df', 1.5,.25,1.05,2.3,1.25);
label('FORWARD TO CAMERA', '#8e9d86', 2.5,.3,0,.12,-1.7);
// One monitor, not two imaginary face-to-face monitors.
const monitor = new THREE.Group();scene.add(monitor);
box(4.22,2.24,.18,material('#111512'),0,2.1,-3,monitor);
box(.12,1.05,.14,dark,0,.52,-3,monitor);
box(1.25,.1,.6,dark,0,.06,-3,monitor);
const screenTexture = new THREE.CanvasTexture(preview);
screenTexture.colorSpace = THREE.SRGBColorSpace;
const screen = new THREE.Mesh(new THREE.PlaneGeometry(4,2),new THREE.MeshBasicMaterial({map:screenTexture}));
screen.position.set(0,2.1,-2.898);monitor.add(screen);
box(.3,.09,.1,material('#334e4a'),0,3.32,-2.98,monitor);
for(const x of [-.09,.09]){
  const lens = new THREE.Mesh(new THREE.SphereGeometry(.025,12,8),material('#7ee6df'));
  lens.position.set(x,3.32,-2.92);monitor.add(lens);
}
label('ZED + SHARED DISPLAY', '#9dbaab', 2.7,.25,0,3.65,-3);

function limb(parent, radius, mat) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,1,12),mat);
  mesh.castShadow = true; parent.add(mesh);return mesh;
}
const up=new THREE.Vector3(0,1,0);
function link(mesh,a,b){
  const av=new THREE.Vector3(...a),bv=new THREE.Vector3(...b),delta=bv.clone().sub(av);
  mesh.position.copy(av).add(bv).multiplyScalar(.5);mesh.scale.y=delta.length();mesh.quaternion.setFromUnitVectors(up,delta.normalize());
}
function actor(x,color){
  const group=new THREE.Group();group.position.set(x,0,1.15);scene.add(group);
  const cloth=material(color);
  const torso=box(.43,.58,.26,cloth,0,1.15,0,group);
  const head=new THREE.Mesh(new THREE.SphereGeometry(.155,24,16),skin);head.scale.y=1.15;head.position.set(0,1.66,0);group.add(head);head.castShadow=true;
  // Nose and eyes explicitly face the display (-Z).
  box(.055,.06,.055,skin,0,1.66,-.15,group);
  for (const eyeX of [-.057,.057]) box(.025,.018,.014,dark,eyeX,1.7,-.143,group);
  const arms=[limb(group,.065,cloth),limb(group,.05,skin),limb(group,.065,cloth),limb(group,.05,skin)];
  const legs=[limb(group,.085,cloth),limb(group,.07,dark),limb(group,.085,cloth),limb(group,.07,dark)];
  const hands=[-1,1].map(()=>{const m=new THREE.Mesh(new THREE.SphereGeometry(.066,12,8),skin);group.add(m);return m;});
  for(const fx of [-.13,.13])box(.14,.09,.28,dark,fx,.065,-.07,group);
  return {group,torso,head,arms,legs,hands,x};
}
const knight=actor(-1.05,'#727d53');
const mage=actor(1.05,'#46718a');
function pose(a,guard,thrust,duck=0,side=0){
  a.group.position.set(a.x+side,-duck,1.15);
  const shoulderL=[-.245,1.38,0],shoulderR=[.245,1.38,0];
  const elbowL=[-.31+guard*.12,1.02+guard*.24,-.05-guard*.25];
  const wristL=[-.30+guard*.13,.78+guard*.66,-.15-guard*.37];
  const elbowR=[.32-guard*.14-thrust*.12,1.04+guard*.22+thrust*.16,-.07-guard*.23-thrust*.25];
  const wristR=[.29-guard*.14-thrust*.09,.8+guard*.64+thrust*.52,-.15-guard*.37-thrust*.67];
  link(a.arms[0],shoulderL,elbowL);link(a.arms[1],elbowL,wristL);link(a.arms[2],shoulderR,elbowR);link(a.arms[3],elbowR,wristR);
  a.hands[0].position.set(...wristL);a.hands[1].position.set(...wristR);
  link(a.legs[0],[-.13,.91,0],[-.15,.49,-.02]);link(a.legs[1],[-.15,.49,-.02],[-.13,.12,0]);
  link(a.legs[2],[.13,.91,0],[.15,.49,-.02]);link(a.legs[3],[.15,.49,-.02],[.13,.12,0]);
}

// A second renderer supplies actual 3D front-camera crops to the virtual monitor.
const feedRenderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
feedRenderer.setSize(1024,512);feedRenderer.setPixelRatio(1);feedRenderer.outputColorSpace=THREE.SRGBColorSpace;
const cropCameras=[knight,mage].map(a=>{
  const c=new THREE.PerspectiveCamera(40,1,.1,15);
  c.position.set(a.x,1.48,-1.9);c.lookAt(a.x,1.15,1.15);return c;
});
const previewDecorations = scene.children.filter(o=>o.isSprite || o.isArrowHelper);
function roundedRect(x,y,w,h,r,fill){ctx.fillStyle=fill;ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fill();}
function text(str,x,y,size,color,align='left'){
  ctx.fillStyle=color;ctx.font=`500 ${size}px monospace`;ctx.textAlign=align;ctx.fillText(str,x,y);
}
function projectile(cx,cy,r,type){
  ctx.save();ctx.translate(cx,cy);
  ctx.shadowBlur=36;ctx.shadowColor=type==='spell'?'#69d5fc':'#ffe7a0';
  if(type==='spell'){
    const grad=ctx.createRadialGradient(0,0,0,0,0,r);grad.addColorStop(0,'#fff');grad.addColorStop(.35,'#b7f4ff');grad.addColorStop(1,'#43b6ec00');ctx.fillStyle=grad;ctx.beginPath();ctx.arc(0,0,r,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle='#a2eeff';ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(-r*.9,-r*.45);ctx.lineTo(r*.15,-r*.1);ctx.lineTo(-r*.1,r*.3);ctx.lineTo(r*.8,r*.5);ctx.stroke();
  }else{
    ctx.rotate(-.5);ctx.strokeStyle='#ffefb1';ctx.lineWidth=9;ctx.beginPath();ctx.ellipse(0,0,r*.6,r,0,-1.3,1.3);ctx.stroke();ctx.lineWidth=2;ctx.strokeStyle='#fff';ctx.stroke();
  }ctx.restore();
}
function drawFeeds(state){
  const {index,progress:p}=state;
  monitor.visible=false;for(const obj of previewDecorations)obj.visible=false;
  feedRenderer.setScissorTest(true);
  // P1 left = opponent mage. P2 right = opponent knight. Neither feed is a self-view.
  for(let i=0;i<2;i++){
    feedRenderer.setViewport(i*512,0,512,512);feedRenderer.setScissor(i*512,0,512,512);
    feedRenderer.render(scene,cropCameras[1-i]);
  }
  monitor.visible=true;for(const obj of previewDecorations)obj.visible=true;
  ctx.drawImage(feedRenderer.domElement,0,0);
  ctx.fillStyle='#07100dd9';ctx.fillRect(0,0,1024,96);ctx.fillRect(0,440,1024,72);
  ctx.fillStyle='#d4b56c';ctx.fillRect(510,0,4,512);
  text('P1  /  SWORD USER',23,30,17,'#e5c780');text('P2  /  MAGE',535,30,17,'#8acde8');
  text('OPPONENT: MAGE',23,84,12,'#a5b3a5');text('OPPONENT: SWORD USER',535,84,12,'#a5b3a5');
  for(let i=0;i<2;i++){
    roundedRect(i*512+23,43,466,7,3,'#334337');roundedRect(i*512+23,43,466,7,3,i===0?'#dfbd71':'#78beda');
  }
  let left='WATCH YOUR OPPONENT',right='WATCH YOUR OPPONENT';
  if(index===1){
    left=p<.3?'SPELL CHARGING…':'INCOMING — PREPARE TO GUARD';right=p<.3?'“LIGHTNING, ANSWER MY CALL”':'SPELL RELEASED';
    if(p>.28)projectile(256,270,16+smooth(.28,1,p)*110,'spell');
  }
  if(index===2){
    left=p<.55?'PARRY!':'RIPOSTE READY';right='OPPONENT PARRIED YOUR SPELL';
    const pulse=1-smooth(.05,.7,p);
    ctx.save();ctx.strokeStyle=`rgba(255,232,153,${.35+pulse*.65})`;ctx.shadowBlur=24;ctx.shadowColor='#ffe19a';ctx.lineWidth=5;
    ctx.beginPath();ctx.moveTo(256,135);ctx.lineTo(350,175);ctx.lineTo(335,295);ctx.quadraticCurveTo(320,350,256,380);ctx.quadraticCurveTo(192,350,177,295);ctx.lineTo(162,175);ctx.closePath();ctx.stroke();ctx.restore();
    text(left,256,411,24,'#ffe4a0','center');text('1 EMPOWERED STRIKE',256,432,12,'#e1c780','center');
  }
  if(index===3){
    left=p<.3?'THRUST TO RELEASE':'RIPOSTE RELEASED';right=p<.3?'READ THE SWORD USER':p<.76?'BLADE WAVE — STEP ASIDE':'DODGED';
    if(p>.28&&p<.8)projectile(768,267,28+smooth(.28,.8,p)*130,'blade');
    if(p>=.8)text('DODGED',768,265,36,'#a9e0c0','center');
  }
  text(left,256,476,14,index===2?'#ffe4a0':'#dce4d4','center');text(right,768,476,14,'#dce4d4','center');
  text('YOUR VIEW · LEFT HALF',256,498,10,'#8d9e8a','center');text('YOUR VIEW · RIGHT HALF',768,498,10,'#8d9e8a','center');
  screenTexture.needsUpdate=true;
}

let time=0, playing=false, last=performance.now(),lastBeat=-1;
const play=document.querySelector('#play');
const timeline=document.querySelector('#timeline');
const steps=[...document.querySelectorAll('[data-goto]')];
function setPlaying(value){playing=value;play.textContent=playing?'Ⅱ Pause sequence':'▶ Play sequence';play.setAttribute('aria-pressed',String(playing));}
play.addEventListener('click',()=>setPlaying(!playing));
timeline.addEventListener('input',()=>{time=Number(timeline.value);setPlaying(false);});
for(const b of steps)b.addEventListener('click',()=>{time=BEATS[Number(b.dataset.goto)].start+.04;setPlaying(false);});
const views={room:{pos:[6,5.5,7.5],target:[0,1,-.25]},overhead:{pos:[0,10,3],target:[0,0,0]},player:{pos:[-.95,2,3.4],target:[0,2,-3]}};
for(const b of document.querySelectorAll('[data-view]'))b.addEventListener('click',()=>{
  const v=views[b.dataset.view];camera.position.set(...v.pos);controls.target.set(...v.target);controls.update();
  for(const button of document.querySelectorAll('[data-view]'))button.setAttribute('aria-pressed',String(button===b));
});
renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();setPlaying(false);document.querySelector('#status').hidden=false;document.querySelector('#status').textContent='WebGL context lost. Reload to restart the demo.';});
document.addEventListener('keydown',e=>{if(e.code==='Space'&& !['INPUT','BUTTON'].includes(document.activeElement.tagName)){e.preventDefault();setPlaying(!playing);}});
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
function resize(){renderer.setSize(stage.clientWidth,stage.clientHeight);camera.aspect=stage.clientWidth/stage.clientHeight;camera.updateProjectionMatrix();}
new ResizeObserver(resize).observe(stage);resize();
document.querySelector('#status').hidden=true;
function frame(now){
  const delta=Math.min((now-last)/1000,.08);last=now;
  if(playing && !document.hidden)time=(time+delta)%DURATION;
  const state=sample(time),p=state.progress;
  let guard=0,kt=0,mt=0,side=0;
  if(state.index===1)mt=smooth(.16,.35,p)*(1-smooth(.58,.88,p));
  if(state.index===2)guard=smooth(0,.2,p);
  if(state.index===3){guard=1-smooth(0,.22,p);kt=smooth(.1,.3,p)*(1-smooth(.5,.72,p));side=.4*smooth(.54,.75,p)*(1-smooth(.92,1,p));}
  pose(knight,guard,kt);pose(mage,0,mt,0,side);
  // Mage camera stays fixed while the mage sidesteps; the camera crop does not undo their dodge.
  if(state.index!==lastBeat){
    lastBeat=state.index;const b=BEATS[state.index];stage.dataset.step=String(state.index);
    document.querySelector('#eyebrow').textContent=`Beat 0${state.index+1} / ${b.label}`;
    document.querySelector('#beat').textContent=b.title;document.querySelector('#description').textContent=b.description;
    steps.forEach((button,i)=>{button.classList.toggle('active',i===state.index);button.setAttribute('aria-current',i===state.index?'step':'false');});
  }
  timeline.value=String(time);drawFeeds(state);controls.update();renderer.render(scene,camera);
  requestAnimationFrame(frame);
}
// Respect reduced motion; otherwise begin the narrated loop automatically.
setPlaying(!reducedMotion);
requestAnimationFrame(frame);
