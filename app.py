from flask import Flask, render_template
from flask_wtf import CSRFProtect

from config import Config
from extensions import db, login_manager
from models import User

csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.teacher import teacher_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teacher_bp)

    @app.route("/")
    def index():
        return render_template("index.html")

    # --- error handlers (NFR: graceful error handling) ---
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/error.html", code=403,
                                message="You don't have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/error.html", code=404,
                                message="That page doesn't exist."), 404

    @app.errorhandler(401)
    def unauthorized(e):
        return render_template("errors/error.html", code=401,
                                message="Please log in to continue."), 401

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/error.html", code=500,
                                message="Something went wrong on our end."), 500

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
