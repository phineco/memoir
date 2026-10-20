"""Flask 应用入口。"""
from flask import Flask, session

from config import Config
from models import User, get_session, init_db, remove_session
from views import bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY
    init_db(Config.DATABASE_URL)
    app.register_blueprint(bp)

    @app.teardown_appcontext
    def close_session(error=None):
        remove_session()

    @app.context_processor
    def inject_user():
        uid = session.get("user_id")
        me = get_session().query(User).filter_by(id=uid, del_flag=0).first() if uid else None
        from storage import storage_url
        return {"me": me, "storage_url": storage_url}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
