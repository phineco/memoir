"""Family photos and stable, permission-checked article image references."""
import calendar
import io
import re
import warnings
from html.parser import HTMLParser

from flask import Blueprint,abort,current_app,redirect,render_template,request,send_file,url_for
from sqlalchemy import case,func,or_

from forms import require_csrf
from models import Photo,Person,User,get_session,new_id
from reporting import local_now
from storage import get_storage
from views import _current_user,_family_or_404,_is_admin

bp=Blueprint('album',__name__)
MAX_IMAGE=10*1024*1024
PAGE_SIZE=24


@bp.before_request
def guard():
    request.max_content_length=MAX_IMAGE+512*1024
    if not _current_user():
        if request.path.endswith(('/image','/choices')):abort(401)
        return redirect(url_for('main.login',next=request.path))
    _family_or_404(request.view_args['family_id'])
    if request.method=='POST':require_csrf()


def photo_or_404(family_id,photo_id):
    photo=get_session().query(Photo).filter_by(id=photo_id,family_id=family_id,del_flag=0).first()
    if not photo:abort(404)
    return photo


def date_label(photo):
    if not photo.photo_year:return '拍摄时间不详'
    value=str(photo.photo_year)+'年'
    if photo.photo_month:value+=str(photo.photo_month)+'月'
    if photo.photo_day:value+=str(photo.photo_day)+'日'
    return value


def metadata(data,family_id):
    title=(data.get('title') or '').strip();caption=(data.get('caption') or '').strip();location=(data.get('location') or '').strip()
    if not title and not caption:raise ValueError('请填写照片名称或描述，至少一项。')
    if len(title)>120 or len(caption)>255:raise ValueError('名称最多 120 字，描述最多 255 字。')
    if not location or len(location)>255:raise ValueError('请填写地点，最多 255 字；不知道时可填写“地点不详”。')
    precision=data.get('time_precision','')
    if precision not in ('year','month','day','unknown'):raise ValueError('请选择拍摄时间精度；不知道时请选择“时间不详”。')
    year=month=day=None
    if precision!='unknown':
        try:
            year=int(data.get('photo_year',''))
            if not 1<=year<=9999:raise ValueError
            if precision in ('month','day'):month=int(data.get('photo_month',''))
            if month is not None and not 1<=month<=12:raise ValueError
            if precision=='day':
                day=int(data.get('photo_day',''))
                if not 1<=day<=calendar.monthrange(year,month)[1]:raise ValueError
        except (ValueError,TypeError):raise ValueError('请按所选精度填写有效的公历年、月、日。') from None
    person_id=data.get('person_id') or None
    if person_id and not get_session().query(Person.id).filter_by(id=person_id,family_id=family_id,del_flag=0).first():
        raise ValueError('关联人物必须属于本家庭。')
    return dict(title=title or None,caption=caption or None,location=location,photo_year=year,photo_month=month,photo_day=day,person_id=person_id)


def normalize(data):
    from PIL import Image,ImageOps,UnidentifiedImageError
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ('JPEG','PNG','GIF','WEBP') or source.width*source.height>30000000:raise ValueError
                source.seek(0);source.load()
                image=ImageOps.exif_transpose(source)
                transparent=image.mode in ('RGBA','LA') or 'transparency' in image.info
                image=image.convert('RGBA' if transparent else 'RGB')
                image.thumbnail((4096,4096))
                # A new image deliberately strips EXIF/GPS, embedded comments and profiles.
                clean=Image.new(image.mode,image.size);clean.paste(image)
                output=io.BytesIO();ext='png' if transparent else 'jpg'
                clean.save(output,'PNG' if transparent else 'JPEG',**({} if transparent else {'quality':90}))
                if output.tell()>MAX_IMAGE:raise ValueError
                clean.thumbnail((640,640));thumb=io.BytesIO();clean.save(thumb,'PNG' if transparent else 'JPEG',**({} if transparent else {'quality':80}))
                return output.getvalue(),thumb.getvalue(),ext
    except (ValueError,OSError,SyntaxError,OverflowError,UnidentifiedImageError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ValueError('照片无法读取，请使用有效的 JPG、PNG、GIF 或 WebP（不超过 3000 万像素）；HEIC 请先转为 JPG。') from None


def thumb_key(key):
    name,ext=key.rsplit('.',1)
    return name+'-thumb.'+ext


def uploader_label(user):
    if not user:return '上传人未记录'
    if user.del_flag==1:return '已注销家人'
    return (user.nickname or '').strip() or '家人（未设置昵称）'


def uploader_info(family_id,selected=""):
    s=get_session()
    ids={row[0] for row in s.query(Photo.uploaded_by).filter_by(family_id=family_id,del_flag=0).distinct()}
    users=s.query(User.id,User.nickname,User.del_flag).filter(User.id.in_([uid for uid in ids if uid])).all()
    labels={user.id:uploader_label(user) for user in users}
    options=[dict(value='user:'+uid,label=label) for uid,label in sorted(labels.items(),key=lambda item:(item[1],item[0]))]
    if ids-set(labels):options.append(dict(value='unknown',label='上传人未记录'))
    if selected and selected not in {option['value'] for option in options}:options.append(dict(value=selected,label='所选上传人（暂无照片）'))
    return options,labels


def uploader_filter():
    value=request.args.get('uploader','')
    if value not in ('','unknown') and not (value.startswith('user:') and 1<=len(value[5:])<=64):
        abort(400,'上传人筛选无效，请重新选择。')
    return value


def query_photos(family_id):
    location=request.args.get('location','').strip()
    if len(location)>255:abort(400,'地点搜索最多 255 字')
    query=get_session().query(Photo).filter_by(family_id=family_id,del_flag=0)
    if location:query=query.filter(Photo.location.contains(location,autoescape=True))
    uploader=uploader_filter()
    if uploader=='unknown':
        query=query.filter(or_(Photo.uploaded_by.is_(None),Photo.uploaded_by=='',~Photo.uploaded_by.in_(get_session().query(User.id))))
    elif uploader:query=query.filter(Photo.uploaded_by==uploader[5:])
    if request.endpoint=='album.choices' and request.args.get('photo_id'):
        selected=photo_or_404(family_id,request.args['photo_id']);query=query.filter(Photo.id==selected.id)
    # Unknown capture dates remain a separate last group, never substitute upload time.
    query=query.order_by(case((Photo.photo_year.is_(None),1),else_=0),Photo.photo_year.desc(),
                         func.coalesce(Photo.photo_month,0).desc(),func.coalesce(Photo.photo_day,0).desc(),Photo.id)
    page=request.args.get('page','1')
    if not re.fullmatch(r'[1-9][0-9]{0,5}',page):abort(400,'页码无效')
    page=int(page);total=query.count();pages=max(1,(total+PAGE_SIZE-1)//PAGE_SIZE)
    if page>pages:abort(404)
    return query.offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE).all(),location,page,pages,total,uploader


@bp.get('/f/<family_id>/album')
def index(family_id):
    family=_family_or_404(family_id);photos,location,page,pages,total,uploader=query_photos(family_id)
    options,labels=uploader_info(family_id,uploader)
    return render_template('album.html',family=family,photos=photos,location=location,page=page,pages=pages,total=total,date_label=date_label,
                           uploader=uploader,uploader_options=options,uploader_names=labels)


@bp.get('/f/<family_id>/album/choices')
def choices(family_id):
    photos,location,page,pages,total,uploader=query_photos(family_id)
    options,labels=uploader_info(family_id,uploader)
    return dict(photos=[dict(id=p.id,title=p.title or p.caption or '家庭照片',caption=p.caption or '',date=date_label(p),
                            uploader=labels.get(p.uploaded_by,'上传人未记录'),
                            location=p.location or '地点未记录',thumbnail=url_for('album.image',family_id=family_id,photo_id=p.id,size='thumb'),url=url_for('album.image',family_id=family_id,photo_id=p.id)) for p in photos],page=page,pages=pages,total=total,uploader_options=options,selected_uploader=uploader)


def form_page(family,photo=None,error=None,status=200):
    people=get_session().query(Person).filter_by(family_id=family.id,del_flag=0).order_by(Person.name,Person.id).all()
    if request.method=='POST':form=request.form
    elif photo:
        form={key:getattr(photo,key) or '' for key in ('title','caption','location','photo_year','photo_month','photo_day','person_id')}
        form['time_precision']='day' if photo.photo_day else 'month' if photo.photo_month else 'year' if photo.photo_year else 'unknown'
    else:form={'person_id':request.args.get('person_id','')}
    return render_template('album_form.html',family=family,photo=photo,form=form,people=people,error=error),status


@bp.route('/f/<family_id>/album/upload',methods=['GET','POST'])
def upload(family_id,person_id=None):
    family=_family_or_404(family_id)
    if request.method=='GET':return form_page(family)
    try:
        data=request.form.to_dict()
        if person_id:data['person_id']=person_id
        values=metadata(data,family_id);file=request.files.get('photo') or request.files.get('photo2')
        if not file or not file.filename:raise ValueError('请选择照片。')
        data=file.read(MAX_IMAGE+1)
        if len(data)>MAX_IMAGE:raise ValueError('照片太大，请选择 10 MB 以内的文件。')
        data,thumbnail,ext=normalize(data)
    except ValueError as error:return form_page(family,error=str(error),status=400)
    identifier=new_id();key=f'album/{family_id}/{identifier}.{ext}'
    try:
        get_storage().save(data,key)
        try:get_storage().save(thumbnail,thumb_key(key))
        except Exception:current_app.logger.warning('album thumbnail unavailable; using full image')
    except Exception:
        current_app.logger.warning('album upload storage failed')
        return form_page(family,error='照片暂未保存，请保留原图并稍后重试。',status=503)
    me=_current_user();s=get_session()
    s.add(Photo(id=identifier,family_id=family_id,storage_path=key,uploaded_by=me.id,create_by=me.id,create_date=local_now(),**values))
    try:s.commit()
    except Exception:
        s.rollback()
        try:
            get_storage().delete(key);get_storage().delete(thumb_key(key))
        except Exception:current_app.logger.warning('album upload cleanup needed')
        raise
    return redirect(url_for('album.detail',family_id=family_id,photo_id=identifier))


@bp.get('/f/<family_id>/album/<photo_id>')
def detail(family_id,photo_id):
    family=_family_or_404(family_id);photo=photo_or_404(family_id,photo_id)
    user=get_session().query(User.id,User.nickname,User.del_flag).filter_by(id=photo.uploaded_by).first() if photo.uploaded_by else None
    return render_template('album_detail.html',family=family,photo=photo,date_label=date_label,
                           uploader_name=uploader_label(user),
                           can_manage=photo.uploaded_by==_current_user().id or _is_admin(family,_current_user()))


@bp.route('/f/<family_id>/album/<photo_id>/edit',methods=['GET','POST'])
def edit(family_id,photo_id):
    family=_family_or_404(family_id);photo=photo_or_404(family_id,photo_id)
    if photo.uploaded_by!=_current_user().id and not _is_admin(family,_current_user()):abort(403)
    if request.method=='GET':return form_page(family,photo)
    try:values=metadata(request.form,family_id)
    except ValueError as error:return form_page(family,photo,error=str(error),status=400)
    s=get_session()
    if request.form.get('base_version')!=str(photo.metadata_version):abort(409,'照片资料已更新，请刷新后核对。')
    changed=s.query(Photo).filter_by(id=photo.id,family_id=family_id,del_flag=0,metadata_version=photo.metadata_version).update(
        dict(**values,metadata_version=photo.metadata_version+1,update_by=_current_user().id,update_date=local_now()),synchronize_session=False)
    if changed!=1:s.rollback();abort(409,'照片资料已更新，请刷新后核对。')
    s.commit();return redirect(url_for('album.detail',family_id=family_id,photo_id=photo_id))


def remove_photo(family,photo):
    if photo.uploaded_by!=_current_user().id and not _is_admin(family,_current_user()):abort(403)
    # Deny every reference immediately even if object cleanup needs a retry.
    photo.del_flag=1;photo.update_by=_current_user().id;photo.update_date=local_now();get_session().commit()
    try:
        if photo.storage_path:
            get_storage().delete(photo.storage_path)
            if photo.storage_path.startswith('album/'):get_storage().delete(thumb_key(photo.storage_path))
    except Exception:current_app.logger.warning('album removed; private storage cleanup needed')


@bp.post('/f/<family_id>/album/<photo_id>/delete')
def delete(family_id,photo_id):
    remove_photo(_family_or_404(family_id),photo_or_404(family_id,photo_id))
    return redirect(url_for('album.index',family_id=family_id))


@bp.get('/f/<family_id>/album/<photo_id>/image')
def image(family_id,photo_id):
    photo=photo_or_404(family_id,photo_id)
    ext=(photo.storage_path or '').rsplit('.',1)[-1].lower()
    types={'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','gif':'image/gif','webp':'image/webp'}
    if ext not in types:abort(404)
    try:
        if request.args.get('size')=='thumb' and photo.storage_path.startswith('album/'):
            try:data=get_storage().read(thumb_key(photo.storage_path),MAX_IMAGE+1)
            except Exception:data=get_storage().read(photo.storage_path,MAX_IMAGE+1)
        else:data=get_storage().read(photo.storage_path,MAX_IMAGE+1)
    except Exception:abort(404)
    if len(data)>MAX_IMAGE:abort(404)
    response=send_file(io.BytesIO(data),mimetype=types[ext],max_age=0)
    response.headers.update({'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Cross-Origin-Resource-Policy':'same-origin'})
    return response


def clean_story_images(content,family_id):
    # Inspect the raw input before cleaning so bad family/image references are explicit errors.
    ids=set()
    class Images(HTMLParser):
        def handle_starttag(self,tag,attrs):
            if tag!='img':return
            values=dict(attrs);src=values.get('src') or ''
            match=re.fullmatch(r'/f/'+re.escape(family_id)+r'/album/([A-Za-z0-9_-]{1,64})/image',src)
            if not match:abort(400,'请从本家庭相册选择图片，不能插入外部链接或其他家庭的照片。')
            ids.add(match[1])
    parser=Images();parser.feed(content)
    if len(ids)>100:abort(400,'每篇文章最多引用 100 张相册照片。')
    if ids:
        valid={row[0] for row in get_session().query(Photo.id).filter(Photo.id.in_(ids),Photo.family_id==family_id)}
        if ids!=valid:abort(400,'引用的照片不存在或不属于本家庭，请删除该图片后重新保存。')
    return display_html(content,family_id)


def display_html(content,family_id):
    """Keep old article text readable when a referenced shared photo is removed."""
    from sanitize import sanitize_html
    html=sanitize_html(content,family_id=family_id)
    pattern=r'<img\b[^>]*>'
    ids=set(re.findall(r'src="/f/'+re.escape(family_id)+r'/album/([A-Za-z0-9_-]{1,64})/image"',html))
    valid={row[0] for row in get_session().query(Photo.id).filter(Photo.id.in_(ids),Photo.family_id==family_id,Photo.del_flag==0)} if ids else set()
    def replace(match):
        found=re.search(r'src="/f/'+re.escape(family_id)+r'/album/([A-Za-z0-9_-]{1,64})/image"',match[0])
        return match[0] if found and found[1] in valid else '<span>（照片已移除或不可用）</span>'
    return re.sub(pattern,replace,html)
