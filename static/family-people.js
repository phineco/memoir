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
 const status=document.getElementById('tree-status'),reset=document.getElementById('tree-reset');
 let chart;
 function fallback(){
  holder.hidden=true;reset.hidden=true;
  status.textContent='家族树暂时无法显示，请使用下方人物名单。';
 }
 function draw(){
  try{
   if(!window.echarts){fallback();return;}
   holder.hidden=false;
   if(!chart){
    chart=echarts.init(holder);
    chart.on('click',function(event){
     if(!event.data||!event.data.person_id)return;
     const target=new URL('/f/'+encodeURIComponent(body.dataset.familyId)+'/person/'+encodeURIComponent(event.data.person_id),location.origin);
     target.searchParams.set('return_to',location.pathname+location.search);location.assign(target.href);
    });
   }
   const style=getComputedStyle(document.documentElement);
   chart.setOption({tooltip:{trigger:'item',renderMode:'richText'},series:[{
    type:'tree',data:[JSON.parse(data.textContent)],orient:'TB',top:'28%',bottom:'12%',left:'22%',right:'22%',
    symbolSize:16,roam:true,expandAndCollapse:true,initialTreeDepth:3,
    label:{position:'top',align:'center',verticalAlign:'bottom',width:160,overflow:'break',distance:10,fontSize:Math.max(18,Number(document.documentElement.dataset.size)||18),color:style.getPropertyValue('--ink').trim(),fontFamily:style.getPropertyValue('--font-ui').trim()},
    lineStyle:{color:style.getPropertyValue('--muted').trim()},
    animation:!matchMedia('(prefers-reduced-motion: reduce)').matches
   }]},true);
   chart.resize();reset.hidden=false;status.textContent='家族树与下方名单均可进入人物详情。';
  }catch(e){fallback();}
 }
 reset.addEventListener('click',draw);window.addEventListener('resize',()=>{if(chart)chart.resize();});
 document.addEventListener('memoir:display-change',draw);draw();
})();
