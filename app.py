"""Flask 应用入口。"""
import re
from flask import Flask, request, session

from config import Config
from models import User, get_session, init_db, remove_session
from views import bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    from invite_links import public_base_url
    app.config["PUBLIC_BASE_URL"] = public_base_url(app.config["PUBLIC_BASE_URL"])
    app.secret_key = Config.SECRET_KEY
    init_db(Config.DATABASE_URL)
    app.register_blueprint(bp)
    from person_dates import LUNAR_MONTHS, LUNAR_DAYS
    app.jinja_env.globals.update(lunar_months=LUNAR_MONTHS, lunar_days=LUNAR_DAYS)
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
        return {"me": me, "storage_url": storage_url, "asset_url": asset_url,
                "terms_version": TERMS_VERSION, "privacy_version": PRIVACY_VERSION,
                "privacy_contact_email": app.config["PRIVACY_CONTACT_EMAIL"]}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
