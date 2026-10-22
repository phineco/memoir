const assert=require('node:assert/strict');
module.exports=async function(browser,signedIn,base){
 const context=await browser.newContext({viewport:{width:390,height:844}});await context.addCookies(await signedIn.cookies());
 let mode='fail',sent=0,cancelled=0;
 await context.route('**/ask/stream',async route=>{
  sent++;if(mode==='fail')return route.abort('failed');
  if(mode==='hold')await new Promise(resolve=>setTimeout(resolve,800));
  const data='data: '+JSON.stringify({sources:[{index:1,title:'原始故事',url:'/f/ui/story/story#articleBody',excerpt:'实际检索的原文片段。'}]})+'\n\ndata: '+JSON.stringify({chunk:'本地模拟答案 [1]。'})+'\n\n';
  try{return await route.fulfill({contentType:'text/event-stream',body:data+(mode==='incomplete'?'':'data: [DONE]\n\n')});}catch(_){}
 });
 await context.route('**/ask/turn/*',route=>{
  if(route.request().method()==='POST'){cancelled++;return route.fulfill({json:{status:'cancelled',question:'问题',answer:'',sources:[]}});}
  return route.fulfill({status:404,body:'not found'});
 });
 const page=await context.newPage();
 try{
  await page.goto(base+'/f/ui/ask');await page.locator('#auto-speak').uncheck();
  const question='失败后必须保留的提问';await page.locator('#msg-input').fill(question);
  await page.evaluate(()=>{document.getElementById('chatform').requestSubmit();document.getElementById('chatform').requestSubmit();});
  await page.locator('#retry-ai').waitFor({state:'visible'});assert.equal(sent,1);
  assert.equal(await page.locator('#msg-input').inputValue(),question);
  await page.reload();
  await page.getByText('本机未完成的问题',{exact:true}).click();
  await page.getByRole('button',{name:'恢复未完成的问题：'+question,exact:true}).click();
  mode='success';await page.locator('#retry-ai').click();
  await page.waitForFunction(()=>document.getElementById('ai-state').textContent.includes('回答已保存'));
  assert.equal(sent,2);assert.equal(await page.locator('#msg-input').inputValue(),'');
  assert.equal(await page.locator('.ai-sources a').getAttribute('href'),'/f/ui/story/story#articleBody');
  mode='incomplete';await page.locator('#msg-input').fill('半途断流问题');await page.locator('#send-btn').click();
  await page.locator('#retry-ai').waitFor({state:'visible'});assert.equal(await page.locator('#msg-input').inputValue(),'半途断流问题');
  mode='hold';await page.locator('#msg-input').fill('需要取消的问题');await page.locator('#send-btn').click();
  await page.locator('#cancel-ai').click();await page.waitForFunction(()=>document.getElementById('ai-state').textContent.includes('已请求取消'));
  assert.equal(await page.locator('#msg-input').inputValue(),'需要取消的问题');assert.equal(cancelled,1);
  await page.goto(base+'/f/empty/ask');assert.equal(await page.locator('#ai-recoveries button').count(),0);
  console.log('AI UI: failed question recovery, refresh, explicit retry, duplicate submit, source links, incomplete stream, cancel and family isolation passed.');
 }finally{await context.close();}
};
