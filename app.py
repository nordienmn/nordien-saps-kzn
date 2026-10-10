"""SAPS KZN demo: entry point. `python app.py` for a laptop, gunicorn on Cloud Run.

Demo only. Not a real 10111 service. A human stays in the loop.
"""
import os

from flask import Flask, jsonify, redirect, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from saps import api, security, service
from saps.config import Config
from saps.seed import seed
from saps.store import FirestorePersister, Store


def create_app(testing=False, store=None):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(
        SECRET_KEY=Config.SECRET_KEY,
        MAX_CONTENT_LENGTH=Config.MAX_BODY,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.environ.get("K_SERVICE")),  # true on Cloud Run, off on a laptop
        JSON_SORT_KEYS=False,
        TESTING=testing,
    )
    # Cloud Run terminates TLS in front of us; trust one proxy hop so URLs and client IPs are right.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ---- data
    if store is None:
        persister = None
        if Config.STORE == "firestore" and not testing:
            persister = FirestorePersister(Config.GCP_PROJECT, Config.FIRESTORE_PREFIX)
        store = Store(persister)
        store.load()
        if Config.SEED_ON_START and not store.all("cases") and not testing:
            seed(store)
    app.extensions["store"] = store

    # ---- limits (per client address, in memory; the app runs as a single instance)
    limiter = Limiter(get_remote_address, app=app, default_limits=["600 per minute"], storage_uri="memory://", enabled=not testing)
    app.extensions["limiter"] = limiter

    app.register_blueprint(api.bp)
    if Config.whatsapp_enabled():
        from saps import whatsapp  # imported only when configured, so the app runs without Twilio installed

        app.register_blueprint(whatsapp.bp)
        limiter.exempt(whatsapp.bp)

    for endpoint, rule in (("api.citizen_report", "20 per minute"), ("api.citizen_upload", "10 per minute"), ("api.call_start", "10 per minute"), ("api.login", "10 per minute"), ("api.admin_reset", "5 per minute")):
        app.view_functions[endpoint] = limiter.limit(rule)(app.view_functions[endpoint])

    app.after_request(security.apply_headers)

    # ---- pages (the pages hold no data; they call the API)
    def page(template):
        return render_template(template, demo=True)

    @app.get("/")
    @app.get("/citizen")
    def citizen():
        return page("citizen.html")

    @app.get("/desk")
    def desk():
        return page("desk.html")

    @app.get("/commissioner")
    def commissioner():
        return page("board.html")

    @app.get("/weather")
    def weather():
        return page("weather.html")

    @app.get("/unit")
    @app.get("/unit/<ap_id>")
    @app.get("/partner")
    def unit(ap_id=None):
        return page("unit.html")

    # old addresses keep working
    @app.get("/headoffice")
    @app.get("/brief")
    def to_board():
        return redirect("/commissioner", 302)

    @app.get("/municipality")
    @app.get("/flying")
    @app.get("/cluster")
    @app.get("/station")
    @app.get("/fcs")
    @app.get("/hold")
    @app.get("/ems")
    @app.get("/durban")
    @app.get("/umlazi")
    @app.get("/chatsworth")
    @app.get("/pmb")
    @app.get("/richards")
    def to_partner():
        return redirect("/unit", 302)

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "store": Config.STORE, "video": Config.video_enabled(), "whatsapp": Config.whatsapp_enabled()})

    @app.errorhandler(404)
    def not_found(_):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found."}), 404
        return render_template("error.html", code=404, message="That page does not exist."), 404

    @app.errorhandler(413)
    def too_big(_):
        return jsonify({"error": "That upload is too large."}), 413

    @app.errorhandler(429)
    def too_many(_):
        return jsonify({"error": "Too many attempts. Please wait a minute."}), 429

    @app.errorhandler(500)
    def broken(_):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Something went wrong on our side. Please try again."}), 500
        return render_template("error.html", code=500, message="Something went wrong. Please try again."), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
