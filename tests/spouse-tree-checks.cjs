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
   await page.waitForFunction(()=>document.querySelector('#tree canvas')?.width>0);
   const getZoom=()=>page.evaluate(()=>echarts.getInstanceByDom(document.getElementById('tree')).getOption().series[0].zoom);
   await page.getByRole('button',{name:'放大家族树',exact:true}).click();assert((await getZoom())>1);
   await page.getByRole('button',{name:'缩小家族树',exact:true}).click();assert(Math.abs((await getZoom())-1)<.001);
   const mover=page.getByRole('button',{name:'移动家族树',exact:true});await mover.click();assert.equal(await mover.getAttribute('aria-pressed'),'true');
   await page.locator('#tree').scrollIntoViewIfNeeded();const canvas=await page.locator('#tree').boundingBox();
   const before=await page.evaluate(()=>echarts.getInstanceByDom(document.getElementById('tree')).getOption().series[0].center);
   await page.mouse.move(canvas.x+canvas.width/2,canvas.y+canvas.height/2);await page.mouse.down();await page.mouse.move(canvas.x+canvas.width/2+40,canvas.y+canvas.height/2-30,{steps:5});await page.mouse.up();
   const after=await page.evaluate(()=>echarts.getInstanceByDom(document.getElementById('tree')).getOption().series[0].center);assert.notDeepEqual(after,before);
   await page.getByRole('button',{name:'重置视图',exact:true}).click();assert.equal(await mover.getAttribute('aria-pressed'),'false');assert.equal(await getZoom(),1);
   await page.getByRole('button',{name:'展开全部',exact:true}).click();
   const geometry=await page.evaluate(()=>{
    const chart=echarts.getInstanceByDom(document.getElementById('tree')),series=chart.getModel().getSeriesByIndex(0),data=series.getData();
    return {option:chart.getOption().series[0].data,positions:data.mapArray((i)=>{const raw=data.getRawDataItem(i),el=data.getItemGraphicEl(i),rect=el?.getBoundingRect();return {id:raw.id,pid:raw.person_id,toggle:raw.toggle,layout:data.getItemLayout(i),screen:rect?el.transformCoordToGlobal(rect.x+rect.width/2,rect.y+rect.height/2):null,transform:el?.getComputedTransform()};})};
   });
   const personNode=geometry.option.find(n=>n.person_id===spouse);assert(personNode.symbol.startsWith('path://'));assert.match(personNode.name,/新建配偶\[三婶\]\n1950年3月8日\[阳历\]/);assert(!personNode.name.includes('对你：'));
   const wife=geometry.positions.find(n=>n.pid==='daughter'),partner=geometry.positions.find(n=>n.pid===spouse),child=geometry.positions.find(n=>n.pid==='p02');
   assert.equal(wife.screen[1],partner.screen[1]);assert(child.screen[1]>wife.screen[1]);
   assert(Math.abs(wife.screen[0]-partner.screen[0])>=120);
   assert(wife.screen[0]>0&&partner.screen[0]<width-32);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   async function clickNode(item){
    await page.locator('#tree').scrollIntoViewIfNeeded();const box=await page.locator('#tree').boundingBox();
    await page.mouse.click(box.x+item.screen[0]+1,box.y+item.screen[1]+(item.pid?12:1));
   }
   const branch=geometry.positions.find(n=>n.toggle==='daughter');
   await clickNode(branch);
   assert.equal(await page.evaluate(()=>echarts.getInstanceByDom(document.getElementById('tree')).getOption().series[0].data.filter(n=>n.person_id).length),3);
   await page.getByRole('button',{name:'展开全部',exact:true}).click();
   assert.equal(await page.evaluate(()=>echarts.getInstanceByDom(document.getElementById('tree')).getOption().series[0].data.filter(n=>n.person_id).length),4);
   await clickNode(partner);await page.waitForURL('**/person/'+spouse+'?*');
   assert.equal(new URL(page.url()).searchParams.get('return_to'),'/f/ui?view=tree');
   await page.goto(base+'/f/ui?view=tree');
   if(process.env.UI_SCREENSHOTS){require('node:fs').mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});await page.locator('#tree').screenshot({path:process.env.UI_SCREENSHOTS+'/spouse-'+width+'.png'});}
  }
  assert.deepEqual(errors,[]);console.log('New spouse with independent parent and different sort: visible same-row nodes, actual child edge, branch controls, click-through and return context passed at 320/390/1280.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
