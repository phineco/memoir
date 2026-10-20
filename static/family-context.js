/* Remember a family only when the server has rendered authorized family links. */
(function(){
  var body=document.body, uid=body.dataset.userId, fid=body.dataset.familyId;
  if(!uid)return;
  var key='memoir.last-family.v1.'+uid;
  try {
    if(fid){localStorage.setItem(key,fid);return;}
    if(!body.hasAttribute('data-family-picker') || new URLSearchParams(location.search).has('switch'))return;
    var last=localStorage.getItem(key);
    var link=Array.from(document.querySelectorAll('a[data-family-choice]')).find(function(a){return a.dataset.familyChoice===last;});
    if(link)location.replace(link.href);
    else localStorage.removeItem(key);
  } catch(e) { /* Storage is optional; the server-rendered picker remains usable. */ }
})();
