import os
import sqlite3
import sys
from datetime import timedelta

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, jsonify, render_template_string, request, send_from_directory
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import event
from sqlalchemy.engine import Engine

from src.models.user import db
from src.routes.user import user_bp
from src.routes.note import note_bp
from src.routes.translate import translate_bp
from src.routes.generate import generate_bp
from src.routes.tags import tags_bp
from src.routes.ai import ai_bp
from src.routes.auth import auth_bp
from src.models.note import Note


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ('0', 'false', 'no', 'off', '')


app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Behind the host Nginx: honour X-Forwarded-Proto/Host so generated absolute
# URLs (e.g. share links) use https:// and the public hostname.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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
app.register_blueprint(ai_bp, url_prefix='/api')
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


def _ensure_note_columns():
    """Add columns introduced after the first deployment.

    `create_all()` only creates missing tables, so an existing SQLite database
    needs an explicit ALTER. The statements are idempotent and also work on
    Postgres, which keeps the migration path identical on both backends.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if 'note' not in inspector.get_table_names():
        return
    existing = {column['name'] for column in inspector.get_columns('note')}

    with db.engine.begin() as connection:
        if 'share_token' not in existing:
            connection.execute(text('ALTER TABLE note ADD COLUMN share_token VARCHAR(64)'))
        if 'pinned' not in existing:
            connection.execute(
                text('ALTER TABLE note ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT 0')
            )
        if 'summary' not in existing:
            connection.execute(text('ALTER TABLE note ADD COLUMN summary TEXT'))
        if 'todos' not in existing:
            connection.execute(text('ALTER TABLE note ADD COLUMN todos TEXT'))
        connection.execute(
            text('CREATE UNIQUE INDEX IF NOT EXISTS ix_note_share_token ON note (share_token)')
        )


db.init_app(app)
with app.app_context():
    db.create_all()
    _ensure_note_columns()




SHARE_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ note.title }} · NoteTaker</title>
<style>
  :root { color-scheme: light; }
  body { margin:0; padding:48px 20px; background:#f6f1e3; color:#1f2a24;
         font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',Arial,sans-serif; }
  .card { max-width:720px; margin:0 auto; background:#fff; border-radius:16px; padding:36px 40px;
          box-shadow:0 10px 32px rgba(120,100,50,.12); }
  h1 { margin:0 0 8px; font-size:26px; color:#0f7a54; }
  .meta { margin:0 0 22px; font-size:13px; color:#8a9790; }
  .block { margin:0 0 20px; padding:14px 16px; border:1px solid #e6ebe8; border-radius:12px; background:#fbfdfb; }
  .block-title { margin:0 0 8px; font-size:12px; font-weight:700; color:#0f7a54; letter-spacing:.2px; }
  .summary { margin:0; font-size:14px; line-height:1.75; color:#374151; white-space:pre-wrap; }
  .content { white-space:pre-wrap; line-height:1.85; font-size:15px; }
  .todo { display:flex; align-items:flex-start; gap:10px; padding:4px 0; font-size:14px; line-height:1.6; cursor:pointer; }
  .todo input { width:17px; height:17px; margin-top:3px; accent-color:#0f7a54; cursor:pointer; }
  .todo.done span { color:#9aa0a6; text-decoration:line-through; }
  .tags { margin-top:24px; display:flex; flex-wrap:wrap; gap:8px; }
  .tag { padding:3px 10px; border-radius:999px; background:#eaf6f0; color:#0f7a54; font-size:12px; }
  .foot { max-width:720px; margin:20px auto 0; text-align:center; font-size:12px; color:#9aa0a6; }
  .foot a { color:#0f7a54; text-decoration:none; }
  .hint { margin:10px 0 0; font-size:11px; color:#9aa0a6; }
</style>
</head>
<body data-token="{{ note.share_token }}">
  <article class="card">
    <h1>{{ note.title }}</h1>
    <p class="meta">{{ note.event_date or (note.updated_at.strftime('%Y-%m-%d') if note.updated_at else '') }}{% if note.event_time %} {{ note.event_time.strftime('%H:%M') }}{% endif %} · 来自 NoteTaker 的分享笔记</p>

    {% if note.summary %}
    <section class="block">
      <p class="block-title">📝 AI 摘要</p>
      <p class="summary">{{ note.summary }}</p>
    </section>
    {% endif %}

    <div class="content">{{ note.content }}</div>

    {% if todos %}
    <section class="block" style="margin-top:22px;">
      <p class="block-title">✅ 待办清单</p>
      {% for todo in todos %}
      <label class="todo {% if todo.done %}done{% endif %}">
        <input type="checkbox" data-index="{{ loop.index0 }}" {% if todo.done %}checked{% endif %}>
        <span>{{ todo.text }}</span>
      </label>
      {% endfor %}
      <p class="hint">勾选会同步给持有这个链接的人</p>
    </section>
    {% endif %}

    {% if tags %}<div class="tags">{% for tag in tags %}<span class="tag">#{{ tag }}</span>{% endfor %}</div>{% endif %}
  </article>
  <p class="foot">由 <a href="https://notes.dabuw.online">NoteTaker</a> 分享 · 只读页面</p>

  <script>
    (function () {
      var token = document.body.getAttribute('data-token');
      document.querySelectorAll('.todo input[type=checkbox]').forEach(function (cb) {
        cb.addEventListener('change', function () {
          var index = Number(cb.getAttribute('data-index'));
          cb.disabled = true;
          fetch('/s/' + token + '/todos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: index, done: cb.checked })
          }).then(function (r) {
            if (!r.ok) throw new Error('failed');
            cb.closest('.todo').classList.toggle('done', cb.checked);
          }).catch(function () {
            cb.checked = !cb.checked;
            alert('保存失败，请稍后重试');
          }).finally(function () {
            cb.disabled = false;
          });
        });
      });
    })();
  </script>
</body>
</html>"""



@app.route('/s/<token>')
def shared_note(token):
    """Public read-only view of a single shared note."""
    from src.models.note import Note

    note = Note.query.filter_by(share_token=token).first()
    if note is None:
        return '分享链接已失效', 404
    return render_template_string(SHARE_PAGE, note=note, tags=note.get_tags(), todos=note.get_todos())


@app.route('/s/<token>/todos', methods=['POST'])
def shared_todo_toggle(token):
    """Tick a checklist item from a shared page.

    Anyone holding the link may tick items; the change is written back to the
    note so the owner and other readers see the same state.
    """
    from src.models.note import Note

    note = Note.query.filter_by(share_token=token).first()
    if note is None:
        return jsonify({'error': 'not_found'}), 404

    data = request.get_json(silent=True) or {}
    index = data.get('index')
    done = bool(data.get('done'))

    todos = note.get_todos()
    if not isinstance(index, int) or index < 0 or index >= len(todos):
        return jsonify({'error': 'invalid_index'}), 400

    todos[index]['done'] = done
    note.set_todos(todos)
    db.session.commit()
    return jsonify({'todos': note.get_todos()})


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
