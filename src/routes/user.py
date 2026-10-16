"""Legacy user CRUD endpoints.

The application no longer has per-user accounts -- access is either "guest" or
the shared-password owner (see src/auth.py). These endpoints are kept only so
nothing that referenced them breaks, so every route now requires the owner
password. Without that, `/api/users` was an unauthenticated endpoint that let
anyone enumerate, create and delete rows in the users table.
"""

from flask import Blueprint, jsonify, request

from src.auth import login_required
from src.models.user import User, db

user_bp = Blueprint('user', __name__)


@user_bp.route('/users', methods=['GET'])
@login_required
def get_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users])


@user_bp.route('/users', methods=['POST'])
@login_required
def create_user():
    data = request.get_json(silent=True) or {}
    if not data.get('username') or not data.get('email'):
        return jsonify({'error': 'username and email are required'}), 400
    user = User(username=data['username'], email=data['email'])
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@user_bp.route('/users/<int:user_id>', methods=['GET'])
@login_required
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())


@user_bp.route('/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    user.username = data.get('username', user.username)
    user.email = data.get('email', user.email)
    db.session.commit()
    return jsonify(user.to_dict())


@user_bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return '', 204
