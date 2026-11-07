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
 const section=document.getElementById('family-tree'),fullscreen=tools.querySelector('[data-tree-action=fullscreen]');
 let chart,collapsed,moving=false,full=false,fullscreenBusy=false,returnScroll=null;
 function fullState(active){
  if(active===full)return;
  full=active;if(active)returnScroll=[window.scrollX,window.scrollY];
  section.classList.toggle('tree-fullscreen',active);body.classList.toggle('tree-fullscreen-open',active);
  fullscreen.setAttribute('aria-pressed',String(active));fullscreen.setAttribute('aria-label',active?'退出家族树全屏':'全屏查看家族树');fullscreen.querySelector('span').textContent=active?'退出全屏':'全屏';
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
  const zoom=chart?Number(chart.getOption().series[0].zoom)||1:1;
  zoomIn.disabled=zoom>=4-.001;zoomOut.disabled=zoom<=.25+.001;
  move.setAttribute('aria-pressed',String(moving));move.className=moving?'btn-primary':'btn-secondary';holder.classList.toggle('tree-moving',moving);
 }
 function fallback(){
  holder.hidden=true;reset.hidden=true;expand.hidden=true;tools.hidden=true;
  status.textContent='家族树暂时无法显示，请使用下方人物名单。';
 }
 function draw(preserveView=false){
  try{
   if(!window.echarts||!window.familyTreeLayout){fallback();return;}
   holder.hidden=false;
   if(!chart){
    chart=echarts.init(holder);
    chart.on('graphRoam',toolState);
    chart.on('click',function(event){
     if(moving)return;
     if(event.dataType!=='node'||!event.data)return;
     if(event.data.toggle){
      if(collapsed.has(event.data.toggle))collapsed.delete(event.data.toggle);else collapsed.add(event.data.toggle);
      draw();return;
     }
     if(!event.data.person_id)return;
     const target=new URL('/f/'+encodeURIComponent(body.dataset.familyId)+'/person/'+encodeURIComponent(event.data.person_id),location.origin);
     target.searchParams.set('return_to',location.pathname+location.search);location.assign(target.href);
    });
   }
   const previous=preserveView===true&&chart?chart.getOption().series?.[0]:null;
   const style=getComputedStyle(document.documentElement),fontSize=Math.max(18,Number(document.documentElement.dataset.size)||18);
   const layout=familyTreeLayout(JSON.parse(data.textContent),fontSize,collapsed,holder.clientWidth);collapsed=layout.collapsed;
   holder.style.minHeight=Math.max(480,Math.min(720,layout.labelHeight+36+layout.rowHeight+90))+'px';
   chart.resize();
   const bounds=[{id:'extent:start',x:0,y:0},{id:'extent:end',x:layout.width,y:layout.height}].map(n=>({...n,symbolSize:0,silent:true,label:{show:false},tooltip:{show:false},itemStyle:{opacity:0}}));
   chart.setOption({tooltip:{trigger:'item',renderMode:'richText',formatter:event=>event.dataType==='edge'?(event.data.kind==='spouse'?'配偶关系':'已记录的上级关系'):event.name},series:[{
    type:'graph',layout:'none',data:[...layout.nodes,...bounds],links:layout.links,roam:moving?'move':true,scaleLimit:{min:.25,max:4},
    // Explicit extents keep one layout unit equal to one pixel on every viewport.
    left:(holder.clientWidth-layout.width)/2,top:Math.max(100,layout.labelHeight+36),width:layout.width,height:layout.height,
    zoom:previous?.zoom||1,center:previous?.center||null,nodeScaleRatio:0,edgeSymbolSize:8,
    label:{show:true,formatter:params=>params.data.display_name||params.name,position:'top',align:'center',verticalAlign:'bottom',width:layout.labelWidth,overflow:'none',distance:10,lineHeight:fontSize+4,fontSize,color:style.getPropertyValue('--ink').trim(),fontFamily:style.getPropertyValue('--font-ui').trim()},
    lineStyle:{color:style.getPropertyValue('--muted').trim(),opacity:1},
    animation:false
   }]},true);
   reset.hidden=false;expand.hidden=false;tools.hidden=false;toolState();
   status.textContent=layout.unresolved?'部分上级关系存在循环，请核对；人物均已保留，可使用下方名单查找。':'配偶同层并排；点击人物查看详情，点击分支按钮展开或收起。';
  }catch(e){fallback();}
 }
 tools.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!chart||!button||!tools.contains(button))return;
  if(button.dataset.treeAction==='fullscreen'){toggleFullscreen();return;}
  if(button.dataset.treeAction==='move'){
   moving=!moving;chart.setOption({series:[{roam:moving?'move':true}]});toolState();
   status.textContent=moving?'移动模式：拖动家族树查看；再次点击移动，可恢复点击人物详情。':'点击人物查看详情；可用放大、缩小和移动按钮调整视图。';return;
  }
  const zoom=Number(chart.getOption().series[0].zoom)||1,target=Math.max(.25,Math.min(4,zoom*(button.dataset.treeAction==='zoom-in'?1.25:.8)));
  chart.dispatchAction({type:'graphRoam',seriesIndex:0,zoom:target/zoom,originX:chart.getWidth()/2,originY:chart.getHeight()/2});toolState();
 });
 reset.addEventListener('click',()=>{collapsed=undefined;moving=false;draw();});
 expand.addEventListener('click',()=>{collapsed=new Set();draw();});
 window.addEventListener('resize',()=>draw(true));document.addEventListener('memoir:display-change',draw);draw();
})();
