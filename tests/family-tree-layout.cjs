const assert=require('node:assert/strict');
const layout=require('../static/family-tree-layout.js');
function tree(rows){return {children:rows.map(([id,parent,spouse,order=0])=>({person_id:id,parent_id:parent,spouse_id:spouse,order,name:id,children:[]}))};}
function check(rows){const graph=layout(tree(rows),18,new Set());const people=graph.nodes.filter(n=>n.person_id);assert.equal(people.length,rows.length);assert.equal(new Set(people.map(n=>n.id)).size,rows.length);return graph;}
for(const rows of [
 [['root',null,null,0],['husband','root','wife',1],['sibling','root',null,2],['wife',null,'husband',99],['child','wife',null,3]],
 [['root',null,null,0],['husband','root','wife',99],['wife','husband','husband',0],['child','husband',null,1]],
 [['root',null,null,0],['mother',null,null,0],['husband','root','wife',1],['wife','mother','husband',2],['child','wife',null,3]],
]){
 const graph=check(rows),byId=new Map(graph.nodes.map(n=>[n.id,n]));
 assert.equal(byId.get('husband').y,byId.get('wife').y);
 const between=graph.nodes.filter(n=>n.person_id&&n.y===byId.get('wife').y&&n.x>Math.min(byId.get('wife').x,byId.get('husband').x)&&n.x<Math.max(byId.get('wife').x,byId.get('husband').x));
 assert.equal(between.length,0);
 assert(byId.get('child').y>byId.get('wife').y);
 assert.equal(graph.links.filter(l=>l.kind==='spouse').length,1);
 assert.equal(graph.links.some(l=>l.kind==='parent'&&l.source==='husband'&&l.target==='wife'),false);
}
const both=check([['dad',null,null],['mom',null,null],['a','dad','b'],['b','mom','a']]);
assert.equal(both.links.filter(l=>l.kind==='parent').length,2);
assert(!both.links.some(l=>l.source==='dad'&&l.target==='b'));
const cyclic=check([['a','b'],['b','a'],['orphan','missing']]);assert.equal(cyclic.unresolved,2);
const big='9007199254740993';check([[big,null,'other'],['other',null,big]]);
const branchTree=tree([['a',null,'b'],['b',null,'a'],['child','a','partner'],['partner',null,'child'],['grandchild','child']]);
const folded=layout(branchTree,26,new Set(['a']));assert.deepEqual(folded.nodes.filter(n=>n.person_id).map(n=>n.id),['a','b']);
assert.equal(folded.nodes.find(n=>n.toggle).toggle,'a');
assert.equal(layout(branchTree,26,new Set()).nodes.filter(n=>n.person_id).length,5);
assert.equal(check([['solo',null,'missing']]).links.length,0);
console.log('Spouse adjacency, differing parent levels/sorts, both ancestries, no invented parenthood, cycles, orphans, string IDs and branch folding passed.');
const people=check([['one'],['two']]).nodes.filter(n=>n.person_id);
assert(people.every(n=>n.symbol.startsWith('path://')&&n.symbolSize[0]>=40));
const future=layout({person_id:'avatar',name:'Future',symbol:'image:///static/future-avatar.png'},18,new Set());
assert.equal(future.nodes.find(n=>n.person_id).symbol,'image:///static/future-avatar.png');
