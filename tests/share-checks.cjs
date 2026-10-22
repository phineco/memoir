const assert=require('node:assert/strict');
module.exports=async function(browser,signedIn,base){
 const context=await browser.newContext({viewport:{width:320,height:850}});await context.addCookies(await signedIn.cookies());
 await context.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async function(value){if(window.denyClipboard)throw Error('denied');window.copiedShare=value;}}}));
 const page=await context.newPage();page.on('dialog',d=>d.accept());
 try{
  const response=await context.request.post(base+'/f/ui/shares/new',{maxRedirects:0});assert.equal(response.status(),302);
  const sid=response.headers().location.split('/').pop();
  await page.goto(base+response.headers().location);assert.match(await page.locator('main').innerText(),/非完整文章或电子书/);
  assert.equal(await page.locator('nav[aria-label="家庭导航"]').count(),1);
  await context.request.post(base+'/f/ui/shares/'+sid+'/publish',{form:{password:'ui-test-only'}});
  await page.goto(base+'/f/ui/shares');
  const field=page.locator('#share-link-'+sid);const url=await field.inputValue();assert.match(url,/^https:\/\/family\.scyllatech\.cn\/s\//);
  await page.getByRole('button',{name:'复制分享链接',exact:true}).click();assert.equal(await page.evaluate(()=>window.copiedShare),url);
  await page.evaluate(()=>window.denyClipboard=true);await page.getByRole('button',{name:'复制分享链接',exact:true}).click();
  assert.match(await page.locator('#share-copy-status').innerText(),/已选中/);
  assert.equal(await field.evaluate(n=>n.selectionEnd-n.selectionStart),url.length);
  await page.evaluate(()=>{document.documentElement.setAttribute('data-size','26');document.documentElement.setAttribute('data-theme','contrast');});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));
  console.log('Share UI: summary preview, preserved navigation, canonical URL, copy/fallback and narrow large-text layout passed.');
 }finally{await context.close();}
};
