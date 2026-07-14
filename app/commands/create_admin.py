# app/commands/create_admin.py

import asyncio
from getpass import getpass

from sqlalchemy import select

from app.database import async_session_maker
from app.models import User
from app.auth import hash_password


async def main():
    email = input("Email: ").strip()
    password = getpass("Password: ")

    async with async_session_maker() as db:
        existing = await db.scalar(
            select(User).where(User.email == email)
        )

        if existing:
            print("User already exists")
            return

        admin = User(
            email=email,
            hashed_password=hash_password(password),
            role="admin"
        )

        db.add(admin)
        await db.commit()

        print("Admin created")


if __name__ == "__main__":
    asyncio.run(main())