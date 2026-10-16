from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, time
import json
from src.models.user import db


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
            'can_edit': can_edit,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

