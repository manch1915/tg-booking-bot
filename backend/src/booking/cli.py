"""Admin tasks for a real deployment.

python -m booking.cli create-admin owner@example.com "Anna Petrova"
"""

import argparse
import asyncio
import getpass

from sqlalchemy import select

from booking.config import get_settings
from booking.domain.enums import AdminRole
from booking.infra.db.models import AdminUser
from booking.infra.db.session import make_engine, make_sessionmaker, transaction
from booking.services.auth import hash_password

MIN_PASSWORD = 10


async def create_admin(email: str, name: str, password: str) -> None:
    engine = make_engine(get_settings().database_url)
    async with transaction(make_sessionmaker(engine)) as session:
        existing = await session.scalar(select(AdminUser).where(AdminUser.email == email))
        if existing is not None:
            existing.password_hash = hash_password(password)
            existing.name = name
            print(f"Updated {email}")
        else:
            session.add(
                AdminUser(
                    email=email,
                    name=name,
                    password_hash=hash_password(password),
                    role=AdminRole.OWNER,
                )
            )
            print(f"Created {email}")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="booking.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser(
        "create-admin", help="create an owner account or reset its password"
    )
    admin.add_argument("email")
    admin.add_argument("name")
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD:
        raise SystemExit(f"Use at least {MIN_PASSWORD} characters")
    if password != getpass.getpass("Repeat: "):
        raise SystemExit("Passwords do not match")
    asyncio.run(create_admin(args.email.lower(), args.name, password))


if __name__ == "__main__":
    main()
