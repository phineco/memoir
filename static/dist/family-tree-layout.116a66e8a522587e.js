/* Pure display layout: spouse units never rewrite recorded ancestry. */
(function(root,factory){
 if(typeof module==='object' && module.exports)module.exports=factory;
 else root.familyTreeLayout=factory;
})(typeof window==='undefined'?globalThis:window,function(tree,fontSize,collapsed,viewportWidth,options={}){
 // A validated avatar symbol can replace this shared person silhouette later.
 const personSymbol='path://M16 2a6 6 0 1 0 0 12a6 6 0 0 0 0-12ZM4 32v-4a12 12 0 0 1 24 0v4Z';
 const people=[],stack=[tree];
 while(stack.length){const node=stack.pop();if(node.person_id)people.push(node);stack.push(...(node.children||[]).slice().reverse());}
 people.sort((a,b)=>a.order-b.order);
 const byId=new Map(people.map(p=>[p.person_id,p])),unitOf=new Map(),units=[];
 for(const person of people){
  if(unitOf.has(person.person_id))continue;
  const partner=byId.get(person.spouse_id),members=[person];
  // Accept legacy one-way pairs only when the other person has no competing pair.
  if(partner && partner!==person && !unitOf.has(partner.person_id) &&
     (!partner.spouse_id || partner.spouse_id===person.person_id))members.push(partner);
  const unit={id:person.person_id,members,parents:new Set(),next:new Set(),children:[],level:0};
  units.push(unit);for(const member of members)unitOf.set(member.person_id,unit);
 }
 const relations=[];
 for(const person of people){
  const from=unitOf.get(person.parent_id),to=unitOf.get(person.person_id);
  // An old spouse-as-parent attachment must not put a spouse on the next row.
  if(from && from!==to){from.next.add(to);to.parents.add(from);relations.push({source:person.parent_id,target:person.person_id});}
 }
 const remaining=new Map(units.map(u=>[u,u.parents.size])),queue=units.filter(u=>!u.parents.size);
 for(let i=0;i<queue.length;i++){
  const unit=queue[i];
  for(const child of unit.next){child.level=Math.max(child.level,unit.level+1);remaining.set(child,remaining.get(child)-1);if(!remaining.get(child))queue.push(child);}
 }
 const unresolved=new Set(units.filter(u=>remaining.get(u)>0));
 // Cyclic/inconsistent units stay visible independently; no ancestry is invented.
 for(const unit of unresolved)unit.level=0;
 const roots=[];
 for(const unit of units){
  const candidates=[...unit.parents].filter(p=>!unresolved.has(p) && !unresolved.has(unit));
  const parent=candidates.sort((a,b)=>b.level-a.level)[0];
  if(parent)parent.children.push(unit);else roots.push(unit);
 }
 const hidden=collapsed || new Set(units.filter(u=>u.level>=2 && u.children.length).map(u=>u.id));
 const cardWidth=options.cards?Math.max(112,Math.min(220,(viewportWidth-40)/2)):0;
 const labelWidth=options.cards?cardWidth-22:viewportWidth?Math.min(Math.max(160,fontSize*7),Math.max(104,(viewportWidth-40)/2)):Math.max(160,fontSize*7);
 const textWidth=text=>[...text].reduce((width,c)=>width+(/[\u0000-\u007f]/.test(c)?.6:1)*fontSize,0);
 function wrapLabel(text){
  return text.split('\n').map(line=>{
   const tokens=line.match(/\[[^\]]*\]|\d+年|闰?\d+月|\d+日|./gu)||[];
   const lines=[];let current='';
   for(const token of tokens){if(current&&textWidth(current+token)>labelWidth){lines.push(current);current='';}current+=token;}
   lines.push(current);return lines.join('\n');
  }).join('\n');
 }
 const displayNames=new Map(people.map(p=>[p.person_id,wrapLabel(p.name)]));
 const labelHeight=Math.max(1,...[...displayNames.values()].map(text=>text.split('\n').length))*(fontSize+4)+12;
 const cardHeight=labelHeight+76;
 const gap=options.cards?cardWidth+16:viewportWidth?labelWidth+20:Math.max(200,fontSize*9),row=Math.max(180,labelHeight+110,options.cards?cardHeight+100:0);
 function measure(unit){
  unit.visibleChildren=hidden.has(unit.id)?[]:unit.children;
  unit.width=Math.max(unit.members.length*gap,unit.visibleChildren.reduce((n,c)=>n+measure(c),0));
  return unit.width;
 }
 roots.forEach(measure);
 const nodes=[],links=[],visible=new Set();let cursor=0;
 function place(unit,left){
  const x=left+unit.width/2,y=unit.level*row;
  unit.members.forEach((person,i)=>{
   visible.add(person.person_id);
   nodes.push({...person,display_name:displayNames.get(person.person_id),id:person.person_id,x:x+(i-(unit.members.length-1)/2)*gap,y,symbol:person.symbol||personSymbol,symbolSize:[40,44],symbolKeepAspect:true,itemStyle:{...person.itemStyle,borderColor:'#52685b',borderWidth:1}});
  });
  if(unit.members.length===2)links.push({source:unit.members[0].person_id,target:unit.members[1].person_id,kind:'spouse',symbol:['none','none'],lineStyle:{width:3}});
  if(unit.children.length){
   const id='branch:'+unit.id;
   nodes.push({id,name:hidden.has(unit.id)?'＋ 展开分支':'－ 收起分支',toggle:unit.id,x,y:y+(options.cards?cardHeight/2+28:48),symbol:'roundRect',symbolSize:[100,28],
    itemStyle:{color:'#f0f0f0',borderColor:'#888',borderWidth:1},label:{position:'inside',fontSize:14,color:'#222',distance:0}});
  }
  let next=left+(unit.width-unit.visibleChildren.reduce((n,c)=>n+c.width,0))/2;for(const child of unit.visibleChildren){place(child,next);next+=child.width;}
 }
 for(const unit of roots){place(unit,cursor);cursor+=unit.width+gap/2;}
 for(const relation of relations){
  if(!visible.has(relation.source)||!visible.has(relation.target))continue;
  const inconsistent=unresolved.has(unitOf.get(relation.source))||unresolved.has(unitOf.get(relation.target));
  links.push({...relation,kind:'parent',symbol:['none','arrow'],lineStyle:{type:inconsistent?'dashed':'solid',curveness:.08}});
 }
 return {nodes,links,collapsed:hidden,unresolved:unresolved.size,width:Math.max(gap,cursor-gap/2),height:Math.max(row,...nodes.map(n=>n.y+row)),labelHeight,labelWidth,rowHeight:row,cardWidth,cardHeight,units};
});
