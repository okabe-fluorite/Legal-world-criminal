"""Grant an existing local user a student/teacher/admin role.

This is an explicit operator action. It does not create users, send messages,
or accept a role claim from the browser.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from src.core.database import Base, create_database_engine, create_session_factory, get_db_session
from src.core.models import User
from src.core.role_service import VALID_USER_ROLES, grant_user_role


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=sorted(VALID_USER_ROLES), required=True)
    parser.add_argument("--granted-by", default="local-operator-cli")
    args = parser.parse_args()

    engine = create_database_engine()
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with get_db_session(factory) as session:
        user = session.scalar(select(User).where(User.email == args.email.strip().lower()))
        if user is None:
            raise SystemExit("user account not found; register the account first")
        record = grant_user_role(
            session=session,
            user=user,
            role=args.role,
            granted_by=args.granted_by,
        )
        print(f"role_granted user_id={user.id} role={record.role} granted_by={record.granted_by}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
