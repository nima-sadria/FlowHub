"""FlowHub - FlowHubUser and Permission ORM models.

Defines flowhub_users and FLOWHUB_permissions tables in the FLOWHUB database.

Implementation begins in B10 (migration: FLOWHUB_001).
"""


class FlowHubUser:
    """ORM model for the flowhub_users table.

    Fields: id, email, hashed_password, is_admin, is_active,
    created_at, last_login_at.

    Implementation begins in B10.
    """
    pass


class Permission:
    """ORM model for the FLOWHUB_user_permissions table.

    Fields: user_id (FK -> flowhub_users.id), permission (named string).

    Implementation begins in B10.
    """
    pass
