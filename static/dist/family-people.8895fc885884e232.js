/* A family tree is another view of the same authorized people. */
(function(){
 const params=new URLSearchParams(location.search),body=document.body;
 const key='memoir.people-view.v1.'+body.dataset.userId+'.'+body.dataset.familyId;
 try {
  if(params.has('view'))localStorage.setItem(key,params.get('view'));
  else if(!params.has('q') && localStorage.getItem(key)==='tree'){
   const target=new URL(location.href);target.searchParams.set('view','tree');location.replace(target.href);return;
  }
 }catch(e){}
 const holder=document.getElementById('tree'),data=document.getElementById('family-tree-data');
 if(!holder||!data)return;
 const status=document.getElementById('tree-status'),reset=document.getElementById('tree-reset'),expand=document.getElementById('tree-expand');
 const tools=document.getElementById('tree-view-tools'),zoomIn=tools.querySelector('[data-tree-action=zoom-in]'),zoomOut=tools.querySelector('[data-tree-action=zoom-out]'),move=tools.querySelector('[data-tree-action=move]');
 const zoomLabel=document.getElementById('tree-zoom');
 const section=document.getElementById('family-tree'),fullscreen=tools.querySelector('[data-tree-action=fullscreen]');
 let chart,cardRenderer,collapsed,moving=false,full=false,fullscreenBusy=false,returnScroll=null;
 function fullState(active){
  if(active===full)return;
  full=active;if(active)returnScroll=[window.scrollX,window.scrollY];
  section.classList.toggle('tree-fullscreen',active);body.classList.toggle('tree-fullscreen-open',active);
  fullscreen.setAttribute('aria-pressed',String(active));fullscreen.setAttribute('aria-label',active?'退出家族树全屏':'全屏查看家族树');fullscreen.querySelector('span').textContent=active?'退出全屏':'全屏';fullscreen.title=fullscreen.getAttribute('aria-label');
  if(active){section.setAttribute('role','dialog');section.setAttribute('aria-modal','true');section.setAttribute('aria-label','家族树全屏查看');}
  else{section.removeAttribute('role');section.removeAttribute('aria-modal');section.removeAttribute('aria-label');}
  requestAnimationFrame(()=>{draw(true);fullscreen.focus({preventScroll:true});if(!active&&returnScroll)window.scrollTo(...returnScroll);});
 }
 async function toggleFullscreen(){
  if(fullscreenBusy)return;fullscreenBusy=true;fullscreen.disabled=true;
  try{
   if(full){if(document.fullscreenElement===section)await document.exitFullscreen();fullState(false);}
   else{fullState(true);if(section.requestFullscreen){try{await section.requestFullscreen();}catch(e){/* Keep the page-filling fallback. */}}}
  }catch(e){status.textContent='请使用退出全屏按钮，或按 Esc 返回。';}
  finally{fullscreenBusy=false;fullscreen.disabled=false;}
 }
 document.addEventListener('fullscreenchange',()=>{if(document.fullscreenElement===section)fullState(true);else if(full)fullState(false);});
 document.addEventListener('keydown',event=>{
  if(!full)return;
  if(event.key==='Escape'&&document.fullscreenElement!==section){event.preventDefault();fullState(false);return;}
  if(event.key==='Tab'){
   const nodes=[...section.querySelectorAll('button,a[href],select,input,textarea,[tabindex]')].filter(n=>!n.disabled&&n.tabIndex>=0&&n.getClientRects().length);
   const first=nodes[0],last=nodes[nodes.length-1];
   if(!section.contains(document.activeElement)||(event.shiftKey&&document.activeElement===first)){event.preventDefault();last?.focus();}
   else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  }
 });
 function toolState(){
  const zoom=chart?f3.handlers.getCurrentZoom(chart.svg).k:1;
  zoomIn.disabled=zoom>=4-.001;zoomOut.disabled=zoom<=(chart?chart.zoom.scaleExtent()[0]:.25)+.00001;
  zoomLabel.textContent=(zoom<.1?(zoom*100).toFixed(1):Math.round(zoom*100))+'%';
  move.querySelector('[data-tree-move-label]').textContent=moving?'停止移动':'移动';move.title=moving?'停止移动，恢复查看人物':'移动家族树';
  move.setAttribute('aria-pressed',String(moving));move.className=moving?'btn-primary':'btn-secondary';holder.classList.toggle('tree-moving',moving);
 }
 function fallback(){
  holder.hidden=true;reset.hidden=true;expand.hidden=true;tools.hidden=true;
  status.textContent='家族树暂时无法显示，请使用下方人物名单。';
 }
 const escapeHtml=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function activate(event,d){
  if(moving||event.defaultPrevented)return;
  const node=d.data.person;
  if(node.toggle){
   if(collapsed.has(node.toggle))collapsed.delete(node.toggle);else collapsed.add(node.toggle);
   draw();[...holder.querySelectorAll('[data-branch-id]')].find(card=>card.dataset.branchId===node.toggle)?.focus({preventScroll:true});return;
  }
  if(!node.person_id)return;
  const target=new URL('/f/'+encodeURIComponent(body.dataset.familyId)+'/person/'+encodeURIComponent(node.person_id),location.origin);
  target.searchParams.set('return_to',location.pathname+location.search);location.assign(target.href);
 }
 function initialize(){
  chart=f3.htmlHandlers.default(holder);
  const listener=chart.svg.__zoomObj?chart.svg:chart.svg.parentNode;
  chart.listener=listener;chart.zoom=listener.__zoomObj;
  chart.zoom.scaleExtent([.25,4]).filter(event=>{
   if(event.type==='dblclick')return false;
   if(event.touches)return moving||event.touches.length>1;
   return !event.button;
  }).on('zoom.memoir',toolState);
  cardRenderer=f3.elements.CardHtml({mini_tree:false,card_dim:{},onCardClick:activate,
   cardInnerHtmlCreator:d=>{
    const node=d.data.person;
    if(node.toggle)return '<span class="tree-branch-label">'+escapeHtml(node.name)+'</span>';
    const lines=node.name.split('\n');
    return '<span class="tree-person-icon" aria-hidden="true"><svg viewBox="0 0 32 34"><path d="M16 2a6 6 0 1 0 0 12a6 6 0 0 0 0-12ZM4 32v-4a12 12 0 0 1 24 0v4Z"/></svg></span><strong class="tree-person-name">'+escapeHtml(lines[0])+'</strong><span class="tree-person-dates">'+lines.slice(1).map(escapeHtml).join('<br>')+'</span>';
   },onCardUpdate:function(d){
    const node=d.data.person,card=this.querySelector('.card');
    card.classList.add(node.toggle?'tree-branch-card':'tree-person-card');
    card.setAttribute('role','button');card.tabIndex=0;card.setAttribute('aria-label',node.name.replaceAll('\n','，'));
    if(node.toggle){card.dataset.branchId=node.toggle;card.setAttribute('aria-expanded',String(!collapsed.has(node.toggle)));}
    else{card.dataset.personId=node.person_id;const color=node.itemStyle?.color;if(/^#[0-9a-f]{6}$/i.test(color))card.style.setProperty('--tree-person-color',color);}
    card.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();activate({defaultPrevented:false},d);}});
   }
  });
 }
 function setTransform(transform){d3.select(chart.listener).call(chart.zoom.transform,transform);}
 function draw(preserveView=false,fitAll=false){
  try{
   if(!window.f3||!window.d3||!window.familyTreeLayout||!window.familyChartTree){fallback();return;}
   holder.hidden=false;
   const previous=preserveView===true&&chart?f3.handlers.getCurrentZoom(chart.svg):null;
   if(!chart)initialize();
   const fontSize=Math.max(18,Number(document.documentElement.dataset.size)||18);
   const layout=familyTreeLayout(JSON.parse(data.textContent),fontSize,collapsed,holder.clientWidth,{cards:true});collapsed=layout.collapsed;
   holder.style.minHeight=Math.max(480,Math.min(720,layout.cardHeight+layout.rowHeight+80))+'px';
   holder.style.setProperty('--tree-card-width',layout.cardWidth+'px');holder.style.setProperty('--tree-card-height',layout.cardHeight+'px');
   holder.style.setProperty('--tree-font-size',fontSize+'px');
   const tree=familyChartTree(layout);
   f3.view(tree,chart.svg,cardRenderer,{cardHtml:true,initial:false,tree_position:'inherit',transition_time:0});
   d3.timerFlush();
   d3.select(chart.svg).selectAll('path.link').each(function(link){
    this.dataset.relation=link.spouse?'spouse':'parent';
    this.style.strokeDasharray=!link.spouse&&link.source.unresolvedParent?'6 4':'';
   });
   if(previous)setTransform(previous);
   else if(fitAll){
    const k=Math.min(1,Math.max(1,holder.clientWidth-24)/tree.dim.width,Math.max(1,holder.clientHeight-24)/tree.dim.height);
    chart.zoom.scaleExtent([Math.min(.25,k),4]);
    setTransform(d3.zoomIdentity.translate((holder.clientWidth-tree.dim.width*k)/2+tree.dim.x_off*k,(holder.clientHeight-tree.dim.height*k)/2+tree.dim.y_off*k).scale(k));
   }
   else{
    chart.zoom.scaleExtent([.25,4]);
    // Keep labels readable; large forests can be explored by dragging and zooming.
    const k=Math.max(.6,Math.min(1,holder.clientWidth/tree.dim.width,holder.clientHeight/tree.dim.height));
    const x=(holder.clientWidth-tree.dim.width*k)/2+tree.dim.x_off*k;
    setTransform(d3.zoomIdentity.translate(x,tree.dim.y_off*k+20).scale(k));
   }
   reset.hidden=false;expand.hidden=false;tools.hidden=false;toolState();
   status.textContent=layout.unresolved?'部分上级关系存在循环，请核对；人物均已保留，可使用下方名单查找。':moving?'移动中：拖动查看，点“停止移动”后可查看人物。':fitAll?'已展开全部人物并显示全图；字太小时可点“放大”。':'点击人物看详情；点“移动”可拖动，点“查看全图”可找回整棵树。';
  }catch(e){fallback();}
 }
 tools.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!chart||!button||!tools.contains(button))return;
  if(button.dataset.treeAction==='fullscreen'){toggleFullscreen();return;}
  if(button.dataset.treeAction==='fit'){collapsed=new Set();moving=false;draw(false,true);return;}
  if(button.dataset.treeAction==='move'){
   moving=!moving;toolState();
   status.textContent=moving?'移动中：按住鼠标或用一根手指拖动；点“停止移动”后可查看人物。':'点击人物查看详情；可用放大、缩小和移动按钮调整视图。';return;
  }
  const zoom=f3.handlers.getCurrentZoom(chart.svg).k,target=Math.max(chart.zoom.scaleExtent()[0],Math.min(4,zoom*(button.dataset.treeAction==='zoom-in'?1.25:.8)));
  d3.select(chart.listener).call(chart.zoom.scaleTo,target);toolState();
 });
 reset.addEventListener('click',()=>{collapsed=undefined;moving=false;draw();});
 expand.addEventListener('click',()=>{collapsed=new Set();draw();});
 window.addEventListener('resize',()=>draw(true));document.addEventListener('memoir:display-change',draw);draw();
})();
