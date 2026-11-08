from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, time, timezone
import json
from src.models.user import db


def iso_utc(value):
    """Serialise a naive-UTC datetime as an explicit UTC ISO 8601 string.

    The columns store `datetime.utcnow()`, i.e. UTC without a timezone marker.
    A browser parsing "2026-10-16T10:16:21" treats it as *local* time, which
    skews every relative date by the client's UTC offset. Appending the "Z"
    makes the client convert it properly instead.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    # store tags as JSON string in text column for compatibility
    tags = db.Column(db.Text, nullable=True)
    event_date = db.Column(db.Date, nullable=True)
    event_time = db.Column(db.Time, nullable=True)
    # IP that created the note when it came from a guest; NULL for the owner.
    author_ip = db.Column(db.String(45), nullable=True, index=True)
    # Only notes flagged public are readable by other visitors.
    # Guests can never set this to True.
    is_public = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    # When set, the note is readable at /s/<token> without a password.
    share_token = db.Column(db.String(64), nullable=True, unique=True, index=True)
    # Owner-only: pinned notes sort above the rest.
    pinned = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    # AI generated summary, shown above the content (never mixed into it).
    summary = db.Column(db.Text, nullable=True)
    # AI generated checklist, stored as a JSON array of {"text", "done"}.
    todos = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Note {self.title}>'

    def get_tags(self):
        if not self.tags:
            return []
        try:
            # 如果已经是列表，直接返回
            if isinstance(self.tags, list):
                return self.tags
            # 如果是字符串，尝试解析JSON
            return json.loads(self.tags)
        except Exception:
            # fallback: comma separated string
            if isinstance(self.tags, str):
                return [t.strip() for t in self.tags.split(',') if t.strip()]
            else:
                return []

    def set_tags(self, tags_list):
        try:
            if tags_list is None:
                self.tags = None
            else:
                # ensure it's a list
                if isinstance(tags_list, str):
                    tags_list = [t.strip() for t in tags_list.split(',') if t.strip()]
                self.tags = json.dumps(tags_list)
        except Exception:
            self.tags = None

    def get_todos(self):
        """Return the AI checklist as a list of {text, done} dicts."""
        if not self.todos:
            return []
        try:
            data = json.loads(self.todos)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        result = []
        for item in data:
            if isinstance(item, dict):
                result.append({'text': str(item.get('text', '')), 'done': bool(item.get('done', False))})
            elif isinstance(item, str):
                result.append({'text': item, 'done': False})
        return result

    def set_todos(self, todos):
        """Persist a list of {text, done} dicts (or plain strings)."""
        if todos is None:
            self.todos = None
            return
        cleaned = []
        for item in todos:
            if isinstance(item, dict):
                text = str(item.get('text', '')).strip()
                if text:
                    cleaned.append({'text': text, 'done': bool(item.get('done', False))})
            elif isinstance(item, str) and item.strip():
                cleaned.append({'text': item.strip(), 'done': False})
        self.todos = json.dumps(cleaned, ensure_ascii=False) if cleaned else None

    def to_dict(self, viewer_ip=None, role='guest'):
        """Serialise the note for a viewer.

        `can_edit` tells the frontend whether the current viewer is allowed to
        modify or delete this note. Guests may only edit the note they created
        themselves; the logged-in owner may edit everything.
        """
        if role == 'user':
            can_edit = True
        else:
            can_edit = self.author_ip is not None and self.author_ip == viewer_ip

        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'tags': self.get_tags(),
            'event_date': self.event_date.isoformat() if self.event_date else None,
            'event_time': self.event_time.isoformat() if self.event_time else None,
            'is_public': bool(self.is_public),
            'shared': bool(self.share_token),
            'summary': self.summary or '',
            'todos': self.get_todos(),
            'pinned': bool(self.pinned),
            'can_edit': can_edit,
            'created_at': iso_utc(self.created_at),
            'updated_at': iso_utc(self.updated_at)
        }

