"""FlowHub - FeatureFlag ORM model.

Defines the FLOWHUB_feature_flags table in the FLOWHUB database.

Implementation begins in B11 (migration: FLOWHUB_001).
"""


class FeatureFlag:
    """ORM model for the FLOWHUB_feature_flags table.

    Fields: id (flag name), is_enabled, description, admin_only,
    locked, updated_at, updated_by.

    Implementation begins in B11.
    """
    pass
