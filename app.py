"""Flask 应用入口。"""
import re
from flask import Flask, request, session

from config import Config
from models import User, get_session, init_db, remove_session
from views import bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    from invite_links import public_base_url, public_url
    app.config["PUBLIC_BASE_URL"] = public_base_url(app.config["PUBLIC_BASE_URL"])
    app.secret_key = Config.SECRET_KEY
    init_db(Config.DATABASE_URL, pool_recycle_seconds=Config.DB_POOL_RECYCLE_SECONDS)
    import models
    from observability import install
    install(app, models._engine)
    app.register_blueprint(bp)
    from privacy_routes import bp as privacy_bp
    app.register_blueprint(privacy_bp)
    from product_metrics import bp as metrics_bp
    app.register_blueprint(metrics_bp)
    from voices import bp as voices_bp
    app.register_blueprint(voices_bp)
    from album import bp as album_bp
    app.register_blueprint(album_bp)
    from album import display_html
    app.jinja_env.globals["article_html"]=display_html
    from person_dates import LUNAR_MONTHS, LUNAR_DAYS
    app.jinja_env.globals.update(lunar_months=LUNAR_MONTHS, lunar_days=LUNAR_DAYS)
    from writing_aids import QUESTIONS
    app.jinja_env.globals['writing_questions'] = QUESTIONS
    from navigation import context as site_navigation, back_url, context_link, return_label
    app.jinja_env.globals.update(site_navigation=site_navigation, back_url=back_url, context_link=context_link, return_label=return_label)
    from forms import csrf_token
    app.jinja_env.globals['csrf_token']=csrf_token
    from assets import asset_resolver
    asset_url = asset_resolver(app.root_path)

    @app.after_request
    def cache_policy(response):
        if request.path.startswith("/static/dist/") and re.search(r"\.[0-9a-f]{16}\.(css|js)$", request.path) and response.status_code in (200, 304):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.teardown_appcontext
    def close_session(error=None):
        remove_session()

    @app.context_processor
    def inject_user():
        uid = session.get("user_id")
        me = get_session().query(User).filter_by(id=uid, del_flag=0).first() if uid else None
        from storage import storage_url
        from legal import TERMS_VERSION, PRIVACY_VERSION
        from sms import development_mode
        from operations import is_operator
        from product_metrics import collection_enabled
        return {"me": me, "storage_url": storage_url, "asset_url": asset_url, "public_url":public_url,
                "terms_version": TERMS_VERSION, "privacy_version": PRIVACY_VERSION,
                "privacy_contact_email": app.config["PRIVACY_CONTACT_EMAIL"],
                "sms_development_mode": development_mode(),
                "app_version": app.config['RELEASE_VERSION'],
                "is_operator":is_operator(me),
                "voice_feature_enabled":bool(app.config.get('VOICE_ENABLED')),
                "usage_metrics":bool(me and collection_enabled()),
                "saved_write_recovery": session.pop("saved_write_recovery", None)}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
