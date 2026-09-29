#!/usr/bin/env python
"""Register the test user for browser verification if it doesn't exist."""

import sys
sys.path.insert(0, '/'.join(__file__.split('/')[:-2]))

from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.auth.passwords import hash_password
from sqlalchemy import select

db = SessionLocal()
email = "asha@example.com"
password = "strong-password"

# Check if user exists
existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

if existing:
    print(f"User {email} already exists.")
else:
    # Get the Learner role
    learner_role = db.execute(select(Role).where(Role.name == "Learner")).scalar_one_or_none()
    if not learner_role:
        print("Learner role not found. Creating it.")
        learner_role = Role(name="Learner")
        db.add(learner_role)
        db.commit()
    
    # Create the user
    hashed = hash_password(password)
    user = User(
        email=email,
        password_hash=hashed,
        full_name="Asha Kumar",
        role_id=learner_role.id
    )
    db.add(user)
    db.commit()
    print(f"User {email} created successfully with role_id={learner_role.id}")

db.close()
