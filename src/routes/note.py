from flask import Blueprint, jsonify, request
from datetime import datetime, time, date

from src.auth import (
    client_ip,
    current_role,
    guest_note_limit,
    is_authenticated,
    serialize,
    visible_notes_query,
)
from src.models.note import Note, db

note_bp = Blueprint('note', __name__)


def _may_edit(note):
    """Guests may only touch the note they created; the owner may edit all."""
    if is_authenticated():
        return True
    ip = client_ip()
    return note.author_ip is not None and note.author_ip == ip


def _may_read(note):
    """Guests may read public notes plus the note they created themselves."""
    if is_authenticated():
        return True
    if note.is_public:
        return True
    ip = client_ip()
    return note.author_ip is not None and note.author_ip == ip


@note_bp.route('/notes', methods=['GET'])
def get_notes():
    """List notes visible to the current viewer, most recently updated first."""
    notes = visible_notes_query().order_by(Note.updated_at.desc()).all()
    return jsonify([serialize(note) for note in notes])


@note_bp.route('/notes', methods=['POST'])
def create_note():
    """Create a new note.

    Guest behaviour is driven by GUEST_NOTE_LIMIT:
      * 0  -> guest writing is switched off entirely (read-only showcase, used
              while the site is registered as a non-interactive service)
      * >0 -> a guest may create that many notes per IP

    Either way a guest can never publish one, so visitor content never becomes
    publicly readable UGC. The logged-in owner has no limit and controls the
    public flag explicitly.
    """
    try:
        data = request.get_json(silent=True)
        if not data or not data.get('title') or not data.get('content'):
            return jsonify({'error': 'Title and content are required'}), 400

        ip = client_ip()
        authenticated = is_authenticated()

        if not authenticated:
            limit = guest_note_limit()
            if limit == 0:
                return (
                    jsonify(
                        {
                            'error': 'guest_write_disabled',
                            'message': '本站为只读展示，创建笔记需要获得管理员权限',
                        }
                    ),
                    403,
                )
            existing = Note.query.filter_by(author_ip=ip).count()
            if existing >= limit:
                return (
                    jsonify(
                        {
                            'error': 'guest_limit_reached',
                            'message': '游客模式最多只能创建 %d 条笔记，需要获得管理员权限' % limit,
                        }
                    ),
                    403,
                )

        note = Note(title=data['title'], content=data['content'])
        note.set_tags(data.get('tags'))
        note.author_ip = None if authenticated else ip
        # Guests are never allowed to publish content.
        note.is_public = bool(data.get('is_public')) if authenticated else False

        event_date = data.get('event_date')
        if event_date:
            try:
                note.event_date = date.fromisoformat(event_date)
            except Exception:
                note.event_date = None

        event_time = data.get('event_time')
        if event_time:
            try:
                note.event_time = datetime.fromisoformat(event_time).time()
            except Exception:
                try:
                    parts = event_time.split(':')
                    h, m = int(parts[0]), int(parts[1])
                    s = int(parts[2]) if len(parts) > 2 else 0
                    note.event_time = time(hour=h, minute=m, second=s)
                except Exception:
                    note.event_time = None

        db.session.add(note)
        db.session.commit()
        return jsonify(serialize(note)), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@note_bp.route('/notes/search', methods=['GET'])
def search_notes():
    """Search notes by title or content, limited to what the viewer may read."""
    query = request.args.get('q', '')
    if not query:
        return jsonify([])

    notes = (
        visible_notes_query()
        .filter((Note.title.contains(query)) | (Note.content.contains(query)))
        .order_by(Note.updated_at.desc())
        .all()
    )
    return jsonify([serialize(note) for note in notes])


@note_bp.route('/notes/<int:note_id>', methods=['GET'])
def get_note(note_id):
    """Get a specific note, if the viewer is allowed to read it."""
    note = Note.query.get_or_404(note_id)
    if not _may_read(note):
        return jsonify({'error': 'not_found'}), 404
    return jsonify(serialize(note))


@note_bp.route('/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    """Update a specific note.

    Guests can only edit their own note and cannot flip it to public.
    """
    try:
        note = Note.query.get_or_404(note_id)
        if not _may_edit(note):
            return (
                jsonify(
                    {
                        'error': 'forbidden',
                        'message': '只能修改自己创建的笔记',
                    }
                ),
                403,
            )

        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        note.title = data.get('title', note.title)
        note.content = data.get('content', note.content)

        if 'tags' in data:
            note.set_tags(data.get('tags'))

        if 'event_date' in data:
            ed = data.get('event_date')
            if ed:
                try:
                    note.event_date = date.fromisoformat(ed)
                except Exception:
                    note.event_date = None
            else:
                note.event_date = None

        if 'event_time' in data:
            et = data.get('event_time')
            if et:
                try:
                    note.event_time = datetime.fromisoformat(et).time()
                except Exception:
                    try:
                        parts = et.split(':')
                        h, m = int(parts[0]), int(parts[1])
                        s = int(parts[2]) if len(parts) > 2 else 0
                        note.event_time = time(hour=h, minute=m, second=s)
                    except Exception:
                        note.event_time = None
            else:
                note.event_time = None

        # Only the owner may change visibility; guests stay private.
        if 'is_public' in data and is_authenticated():
            note.is_public = bool(data.get('is_public'))

        db.session.commit()
        return jsonify(serialize(note))
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@note_bp.route('/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """Delete a specific note. Guests may only delete their own note."""
    try:
        note = Note.query.get_or_404(note_id)
        if not _may_edit(note):
            return (
                jsonify(
                    {
                        'error': 'forbidden',
                        'message': '只能删除自己创建的笔记',
                    }
                ),
                403,
            )
        db.session.delete(note)
        db.session.commit()
        return '', 204
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
