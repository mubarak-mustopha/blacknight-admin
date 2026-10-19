import os

from dotenv import load_dotenv
from passlib.hash import bcrypt
from sqlalchemy import select

import db 

load_dotenv()
username = os.environ["ADMIN_USERNAME"]
hash_password = bcrypt.hash(os.environ["ADMIN_PASSWORD"])

admin_user = db.User(username=username, hash_password=hash_password)
SessionLocal = db.get_session_factory()

with SessionLocal() as session:
    with session.begin():
        user_exists = select(1).where(select(db.User.id).exists())
        result = session.execute(user_exists).scalar_one_or_none()
        if result is None:
            session.add(admin_user)
        else:
            print("An admin user already exists")
