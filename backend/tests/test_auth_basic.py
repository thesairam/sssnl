import os
import sys
import json
import pytest

# Ensure package import works when running tests from backend/
THIS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Force SQLite for tests
os.environ['DB_URI'] = 'sqlite:///:memory:'

from app import app, init_users_db  # noqa: E402


@pytest.fixture()
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        with app.app_context():
            try:
                init_users_db()
            except Exception:
                pass
        yield c


def test_healthz(client):
    rv = client.get('/healthz')
    assert rv.status_code == 200


def test_signup_login_me(client):
    rv = client.post('/api/auth/signup', json={'username': 'u1', 'password': 'p1'})
    assert rv.status_code == 200
    rv = client.post('/api/auth/login', json={'username': 'u1', 'password': 'p1'})
    assert rv.status_code == 200
    # session cookie should allow /api/auth/me
    rv = client.get('/api/auth/me')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['user']['username'] == 'u1'
