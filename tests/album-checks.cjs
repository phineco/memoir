const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAEAAAAAwCAIAAAAuKetIAAAAZElEQVR4nNXOQREAMAjAsK7KkT4RPLhGQR5DmsRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnNeBrQ8FpwDgcdr+CAAAAABJRU5ErkJggg==','base64');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL,context=await browser.newContext({viewport:{width:390,height:844}});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  const errors=[];const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
  async function nav(action){await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),action()]);}
  async function add(title,place,precision,year,month,day){
   await page.goto(base+'/f/ui/album/upload');
   await page.locator('[name=photo]').setInputFiles({name:'photo.png',mimeType:'image/png',buffer:png});
   await page.locator('[name=title]').fill(title);await page.locator('[name=location]').fill(place);
   await page.locator('[name=time_precision]').selectOption(precision);
   if(year)await page.locator('[name=photo_year]').fill(year);
   if(month)await page.locator('[name=photo_month]').fill(month);
   if(day)await page.locator('[name=photo_day]').fill(day);
   await nav(()=>page.getByRole('button',{name:'保存到家庭相册'}).click());
   assert.match(new URL(page.url()).pathname,/\/album\/[a-f0-9]{32}$/);
   assert(await page.locator('.album-preview').evaluate(img=>img.complete&&img.naturalWidth>0));
   return new URL(page.url()).pathname.split('/').at(-1);
  }
  await page.goto(base+'/f/ui/more');await nav(()=>page.getByRole('link',{name:/家庭相册/}).click());
  assert(await page.getByRole('heading',{name:'家庭相册',exact:true}).isVisible());
  const first=await add('老院子的合影','合肥老家','year','1985');
  assert.match(await page.locator('#photo-uploader').innerText(),/测试家人/);
  const second=await add('西湖散步','杭州西湖','day','2002','6','15');
  const unknown=await add('未记年份的照片','地点不详','unknown');
  await page.goto(base+'/f/ui/album');
  assert.deepEqual(await page.locator('.album-year').allTextContents(),['2002年','1985年','拍摄时间不详']);
  await page.locator('#album-location').fill('合肥');await nav(()=>page.getByRole('button',{name:'筛选照片',exact:true}).click());
  assert.equal(await page.locator('.album-card').count(),1);
  await page.locator('#album-uploader').selectOption('user:ui-user');await nav(()=>page.getByRole('button',{name:'筛选照片',exact:true}).click());
  assert.equal(new URL(page.url()).searchParams.get('uploader'),'user:ui-user');assert.match(await page.locator('.album-card').innerText(),/上传人：测试家人/);
  assert.match(await page.locator('.album-card').innerText(),/老院子的合影/);
  if(process.env.ALBUM_UPLOADER_UI==='1'){
   const relative=await browser.newContext();await relative.request.post(base+'/login',{form:{phone:'ui-relative',password:'ui-relative-test-only'}});
   const uploadPage=await relative.request.get(base+'/f/ui/album/upload');
   const csrf=(await uploadPage.text()).match(/name="csrf_token" value="([^"]+)"/)[1];
   const added=await relative.request.post(base+'/f/ui/album/upload',{multipart:{csrf_token:csrf,title:'另一位家人的照片',location:'合肥老家',time_precision:'unknown',photo:{name:'relative.png',mimeType:'image/png',buffer:png}}});assert(added.ok());await relative.close();
   await page.reload();assert.equal(await page.locator('.album-card').count(),1,'selected owner and location survive reload');
   await page.locator('#album-uploader').selectOption('user:ui-relative');await nav(()=>page.getByRole('button',{name:'筛选照片',exact:true}).click());
   assert.equal(await page.locator('.album-card').count(),1);assert.match(await page.locator('.album-card').innerText(),/另一位家人的照片/);
   await nav(()=>page.locator('.album-card').click());assert.match(await page.locator('#photo-uploader').innerText(),/另一位家人/);
   await page.goto(base+'/f/ui/album?location='+encodeURIComponent('合肥')+'&uploader=user:ui-user');
   assert.equal(await page.locator('.album-card').count(),1);
  }
  await nav(()=>page.locator('.album-card').click());await nav(()=>page.getByRole('link',{name:'编辑照片资料',exact:true}).click());
  await page.locator('[name=caption]').fill('四代人在院子里合影');await nav(()=>page.getByRole('button',{name:'保存照片资料'}).click());
  assert(await page.getByText('四代人在院子里合影',{exact:true}).isVisible());
  await nav(()=>page.getByRole('link',{name:'用这张照片写文章'}).click());
  await page.locator('#picker-results button').first().waitFor();
  assert.equal(await page.locator('#picker-results button').count(),1,'photo detail opens the selected photo');
  assert.match(await page.locator('#picker-results').innerText(),/上传人：测试家人/);
  await Promise.all([page.waitForResponse(r=>r.url().includes('/album/choices')&&new URL(r.url()).searchParams.get('uploader')==='user:ui-user'),page.locator('#picker-uploader').selectOption('user:ui-user')]);
  assert.equal(await page.locator('.ql-editor img').count(),0,'opening picker must not alter content');
  await page.locator('[name=topic]').fill('看照片讲故事');
  await page.locator('.ql-editor').fill('开头与结尾都要保留。');
  await page.locator('.ql-editor').press('End');
  await page.getByRole('button',{name:'插入图片：老院子的合影'}).click();
  assert.equal(await page.locator('.ql-editor img').getAttribute('src'),'/f/ui/album/'+first+'/image');
  assert.equal(await page.locator('.ql-editor img').getAttribute('alt'),'老院子的合影');
  assert.match(await page.locator('.ql-editor').innerText(),/开头与结尾都要保留/);
  // A literal filter and pagination control do not submit the article form.
  await page.locator('#picker-location').fill('杭州');await page.getByRole('button',{name:'查找照片',exact:true}).click();
  await page.getByRole('button',{name:'插入图片：西湖散步'}).waitFor();
  await page.getByRole('button',{name:'插入图片：西湖散步'}).click();
  assert.equal(await page.locator('.ql-editor img').count(),2);
  await page.waitForFunction(([a,b])=>Object.keys(localStorage).some(k=>k.startsWith('memoir:writer:')&&localStorage.getItem(k).includes(a)&&localStorage.getItem(k).includes(b)),[first,second]);
  await page.reload();await page.locator('#recovery-list button').filter({hasText:'看照片讲故事'}).first().click();
  assert.equal(await page.locator('.ql-editor img').count(),2,'browser recovery keeps photo references');
  if(!await page.locator('#album-picker').evaluate(e=>e.open))await page.locator('#album-picker summary').click();
  await page.locator('#picker-location').fill('杭州');await page.getByRole('button',{name:'查找照片',exact:true}).click();
  await page.getByRole('button',{name:'插入图片：西湖散步'}).waitFor();
  for(const width of [320,390,1280]){
   await page.setViewportSize({width,height:844});await page.evaluate(()=>document.documentElement.setAttribute('data-size','26'));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'picker large text '+width);
  }
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.setAttribute('data-size','18'));
  await nav(()=>page.getByRole('button',{name:'发布故事',exact:true}).click());
  const storyPath=new URL(page.url()).pathname;
  assert.equal(await page.locator('#articleBody img').count(),2);
  for(const img of await page.locator('#articleBody img').all())assert(await img.evaluate(i=>i.complete&&i.naturalWidth>0));
  await nav(()=>page.getByRole('link',{name:'编辑故事',exact:true}).click());
  assert.equal(await page.locator('.ql-editor img').count(),2);
  await page.locator('[name=revision_reason]').fill('补充照片说明');
  await nav(()=>page.getByRole('button',{name:'保存修订',exact:true}).click());
  assert.equal(await page.locator('#articleBody img').count(),2);
  await page.goto(base+'/f/ui/album');
  for(const width of [320,390,1280]){
   await page.setViewportSize({width,height:844});await page.evaluate(()=>document.documentElement.setAttribute('data-size','26'));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'album large text '+width);
   if(process.env.UI_SCREENSHOTS){fs.mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});await page.screenshot({path:path.join(process.env.UI_SCREENSHOTS,'album-'+width+'.png'),fullPage:true});}
  }
  await page.goto(base+'/f/ui/album/'+first);await page.getByText('移除照片',{exact:true}).click();
  page.once('dialog',d=>d.accept());await nav(()=>page.getByRole('button',{name:'确认移除照片'}).click());
  assert.equal((await context.request.get(base+'/f/ui/album/'+first+'/image')).status(),404);
  await page.goto(base+storyPath);assert.equal(await page.locator('#articleBody img').count(),1);
  assert.match(await page.locator('#articleBody').innerText(),/照片已移除或不可用/);
  assert.match(await page.locator('#articleBody').innerText(),/开头与结尾都要保留/);
  const anonymous=await browser.newContext();assert.equal((await anonymous.request.get(base+'/f/ui/album/'+second+'/image')).status(),401);await anonymous.close();
  assert.deepEqual(errors,[]);
  console.log('Family album UI passed: upload metadata and partial/unknown dates, timeline and uploader/place filters, uploader attribution, edit, selected-photo entry, two inline images, browser recovery, published revision, removal, private bytes and 3 large-text layouts.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
