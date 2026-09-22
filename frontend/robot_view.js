import * as THREE from './vendor/three.module.js';
import { STLLoader } from './vendor/STLLoader.js';

function quatFromWXYZ(q){ return new THREE.Quaternion(q[1]||0,q[2]||0,q[3]||0,q[0] ?? 1); }

function objIndex(raw,count){ const i=Number.parseInt(raw,10); return Number.isFinite(i) ? (i<0 ? count+i : i-1) : -1; }
function parseObjGeometry(text){
  const vertices=[],normals=[],positions=[],outNormals=[];
  for(const raw of text.split(/\r?\n/)){
    const line=raw.trim(); if(!line||line.startsWith('#'))continue;
    const parts=line.split(/\s+/), tag=parts[0];
    if(tag==='v'&&parts.length>=4)vertices.push([+parts[1],+parts[2],+parts[3]]);
    else if(tag==='vn'&&parts.length>=4)normals.push([+parts[1],+parts[2],+parts[3]]);
    else if(tag==='f'&&parts.length>=4){
      const face=parts.slice(1).map(token=>{const p=token.split('/');return {v:objIndex(p[0],vertices.length),n:p[2]?objIndex(p[2],normals.length):-1}});
      for(let i=1;i<face.length-1;i++)for(const ref of [face[0],face[i],face[i+1]]){
        const v=vertices[ref.v]; if(!v)continue; positions.push(...v);
        const n=normals[ref.n]; if(n)outNormals.push(...n);
      }
    }
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  if(outNormals.length===positions.length)geometry.setAttribute('normal',new THREE.Float32BufferAttribute(outNormals,3));
  else geometry.computeVertexNormals();
  return geometry;
}

export class UnitreeModelView {
  constructor(container){
    this.container=container; this.scene=new THREE.Scene(); this.camera=new THREE.PerspectiveCamera(42,1,.02,100);
    this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:true}); this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,2)); this.renderer.shadowMap.enabled=true; container.appendChild(this.renderer.domElement);
    this.world=new THREE.Group(); this.world.rotation.x=-Math.PI/2; this.scene.add(this.world); this.joints=[]; this.loader=new STLLoader();
    this.target=new THREE.Vector3(0,.8,0); this.defaultTarget=this.target.clone(); this.followEnabled=false; this.followOffset=new THREE.Vector3();
    this.grid=new THREE.GridHelper(12,30,0x34516f,0x22364d); this.scene.add(this.grid);
    this.scene.add(new THREE.HemisphereLight(0xe9f3ff,0x263747,2.1)); const key=new THREE.DirectionalLight(0xffffff,2.4);key.position.set(4,7,5);key.castShadow=true;this.scene.add(key);
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(container);this._orbit();this.resetCamera();this._animate();
  }
  clear(){ while(this.world.children.length)this.world.remove(this.world.children[0]); this.joints=[]; this.floatingRoot=null; }
  async loadRobot(robotId){
    this.clear(); const res=await fetch(`/api/model/${encodeURIComponent(robotId)}`); if(!res.ok) throw new Error(await res.text()); const manifest=await res.json();
    const jobs=[]; for(const body of manifest.bodies){ const group=this._body(body,robotId,jobs); if(!this.floatingRoot)this.floatingRoot=group; this.world.add(group); } await Promise.allSettled(jobs); this.resetCamera(); return manifest;
  }
  _body(node,robotId,jobs){
    const group=new THREE.Group(); group.name=node.name; group.position.fromArray(node.pos||[0,0,0]); group.quaternion.copy(quatFromWXYZ(node.quat||[1,0,0,0]));
    const base=group.quaternion.clone(); if(node.joint){ const axis=new THREE.Vector3(...(node.joint.axis||[0,0,1])).normalize(); this.joints.push({name:node.joint.name,group,base,axis}); }
    for(const geom of node.geoms||[]){
      const holder=new THREE.Group(); holder.position.fromArray(geom.pos||[0,0,0]); holder.quaternion.copy(quatFromWXYZ(geom.quat||[1,0,0,0])); group.add(holder);
      const url=`/api/model/${encodeURIComponent(robotId)}/asset?path=${encodeURIComponent(geom.asset)}`;
      const addMesh=(geometry)=>{ geometry.computeVertexNormals(); const rgba=geom.rgba||[.72,.74,.78,1]; const mat=new THREE.MeshStandardMaterial({color:new THREE.Color(rgba[0],rgba[1],rgba[2]),roughness:.55,metalness:.18,transparent:rgba[3]<.999,opacity:rgba[3]}); const mesh=new THREE.Mesh(geometry,mat); mesh.scale.fromArray(geom.scale||[1,1,1]); mesh.castShadow=true;mesh.receiveShadow=true;holder.add(mesh); };
      let job;
      if(String(geom.asset||'').toLowerCase().endsWith('.obj')){
        job=fetch(url).then(r=>{if(!r.ok)throw new Error(`OBJ asset failed: ${r.status}`);return r.text()}).then(t=>addMesh(parseObjGeometry(t))).catch(()=>{});
      }else{
        job=new Promise((resolve)=>this.loader.load(url,(geometry)=>{addMesh(geometry);resolve();},undefined,()=>resolve()));
      }
      jobs.push(job);
    }
    for(const child of node.children||[]) group.add(this._body(child,robotId,jobs)); return group;
  }
  updateState(state){
    if(this.floatingRoot && state?.base_position){
      this.floatingRoot.position.fromArray(state.base_position);
      if(state.base_quaternion)this.floatingRoot.quaternion.copy(quatFromWXYZ(state.base_quaternion));
      const local=new THREE.Vector3(...state.base_position);
      const worldTarget=local.clone().applyQuaternion(this.world.quaternion).add(this.world.position);
      worldTarget.y+=.82;
      if(this.followEnabled){ this.target.copy(worldTarget); this._positionCamera(); }
    }
    const q=state?.joint_positions||[]; this.joints.forEach((j,i)=>{ const rot=new THREE.Quaternion().setFromAxisAngle(j.axis,q[i]||0); j.group.quaternion.copy(j.base).multiply(rot); });
  }
  setFollowEnabled(enabled){
    this.followEnabled=!!enabled;
    if(!this.followEnabled)this.target.copy(this.defaultTarget);
    this._positionCamera();
  }
  resetCamera(){this.azimuth=.72;this.elevation=.25;this.distance=3.6;if(!this.followEnabled)this.target.copy(this.defaultTarget);this._positionCamera()}
  _positionCamera(){const c=Math.cos(this.elevation),s=Math.sin(this.elevation);this.camera.position.set(this.target.x+Math.sin(this.azimuth)*c*this.distance,this.target.y+.3+s*this.distance,this.target.z+Math.cos(this.azimuth)*c*this.distance);this.camera.lookAt(this.target)}
  toggleGrid(){this.grid.visible=!this.grid.visible}
  resize(){const w=Math.max(1,this.container.clientWidth),h=Math.max(1,this.container.clientHeight);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();this.renderer.setSize(w,h,false)}
  _orbit(){let drag=false,x=0,y=0;const el=this.renderer.domElement;el.addEventListener('pointerdown',e=>{drag=true;x=e.clientX;y=e.clientY;el.setPointerCapture(e.pointerId)});el.addEventListener('pointermove',e=>{if(!drag)return;this.azimuth-=(e.clientX-x)*.007;this.elevation=Math.max(-.1,Math.min(1.1,this.elevation+(e.clientY-y)*.006));x=e.clientX;y=e.clientY;this._positionCamera()});el.addEventListener('pointerup',()=>drag=false);el.addEventListener('wheel',e=>{e.preventDefault();this.distance=Math.max(1.5,Math.min(9,this.distance+e.deltaY*.004));this._positionCamera()},{passive:false})}
  _animate(){requestAnimationFrame(()=>this._animate());this.renderer.render(this.scene,this.camera)}
  screenshot(){return this.renderer.domElement.toDataURL('image/png')}
}
