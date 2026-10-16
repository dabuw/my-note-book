import os
import sqlite3
import sys
from datetime import timedelta

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory
from flask_cors import CORS
from sqlalchemy import event
from sqlalchemy.engine import Engine

from src.models.user import db
from src.routes.user import user_bp
from src.routes.note import note_bp
from src.routes.translate import translate_bp
from src.routes.generate import generate_bp
from src.routes.tags import tags_bp
from src.routes.auth import auth_bp
from src.models.note import Note


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ('0', 'false', 'no', 'off', '')


app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# ---------------------------------------------------------------------------
# Session / cookie security
# ---------------------------------------------------------------------------
# No insecure fallback: the app must not start with a predictable signing key,
# because that key protects the "logged in" session cookie.
secret_key = os.environ.get('SECRET_KEY')
if not secret_key or len(secret_key) < 32:
    raise RuntimeError(
        'SECRET_KEY must be set to a random string of at least 32 characters '
        '(see .env.example). Refusing to start with a weak or missing key.'
    )

app.config['SECRET_KEY'] = secret_key
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Requires HTTPS; the Docker deployment is always served through Nginx + TLS.
app.config['SESSION_COOKIE_SECURE'] = _env_flag('SESSION_COOKIE_SECURE', True)
app.config['SESSION_COOKIE_NAME'] = 'notetaker_session'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
    days=int(os.environ.get('SESSION_LIFETIME_DAYS', '7'))
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# The SPA is served from the same origin as the API, so no CORS headers are
# needed by default. Set ALLOWED_ORIGINS (comma separated) only if you really
# need a different origin; the cookie session is never shared cross-origin.
_allowed_origins = [o.strip() for o in (os.environ.get('ALLOWED_ORIGINS') or '').split(',') if o.strip()]
if _allowed_origins:
    CORS(app, origins=_allowed_origins)

# ---------------------------------------------------------------------------
# Blueprints
# ---------------------------------------------------------------------------
app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(note_bp, url_prefix='/api')
app.register_blueprint(translate_bp, url_prefix='/api')
app.register_blueprint(generate_bp, url_prefix='/api')
app.register_blueprint(tags_bp)

# ---------------------------------------------------------------------------
# Database: prefer DATABASE_URL (e.g. Postgres), fallback to local SQLite
# ---------------------------------------------------------------------------
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres') and 'sslmode=' not in database_url:
        sep = '&' if '?' in database_url else '?'
        database_url = f"{database_url}{sep}sslmode=require"
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    ROOT_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    DB_PATH = os.environ.get('SQLITE_PATH') or os.path.join(ROOT_DIR, 'database', 'app.db')
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


@event.listens_for(Engine, 'connect')
def _sqlite_pragmas(dbapi_connection, connection_record):
    """WAL + busy timeout so concurrent readers do not block on the writer."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.execute('PRAGMA busy_timeout=5000')
        cursor.close()


db.init_app(app)
with app.app_context():
    db.create_all()


@app.route('/api/health')
def health_check():
    return {'status': 'healthy'}


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404


if __name__ == '__main__':
    # Development only. In production gunicorn imports `app` directly
    # (see gunicorn.conf.py) — never run this with debug=True behind Nginx.
    app.run(
        host=os.environ.get('HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', '5001')),
        debug=_env_flag('FLASK_DEBUG', False),
    )
