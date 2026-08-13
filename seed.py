"""Seed the database with test-user credentials for grading/demo purposes.
Run once: python seed.py
"""
from app import create_app
from extensions import db
from models import User

app = create_app()

with app.app_context():
    db.create_all()

    if not User.query.filter_by(email="a.boateng@nyakoa-shs.edu.gh").first():
        admin = User(
            name="Coordinator Ama Boateng",
            email="a.boateng@nyakoa-shs.edu.gh",
            role="admin",
            department="PLC Coordination",
            is_approved=True,
        )
        admin.set_password("AdminPass123")
        db.session.add(admin)

    if not User.query.filter_by(email="k.owusu@nyakoa-shs.edu.gh").first():
        teacher = User(
            name="Kwame Owusu",
            email="k.owusu@nyakoa-shs.edu.gh",
            role="teacher",
            department="Mathematics",
            is_approved=True,
        )
        teacher.set_password("TeacherPass123")
        db.session.add(teacher)

    db.session.commit()
    print("Seed complete.")
    print("Admin login:   a.boateng@nyakoa-shs.edu.gh / AdminPass123")
    print("Teacher login: k.owusu@nyakoa-shs.edu.gh / TeacherPass123")
