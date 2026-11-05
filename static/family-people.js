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
 let chart,collapsed;
 function fallback(){
  holder.hidden=true;reset.hidden=true;expand.hidden=true;
  status.textContent='家族树暂时无法显示，请使用下方人物名单。';
 }
 function draw(){
  try{
   if(!window.echarts||!window.familyTreeLayout){fallback();return;}
   holder.hidden=false;
   if(!chart){
    chart=echarts.init(holder);
    chart.on('click',function(event){
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
   const style=getComputedStyle(document.documentElement),fontSize=Math.max(18,Number(document.documentElement.dataset.size)||18);
   const layout=familyTreeLayout(JSON.parse(data.textContent),fontSize,collapsed);collapsed=layout.collapsed;
   chart.resize();
   const bounds=[{id:'extent:start',x:0,y:0},{id:'extent:end',x:layout.width,y:layout.height}].map(n=>({...n,symbolSize:0,silent:true,label:{show:false},tooltip:{show:false},itemStyle:{opacity:0}}));
   chart.setOption({tooltip:{trigger:'item',renderMode:'richText',formatter:event=>event.dataType==='edge'?(event.data.kind==='spouse'?'配偶关系':'已记录的上级关系'):event.name},series:[{
    type:'graph',layout:'none',data:[...layout.nodes,...bounds],links:layout.links,roam:true,
    // Explicit extents keep one layout unit equal to one pixel on every viewport.
    left:(holder.clientWidth-layout.width)/2,top:Math.max(100,fontSize*5),width:layout.width,height:layout.height,
    zoom:1,nodeScaleRatio:0,edgeSymbolSize:8,
    label:{show:true,position:'top',align:'center',verticalAlign:'bottom',width:Math.max(160,fontSize*7),overflow:'break',distance:10,lineHeight:fontSize+4,fontSize,color:style.getPropertyValue('--ink').trim(),fontFamily:style.getPropertyValue('--font-ui').trim()},
    lineStyle:{color:style.getPropertyValue('--muted').trim(),opacity:1},
    animation:false
   }]},true);
   reset.hidden=false;expand.hidden=false;
   status.textContent=layout.unresolved?'部分上级关系存在循环，请核对；人物均已保留，可使用下方名单查找。':'配偶同层并排；点击人物查看详情，点击分支按钮展开或收起。';
  }catch(e){fallback();}
 }
 reset.addEventListener('click',()=>{collapsed=undefined;draw();});
 expand.addEventListener('click',()=>{collapsed=new Set();draw();});
 window.addEventListener('resize',draw);document.addEventListener('memoir:display-change',draw);draw();
})();
