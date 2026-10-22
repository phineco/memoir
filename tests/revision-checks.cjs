const assert=require('node:assert/strict');
module.exports=async function(browser,signedIn,base){
 const context=await browser.newContext({viewport:{width:390,height:844}});await context.addCookies(await signedIn.cookies());
 const page=await context.newPage();page.on('dialog',d=>d.accept());
 try{
  await page.goto(base+'/f/ui/story/story');
  await page.getByText('提出修正或补充',{exact:true}).click();
  await page.locator('[name=proposal]').fill('照片背面记载为一九八八年。');
  await page.locator('[name=evidence]').fill('已核对家庭老照片');
  await page.locator('[name=verification_id]').selectOption('verify-ui');
  await page.getByRole('button',{name:'提交建议',exact:true}).click();await page.waitForURL(url=>url.hash==='#corrections');
  await page.getByRole('button',{name:'采纳并修订正文',exact:true}).click();await page.waitForURL('**/edit?correction=*');
  await page.locator('.ql-editor').fill('已经核对：一九八八年搬入老院子。');
  await page.locator('[name=revision_reason]').fill('根据老照片确认搬家年份');
  await page.getByRole('button',{name:'保存修订',exact:true}).click();await page.waitForURL('**/story/story');
  assert.match(await page.locator('#corrections').innerText(),/已采纳并保存修订/);
  assert.match(await page.locator('#articleBody').innerText(),/一九八八年/);
  await page.getByRole('link',{name:'历次版本',exact:true}).click();
  assert.equal(await page.locator('details.disclosure').count(),2);
  console.log('Revisions: proposal, reviewed edit, atomic acceptance, verification and version history passed.');
 }finally{await context.close();}
};
