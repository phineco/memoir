/* Only an explicit list of versioned public files is eligible for CacheStorage. */
'use strict';
const CACHE='memoir-easy-static-__VERSION__',ASSETS=__ASSETS__,ALLOWED=new Set(ASSETS);
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)));});
self.addEventListener('activate',event=>{event.waitUntil((async()=>{
 for(const name of await caches.keys())if(name.startsWith('memoir-easy-static-')&&name!==CACHE)await caches.delete(name);
 await self.clients.claim();
})());});
self.addEventListener('message',event=>{if(event.data&&event.data.type==='SKIP_WAITING')self.skipWaiting();});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==self.location.origin)return;
 if(ALLOWED.has(url.pathname)&&!url.search&&!request.headers.has('Range')){
  event.respondWith((async()=>{const cache=await caches.open(CACHE);const hit=await cache.match(request);if(hit)return hit;
   const response=await fetch(request);if(response.ok&&response.type==='basic')await cache.put(request,response.clone());return response;})());return;
 }
 if(request.mode==='navigate')event.respondWith(fetch(request).catch(()=>caches.match('/static/easy-offline.html')));
 // API, HTML, authenticated photos and every kind of audio remain network-only.
});
