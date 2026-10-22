const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const context=await browser.newContext();const base=process.env.UI_TEST_URL;
  assert.equal((await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}})).status(),200);
  await context.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
  await require('./revision-checks.cjs')(browser,context,base);
  await require('./recovery-checks.cjs')(browser,context,base);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
