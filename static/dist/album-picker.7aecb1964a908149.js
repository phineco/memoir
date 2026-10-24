/* Album selection is read-only until the writer explicitly inserts an image. */
window.initAlbumPicker=function(options){
 'use strict';
 var picker=document.getElementById('album-picker');if(!picker)return;
 var results=document.getElementById('picker-results'),status=document.getElementById('picker-status'),search=document.getElementById('picker-location');
 var uploader=document.getElementById('picker-uploader');
 var previous=document.getElementById('picker-prev'),next=document.getElementById('picker-next'),pageText=document.getElementById('picker-page');
 var page=1,pages=1,serial=0,loaded=false,controller;
 function message(text){status.textContent=text;}
 async function load(number,photoId){
  if(!options.available){message('格式编辑器暂不可用，请先保存文字，待编辑器恢复后再插入相册图片。');return;}
  var current=++serial;if(controller)controller.abort();controller=new AbortController();
  previous.disabled=next.disabled=true;results.replaceChildren();pageText.textContent='';message('正在查找相册照片…');
  try{
   var url=new URL(picker.dataset.endpoint,location.origin);url.searchParams.set('page',number);url.searchParams.set('location',search.value.trim());url.searchParams.set('uploader',uploader.value);if(photoId)url.searchParams.set('photo_id',photoId);
   var response=await fetch(url,{credentials:'same-origin',cache:'no-store',signal:controller.signal});
   if(!response.ok)throw Error('unavailable');var data=await response.json();if(current!==serial)return;
   page=data.page;pages=data.pages;loaded=true;
   uploader.replaceChildren();var all=document.createElement('option');all.value='';all.textContent='全部上传人';uploader.append(all);
   data.uploader_options.forEach(function(item){var option=document.createElement('option');option.value=item.value;option.textContent=item.label;uploader.append(option);});uploader.value=data.selected_uploader;

   data.photos.forEach(function(photo){
    var button=document.createElement('button');button.type='button';button.className='card album-card';
    var img=document.createElement('img');img.src=photo.thumbnail;img.alt='';img.loading='lazy';img.width=640;img.height=480;
    var name=document.createElement('strong');name.textContent=photo.title;
    var info=document.createElement('p');info.className='hint';info.textContent=photo.date+' · '+photo.location+' · 上传人：'+photo.uploader;
    var label=document.createElement('span');label.textContent='插入图片';button.setAttribute('aria-label','插入图片：'+photo.title);
    button.append(img,name,info,label);button.addEventListener('click',function(){options.insert(photo);message('已插入“'+photo.title+'”，可继续编辑并保存文章。');});results.append(button);
   });
   pageText.textContent='第 '+page+' / '+pages+' 页';previous.disabled=page<=1;next.disabled=page>=pages;
   message(data.photos.length?'找到 '+data.total+' 张，点击照片插入正文。':'没有符合条件的照片，可切换上传人或地点，或先上传照片再点查找。');
  }catch(error){if(current!==serial||error.name==='AbortError')return;loaded=false;message('相册暂时无法读取，正文仍保留，可稍后点击查找重试。');}
 }
 uploader.addEventListener('change',function(){load(1);});
 picker.addEventListener('toggle',function(){if(picker.open&&!loaded)load(1,picker.dataset.initialPhoto);});
 document.getElementById('picker-search').addEventListener('click',function(){load(1);});
 search.addEventListener('keydown',function(event){if(event.key==='Enter'){event.preventDefault();load(1);}});
 previous.addEventListener('click',function(){if(page>1)load(page-1);});next.addEventListener('click',function(){if(page<pages)load(page+1);});
 if(picker.dataset.initialPhoto){picker.open=true;message('请在相册中选择要插入的照片；不会自动修改正文。');}
 window.addEventListener('pagehide',function(){serial++;if(controller)controller.abort();});
};
