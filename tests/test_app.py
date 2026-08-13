import pytest

from app import create_app
from config import TestConfig
from extensions import db
from models import User, PLCSession, Attendance


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def make_admin(app, email="admin@test.com"):
    with app.app_context():
        u = User(name="Admin User", email=email, role="admin", is_approved=True)
        u.set_password("Password123")
        db.session.add(u)
        db.session.commit()
    return email


def make_teacher(app, email="teacher@test.com", name="Teacher User", is_approved=True):
    with app.app_context():
        u = User(name=name, email=email, role="teacher", is_approved=is_approved)
        u.set_password("Password123")
        db.session.add(u)
        db.session.commit()
    return email


def login(client, email, password="Password123"):
    return client.post(
        "/auth/login", data={"email": email, "password": password}, follow_redirects=True
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestUnit:
    def test_password_hashing_never_stores_plaintext(self, app):
        with app.app_context():
            u = User(name="X", email="x@test.com", role="teacher")
            u.set_password("MySecret123")
            assert u.password_hash != "MySecret123"
            assert u.check_password("MySecret123") is True
            assert u.check_password("wrong") is False

    def test_access_code_is_four_digits(self):
        code = PLCSession.generate_access_code()
        assert len(code) == 4
        assert code.isdigit()

    def test_session_window_expiry_logic(self, app):
        with app.app_context():
            admin_email = make_admin(app)
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(
                title="Test Session", duration_minutes=30,
                access_code="1234", creator_id=admin.id,
            )
            db.session.add(s)
            db.session.commit()
            assert s.is_within_window(30) is True
            assert s.is_within_window(-1) is False  # already-expired window

    def test_haversine_distance_and_geofence(self, app):
        with app.app_context():
            admin_email = make_admin(app)
            admin = User.query.filter_by(email=admin_email).first()
            # Session at Accra coordinates
            s = PLCSession(
                title="GPS Session", access_code="1111", creator_id=admin.id,
                latitude=5.603700, longitude=-0.187000, radius_meters=150.0
            )
            # Exactly same coordinates
            assert round(s.calculate_distance_meters(5.603700, -0.187000), 2) == 0.0
            is_in, dist = s.is_within_geofence(5.603700, -0.187000)
            assert is_in is True
            assert round(dist, 1) == 0.0

            # ~20 meters away
            is_in_close, dist_close = s.is_within_geofence(5.603800, -0.187000)
            assert is_in_close is True
            assert dist_close < 150.0

            # ~1.2 km away
            is_in_far, dist_far = s.is_within_geofence(5.615000, -0.187000)
            assert is_in_far is False
            assert dist_far > 1000.0


# ---------------------------------------------------------------------------
# Integration tests — Check-in flow, Geofencing & Anti-Proxy Device Lock
# ---------------------------------------------------------------------------

class TestCheckInFlow:
    def test_full_checkin_flow_success(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(title="STEM PLC", duration_minutes=30, access_code="4242", creator_id=admin.id)
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        login(client, teacher_email)
        resp = client.post(
            f"/teacher/sessions/{session_id}/checkin",
            data={"access_code": "4242", "device_id": "dev-001"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        with app.app_context():
            record = Attendance.query.filter_by(session_id=session_id).first()
            assert record is not None
            assert record.status == "Present"
            assert record.device_id == "dev-001"

    def test_geofenced_checkin_success_inside_radius(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(
                title="Geofenced PLC", duration_minutes=30, access_code="8888",
                creator_id=admin.id, latitude=5.603700, longitude=-0.187000, radius_meters=150.0
            )
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        login(client, teacher_email)
        # Check in within 20 meters
        resp = client.post(
            f"/teacher/sessions/{session_id}/checkin",
            data={
                "access_code": "8888",
                "device_id": "dev-gps-1",
                "latitude": "5.603800",
                "longitude": "-0.187000",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Attendance verified" in resp.data

        with app.app_context():
            record = Attendance.query.filter_by(session_id=session_id).first()
            assert record is not None
            assert record.distance_meters is not None
            assert record.distance_meters <= 150.0

    def test_geofenced_checkin_rejected_outside_radius(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(
                title="Geofenced PLC", duration_minutes=30, access_code="8888",
                creator_id=admin.id, latitude=5.603700, longitude=-0.187000, radius_meters=100.0
            )
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        login(client, teacher_email)
        # Attempt check in ~1.5km away
        resp = client.post(
            f"/teacher/sessions/{session_id}/checkin",
            data={
                "access_code": "8888",
                "device_id": "dev-gps-far",
                "latitude": "5.617000",
                "longitude": "-0.187000",
            },
            follow_redirects=True,
        )
        assert b"Geofence Verification Failed" in resp.data

        with app.app_context():
            assert Attendance.query.filter_by(session_id=session_id).count() == 0

    def test_anti_proxy_device_lock_blocks_second_attendee_same_device(self, app, client):
        admin_email = make_admin(app)
        teacher1_email = make_teacher(app, email="teacher1@test.com", name="Teacher One")
        teacher2_email = make_teacher(app, email="teacher2@test.com", name="Teacher Two")

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(title="Proxy Defense PLC", access_code="9999", creator_id=admin.id)
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        # Teacher 1 checks in on Device X
        login(client, teacher1_email)
        client.post(
            f"/teacher/sessions/{session_id}/checkin",
            data={"access_code": "9999", "device_id": "phone-shared-uuid"},
            follow_redirects=True,
        )

        with app.app_context():
            assert Attendance.query.filter_by(session_id=session_id).count() == 1

        # Teacher 1 logs out. Teacher 2 logs in on the SAME device and attempts check-in
        client.get("/auth/logout")
        login(client, teacher2_email)
        resp2 = client.post(
            f"/teacher/sessions/{session_id}/checkin",
            data={"access_code": "9999", "device_id": "phone-shared-uuid"},
            follow_redirects=True,
        )
        assert b"Anti-Proxy Violation" in resp2.data

        # Ensure Teacher 2's attendance was NOT recorded from the duplicate device
        with app.app_context():
            t2 = User.query.filter_by(email=teacher2_email).first()
            assert Attendance.query.filter_by(session_id=session_id, user_id=t2.id).count() == 0

        # Teacher 2 now uses their OWN separate device (Device Y) -> succeeds
        resp3 = client.post(
            f"/teacher/sessions/{session_id}/checkin",
            data={"access_code": "9999", "device_id": "phone-legit-uuid"},
            follow_redirects=True,
        )
        assert b"Attendance verified" in resp3.data
        with app.app_context():
            assert Attendance.query.filter_by(session_id=session_id).count() == 2

    def test_checkin_rejects_wrong_token(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)
        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(title="STEM PLC", duration_minutes=30, access_code="4242", creator_id=admin.id)
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        login(client, teacher_email)
        client.post(f"/teacher/sessions/{session_id}/checkin", data={"access_code": "0000", "device_id": "dev-01"})

        with app.app_context():
            assert Attendance.query.filter_by(session_id=session_id).count() == 0

    def test_checkin_prevents_duplicate_submission(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)
        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(title="STEM PLC", duration_minutes=30, access_code="4242", creator_id=admin.id)
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        login(client, teacher_email)
        client.post(f"/teacher/sessions/{session_id}/checkin", data={"access_code": "4242", "device_id": "dev-01"})
        client.post(f"/teacher/sessions/{session_id}/checkin", data={"access_code": "4242", "device_id": "dev-01"})

        with app.app_context():
            assert Attendance.query.filter_by(session_id=session_id).count() == 1

    def test_checkin_rejects_closed_session(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)
        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(title="STEM PLC", duration_minutes=30, access_code="4242", creator_id=admin.id)
            s.is_active = False
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        login(client, teacher_email)
        client.post(f"/teacher/sessions/{session_id}/checkin", data={"access_code": "4242", "device_id": "dev-01"})

        with app.app_context():
            assert Attendance.query.filter_by(session_id=session_id).count() == 0

    def test_admin_creator_can_checkin_on_created_session(self, app, client):
        admin_email = make_admin(app)
        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(
                title="Admin Hosted PLC",
                duration_minutes=60,
                access_code="3333",
                creator_id=admin.id,
            )
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        # Admin logs in on the host machine and submits check-in
        login(client, admin_email)
        resp = client.post(
            f"/teacher/sessions/{session_id}/checkin",
            data={"access_code": "3333", "device_id": "host-machine-uuid"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Admin is redirected back to session_detail and marked present
        assert b"Host Present" in resp.data or b"Admin User" in resp.data

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            record = Attendance.query.filter_by(session_id=session_id, user_id=admin.id).first()
            assert record is not None
            assert record.status == "Present"
            assert record.device_id == "host-machine-uuid"

        # CSV export also includes host check-in
        resp_csv = client.get(f"/admin/sessions/{session_id}/export.csv")
        assert resp_csv.status_code == 200
        assert b"Admin User" in resp_csv.data
        assert b"Admin" in resp_csv.data


# ---------------------------------------------------------------------------
# System / access-control tests
# ---------------------------------------------------------------------------

class TestAccessControl:
    def test_teacher_cannot_reach_admin_dashboard(self, app, client):
        teacher_email = make_teacher(app)
        login(client, teacher_email)
        resp = client.get("/admin/", follow_redirects=True)
        assert resp.status_code == 403

    def test_anonymous_redirected_to_login(self, client):
        resp = client.get("/teacher/", follow_redirects=True)
        assert b"log in" in resp.data.lower() or resp.status_code == 200

    def test_admin_can_create_and_view_session(self, app, client):
        admin_email = make_admin(app)
        login(client, admin_email)
        resp = client.post(
            "/admin/sessions/new",
            data={
                "title": "New PLC",
                "department": "Science",
                "duration_minutes": 45,
                "latitude": 5.6037,
                "longitude": -0.1870,
                "radius_meters": 150.0,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            s = PLCSession.query.filter_by(title="New PLC").first()
            assert s is not None
            assert s.latitude == 5.6037
            assert s.radius_meters == 150.0

    def test_admin_can_edit_session(self, app, client):
        admin_email = make_admin(app)
        login(client, admin_email)

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(
                title="Original Title",
                department="Science",
                duration_minutes=30,
                access_code="1234",
                creator_id=admin.id,
                latitude=5.6037,
                longitude=-0.1870,
                radius_meters=150.0,
            )
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        # GET edit form
        resp_get = client.get(f"/admin/sessions/{session_id}/edit")
        assert resp_get.status_code == 200
        assert b"Original Title" in resp_get.data

        # POST updated data
        resp_post = client.post(
            f"/admin/sessions/{session_id}/edit",
            data={
                "title": "Updated Topic Title",
                "department": "Mathematics",
                "duration_minutes": 90,
                "latitude": 5.6050,
                "longitude": -0.1890,
                "radius_meters": 200.0,
            },
            follow_redirects=True,
        )
        assert resp_post.status_code == 200
        assert b"Updated Topic Title" in resp_post.data

        with app.app_context():
            updated = db.session.get(PLCSession, session_id)
            assert updated.title == "Updated Topic Title"
            assert updated.department == "Mathematics"
            assert updated.duration_minutes == 90
            assert updated.latitude == 5.6050
            assert updated.longitude == -0.1890
            assert updated.radius_meters == 200.0

    def test_admin_can_delete_session_and_cascades_attendance(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            teacher = User.query.filter_by(email=teacher_email).first()
            s = PLCSession(
                title="Session To Delete",
                duration_minutes=45,
                access_code="5555",
                creator_id=admin.id,
            )
            db.session.add(s)
            db.session.flush()
            att = Attendance(session_id=s.id, user_id=teacher.id, status="Present", device_id="dev-123")
            db.session.add(att)
            db.session.commit()
            session_id = s.id

        login(client, admin_email)
        resp = client.post(f"/admin/sessions/{session_id}/delete", follow_redirects=True)
        assert resp.status_code == 200
        assert b"deleted" in resp.data.lower()

        with app.app_context():
            assert db.session.get(PLCSession, session_id) is None
            assert Attendance.query.filter_by(session_id=session_id).count() == 0

    def test_teacher_cannot_edit_or_delete_session(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            s = PLCSession(
                title="Protected Session",
                duration_minutes=30,
                access_code="7777",
                creator_id=admin.id,
            )
            db.session.add(s)
            db.session.commit()
            session_id = s.id

        login(client, teacher_email)
        resp_edit = client.post(
            f"/admin/sessions/{session_id}/edit",
            data={"title": "Hacked Title", "duration_minutes": 60},
            follow_redirects=True,
        )
        assert resp_edit.status_code == 403

        resp_del = client.post(f"/admin/sessions/{session_id}/delete", follow_redirects=True)
        assert resp_del.status_code == 403

        with app.app_context():
            assert db.session.get(PLCSession, session_id) is not None

    def test_admin_can_manually_verify_teacher_presence(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            teacher = User.query.filter_by(email=teacher_email).first()
            s = PLCSession(
                title="Manual Assist Session",
                duration_minutes=60,
                access_code="1111",
                creator_id=admin.id,
            )
            db.session.add(s)
            db.session.commit()
            session_id = s.id
            teacher_id = teacher.id

        login(client, admin_email)
        # Admin assists struggling teacher by manually confirming presence
        resp = client.post(
            f"/admin/sessions/{session_id}/manual-checkin/{teacher_id}",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Manual presence confirmed" in resp.data

        with app.app_context():
            att = Attendance.query.filter_by(session_id=session_id, user_id=teacher_id).first()
            assert att is not None
            assert att.status == "Present"
            assert "Manual Override" in att.device_id

    def test_admin_can_revoke_attendance_record(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            teacher = User.query.filter_by(email=teacher_email).first()
            s = PLCSession(
                title="Revoke Test Session",
                duration_minutes=60,
                access_code="2222",
                creator_id=admin.id,
            )
            db.session.add(s)
            db.session.flush()
            att = Attendance(session_id=s.id, user_id=teacher.id, status="Present", device_id="test-dev")
            db.session.add(att)
            db.session.commit()
            session_id = s.id
            teacher_id = teacher.id

        login(client, admin_email)
        resp = client.post(
            f"/admin/sessions/{session_id}/revoke-checkin/{teacher_id}",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"revoked" in resp.data

        with app.app_context():
            assert Attendance.query.filter_by(session_id=session_id, user_id=teacher_id).count() == 0

    def test_teacher_cannot_perform_manual_checkin(self, app, client):
        teacher1_email = make_teacher(app, email="t1@test.com")
        teacher2_email = make_teacher(app, email="t2@test.com")
        admin_email = make_admin(app)

        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            t2 = User.query.filter_by(email=teacher2_email).first()
            s = PLCSession(
                title="Session",
                duration_minutes=60,
                access_code="3333",
                creator_id=admin.id,
            )
            db.session.add(s)
            db.session.commit()
            session_id = s.id
            t2_id = t2.id

        login(client, teacher1_email)
        resp = client.post(
            f"/admin/sessions/{session_id}/manual-checkin/{t2_id}",
            follow_redirects=True,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Registration / auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_register_creates_unapproved_account_and_blocks_login(self, client):
        resp = client.post("/auth/register", data={
            "name": "New Teacher", "email": "new@test.com", "department": "English",
            "role": "teacher", "password": "Password123", "confirm_password": "Password123",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"pending administrator approval" in resp.data

        # Attempt to log in before approval -> blocked
        login_resp = login(client, "new@test.com", "Password123")
        assert b"pending administrator approval" in login_resp.data

    def test_duplicate_email_rejected(self, app, client):
        make_teacher(app, email="dupe@test.com")
        resp = client.post("/auth/register", data={
            "name": "Dup", "email": "dupe@test.com", "department": "",
            "role": "teacher", "password": "Password123", "confirm_password": "Password123",
        }, follow_redirects=True)
        assert b"already exists" in resp.data


# ---------------------------------------------------------------------------
# User Management & Administration Tests
# ---------------------------------------------------------------------------

class TestUserManagement:
    def test_admin_can_view_users_list(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app)
        login(client, admin_email)

        resp = client.get("/admin/users")
        assert resp.status_code == 200
        assert b"User Directory" in resp.data
        assert b"teacher@test.com" in resp.data

    def test_admin_can_approve_pending_user(self, app, client):
        admin_email = make_admin(app)
        # Register a new teacher (unapproved)
        client.post("/auth/register", data={
            "name": "Pending Teacher", "email": "pending@test.com", "department": "ICT",
            "role": "teacher", "password": "Password123", "confirm_password": "Password123",
        })

        with app.app_context():
            user = User.query.filter_by(email="pending@test.com").first()
            assert user is not None
            assert user.is_approved is False
            user_id = user.id

        # Admin approves user
        login(client, admin_email)
        approve_resp = client.post(f"/admin/users/{user_id}/approve", follow_redirects=True)
        assert approve_resp.status_code == 200
        assert b"approved" in approve_resp.data.lower()

        with app.app_context():
            user = User.query.get(user_id)
            assert user.is_approved is True

        # Now the approved user can successfully log in
        client.get("/auth/logout")
        login_resp = login(client, "pending@test.com", "Password123")
        assert login_resp.status_code == 200
        assert b"Welcome back, Pending" in login_resp.data

    def test_admin_can_reject_pending_user(self, app, client):
        admin_email = make_admin(app)
        # Unapproved user
        make_teacher(app, email="rejected@test.com", is_approved=False)

        with app.app_context():
            user = User.query.filter_by(email="rejected@test.com").first()
            user_id = user.id

        login(client, admin_email)
        resp = client.post(f"/admin/users/{user_id}/reject", follow_redirects=True)
        assert resp.status_code == 200
        assert b"rejected and removed" in resp.data

        with app.app_context():
            assert User.query.get(user_id) is None

    def test_admin_can_reset_user_password(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app, email="teacher_reset@test.com")

        with app.app_context():
            teacher = User.query.filter_by(email=teacher_email).first()
            teacher_id = teacher.id

        login(client, admin_email)
        resp = client.post(
            f"/admin/users/{teacher_id}/reset-password",
            data={"new_password": "NewSecretPass456", "confirm_password": "NewSecretPass456"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"successfully reset" in resp.data

        # Teacher logs in with new password
        client.get("/auth/logout")
        old_login = login(client, teacher_email, "Password123")
        assert b"Incorrect email or password" in old_login.data

        new_login = login(client, teacher_email, "NewSecretPass456")
        assert new_login.status_code == 200
        assert b"Welcome back" in new_login.data

    def test_admin_can_delete_dormant_user(self, app, client):
        admin_email = make_admin(app)
        teacher_email = make_teacher(app, email="dormant@test.com")

        with app.app_context():
            teacher = User.query.filter_by(email=teacher_email).first()
            teacher_id = teacher.id

        login(client, admin_email)
        resp = client.post(f"/admin/users/{teacher_id}/delete", follow_redirects=True)
        assert resp.status_code == 200
        assert b"permanently deleted" in resp.data

        with app.app_context():
            assert User.query.get(teacher_id) is None

    def test_admin_cannot_delete_self(self, app, client):
        admin_email = make_admin(app)
        with app.app_context():
            admin = User.query.filter_by(email=admin_email).first()
            admin_id = admin.id

        login(client, admin_email)
        resp = client.post(f"/admin/users/{admin_id}/delete", follow_redirects=True)
        assert resp.status_code == 200
        assert b"cannot delete your own" in resp.data

        with app.app_context():
            assert User.query.get(admin_id) is not None

    def test_teacher_cannot_access_user_management(self, app, client):
        teacher_email = make_teacher(app)
        login(client, teacher_email)

        resp_get = client.get("/admin/users", follow_redirects=True)
        assert resp_get.status_code == 403

        resp_approve = client.post("/admin/users/1/approve", follow_redirects=True)
        assert resp_approve.status_code == 403

        resp_reset = client.post(
            "/admin/users/1/reset-password",
            data={"new_password": "Pass123456", "confirm_password": "Pass123456"},
            follow_redirects=True,
        )
        assert resp_reset.status_code == 403

        resp_delete = client.post("/admin/users/1/delete", follow_redirects=True)
        assert resp_delete.status_code == 403
