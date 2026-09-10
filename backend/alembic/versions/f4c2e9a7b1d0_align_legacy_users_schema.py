"""Align the legacy users schema with the current ORM models.

Revision ID: f4c2e9a7b1d0
Revises: 89b856a8da67
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "f4c2e9a7b1d0"
down_revision: Union[str, Sequence[str], None] = "89b856a8da67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_no_rows(connection, query: str, message: str) -> None:
    if connection.execute(sa.text(query)).scalar_one() != 0:
        raise RuntimeError(message)


def upgrade() -> None:
    connection = op.get_bind()

    op.execute("ALTER TABLE users ADD COLUMN legacy_id uuid")
    op.execute("UPDATE users SET legacy_id = id")
    op.execute("ALTER TABLE users ADD COLUMN new_id integer")
    op.execute(
        """
        WITH numbered AS (
            SELECT id, row_number() OVER (ORDER BY id)::integer AS new_id
            FROM users
        )
        UPDATE users AS u
        SET new_id = numbered.new_id
        FROM numbered
        WHERE u.id = numbered.id
        """
    )

    _require_no_rows(
        connection,
        "SELECT COUNT(*) FROM users WHERE new_id IS NULL",
        "Cannot assign integer IDs to all existing users.",
    )
    _require_no_rows(
        connection,
        """
        SELECT COUNT(*)
        FROM users AS u
        LEFT JOIN roles ON roles.id = u.role_id
        WHERE roles.id IS NULL
        """,
        "Cannot migrate users with a missing role.",
    )

    op.execute("ALTER TABLE users ADD COLUMN new_name varchar")
    op.execute("ALTER TABLE users ADD COLUMN new_password varchar")
    op.execute("ALTER TABLE users ADD COLUMN new_role varchar")
    op.execute(
        """
        UPDATE users AS u
        SET new_name = u.full_name,
            new_password = u.password_hash,
            new_role = roles.name
        FROM roles
        WHERE roles.id = u.role_id
        """
    )

    _require_no_rows(
        connection,
        """
        SELECT COUNT(*)
        FROM users
        WHERE new_name IS NULL OR new_password IS NULL OR new_role IS NULL
        """,
        "Cannot migrate users with incomplete account data.",
    )

    op.execute("ALTER TABLE videos ADD COLUMN new_user_id integer")
    op.execute(
        """
        UPDATE videos
        SET new_user_id = users.new_id
        FROM users
        WHERE videos.user_id = users.legacy_id
        """
    )
    _require_no_rows(
        connection,
        "SELECT COUNT(*) FROM videos WHERE new_user_id IS NULL",
        "Cannot migrate videos with a missing user.",
    )

    op.execute("ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_user_id_fkey")
    op.execute("DROP INDEX IF EXISTS ix_videos_user_id")
    op.execute("ALTER TABLE videos DROP COLUMN user_id")
    op.execute("ALTER TABLE videos RENAME COLUMN new_user_id TO user_id")
    op.execute("ALTER TABLE videos ALTER COLUMN user_id SET NOT NULL")
    op.execute("CREATE INDEX ix_videos_user_id ON videos (user_id)")

    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_id_fkey")
    op.execute("DROP INDEX IF EXISTS ix_users_role_id")
    op.execute("ALTER TABLE users DROP CONSTRAINT users_pkey")
    op.execute("ALTER TABLE users DROP COLUMN id")
    op.execute("ALTER TABLE users RENAME COLUMN new_id TO id")
    op.execute("ALTER TABLE users RENAME COLUMN new_name TO name")
    op.execute("ALTER TABLE users RENAME COLUMN new_password TO password")
    op.execute("ALTER TABLE users RENAME COLUMN new_role TO role")
    op.execute("ALTER TABLE users DROP COLUMN full_name")
    op.execute("ALTER TABLE users DROP COLUMN password_hash")
    op.execute("ALTER TABLE users DROP COLUMN role_id")
    op.execute("ALTER TABLE users ALTER COLUMN id SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN name SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN password SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN role SET NOT NULL")
    op.execute("ALTER TABLE users ADD CONSTRAINT users_pkey PRIMARY KEY (id)")
    op.execute("CREATE INDEX ix_users_id ON users (id)")
    op.execute("CREATE SEQUENCE IF NOT EXISTS users_id_seq")
    op.execute(
        "SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 1))"
    )
    op.execute("ALTER SEQUENCE users_id_seq OWNED BY users.id")
    op.execute("ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('users_id_seq')")
    op.execute(
        "ALTER TABLE videos ADD CONSTRAINT videos_user_id_fkey "
        "FOREIGN KEY (user_id) REFERENCES users (id)"
    )


def downgrade() -> None:
    connection = op.get_bind()

    for user_id, in connection.execute(
        sa.text("SELECT id FROM users WHERE legacy_id IS NULL")
    ):
        connection.execute(
            sa.text("UPDATE users SET legacy_id = :legacy_id WHERE id = :user_id"),
            {"legacy_id": str(uuid.uuid4()), "user_id": user_id},
        )

    op.execute("ALTER TABLE videos ADD COLUMN old_user_id uuid")
    op.execute(
        """
        UPDATE videos
        SET old_user_id = users.legacy_id
        FROM users
        WHERE videos.user_id = users.id
        """
    )
    _require_no_rows(
        connection,
        "SELECT COUNT(*) FROM videos WHERE old_user_id IS NULL",
        "Cannot restore videos with a missing user mapping.",
    )
    op.execute("ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_user_id_fkey")
    op.execute("DROP INDEX IF EXISTS ix_videos_user_id")
    op.execute("ALTER TABLE videos DROP COLUMN user_id")
    op.execute("ALTER TABLE videos RENAME COLUMN old_user_id TO user_id")
    op.execute("ALTER TABLE videos ALTER COLUMN user_id SET NOT NULL")
    op.execute("CREATE INDEX ix_videos_user_id ON videos (user_id)")

    op.execute("ALTER TABLE users ADD COLUMN old_role_id uuid")
    op.execute(
        """
        UPDATE users
        SET old_role_id = roles.id
        FROM roles
        WHERE lower(users.role) = lower(roles.name)
        """
    )
    _require_no_rows(
        connection,
        "SELECT COUNT(*) FROM users WHERE old_role_id IS NULL",
        "Cannot restore users with a missing role mapping.",
    )

    op.execute("ALTER TABLE users DROP CONSTRAINT users_pkey")
    op.execute("ALTER TABLE users DROP COLUMN id")
    op.execute("ALTER TABLE users RENAME COLUMN legacy_id TO id")
    op.execute("ALTER TABLE users RENAME COLUMN old_role_id TO role_id")
    op.execute("ALTER TABLE users RENAME COLUMN name TO full_name")
    op.execute("ALTER TABLE users RENAME COLUMN password TO password_hash")
    op.execute("ALTER TABLE users DROP COLUMN role")
    op.execute("ALTER TABLE users ALTER COLUMN id SET NOT NULL")
    op.execute("ALTER TABLE users ADD CONSTRAINT users_pkey PRIMARY KEY (id)")
    op.execute("CREATE INDEX ix_users_role_id ON users (role_id)")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_role_id_fkey "
        "FOREIGN KEY (role_id) REFERENCES roles (id)"
    )
    op.execute("ALTER TABLE videos ADD CONSTRAINT videos_user_id_fkey "
               "FOREIGN KEY (user_id) REFERENCES users (id)")
    op.execute("DROP SEQUENCE IF EXISTS users_id_seq")