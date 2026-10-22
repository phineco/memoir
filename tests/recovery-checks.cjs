const assert = require('node:assert/strict');
module.exports = async function(browser, signedIn, base) {
 const context = await browser.newContext(); await context.addCookies(await signedIn.cookies());
 const page = await context.newPage(); page.on('dialog', d=>d.accept());
 try {
  await page.goto(base+'/f/ui/write');
  await page.locator('[name=topic]').fill('自动恢复测试');
  await page.locator('.ql-editor').fill('刷新后这段回忆应可恢复。');
  await page.waitForFunction(()=>document.getElementById('recovery-status').textContent.includes('已自动保留'));
  await page.reload();
  await page.locator('#recovery-list button').filter({hasText:'自动恢复测试'}).click();
  assert.match(await page.locator('.ql-editor').innerText(),/这段回忆应可恢复/);
  const second=await context.newPage();second.on('dialog',d=>d.accept());
  await second.goto(base+'/f/ui/write');
  await second.locator('.ql-editor').fill('另一个窗口的独立正文。');
  await second.waitForFunction(()=>document.getElementById('recovery-status').textContent.includes('已自动保留'));
  assert((await second.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('memoir:writer:v1:ui-user:ui:new:')).length))>=3);
  await page.locator('button[name=action][value=draft]').click();await page.waitForURL('**/drafts');
  assert((await page.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('memoir:writer:v1:ui-user:ui:new:')).length))>=2,'saving must not delete other windows');
  await second.goto(base+'/f/empty/write'); assert.equal(await second.locator('#recovery-list button').count(),0);
  await second.goto(base+'/f/ui/write');await second.locator('#recovery-clear').click();
  assert.equal(await second.locator('#recovery-list button').count(),0);
  const disabled=await browser.newContext();await disabled.addCookies(await signedIn.cookies());
  await disabled.addInitScript(()=>{Storage.prototype.setItem=function(){throw new Error('disabled');};});
  const p=await disabled.newPage();await p.goto(base+'/f/ui/write');await p.locator('.ql-editor').fill('禁止存储时仍须保留编辑区');
  await p.waitForFunction(()=>document.getElementById('recovery-status').textContent.includes('自动保留失败'));
  assert.match(await p.locator('.ql-editor').innerText(),/仍须保留/);await disabled.close();
  console.log('Recovery: refresh, independent windows, save cleanup, family isolation, explicit clear and storage failure passed.');
  return 6;
 } finally {await context.close();}
};
