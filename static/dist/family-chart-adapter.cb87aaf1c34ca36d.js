/* Adapt the complete authorized forest to family-chart's public view renderer.
 * Layout stays independent of a focal person: no invisible people or invented parents.
 */
(function(root,factory){
 if(typeof module==='object'&&module.exports)module.exports=factory;
 else root.familyChartTree=factory;
})(typeof window==='undefined'?globalThis:window,function(layout){
 const safeId=(prefix,id)=>prefix+Array.from(String(id),c=>c.codePointAt(0).toString(16)).join('-');
 const nodes=layout.nodes.map(node=>({
  tid:safeId(node.toggle?'branch-':'person-',node.toggle||node.person_id),
  data:{id:safeId(node.toggle?'branch-':'person-',node.toggle||node.person_id),data:{},rels:{parents:[],spouses:[],children:[]},person:node},
  x:node.x,y:node.y,depth:Math.round(node.y/layout.rowHeight),psx:node.x,psy:node.y,
  all_rels_displayed:true
 }));
 const byId=new Map(nodes.filter(d=>d.data.person.person_id).map(d=>[d.data.person.person_id,d]));
 for(const link of layout.links){
  const source=byId.get(link.source),target=byId.get(link.target);
  if(!source||!target)continue;
  if(link.kind==='spouse'){
   (source.spouses||(source.spouses=[])).push(target);
   source.data.rels.spouses.push(target.data.id);target.data.rels.spouses.push(source.data.id);
  }else{
   // Use direct parent links, rather than treating a spouse as an implicit co-parent.
   (target.parents||(target.parents=[])).push(source);
   target.data.rels.parents.push(source.data.id);source.data.rels.children.push(target.data.id);
   target.unresolvedParent=link.lineStyle?.type==='dashed';
  }
 }
 const minX=Math.min(...nodes.map(d=>d.x))-layout.cardWidth/2-20;
 const maxX=Math.max(...nodes.map(d=>d.x))+layout.cardWidth/2+20;
 const minY=Math.min(...nodes.map(d=>d.y))-layout.cardHeight/2-20;
 const maxY=Math.max(...nodes.map(d=>d.y))+layout.cardHeight/2+20;
 return {data:nodes,data_stash:nodes.map(d=>d.data),main_id:nodes[0]?.data.id,is_horizontal:false,
  dim:{width:maxX-minX,height:maxY-minY,x_off:-minX,y_off:-minY}};
});
