"""Grant or revoke platform administration.

    python -m app.scripts.platform_admin grant  someone@example.com
    python -m app.scripts.platform_admin revoke someone@example.com
    python -m app.scripts.platform_admin list

Uses MIGRATION_DATABASE_URL (the owner role): the application role is blocked by a
database trigger from granting this flag, so it cannot be obtained through the API.
"""

import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main(argv: list[str]) -> int:
    settings = get_settings()
    url = settings.migration_database_url
    if not url:
        print("MIGRATION_DATABASE_URL is not set.")
        return 2
    if len(argv) == 1 and argv[0] == "list":
        action, email = "list", ""
    elif len(argv) == 2 and argv[0] in ("grant", "revoke"):
        action, email = argv
    else:
        print(__doc__)
        return 2
    engine = create_engine(url)
    with engine.begin() as conn:
        if action == "list":
            for row in conn.execute(
                text("SELECT email FROM users WHERE is_platform_admin ORDER BY 1")
            ):
                print(row[0])
            return 0
        changed = conn.execute(
            text("UPDATE users SET is_platform_admin = :flag WHERE email = :email"),
            {"flag": action == "grant", "email": email},
        ).rowcount
    if not changed:
        print(f"No user with e-mail {email}. The person must register first.")
        return 1
    print(f"{action}: {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
