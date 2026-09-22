import { UnitreeModelView } from './robot_view.js';
import { BuildSelectionStore } from './build_selection.js';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const api=async(path,options={})=>{const r=await fetch(path,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});if(!r.ok){let t=await r.text();try{const j=JSON.parse(t);t=typeof j.detail==='string'?j.detail:JSON.stringify(j.detail)}catch{}throw new Error(t)}return r.status===204?null:r.json()};
let robots=[],settings=null,buildStatus=null,state=null,simulationStatus={running:false},activePage='simulate',activeExample=null,pendingKey=null,keyConflict=null,buildTimer=null,activeRunnerStatus=null,llUiBusy=null,confirmResolver=null,activeRobotManagerId=null,scriptsSection='builtin';
const buildSelections = new BuildSelectionStore();
let view=null; try{view=new UnitreeModelView($('#robot-viewport'));}catch(e){$('#viewport-error').hidden=false;$('#viewport-error').textContent=`3D renderer unavailable: ${e.message}`;}
const velocityKeys=new Set(); let velocityKeyboardTimer=null; let followCameraEnabled=false; let wsConnected=false;
const ROBOT_ASSET_VERSION='0.1.0';
const ROBOT_PHOTO_BASE={
  unitree_g1:'/static/assets/robots/g1.png',
  unitree_g1_23dof:'/static/assets/robots/g1_23dof.png',
  unitree_go2:'/static/assets/robots/go2.png',
  unitree_h1:'/static/assets/robots/h1_2.png',
  unitree_r1:'/static/assets/robots/r1.png',
  unitree_a2:'/static/assets/robots/a2.png',
  unitree_h2:'/static/assets/robots/h2.png',
};
const ROBOT_PHOTOS=Object.fromEntries(Object.entries(ROBOT_PHOTO_BASE).map(([id,src])=>[id,`${src}?v=${ROBOT_ASSET_VERSION}`]));
function preloadRobotPhotos(){for(const src of new Set(Object.values(ROBOT_PHOTOS))){const img=new Image();img.decoding='async';img.src=src}}
let terminalActive='logs';
const terminalBuffers={logs:[],build:[],lowstate:[],dds:[]};
function renderTerminal(){const out=$('#terminal-output');if(!out)return;out.textContent=(terminalBuffers[terminalActive]||[]).join('\n');const auto=$('#terminal-autoscroll');if(!auto||auto.checked)out.scrollTop=out.scrollHeight}
function appendTerminal(tab,text){if(!terminalBuffers[tab])return;const lines=String(text??'').replace(/\r/g,'').split('\n');for(const line of lines){if(line.length)terminalBuffers[tab].push(line)}if(terminalBuffers[tab].length>800)terminalBuffers[tab].splice(0,terminalBuffers[tab].length-800);if(terminalActive===tab)renderTerminal()}
function setTerminalSnapshot(tab,text){terminalBuffers[tab]=String(text??'').split('\n');if(terminalActive===tab)renderTerminal()}
function selectTerminalTab(tab){if(!terminalBuffers[tab])return;terminalActive=tab;$$('[data-terminal-tab]').forEach(b=>{const active=b.dataset.terminalTab===tab;b.classList.toggle('active',active);b.setAttribute('aria-selected',active?'true':'false')});renderTerminal()}
function refreshDiagnosticBuffers(){const r=currentRobot();const rpy=state?.rpy||[0,0,0];setTerminalSnapshot('lowstate',[`Robot: ${r?.display_name||'—'}`,`Connected: ${state?.connected?'yes':'no'}`,`FSM: ${state?.fsm_mode||'—'}`,`Owner: ${state?.control_owner||'—'}`,`Sim time: ${(state?.sim_time||0).toFixed(3)} s`,`RPY: ${rpy.map(v=>Number(v||0).toFixed(4)).join(', ')}`,`Policy: ${state?.policy_hz||0} Hz`].join('\n'));setTerminalSnapshot('dds',[`Browser WebSocket: ${wsConnected?'connected':'disconnected'}`,`Native simulation: ${simulationStatus?.running?'running':'stopped'}`,`DDS interface: lo`,`Robot: ${r?.display_name||'—'}`,`Control owner: ${state?.control_owner||'—'}`,`LowState source: ${state?.connected?'live MuJoCo':'not connected'}`].join('\n'))}
const log=(msg,level='INFO')=>{const now=new Date().toLocaleTimeString();appendTerminal('logs',`[${now}] [${level}] ${msg}`)};
const robotBy=id=>robots.find(r=>r.id===id);
const installed=()=>buildStatus?.installed_robots||[];
const currentRobot=()=>robotBy(settings?.active_robot);
function setWorkspaceMode(mode){const host=$('#workspace');if(!host)return;host.className=`workspace mode-${mode}`}

async function boot(){
  [robots,settings,buildStatus,state,simulationStatus]=await Promise.all([api('/api/robots'),api('/api/settings'),api('/api/build/status'),api('/api/state'),api('/api/simulation/status')]);
  applyTheme(settings.theme); preloadRobotPhotos(); renderRobotSelect(); renderBuildCards(); renderBuildProgress(); renderInstalled(); renderSettingsKeymap(); renderKeymap(); renderState(state); renderSimulationStatus(); restorePanels(); initExclusiveAccordion();
  if(!installed().length) showFirstRun(); else { showPage('simulate'); await loadActiveRobot(); }
  connectWs(); pollBuilds(); setInterval(pollNativeState,50); setInterval(pollSimulationStatus,1000); setInterval(refreshRunnerStatus,750);
}
function applyTheme(theme){document.documentElement.dataset.theme=theme||'light';$('#theme-toggle').textContent=theme==='light'?'☀':'☾'}
async function setTheme(theme){settings.theme=theme;await saveSettings();applyTheme(theme)}
async function saveSettings(){settings=await api('/api/settings',{method:'PUT',body:JSON.stringify(settings)})}
function renderRobotSelect(){const sel=$('#robot-select');sel.innerHTML='';const ids=installed();if(!ids.length){sel.add(new Option('No Robot Selected',''));sel.disabled=true;return}sel.disabled=false;for(const id of ids){const r=robotBy(id);if(r)sel.add(new Option(r.display_name,id))}sel.value=settings.active_robot||ids[0]||''}
async function stopSimulationAndContinue(message,affectedRobotIds=null){
  try{simulationStatus=await api('/api/simulation/status');renderSimulationStatus()}catch(e){log(`Could not refresh simulation status: ${e.message}`,'WARN')}
  if(!simulationStatus?.running)return true;
  const runningId=simulationStatus.robot_id||null;
  if(Array.isArray(affectedRobotIds)&&runningId&&!affectedRobotIds.includes(runningId))return true;
  const runningRobot=robotBy(runningId),runningName=runningRobot?.display_name||'The current robot';
  const ok=await confirmAction('Stop running simulation?',`${runningName} is currently running.\n\n${message}\n\nStop the simulation and continue?`,'Stop & Continue');
  if(!ok)return false;
  try{
    stopVelocityKeyboardLoop(true);
    simulationStatus=await api('/api/simulation/stop',{method:'POST'});
    state=await api('/api/state');
    renderState(state);renderSimulationStatus();
    log(`Stopped ${runningName} simulation to continue.`);
    return true;
  }catch(e){log(e.message,'ERROR');alert(e.message);return false}
}
async function chooseRobot(id){
  if(!id)return false;
  const previous=settings.active_robot;
  if(id===previous)return true;
  const target=robotBy(id);
  if(!(await stopSimulationAndContinue(`Switch to ${target?.display_name||id}.`))){
    const sel=$('#robot-select');if(sel)sel.value=previous||'';
    return false;
  }
  settings.active_robot=id;
  if(!settings.installed_robots.includes(id))settings.installed_robots=installed();
  await saveSettings();
  state=await api('/api/state');renderState(state);
  await loadActiveRobot();await refreshExamples();await refreshScriptsFiles();await refreshMimic();renderRobotManager();
  return true;
}
async function loadActiveRobot(){const r=currentRobot();const ph=$('#viewport-placeholder'),vs=$('#viewport-state');if(!r){ph.hidden=false;vs.hidden=true;view?.clear();return}ph.hidden=true;vs.hidden=false;$('#viewport-robot-name').textContent=r.display_name;$('#viewport-state-label').textContent=r.display_name;try{await view?.loadRobot(r.id);$('#viewport-error').hidden=true}catch(e){$('#viewport-error').hidden=false;$('#viewport-error').textContent=`Robot mesh load failed: ${e.message}`;log(`Model load failed: ${e.message}`,'WARN')}renderCapabilityViews()}
function applyLevelView(level,persist=true){const r=currentRobot(),info=buildStatus?.robots?.[r?.id];const highOk=!!(r&&info?.high_level&&r.supports_web_high_level),lowOk=!!(r&&info?.low_level);if(level==='high'&&!highOk)level=lowOk?'low':'high';settings.ui_level=level;$('#level-high').classList.toggle('active',level==='high');$('#level-low').classList.toggle('active',level==='low');if(activePage==='simulate'||activePage==='examples'){$('#high-level-view').hidden=level!=='high';$('#low-level-view').hidden=level!=='low';setWorkspaceMode(level==='low'?'low':'high')}if(persist)saveSettings().catch(e=>log(e.message,'ERROR'));if(level==='low')refreshExamples();renderSettingsSummary();return level}
function renderCapabilityViews(){const r=currentRobot(),info=buildStatus?.robots?.[r?.id];const highOk=!!(r&&info?.high_level&&r.supports_web_high_level);$('#level-high').disabled=!highOk;$('#level-low').disabled=!(r&&info?.low_level);if(settings.ui_level==='high'&&!highOk)settings.ui_level='low';applyLevelView(settings.ui_level,false)}
function showFirstRun(){activePage='first';setWorkspaceMode('first');$$('.page-view').forEach(x=>x.hidden=true);$('#first-run-view').hidden=false;$('#start-simulation').disabled=true;$('#sim-status').textContent='● No Robots Installed';$('#sim-status').className='status-pill offline';$('#viewport-placeholder').hidden=false;$('#viewport-state').hidden=true;renderPackageSummary()}
function showPage(page){activePage=page;$$('.rail-item').forEach(b=>b.classList.toggle('active',b.dataset.page===page));$$('.page-view').forEach(x=>x.hidden=true);if(page==='simulate'){if(!installed().length)return showFirstRun();const level=settings.ui_level;setWorkspaceMode(level==='low'?'low':'high');$(level==='low'?'#low-level-view':'#high-level-view').hidden=false}else if(page==='robots'){setWorkspaceMode('robots');$('#robots-view').hidden=false;renderRobotManager()}else if(page==='scripts'){setWorkspaceMode('scripts');$('#scripts-view').hidden=false;refreshScriptsFiles()}else if(page==='assets'){setWorkspaceMode('assets');$('#assets-view').hidden=false}else if(page==='settings'){setWorkspaceMode('settings');$('#settings-view').hidden=false;renderSettingsSummary()} }
async function switchLevel(level,persist=true){const r=currentRobot(),info=buildStatus?.robots?.[r?.id];if(!r)return;if(level==='high'&&!(info?.high_level&&r.supports_web_high_level)){log('High-Level pack is not available for this robot.','WARN');return}if(level==='low'&&!info?.low_level){log('Low-Level SDK pack is not available for this robot.','WARN');return}const previous=settings.ui_level;$('#level-high').disabled=true;$('#level-low').disabled=true;stopVelocityKeyboardLoop(true);try{if(level==='low'){setLlBusy('switching');state=await api('/api/control/ll-prepare',{method:'POST'});renderState(state)}else{state=await api('/api/control/passive',{method:'POST'});llUiBusy=null;renderState(state);await refreshRunnerStatus()}applyLevelView(level,persist);log(level==='low'?'Low-Level Debug owns control.':'High-Level Passive owns control.')}catch(e){log(e.message,'WARN');applyLevelView(previous,false)}finally{if(llUiBusy==='switching')setLlBusy(null);renderCapabilityViews()}}



async function pollNativeState(){
  if(!simulationStatus?.running)return;
  try{state=await api('/api/state');renderState(state);}
  catch(e){/* transient stop/build race */}
}
async function pollSimulationStatus(){
  try{
    const previous=!!simulationStatus?.running;
    simulationStatus=await api('/api/simulation/status');
    if(previous!==!!simulationStatus.running){
      renderSimulationStatus();
      if(previous&&!simulationStatus.running)log('Native simulation stopped.','WARN');
    }
  }catch(e){/* keep UI responsive during backend restart */}
}

function renderSimulationStatus(){
  const running=!!simulationStatus?.running, button=$('#start-simulation'), pill=$('#sim-status');
  button.disabled=!installed().length;
  button.textContent=running?'■ Stop Simulation':'▶ Start Simulation';
  if(running){pill.textContent='● Simulation Running';pill.className='status-pill online'}
  else if(installed().length){pill.textContent='● Ready';pill.className='status-pill online'}
  else{pill.textContent='● No Robots Installed';pill.className='status-pill offline'}
  refreshDiagnosticBuffers();
  renderSettingsSummary();
}
function renderSettingsSummary(){const r=currentRobot();const active=$('#settings-active-robot'),level=$('#settings-control-level'),sim=$('#settings-sim-status');if(active)active.textContent=r?.display_name||'None';if(level)level.textContent=settings?.ui_level==='low'?'Low Level / LL Debug':'High Level';if(sim)sim.textContent=simulationStatus?.running?`Running · MuJoCo PID ${simulationStatus.sim_pid||'—'}${simulationStatus.controller_pid?` · Controller PID ${simulationStatus.controller_pid}`:''}`:'Stopped'}
function selectSettingsSection(section){$$('[data-settings-section]').forEach(b=>b.classList.toggle('active',b.dataset.settingsSection===section));$$('[data-settings-panel]').forEach(p=>p.hidden=p.dataset.settingsPanel!==section)}
async function toggleSimulation(){
  const r=currentRobot(); if(!r)return;
  try{
    if(simulationStatus?.running){simulationStatus=await api('/api/simulation/stop',{method:'POST'});log('Native simulation stopped.');}
    else{simulationStatus=await api(`/api/simulation/start/${r.id}`,{method:'POST'});log(`Native simulation started: ${r.display_name}`);}
    state=await api('/api/state');renderState(state);renderSimulationStatus();
  }catch(e){log(e.message,'ERROR');alert(e.message)}
}

function capability(robot){const canBuild=!!robot.model_xml,hlConfigured=!!robot.supports_web_high_level,hl=!!(hlConfigured&&robot.high_level_ready);return {canBuild,hl,hlConfigured,ll:!!robot.supports_low_level}}
function highLevelBadge(cap){return cap.hl?'● High-Level Pack':cap.hlConfigured?'! Policy Required':'− High-Level unavailable'}
const FIRST_RUN_PRIMARY=['unitree_g1','unitree_go2','unitree_h1','unitree_r1'];
function robotThumb(robot){return robot.family==='quadruped'?'quadruped':'humanoid'}
function robotCard(robot,manager=false){
  const info=buildStatus?.robots?.[robot.id]||{},cap=capability(robot),disabled=!cap.canBuild||(!cap.hl&&!cap.ll);
  const draft=buildSelections.ensure(robot.id,{highLevel:cap.hl,lowLevel:cap.ll});
  const div=document.createElement('div');
  div.className='robot-card'+(info.installed?' installed':'')+(draft.selected?' selected':'');
  div.dataset.robot=robot.id;
  div.innerHTML=`<label class="robot-card-select"><input class="robot-select-check" type="checkbox" ${draft.selected?'checked':''} ${disabled?'disabled':''}><span></span></label>
    <div class="robot-card-photo-frame">
      <img class="robot-card-photo" src="${ROBOT_PHOTOS[robot.id]||''}" alt="${robot.display_name}" loading="eager" decoding="async" referrerpolicy="no-referrer">
      <div class="robot-photo-fallback robot-card-visual ${robotThumb(robot)}" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
      <span class="robot-photo-source">Local robot asset</span>
    </div>
    <div class="robot-card-title"><h3>${robot.display_name.replace('Unitree ','')}</h3><small>${robot.family==='quadruped'?'Quadruped Robot':'Humanoid Robot'}</small></div>
    <div class="capability-badges">
      <span class="capability ${cap.hl?'available':'unavailable'}">${highLevelBadge(cap)}</span>
      <span class="capability ${cap.ll?'available':'unavailable'}">${cap.ll?'●':'−'} Low-Level SDK</span>
    </div>
    <button type="button" class="robot-details-link">View Details →</button>
    ${manager?`<footer><span>${info.stage||'Not built'}</span><span>${info.progress||0}%</span></footer>`:''}`;
  const photo=$('.robot-card-photo',div),fallback=$('.robot-photo-fallback',div);
  if(photo){photo.addEventListener('load',()=>{photo.classList.add('loaded');if(fallback)fallback.hidden=true});photo.addEventListener('error',()=>{photo.hidden=true;if(fallback)fallback.hidden=false})}
  const check=$('.robot-select-check',div);
  check?.addEventListener('change',()=>{
    buildSelections.setSelected(robot.id,check.checked);
    if(check.checked){
      buildSelections.setPack(robot.id,'highLevel',cap.hl&&($('#global-pack-high')?.checked??true));
      buildSelections.setPack(robot.id,'lowLevel',cap.ll&&($('#global-pack-low')?.checked??true));
    }
    div.classList.toggle('selected',check.checked);renderPackageSummary();
  });
  $('.robot-details-link',div)?.addEventListener('click',()=>alert(`${robot.display_name}\n\n${robot.note||'No additional notes.'}`));
  return div;
}
function renderBuildCards(){
  const first=$('#robot-build-grid'),more=$('#more-robot-build-grid');
  if(first){first.innerHTML='';for(const id of FIRST_RUN_PRIMARY){const r=robotBy(id);if(r)first.appendChild(robotCard(r,false))}}
  if(more){more.innerHTML='';for(const r of robots.filter(x=>!FIRST_RUN_PRIMARY.includes(x.id)))more.appendChild(robotCard(r,false))}
  renderPackageSummary();renderRobotManager();
}
function robotTypeLabel(robot){return robot.family==='quadruped'?'Quadruped Robot':'Humanoid Robot'}
function robotBuildStatus(info){if(info?.installed)return 'Installed';if(info?.stage&&info.stage!=='idle')return info.stage;if((info?.progress||0)>0)return 'Building…';return 'Not Built'}
function robotManagerCard(robot){
  const info=buildStatus?.robots?.[robot.id]||{},cap=capability(robot),draft=buildSelections.ensure(robot.id,{highLevel:cap.hl,lowLevel:cap.ll});
  const card=document.createElement('article');
  card.className='manager-robot-card'+(draft.selected?' selected':'')+(robot.id===activeRobotManagerId?' active':'')+(info.installed?' installed':'');
  card.dataset.robot=robot.id;
  card.innerHTML=`<label class="manager-card-check" title="Select ${robot.display_name} for build"><input type="checkbox" ${draft.selected?'checked':''} ${(!cap.canBuild||(!cap.hl&&!cap.ll))?'disabled':''}></label>
    <div class="manager-card-visual"><img src="${ROBOT_PHOTOS[robot.id]||''}" alt="${robot.display_name}" loading="eager" decoding="async"></div>
    <div class="manager-card-name"><strong>${robot.display_name.replace('Unitree ','')}</strong><small>${robotTypeLabel(robot)}</small></div>
    <div class="manager-card-packages">
      <span class="${cap.hl?'ok':'off'}">${cap.hl?'● High-Level Pack':cap.hlConfigured?'! Policy Required':'○ High-Level unavailable'}</span>
      <span class="${cap.ll?'ok':'off'}">${cap.ll?'●':'○'} Low-Level SDK</span>
    </div>
    <div class="manager-card-status ${info.installed?'ready':''}"><i></i>${robotBuildStatus(info)}</div>
    <button type="button" class="manager-card-details">View Details →</button>`;
  const selectRobot=()=>{activeRobotManagerId=robot.id;$$('.manager-robot-card').forEach(x=>x.classList.toggle('active',x.dataset.robot===robot.id));renderRobotManagerDetail(robot.id)};
  card.addEventListener('click',e=>{if(e.target.closest('input,button,label'))return;selectRobot()});
  $('.manager-card-details',card).onclick=e=>{e.stopPropagation();selectRobot()};
  const check=$('input',card);check.onchange=e=>{e.stopPropagation();buildSelections.setSelected(robot.id,check.checked);if(check.checked){buildSelections.setPack(robot.id,'highLevel',cap.hl);buildSelections.setPack(robot.id,'lowLevel',cap.ll)}card.classList.toggle('selected',check.checked);renderPackageSummary()};
  return card;
}
function renderRobotManager(){
  const grid=$('#robot-manager-grid');if(!grid||!robots.length)return;
  if(!activeRobotManagerId||!robotBy(activeRobotManagerId))activeRobotManagerId=settings?.active_robot||robots[0].id;
  grid.innerHTML='';for(const robot of robots)grid.appendChild(robotManagerCard(robot));
  const count=$('#robot-manager-available-count');if(count)count.textContent=`(${robots.length})`;
  renderRobotManagerDetail(activeRobotManagerId);renderPackageSummary();
}
function renderRobotManagerDetail(robotId){
  const robot=robotBy(robotId);if(!robot)return;
  const info=buildStatus?.robots?.[robot.id]||{},cap=capability(robot),draft=buildSelections.ensure(robot.id,{highLevel:cap.hl,lowLevel:cap.ll});
  const photo=$('#robot-manager-preview-image');if(photo){const nextSrc=ROBOT_PHOTOS[robot.id]||'';if(photo.getAttribute('src')!==nextSrc)photo.src=nextSrc;photo.alt=`${robot.display_name} reference preview`}
  const name=$('#robot-manager-preview-name');if(name)name.textContent=robot.display_name;
  const status=$('#robot-manager-preview-status');if(status){status.innerHTML=`<i></i> ${info.installed?'Ready':robotBuildStatus(info)}`;status.classList.toggle('ready',!!info.installed)}
  const mode=$('#robot-manager-preview-mode');if(mode)mode.textContent=cap.hl?'High Level':'Low Level';
  const control=$('#robot-manager-preview-control');if(control)control.textContent=cap.hl?'Velocity / Native':'Low-Level SDK';
  const packages=$('#robot-manager-preview-packages');if(packages)packages.textContent=[cap.hl?'High-Level Pack':cap.hlConfigured?'High-Level Policy Required':null,cap.ll?'Low-Level SDK':null].filter(Boolean).join(', ')||'No buildable packages';
  const detail=$('#robot-manager-preview-details');if(detail)detail.onclick=()=>alert(`${robot.display_name}\n\n${robot.note||'No additional notes.'}\n\nSelected for build: ${draft.selected?'yes':'no'}`);
}
function updateRobotCardBuildState(){
  for(const robot of robots){
    const info=buildStatus?.robots?.[robot.id]||{};
    $$(`[data-robot="${robot.id}"]`).forEach(card=>{
      card.classList.toggle('installed',!!info.installed);
      const status=$('.manager-card-status',card);
      if(status){status.classList.toggle('ready',!!info.installed);status.innerHTML=`<i></i>${robotBuildStatus(info)}`}
      const footer=$('footer',card);
      if(footer){const spans=$$('span',footer);if(spans[0])spans[0].textContent=info.stage||'Not built';if(spans[1])spans[1].textContent=`${info.progress||0}%`}
    });
  }
  if(activeRobotManagerId)renderRobotManagerDetail(activeRobotManagerId);
}
function selectedBuildItems(){return buildSelections.selectedItems()}
function syncGlobalPack(pack,enabled){
  for(const r of robots){const d=buildSelections.get(r.id);if(!d?.selected)continue;const cap=capability(r);buildSelections.setPack(r.id,pack,Boolean(enabled&&(pack==='highLevel'?cap.hl:cap.ll)))}
  renderPackageSummary();
}
function renderPackageSummary(){
  const items=buildSelections.selectedItems(),count=items.length;
  const p=$('#package-summary');if(p)p.textContent=count?`${count} robot${count===1?'':'s'} selected.`:'Select one or more robots.';
  const first=$('#overview-selected-count'),mgr=$('#robots-selected-count');if(first)first.textContent=count?String(count):'—';if(mgr)mgr.textContent=String(count);
  const estimatedDisk=count?`${(1.3+count*1.1).toFixed(1)} GB`:'—',estimatedTime=count?`~ ${6+count*6} min`:'—';
  const disk=$('#overview-disk'),time=$('#overview-time'),managerDisk=$('#manager-overview-disk'),managerTime=$('#manager-overview-time');
  if(disk)disk.textContent=count?`~ ${estimatedDisk}`:'—';if(time)time.textContent=estimatedTime;if(managerDisk)managerDisk.textContent=estimatedDisk;if(managerTime)managerTime.textContent=estimatedTime;
  const managerBuild=$('#manager-build-selected');if(managerBuild){managerBuild.textContent=`🔨 Build Selected (${count})`;managerBuild.disabled=!count||!!buildStatus?.building}
  const managerRebuild=$('#manager-rebuild-selected');if(managerRebuild)managerRebuild.disabled=!count||!!buildStatus?.building;
  const empty=$('.overview-empty');if(empty){const strong=$('strong',empty),small=$('small',empty);if(count){strong.textContent=`${count} robot${count===1?'':'s'} selected`;small.textContent='Ready to build the selected packages.'}else{strong.textContent='No robots selected';small.textContent='Select one or more robots to see build details here.'}}
}
async function startBuild(){
  const items=selectedBuildItems();
  if(!items.length)return alert('Select at least one robot.');
  const itemIds=items.map(x=>x.robot_id);
  const runningId=simulationStatus?.robot_id;
  const runningRobot=robotBy(runningId);
  const reason=runningId&&itemIds.includes(runningId)
    ? `Rebuild ${runningRobot?.display_name||runningId}.`
    : 'Continue with the selected build.';
  if(!(await stopSimulationAndContinue(reason,itemIds)))return;
  try{
    buildStatus=await api('/api/build/start',{method:'POST',body:JSON.stringify({robots:items})});
    renderBuildProgress();
    log(`Started selective build: ${items.map(x=>x.robot_id).join(', ')}`);
  }catch(e){alert(e.message)}
}
async function cancelBuild(){await api('/api/build/cancel',{method:'POST'});await refreshBuildStatus()}
async function refreshBuildStatus(){const old=buildStatus?.building;buildStatus=await api('/api/build/status');updateRobotCardBuildState();renderBuildProgress();renderInstalled();if(old&&!buildStatus.building){settings=await api('/api/settings/sync-builds',{method:'POST'});renderRobotSelect();if(installed().length){if(!settings.active_robot){settings.active_robot=installed()[0];await saveSettings()}await chooseRobot(settings.active_robot);showPage('simulate')} } }
function pollBuilds(){clearInterval(buildTimer);buildTimer=setInterval(()=>refreshBuildStatus().catch(()=>{}),1000)}
function renderBuildProgress(){for(const id of ['#build-progress','#manager-build-progress']){const host=$(id);if(!host)continue;host.innerHTML='';for(const rid of buildStatus?.current||[]){const r=robotBy(rid),x=buildStatus.robots[rid];host.insertAdjacentHTML('beforeend',`<div class="progress-row"><span>${r?.display_name||rid}</span><div class="progress-bar"><span style="width:${x.progress||0}%"></span></div><b>${x.progress||0}%</b></div><small class="muted">${x.stage||''}</small>`)}if(!(buildStatus?.current||[]).length)host.innerHTML='<span class="muted">No build running.</span>'}const lines=(buildStatus?.log||[]).slice(-120).join('\n');const buildLog=$('#build-log'),managerLog=$('#manager-build-log'),cancel=$('#cancel-build'),queue=$('#robot-build-queue-count');if(buildLog)buildLog.textContent=lines;if(managerLog)managerLog.textContent=lines;if(cancel)cancel.disabled=!buildStatus?.building;if(queue)queue.textContent=String((buildStatus?.current||[]).length);renderPackageSummary()}
function renderInstalled(){const host=$('#installed-robots-list'),ids=installed(),count=$('#robots-installed-count');if(count)count.textContent=String(ids.length);host.innerHTML='';if(!ids.length){host.innerHTML='<span class="muted">No robots installed.</span>';return}for(const id of ids){const r=robotBy(id),info=buildStatus.robots[id];host.insertAdjacentHTML('beforeend',`<div class="list-row"><span><b>${r.display_name}</b><small class="muted"> · ${info.high_level?'HL ':''}${info.low_level?'LL':''}</small></span><span class="badge ok">Ready</span></div>`)}}

function renderState(s){state=s;$('#viewport-mode').textContent=s?.fsm_mode||'—';$('#viewport-time').textContent=formatTime(s?.sim_time||0);$('#ll-owner-badge').textContent=`Owner: ${s?.control_owner||'—'}`;const live=$('#viewport-live-source');if(live)live.textContent=s?.connected?'● Live MuJoCo':'○ Model Ready · Live MuJoCo when simulation runs';view?.updateState(s);refreshDiagnosticBuffers();$$('[data-fsm]').forEach(b=>b.classList.toggle('active',b.dataset.fsm===s?.fsm_mode));renderTelemetry()}
function formatTime(sec){const s=Math.floor(sec%60).toString().padStart(2,'0'),m=Math.floor(sec/60%60).toString().padStart(2,'0'),h=Math.floor(sec/3600).toString().padStart(2,'0');return `${h}:${m}:${s}`}
function renderTelemetry(){const host=$('#telemetry-grid');if(!host)return;const rpy=state?.rpy||[0,0,0];host.innerHTML=`<div class="telemetry-card">FSM <b>${state?.fsm_mode||'—'}</b></div><div class="telemetry-card">Owner <b>${state?.control_owner||'—'}</b></div><div class="telemetry-card">Roll <b>${rpy[0].toFixed(2)}</b></div><div class="telemetry-card">Pitch <b>${rpy[1].toFixed(2)}</b></div><div class="telemetry-card">Yaw <b>${rpy[2].toFixed(2)}</b></div><div class="telemetry-card">Policy <b>${state?.policy_hz||0} Hz</b></div>`}
async function setFsm(mode){if(mode!=='Velocity')stopVelocityKeyboardLoop(false);try{state=await api('/api/control/fsm',{method:'POST',body:JSON.stringify({mode})});renderState(state)}catch(e){log(e.message,'WARN')}}
async function sendVelocity(){const body={vx:+$('#velocity-vx').value,vy:+$('#velocity-vy').value,yaw:+$('#velocity-yaw').value};for(const k of ['vx','vy','yaw'])$(`#velocity-${k}-value`).value=body[k].toFixed(2);try{state=await api('/api/control/velocity',{method:'POST',body:JSON.stringify(body)});renderState(state)}catch(e){if(state?.fsm_mode==='Velocity')log(e.message,'WARN')}}

const velocityActions=new Set(['forward','backward','left','right','yaw_left','yaw_right']);
function actionForKeyboardEvent(e){
  const key=e.key?.toLowerCase?.()||'';
  return Object.entries(settings?.keymap||{}).find(([,mapped])=>(mapped||'').toLowerCase()===key)?.[0]||null;
}
function velocityFromHeldKeys(){
  let vx=0,vy=0,yaw=0;
  if(velocityKeys.has('forward'))vx+=0.55;
  if(velocityKeys.has('backward'))vx-=0.35;
  if(velocityKeys.has('right'))vy+=0.35;
  if(velocityKeys.has('left'))vy-=0.35;
  if(velocityKeys.has('yaw_right'))yaw+=0.65;
  if(velocityKeys.has('yaw_left'))yaw-=0.65;
  return {vx,vy,yaw};
}
async function pushKeyboardVelocity(){
  if(state?.control_owner!=='high'||state?.fsm_mode!=='Velocity'||!simulationStatus?.running)return;
  const body=velocityFromHeldKeys();
  $('#velocity-vx').value=body.vx;$('#velocity-vy').value=body.vy;$('#velocity-yaw').value=body.yaw;
  for(const k of ['vx','vy','yaw'])$(`#velocity-${k}-value`).value=body[k].toFixed(2);
  try{state=await api('/api/control/velocity',{method:'POST',body:JSON.stringify(body)});renderState(state)}catch(e){/* mode may change while a key is held */}
}
function startVelocityKeyboardLoop(){
  if(velocityKeyboardTimer)return;
  velocityKeyboardTimer=setInterval(()=>{if(velocityKeys.size)pushKeyboardVelocity()},50);
}
function stopVelocityKeyboardLoop(sendZero=true){
  if(velocityKeyboardTimer){clearInterval(velocityKeyboardTimer);velocityKeyboardTimer=null}
  velocityKeys.clear();
  if(sendZero&&state?.control_owner==='high'&&state?.fsm_mode==='Velocity'&&simulationStatus?.running){
    const body={vx:0,vy:0,yaw:0};
    $('#velocity-vx').value=0;$('#velocity-vy').value=0;$('#velocity-yaw').value=0;
    for(const k of ['vx','vy','yaw'])$(`#velocity-${k}-value`).value='0.00';
    api('/api/control/velocity',{method:'POST',body:JSON.stringify(body)}).then(x=>{state=x;renderState(x)}).catch(()=>{});
  }
}
function handleVelocityKeyDown(action,e){
  if(!velocityActions.has(action))return false;
  e.preventDefault();
  if(state?.fsm_mode!=='Velocity'||state?.control_owner!=='high'){return true}
  velocityKeys.add(action);startVelocityKeyboardLoop();pushKeyboardVelocity();return true;
}
function handleVelocityKeyUp(action,e){
  if(!velocityActions.has(action))return false;
  e.preventDefault();velocityKeys.delete(action);pushKeyboardVelocity();
  if(!velocityKeys.size)stopVelocityKeyboardLoop(true);return true;
}
async function hanger(action){try{state=await api('/api/control/hanger',{method:'POST',body:JSON.stringify({action})});renderState(state)}catch(e){log(e.message,'WARN')}}

async function runPolicy(policyId){try{state=await api(`/api/control/policy/${encodeURIComponent(policyId)}`,{method:'POST'});renderState(state);log(`Policy started: ${policyId}`)}catch(e){log(e.message,'WARN')}}
async function refreshMimic(){const r=currentRobot();if(!r?.supports_mimic)return;const items=await api(`/api/mimic/${r.id}`);for(const hostId of ['#mimic-policy-list','#asset-policy-list']){const host=$(hostId);host.innerHTML='';if(!items.length)host.innerHTML='<span class="muted">No policies loaded.</span>';for(const p of items)host.insertAdjacentHTML('beforeend',`<div class="list-row"><span>♟ <b>${p.name||p.id}</b></span><span class="badge ok">Ready</span></div>`)}}
async function uploadPolicies(files){const r=currentRobot();if(!r?.supports_mimic)return alert('Mimic web pack is not available for this robot.');for(const f of files){try{await api(`/api/mimic/${r.id}/upload?filename=${encodeURIComponent(f.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:await f.arrayBuffer()});log(`Loaded mimic: ${f.name}`)}catch(e){log(e.message,'ERROR')}}await refreshMimic()}

function keyLabel(action){if(action==='dance_default')return 'Dance1 Subject2';return action.replaceAll('_',' ').replace(/\b\w/g,x=>x.toUpperCase())}
function renderKeymap(){for(const id of ['#keymap-list','#settings-keymap-list']){const host=$(id);if(!host)continue;host.innerHTML='';for(const [action,key] of Object.entries(settings.keymap||{})){const row=document.createElement('div');row.className='keymap-row';row.innerHTML=`<span>${keyLabel(action)}</span><button data-key-action="${action}">${prettyKey(key)}</button>`;host.appendChild(row)}}$$('[data-key-for]').forEach(k=>k.textContent=prettyKey(settings.keymap[k.dataset.keyFor]||'?'))}
function renderSettingsKeymap(){renderKeymap()}
function prettyKey(k){return ({ArrowLeft:'←',ArrowRight:'→',ArrowUp:'↑',ArrowDown:'↓'})[k]||k}
function captureKeyForAction(action,button){pendingKey={action,button};button.classList.add('capturing');button.textContent='Press a key…'}
async function resolveKeyConflict(resolution){if(!keyConflict)return;const {action,key}=keyConflict;if(resolution!=='cancel'){const r=await api('/api/settings/keymap',{method:'POST',body:JSON.stringify({action,key,resolution})});settings.keymap=r.keymap;renderKeymap()}keyConflict=null;$('#duplicate-key-modal').hidden=true}
async function remap(action,key){try{const r=await api('/api/settings/keymap',{method:'POST',body:JSON.stringify({action,key,resolution:'reject'})});settings.keymap=r.keymap;renderKeymap()}catch(e){let detail;try{detail=JSON.parse(e.message)}catch{}const existing=detail?.existing_action||'another action';keyConflict={action,key};$('#duplicate-key-text').textContent=`${prettyKey(key)} is already assigned to ${keyLabel(existing)}. Replace or swap it?`;$('#duplicate-key-modal').hidden=false}}

async function fetchExampleLists(){const r=currentRobot();if(!r||!buildStatus?.robots?.[r.id]?.low_level)return {builtins:[],workspace:[]};const [builtins,workspace]=await Promise.all([api(`/api/examples/${r.id}`),api(`/api/workspace/${r.id}`)]);return {builtins,workspace}}
async function refreshExamples(){const r=currentRobot(),host=$('#examples-tree');if(!host)return;if(!r||!buildStatus?.robots?.[r.id]?.low_level){host.innerHTML='<span class="muted">Build a Low-Level SDK pack first.</span>';return}try{const {builtins,workspace}=await fetchExampleLists();host.innerHTML='<b class="muted">Built-in Low Level</b>';for(const e of builtins)host.appendChild(exampleButton(e,true));host.insertAdjacentHTML('beforeend','<b class="muted" style="margin-top:8px">My Examples</b>');for(const e of workspace)host.appendChild(exampleButton(e,false))}catch(e){host.innerHTML=`<span class="muted">${e.message}</span>`}}
function exampleButton(e,builtin){const b=document.createElement('button');b.className='example-item';b.innerHTML=`<span class="example-icon">${builtin?'▧':'▤'}</span><span class="example-name">${e.name}</span>`;b.title=e.relative_path;b.onclick=()=>openExample(e.relative_path,builtin);return b}
async function openExample(path,builtin){const r=currentRobot();const data=await api(builtin?`/api/examples/${r.id}/source?path=${encodeURIComponent(path)}`:`/api/workspace/${r.id}/source?path=${encodeURIComponent(path)}`);activeExample={path:data.path,builtin,readonly:data.readonly};activeRunnerStatus=null;$('#code-editor').value=data.content;$('#code-editor').readOnly=data.readonly;$('#editor-path').textContent=data.path;$('#editor-mode').textContent=data.readonly?'Read-Only SDK · Build/Run allowed':'Editable';$('#copy-example').disabled=!builtin;$('#save-source').disabled=builtin;await refreshRunnerStatus()}
async function copyExampleToWorkspace(){if(!activeExample?.builtin)return;const r=currentRobot(),name=`my_${activeExample.path.split('/').pop()}`;const out=await api(`/api/workspace/${r.id}/copy`,{method:'POST',body:JSON.stringify({source:activeExample.path,destination:name})});await refreshExamples();await refreshScriptsFiles();await openExample(out.path,false)}
async function saveSource(){if(!activeExample||activeExample.builtin)return;const r=currentRobot();await api(`/api/workspace/${r.id}/source`,{method:'PUT',body:JSON.stringify({path:activeExample.path,content:$('#code-editor').value})});log(`Saved ${activeExample.path}`)}
async function renameWorkspaceFile(path){const r=currentRobot();if(!r)return;const current=path.split('/').pop();const next=prompt('Rename workspace file',current);if(!next||next===current)return;try{const out=await api(`/api/workspace/${r.id}/rename`,{method:'POST',body:JSON.stringify({path,new_name:next})});if(activeExample&&!activeExample.builtin&&activeExample.path===path)await openExample(out.path,false);await refreshExamples();await refreshScriptsFiles();log(`Renamed ${path} → ${out.path}`)}catch(e){alert(e.message)}}
async function deleteWorkspaceFile(path){const r=currentRobot();if(!r)return;const ok=await confirmAction('Delete workspace file?',`Delete ${path}?\n\nThis cannot be undone.`,'Delete');if(!ok)return;try{await api(`/api/workspace/${r.id}/source?path=${encodeURIComponent(path)}`,{method:'DELETE'});if(activeExample&&!activeExample.builtin&&activeExample.path===path){activeExample=null;activeRunnerStatus=null;$('#code-editor').value='';$('#editor-path').textContent='No example open';$('#editor-mode').textContent='—';renderRunnerButtons()}await refreshExamples();await refreshScriptsFiles();log(`Deleted ${path}`)}catch(e){alert(e.message)}}
function selectScriptsSection(section){scriptsSection=section;$$('[data-scripts-section]').forEach(b=>b.classList.toggle('active',b.dataset.scriptsSection===section));$$('[data-scripts-panel]').forEach(p=>p.hidden=p.dataset.scriptsPanel!==section);if(section==='profiles')loadBuildProfiles()}
function fileManagerRow(entry,builtin){const row=document.createElement('div');row.className='file-manager-row';row.innerHTML=`<div class="file-main"><span>${builtin?'▧':'▤'}</span><div><strong>${entry.name}</strong><small>${entry.relative_path}${builtin?' · SDK read-only':' · Workspace editable'}</small></div></div><div class="file-manager-actions"><button data-action="open">Open</button><button data-action="build">Build</button><button data-action="run" class="success">Run</button>${builtin?'<button data-action="copy">Copy</button>':'<button data-action="rename">Rename</button><button data-action="delete" class="danger">Delete</button>'}</div>`;const act=async action=>{if(action==='open'){showPage('simulate');await switchLevel('low');await openExample(entry.relative_path,builtin);return}if(action==='copy'){await openExample(entry.relative_path,true);await copyExampleToWorkspace();return}if(action==='rename')return renameWorkspaceFile(entry.relative_path);if(action==='delete')return deleteWorkspaceFile(entry.relative_path);showPage('simulate');await switchLevel('low');await openExample(entry.relative_path,builtin);if(action==='build')await buildSource();if(action==='run'){await refreshRunnerStatus();if(!activeRunnerStatus?.built)await buildSource();await refreshRunnerStatus();if(activeRunnerStatus?.built)await runSource()}};$$('button',row).forEach(b=>b.onclick=()=>act(b.dataset.action));return row}
async function refreshScriptsFiles(){const r=currentRobot(),built=$('#scripts-builtin-list'),work=$('#scripts-workspace-list');if(!built||!work)return;if(!r){built.innerHTML=work.innerHTML='<span class="muted">Select a built robot.</span>';return}try{const {builtins,workspace}=await fetchExampleLists();built.innerHTML='';work.innerHTML='';if(!builtins.length)built.innerHTML='<span class="muted">No simulator-compatible built-in files.</span>';else for(const e of builtins)built.appendChild(fileManagerRow(e,true));if(!workspace.length)work.innerHTML='<span class="muted">No workspace files yet.</span>';else for(const e of workspace)work.appendChild(fileManagerRow(e,false))}catch(e){built.innerHTML=work.innerHTML=`<span class="muted">${e.message}</span>`}}
async function loadBuildProfiles(){const editor=$('#build-profile-editor');if(!editor)return;try{const out=await api('/api/build-profiles');editor.value=out.content}catch(e){editor.value=`# ${e.message}`}}
async function saveBuildProfiles(){try{const out=await api('/api/build-profiles',{method:'PUT',body:JSON.stringify({content:$('#build-profile-editor').value})});$('#build-profile-editor').value=out.content;log('Build profiles saved.')}catch(e){alert(e.message)}}
function confirmAction(title,message,confirmText='Confirm'){if(confirmResolver)confirmResolver(false);$('#action-confirm-title').textContent=title;$('#action-confirm-text').textContent=message;$('#action-confirm-ok').textContent=confirmText;$('#action-confirm-modal').hidden=false;return new Promise(resolve=>{confirmResolver=resolve})}
function resolveActionConfirm(value){$('#action-confirm-modal').hidden=true;const resolve=confirmResolver;confirmResolver=null;if(resolve)resolve(value)}
function setLlBusy(mode=null){llUiBusy=mode;renderRunnerButtons()}
function renderRunnerButtons(){const runnable=!!activeExample;const status=activeRunnerStatus||{built:false,running:false};const build=$('#build-source'),run=$('#run-source'),stop=$('#stop-source');build.textContent=llUiBusy==='building'?'Building...':status.built?'Rebuild':'Build';build.disabled=!runnable||!!llUiBusy||status.running;run.textContent=llUiBusy==='switching'?'Switching...':(llUiBusy==='running'||status.running)?'Running...':'Run';run.disabled=!runnable||!status.built||!simulationStatus?.running||!!llUiBusy||status.running;stop.disabled=!(status.running||llUiBusy==='running');for(const b of [build,run])b.classList.toggle('btn-busy',!!llUiBusy)}
async function refreshRunnerStatus(){if(!activeExample){activeRunnerStatus=null;renderRunnerButtons();return}const r=currentRobot();if(!r)return;try{const status=await api(`/api/runner/${r.id}/status?path=${encodeURIComponent(activeExample.path)}&builtin=${activeExample.builtin?'true':'false'}`);activeRunnerStatus=status;if(llUiBusy==='running'&&!status.running)llUiBusy=null;renderRunnerButtons()}catch(e){/* source may be changing */}}
async function buildSource(){if(!activeExample)return;await refreshRunnerStatus();if(activeRunnerStatus?.built){const ok=await confirmAction('Rebuild executable?',`Rebuild ${activeExample.path}?\n\nThe existing executable will be replaced if compilation succeeds.`,'Rebuild');if(!ok)return}setLlBusy('building');try{if(!activeExample.builtin)await saveSource();const r=currentRobot();const out=await api(`/api/runner/${r.id}/build`,{method:'POST',body:JSON.stringify({path:activeExample.path,interface:'lo',builtin:activeExample.builtin})});terminalBuffers.build=[];appendTerminal('build',out.output||`Build ${out.ok?'successful':'failed'}`);log(`Build ${out.ok?'successful':'failed'}: ${activeExample.path}`,out.ok?'INFO':'ERROR');await refreshRunnerStatus()}catch(e){log(e.message,'ERROR')}finally{if(llUiBusy==='building')setLlBusy(null)}}
async function runSource(){if(!activeExample)return;await refreshRunnerStatus();if(!activeRunnerStatus?.built){log('Build the program before running it.','WARN');return}const r=currentRobot();const ok=await confirmAction('Run Low-Level Program?',`Robot: ${r.display_name}\nProgram: ${activeExample.path}${activeExample.builtin?' (SDK read-only)':''}\nInterface: lo\nControl owner: ${state?.control_owner||'unknown'}\n\nRobot Web Lab will switch to LL Debug if required.`,'Run');if(!ok)return;try{if(state?.control_owner!=='low'){setLlBusy('switching');stopVelocityKeyboardLoop(true);state=await api('/api/control/ll-prepare',{method:'POST'});renderState(state)}setLlBusy('running');const out=await api(`/api/runner/${r.id}/run`,{method:'POST',body:JSON.stringify({path:activeExample.path,interface:'lo',builtin:activeExample.builtin})});activeRunnerStatus={...(activeRunnerStatus||{}),built:true,running:true,pid:out.pid,path:activeExample.path};renderRunnerButtons();log(`LL program started (PID ${out.pid})`)}catch(e){setLlBusy(null);log(e.message,'ERROR');await refreshRunnerStatus()}}
async function stopSource(){try{const out=await api('/api/runner/stop',{method:'POST'});if(out.stopped)log('LL program stopped.');llUiBusy=null;await refreshRunnerStatus()}catch(e){log(e.message,'ERROR')}}
async function enterLL(){stopVelocityKeyboardLoop(true);setLlBusy('switching');try{state=await api('/api/control/ll-prepare',{method:'POST'});renderState(state)}catch(e){log(e.message,'WARN')}finally{if(llUiBusy==='switching')setLlBusy(null)}}
async function returnPassive(){stopVelocityKeyboardLoop(true);try{await api('/api/runner/stop',{method:'POST'});llUiBusy=null;state=await api('/api/control/passive',{method:'POST'});renderState(state);await refreshRunnerStatus()}catch(e){log(e.message,'WARN')}}



function initSplitters(){
  const ws=$('#workspace'); if(!ws)return;
  const keys={left:'rwl-v010-ll-examples-width',right:'rwl-v010-ll-editor-width',terminal:'rwl-v010-ll-terminal-height'};
  const save=()=>{localStorage.setItem(keys.left,getComputedStyle(ws).getPropertyValue('--ll-examples-width').trim());localStorage.setItem(keys.right,getComputedStyle(ws).getPropertyValue('--ll-editor-width').trim());localStorage.setItem(keys.terminal,getComputedStyle(ws).getPropertyValue('--ll-terminal-height').trim())};
  const savedLeft=localStorage.getItem(keys.left),savedRight=localStorage.getItem(keys.right),savedTerminal=localStorage.getItem(keys.terminal);
  if(savedLeft)ws.style.setProperty('--ll-examples-width',savedLeft);if(savedRight)ws.style.setProperty('--ll-editor-width',savedRight);if(savedTerminal)ws.style.setProperty('--ll-terminal-height',savedTerminal);
  const bindVertical=(selector,side)=>{const bar=$(selector);if(!bar)return;bar.addEventListener('pointerdown',e=>{if(!ws.classList.contains('mode-low'))return;e.preventDefault();bar.classList.add('dragging');bar.setPointerCapture(e.pointerId);const move=ev=>{const rect=ws.getBoundingClientRect();if(side==='left'){const width=Math.max(180,Math.min(390,ev.clientX-rect.left));ws.style.setProperty('--ll-examples-width',`${width}px`)}else{const width=Math.max(520,Math.min(1100,rect.right-ev.clientX));ws.style.setProperty('--ll-editor-width',`${width}px`)}};const up=()=>{bar.classList.remove('dragging');bar.removeEventListener('pointermove',move);bar.removeEventListener('pointerup',up);save();view?.resize()};bar.addEventListener('pointermove',move);bar.addEventListener('pointerup',up)})};
  const bindHorizontal=(selector)=>{const bar=$(selector);if(!bar)return;bar.addEventListener('pointerdown',e=>{if(!ws.classList.contains('mode-low'))return;e.preventDefault();bar.classList.add('dragging');bar.setPointerCapture(e.pointerId);const move=ev=>{const rect=ws.getBoundingClientRect();const height=Math.max(180,Math.min(460,rect.bottom-ev.clientY));ws.style.setProperty('--ll-terminal-height',`${height}px`)};const up=()=>{bar.classList.remove('dragging');bar.removeEventListener('pointermove',move);bar.removeEventListener('pointerup',up);save();view?.resize()};bar.addEventListener('pointermove',move);bar.addEventListener('pointerup',up)})};
  bindVertical('#ll-left-splitter','left');bindVertical('#ll-right-splitter','right');bindHorizontal('#ll-terminal-splitter');
}
function toggleEditorFocus(){const ws=$('#workspace');const on=ws.classList.toggle('editor-focus');if(on)ws.classList.remove('editor-maximized');$('#editor-focus').textContent=on?'Exit Focus':'Focus Code';$('#editor-maximize').textContent='Max Code';view?.resize()}
function toggleEditorMaximize(){const ws=$('#workspace');const on=ws.classList.toggle('editor-maximized');if(on)ws.classList.remove('editor-focus');$('#editor-maximize').textContent=on?'Restore':'Max Code';$('#editor-focus').textContent='Focus Code';view?.resize()}
function connectWs(){const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);ws.onopen=()=>{wsConnected=true;refreshDiagnosticBuffers();log('WebSocket connected.')};ws.onmessage=e=>{const ev=JSON.parse(e.data);if(ev.type==='state')renderState(ev.data)};ws.onclose=()=>{wsConnected=false;refreshDiagnosticBuffers();stopVelocityKeyboardLoop(true);log('WebSocket disconnected; reconnecting…','WARN');setTimeout(connectWs,1800)}}
function restorePanels(){$$('details[data-collapsible]').forEach((d,i)=>{const key=`rwl-v010-panel:${d.closest('.page-view')?.id||'global'}:${i}`;const saved=localStorage.getItem(key);if(saved!==null)d.open=saved==='1';d.addEventListener('toggle',()=>localStorage.setItem(key,d.open?'1':'0'))})}
function initExclusiveAccordion(){const items=$$('details[data-exclusive-group="hl"]');let guard=false;items.forEach(d=>d.addEventListener('toggle',()=>{if(guard||!d.open)return;guard=true;for(const other of items)if(other!==d)other.open=false;guard=false}));const opened=items.filter(d=>d.open);opened.slice(1).forEach(d=>d.open=false)}

// Events
$('#save-layout-top').onclick=()=>{localStorage.setItem('rwl-v010-layout-saved-at',new Date().toISOString());log('Layout saved in this browser.');};
$('#robot-select').addEventListener('change',e=>chooseRobot(e.target.value));$('#level-high').onclick=()=>switchLevel('high');$('#level-low').onclick=()=>switchLevel('low');
$$('.rail-item').forEach(b=>b.onclick=()=>showPage(b.dataset.page));$('#setup-button').onclick=()=>showPage('robots');$('#theme-toggle').onclick=()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');$$('[data-set-theme]').forEach(b=>b.onclick=()=>setTheme(b.dataset.setTheme));
$('#global-pack-high')?.addEventListener('change',e=>syncGlobalPack('highLevel',e.target.checked));$('#global-pack-low')?.addEventListener('change',e=>syncGlobalPack('lowLevel',e.target.checked));$('#view-build-details')?.addEventListener('click',()=>{$('#first-build-progress').open=true;$('#first-build-progress').scrollIntoView({behavior:'smooth',block:'nearest'})});$('#skip-first-run')?.addEventListener('click',()=>showPage('robots'));
$('#build-selected').onclick=startBuild;const managerBuild=$('#manager-build-selected');if(managerBuild)managerBuild.onclick=startBuild;const managerRebuild=$('#manager-rebuild-selected');if(managerRebuild)managerRebuild.onclick=startBuild;$('#cancel-build').onclick=cancelBuild;$('#robots-refresh').onclick=refreshBuildStatus;$('#robot-installation-guide')?.addEventListener('click',()=>alert(`Robot build flow:

1. Select one or more robot cards.
2. Review available High-Level / Low-Level packages.
3. Click Build Selected.
4. Watch Build Queue and Installed Robots below.`));$('#robot-manager-collapse-cards')?.addEventListener('click',e=>{const panel=$('.available-robots-card');const collapsed=panel?.classList.toggle('cards-collapsed');e.currentTarget.textContent=collapsed?'⌄':'⌃'});
$$('[data-fsm]').forEach(b=>b.onclick=()=>setFsm(b.dataset.fsm));$$('[data-run-policy]').forEach(b=>b.onclick=()=>runPolicy(b.dataset.runPolicy));
['vx','vy','yaw'].forEach(k=>$(`#velocity-${k}`).addEventListener('input',sendVelocity));$$('[data-hanger]').forEach(b=>b.onclick=()=>hanger(b.dataset.hanger));
$('#reset-camera').onclick=()=>view?.resetCamera();$('#follow-camera').onclick=()=>{followCameraEnabled=!followCameraEnabled;view?.setFollowEnabled(followCameraEnabled);$('#follow-camera').classList.toggle('active',followCameraEnabled);$('#follow-camera').textContent=followCameraEnabled?'◎ Following':'◎ Follow'};$('#grid-toggle').onclick=()=>view?.toggleGrid();$('#screenshot-button').onclick=()=>{const a=document.createElement('a');a.href=view?.screenshot()||'';a.download='robot-web-lab.png';a.click()};$('#fullscreen-button').onclick=()=>$('#simulation-viewport').requestFullscreen?.();
$('#mimic-drop-zone').onclick=()=>$('#mimic-file-input').click();$('#mimic-file-input').onchange=e=>uploadPolicies([...e.target.files]);for(const id of ['#mimic-drop-zone','#asset-drop-zone']){const z=$(id);z.addEventListener('dragover',e=>{e.preventDefault();z.classList.add('dragging')});z.addEventListener('dragleave',()=>z.classList.remove('dragging'));z.addEventListener('drop',e=>{e.preventDefault();z.classList.remove('dragging');uploadPolicies([...e.dataTransfer.files])})}
document.addEventListener('click',e=>{const b=e.target.closest('[data-key-action]');if(b)captureKeyForAction(b.dataset.keyAction,b)});
document.addEventListener('keydown',e=>{
  if(pendingKey){e.preventDefault();const {action,button}=pendingKey;pendingKey=null;button.classList.remove('capturing');remap(action,e.key);return}
  const globalModeShortcut=e.ctrlKey&&(e.key==='0'||e.key==='1');
  if(globalModeShortcut&&!e.altKey&&!e.metaKey){e.preventDefault();if(e.repeat)return;if(e.key==='0')switchLevel('low');else switchLevel('high');return}
  if(e.target.matches('textarea,input,select'))return;
  const action=actionForKeyboardEvent(e);if(!action)return;
  if(handleVelocityKeyDown(action,e))return;
  if(e.repeat)return;
  if(action==='passive')returnPassive();else if(action==='fix_stand')setFsm('FixStand');else if(action==='velocity')setFsm('Velocity');else if(action==='dance_default')runPolicy('dance1_subject2');else if(action==='enter_ll_debug')switchLevel('low');else if(action==='reset')api('/api/control/reset',{method:'POST'}).then(renderState).catch(e=>log(e.message,'ERROR'));else if(action.startsWith('hanger_'))hanger(action.replace('hanger_',''));
});
document.addEventListener('keyup',e=>{if(e.target.matches('textarea,input,select'))return;const action=actionForKeyboardEvent(e);if(action)handleVelocityKeyUp(action,e)});
window.addEventListener('blur',()=>stopVelocityKeyboardLoop(true));
$$('[data-conflict]').forEach(b=>b.onclick=()=>resolveKeyConflict(b.dataset.conflict));$$('[data-expand-all]').forEach(b=>b.onclick=()=>$$('details[data-collapsible]',$(b.dataset.expandAll)).forEach(d=>d.open=true));$$('[data-collapse-all]').forEach(b=>b.onclick=()=>$$('details[data-collapsible]',$(b.dataset.collapseAll)).forEach(d=>d.open=false));
$('#copy-example').onclick=copyExampleToWorkspace;$('#save-source').onclick=saveSource;$('#build-source').onclick=buildSource;$('#run-source').onclick=runSource;$('#stop-source').onclick=stopSource;$$('[data-terminal-tab]').forEach(b=>b.onclick=()=>selectTerminalTab(b.dataset.terminalTab));$('#terminal-clear').onclick=()=>{terminalBuffers[terminalActive]=[];renderTerminal()};
$('#action-confirm-cancel').onclick=()=>resolveActionConfirm(false);$('#action-confirm-ok').onclick=()=>resolveActionConfirm(true);
$$('[data-scripts-section]').forEach(b=>b.onclick=()=>selectScriptsSection(b.dataset.scriptsSection));$('#reload-build-profiles')?.addEventListener('click',loadBuildProfiles);$('#save-build-profiles')?.addEventListener('click',saveBuildProfiles);$('#scripts-new-file')?.addEventListener('click',()=>$('#new-example-modal').hidden=false);$$('[data-settings-section]').forEach(b=>b.onclick=()=>selectSettingsSection(b.dataset.settingsSection));$$('[data-settings-action="open-robots"]').forEach(b=>b.onclick=()=>showPage('robots'));$('#reset-saved-layout')?.addEventListener('click',()=>{for(const key of Object.keys(localStorage))if(key.startsWith('rwl-v010-'))localStorage.removeItem(key);location.reload()});
const keyboardFocus=$('#keyboard-focus-state'),codeEditor=$('#code-editor');const updateEditorKeyHint=()=>{const focused=document.activeElement===codeEditor;keyboardFocus.classList.toggle('paused',focused);keyboardFocus.textContent=focused?'Robot shortcuts paused while typing · Ctrl+0 Low Level · Ctrl+1 High Level':'Robot keys active · Ctrl+0 Low Level · Ctrl+1 High Level'};codeEditor.addEventListener('focus',updateEditorKeyHint);codeEditor.addEventListener('blur',updateEditorKeyHint);
$('#new-example').onclick=()=>$('#new-example-modal').hidden=false;$$('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).hidden=true);$('#create-example').onclick=async()=>{const r=currentRobot();try{const out=await api(`/api/workspace/${r.id}/new`,{method:'POST',body:JSON.stringify({name:$('#new-example-name').value,language:$('#new-example-language').value,template:$('#new-example-template').value})});$('#new-example-modal').hidden=true;await refreshExamples();await refreshScriptsFiles();if(activePage!=='scripts')await openExample(out.path,false)}catch(e){alert(e.message)}};
$('#example-search').addEventListener('input',e=>$$('.example-item').forEach(x=>x.hidden=!x.textContent.toLowerCase().includes(e.target.value.toLowerCase())));
$('#start-simulation').onclick=toggleSimulation;$('#editor-focus').onclick=toggleEditorFocus;$('#editor-maximize').onclick=toggleEditorMaximize;initSplitters();

boot().catch(e=>{console.error(e);log(e.stack||e.message,'ERROR')});
