"""Public installation metadata, never user HTML or private API/media caches."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint,Response,abort,current_app,redirect,render_template,request,url_for


def enabled():return bool(current_app.config.get('EASY_ENABLED') and current_app.config.get('EASY_PWA_ENABLED'))


def install(app):
    bp=Blueprint('easy_pwa',__name__)
    @bp.get('/easy/manifest.webmanifest')
    def manifest():
        if not enabled():abort(404)
        data={'id':'/easy','name':'家音 · 简易版','short_name':'家音','lang':'zh-CN','start_url':'/easy','scope':'/easy',
            'display':'standalone','background_color':'#f4f6f2','theme_color':'#245e49',
            'icons':[{'src':url_for('static',filename='icons/easy-'+str(n)+'.png'),'sizes':str(n)+'x'+str(n),'type':'image/png','purpose':'any maskable'} for n in (192,512)]}
        return Response(json.dumps(data,ensure_ascii=False),mimetype='application/manifest+json',headers={'Cache-Control':'no-store'})
    @bp.get('/easy/sw.js')
    def worker():
        if not enabled():abort(404)
        root=Path(current_app.root_path)
        files=json.loads((root/'static/dist/manifest.json').read_text())['files']
        assets=['/static/dist/'+name for name in sorted(files.values())]+['/static/icons/easy-192.png','/static/icons/easy-512.png','/static/easy-offline.html']
        source=(root/'static/easy-sw.js').read_text()
        version=hashlib.sha256((source+json.dumps(assets)+str(current_app.config['RELEASE_VERSION'])).encode()).hexdigest()[:16]
        source=source.replace('__ASSETS__',json.dumps(assets)).replace('__VERSION__',version)
        return Response(source,mimetype='application/javascript',headers={'Cache-Control':'no-store','Service-Worker-Allowed':'/easy','X-Content-Type-Options':'nosniff'})
    @bp.get('/easy/install')
    def install_help():
        from easy_routes import selected
        family,response=selected()
        if response:return response
        return render_template('easy_install.html',family=family)
    @bp.route('/easy/login',methods=['GET','POST'])
    def login():
        from views import login as normal_login
        candidate=request.args.get('next') or '/easy'
        try:
            parts=urlsplit(candidate)
            valid=not parts.scheme and not parts.netloc and '\\' not in candidate and not any(ord(c)<32 for c in candidate) and (parts.path=='/easy' or parts.path.startswith('/easy/'))
        except ValueError:valid=False
        if not valid:abort(400,'返回地址无效，请从简易首页重新登录。')
        response=normal_login()
        # Keep an installed login inside the task interface; do not trust arbitrary return URLs.
        if hasattr(response,'status_code') and response.status_code in (301,302,303):
            response.headers['Location']=candidate
        return response

    app.register_blueprint(bp)
