const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL,context=await browser.newContext();
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  const evil='9007199254740993"><img src=x onerror="window.treeInjection=1">';
  const rows=[
   {person_id:'dad',name:'父亲',order:0}, {person_id:'mom',name:'母亲',order:1},
   {person_id:'a',name:'本人[父亲]\n1950年3月8日[阳历]\n1950年闰3月8日[农历]',parent_id:'dad',spouse_id:'b',order:2},
   {person_id:'b',name:'配偶[母亲]',parent_id:'mom',spouse_id:'a',order:3},
   {person_id:evil,name:'<img src=x onerror="window.treeInjection=1">[家人]\n别名：<script>alert(1)</script>',parent_id:'b',order:4},
   {person_id:'unrelated',name:'独立分支',order:5},
   {person_id:'cycle-a',name:'待核对甲',parent_id:'cycle-b',order:6},
   {person_id:'cycle-b',name:'待核对乙',parent_id:'cycle-a',order:7},
  ].map(p=>({...p,children:[]}));
  await context.route('**/f/ui?view=tree',async route=>{
   const response=await route.fetch(),html=await response.text();
   const data=JSON.stringify({children:rows}).replaceAll('<','\\u003c');
   await route.fulfill({response,body:html.replace(/(<script type="application\/json" id="family-tree-data">)[\s\S]*?(<\/script>)/,(_,a,b)=>a+data+b)});
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setViewportSize({width:390,height:844});await page.goto(base+'/f/ui?view=tree');
  await page.waitForSelector('#tree .tree-person-card');
  await page.getByRole('button',{name:'展开全部',exact:true}).click();
  assert.equal(await page.locator('#tree .tree-person-card').count(),rows.length);
  assert.match(await page.locator('#tree-status').innerText(),/循环/);
  assert.equal(await page.locator('#tree img,#tree script').count(),0);
  assert.equal(await page.evaluate(()=>window.treeInjection),undefined);
  const links=await page.locator('#tree path.link').evaluateAll(paths=>paths.map(p=>({kind:p.dataset.relation,child:p.__data__.source?.data?.person?.person_id,parent:p.__data__.target?.[0]?.data?.person?.person_id,dash:p.style.strokeDasharray})));
  for(const [parent,child] of [['dad','a'],['mom','b'],['b',evil],['cycle-a','cycle-b'],['cycle-b','cycle-a']])assert(links.some(l=>l.kind==='parent'&&l.parent===parent&&l.child===child));
  assert.equal(links.filter(l=>l.kind==='parent').length,5);
  assert.equal(links.filter(l=>l.kind==='spouse').length,1);
  assert(links.filter(l=>l.child?.startsWith('cycle')).every(l=>l.dash));
  // A keyboard user can toggle a branch without losing focus.
  const branch=page.locator('#tree [data-branch-id="a"]');await branch.focus();await page.keyboard.press('Enter');
  assert.equal(await branch.getAttribute('aria-expanded'),'false');assert(await branch.evaluate(n=>n===document.activeElement));
  await page.keyboard.press(' ');assert.equal(await branch.getAttribute('aria-expanded'),'true');
  await page.getByRole('button',{name:'查看家族树全图',exact:true}).click();
  assert.equal(await page.locator('#tree .tree-person-card').count(),rows.length);
  const contained=await page.locator('#tree').evaluate(holder=>{
   const bounds=holder.getBoundingClientRect();
   return [...holder.querySelectorAll('.tree-person-card')].every(card=>{const r=card.getBoundingClientRect();return r.left>=bounds.left&&r.right<=bounds.right&&r.top>=bounds.top&&r.bottom<=bounds.bottom;});
  });assert(contained,'Fit must include every person inside the viewport');
  const fitZoom=await page.evaluate(()=>f3.handlers.getCurrentZoom(document.querySelector('#tree svg.main_svg')).k);
  await page.getByRole('button',{name:'放大家族树',exact:true}).click();
  assert(await page.evaluate(()=>f3.handlers.getCurrentZoom(document.querySelector('#tree svg.main_svg')).k)>fitZoom);
  // Moving mode does not accidentally navigate through a person card.
  await page.getByRole('button',{name:'移动家族树',exact:true}).click();
  await page.locator('#tree [data-person-id="dad"]').evaluate(n=>n.click());assert.equal(new URL(page.url()).pathname,'/f/ui');
  // Block either dependency: the authorized server-rendered roster still works.
  await context.unroute('**/f/ui?view=tree');
  for(const pattern of ['**/d3-7.9.0*.js','**/family-chart-0.9.0*.js']){
   await context.route(pattern,r=>r.abort());await page.goto(base+'/f/ui?view=tree');
   assert.match(await page.locator('#tree-status').innerText(),/暂时无法显示/);
   assert(await page.locator('#family-people .person-card').first().isVisible());await context.unroute(pattern);
  }
  assert.deepEqual(errors,[]);
  console.log('family-chart forest: every person, both spouse ancestries, no inferred co-parent, cycles, HTML escaping, keyboard focus, move safety and dependency failures passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
