const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL,context=await browser.newContext({viewport:{width:1280,height:900}});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  const page=await context.newPage();
  async function add(name,parent,spouse,sort){
   await page.goto(base+'/f/ui/tree/add');await page.locator('[name=name]').fill(name);
   await page.locator('[name=parent_id]').selectOption(parent);await page.locator('[name=spouse_id]').selectOption(spouse);
   if(name==='新建配偶'){await page.locator('[name=relation]').fill('三婶');await page.locator('[name=birth_solar_year]').fill('1950');await page.locator('[name=birth_solar_month]').selectOption('3');await page.locator('[name=birth_solar_day]').selectOption('8');}
   await page.locator('[name=sort]').fill(String(sort));await page.getByRole('button',{name:'添加',exact:true}).click();
   assert.equal(new URL(page.url()).pathname,'/f/ui');
  }
  await add('新建配偶','0','daughter',99);
  await page.goto(base+'/f/ui?view=tree');
  const data=await page.locator('#family-tree-data').textContent();
  const flat=[];function walk(n){if(n.person_id)flat.push(n);(n.children||[]).forEach(walk);}walk(JSON.parse(data));
  const spouse=flat.find(n=>n.name.startsWith('新建配偶')).person_id;
  await add('子女分支',spouse,'',1);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const width of [1280,390,320]){
   await page.setViewportSize({width,height:900});await page.goto(base+'/f/ui?view=tree');
   await page.waitForFunction(()=>document.querySelectorAll('#tree .tree-person-card').length>0);
   const getZoom=()=>page.evaluate(()=>f3.handlers.getCurrentZoom(document.querySelector('#tree svg.main_svg')).k);
   const initialZoom=await getZoom();
   await page.getByRole('button',{name:'放大家族树',exact:true}).click();assert((await getZoom())>initialZoom);
   await page.getByRole('button',{name:'缩小家族树',exact:true}).click();assert(Math.abs((await getZoom())-initialZoom)<.001);
   const mover=page.getByRole('button',{name:'移动家族树',exact:true});await mover.click();assert.equal(await mover.getAttribute('aria-pressed'),'true');
   await page.locator('#tree').scrollIntoViewIfNeeded();const canvas=await page.locator('#tree').boundingBox();
   const before=await page.evaluate(()=>({...f3.handlers.getCurrentZoom(document.querySelector('#tree svg.main_svg'))}));
   await page.mouse.move(canvas.x+canvas.width/2,canvas.y+canvas.height/2);await page.mouse.down();await page.mouse.move(canvas.x+canvas.width/2+40,canvas.y+canvas.height/2-30,{steps:5});await page.mouse.up();
   const after=await page.evaluate(()=>({...f3.handlers.getCurrentZoom(document.querySelector('#tree svg.main_svg'))}));assert.notDeepEqual(after,before);
   await page.getByRole('button',{name:'重置视图',exact:true}).click();assert.equal(await mover.getAttribute('aria-pressed'),'false');assert.equal(await getZoom(),initialZoom);
   await page.getByRole('button',{name:'展开全部',exact:true}).click();
   const geometry=await page.locator('#tree .tree-person-card').evaluateAll(cards=>cards.map(card=>{
    const d=card.parentNode.__data__,rect=card.getBoundingClientRect();
    return {id:card.dataset.personId,x:d.x,y:d.y,text:card.textContent,screenX:rect.x+rect.width/2,screenY:rect.y+rect.height/2};
   }));
   const partner=geometry.find(n=>n.id===spouse),wife=geometry.find(n=>n.id==='daughter'),child=geometry.find(n=>n.id==='p02');
   assert.match(partner.text,/新建配偶/);assert.match(partner.text,/三婶/);assert.match(partner.text,/1950年3月8日/);assert.match(partner.text,/阳历/);assert(!partner.text.includes('对你：'));
   assert.equal(wife.y,partner.y);assert(child.y>wife.y);assert(Math.abs(wife.x-partner.x)>=120);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   assert.equal(await page.locator('#tree .tree-person-icon svg').count(),4);
   await page.locator('#tree [data-branch-id="daughter"]').click();
   await page.waitForFunction(()=>document.querySelectorAll('#tree .tree-person-card').length===3);
   await page.getByRole('button',{name:'展开全部',exact:true}).click();
   assert.equal(await page.locator('#tree .tree-person-card').count(),4);
   await page.locator('#tree [data-person-id="'+spouse+'"]').click();await page.waitForURL('**/person/'+spouse+'?*');
   assert.equal(new URL(page.url()).searchParams.get('return_to'),'/f/ui?view=tree');
   await page.goto(base+'/f/ui?view=tree');
   if(process.env.UI_SCREENSHOTS){require('node:fs').mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});await page.locator('#tree').screenshot({path:process.env.UI_SCREENSHOTS+'/spouse-'+width+'.png'});}
  }
  assert.deepEqual(errors,[]);console.log('New spouse with independent parent and different sort: visible same-row nodes, actual child edge, branch controls, click-through and return context passed at 320/390/1280.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
