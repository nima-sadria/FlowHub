"""Frozen explicit FlowHub 016 schema. Generated once from the approved v1.2 model.

This module deliberately imports no application ORM metadata. Future model changes cannot
change the historical migration.
"""

SCHEMA_FINGERPRINT = 'c01766583aa54f9d21637adc49edc5fa3d9349c451beb45748069b74ca4e01fd'
SQLITE_DDL: tuple[str, ...] = ('CREATE TABLE uw_audit_entries (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tcorrelation_id VARCHAR(120) NOT NULL, \n'
 '\tevent_type VARCHAR(120) NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\toccurred_at DATETIME NOT NULL, \n'
 '\tworkspace_id VARCHAR(36), \n'
 '\tsnapshot_id VARCHAR(36), \n'
 '\tdraft_id VARCHAR(36), \n'
 '\tdraft_revision_id VARCHAR(36), \n'
 '\treview_id VARCHAR(36), \n'
 '\tapply_job_id VARCHAR(36), \n'
 '\tcanonical_product_id VARCHAR(36), \n'
 '\tlisting_id VARCHAR(36), \n'
 '\tchannel_id VARCHAR(120), \n'
 '\tchanged_field VARCHAR(20), \n'
 '\tprevious_value TEXT, \n'
 '\ttarget_value TEXT, \n'
 '\tvalidation_result VARCHAR(30), \n'
 '\treview_result VARCHAR(30), \n'
 '\tapply_result VARCHAR(30), \n'
 '\treason TEXT, \n'
 '\trequest_metadata_json JSON NOT NULL, \n'
 '\tmetadata_json JSON NOT NULL, \n'
 '\tmetadata_checksum VARCHAR(64) NOT NULL, \n'
 '\tPRIMARY KEY (id)\n'
 ')',
 'CREATE TABLE uw_canonical_products (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tname VARCHAR(1000) NOT NULL, \n'
 '\tsku VARCHAR(255), \n'
 '\tproduct_type VARCHAR(20) NOT NULL, \n'
 '\tparent_id VARCHAR(36), \n'
 '\tbrand VARCHAR(240), \n'
 '\tcategory VARCHAR(240), \n'
 '\tstatus VARCHAR(20) NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tupdated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_product_type CHECK (product_type IN ('simple','variable','variation')), \n"
 "\tCONSTRAINT ck_uw_product_status CHECK (status IN ('active','inactive','draft')), \n"
 '\tFOREIGN KEY(parent_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_channels (\n'
 '\tid VARCHAR(120) NOT NULL, \n'
 '\tconnector_type VARCHAR(80) NOT NULL, \n'
 '\tname VARCHAR(160) NOT NULL, \n'
 '\timplementation_state VARCHAR(30) NOT NULL, \n'
 '\tcapabilities_json JSON NOT NULL, \n'
 '\tcapability_version VARCHAR(40) NOT NULL, \n'
 '\tenabled BOOLEAN NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tupdated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id)\n'
 ')',
 'CREATE TABLE uw_currency_profiles (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tscope VARCHAR(20) NOT NULL, \n'
 '\tscope_reference VARCHAR(120) NOT NULL, \n'
 '\tcurrency VARCHAR(12) NOT NULL, \n'
 '\tunit VARCHAR(24) NOT NULL, \n'
 '\tnormalization_currency VARCHAR(12) NOT NULL, \n'
 '\tnormalization_unit VARCHAR(24) NOT NULL, \n'
 '\tconversion_factor NUMERIC(24, 8) NOT NULL, \n'
 '\tconversion_rule VARCHAR(120) NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tenabled BOOLEAN NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_currency_scope CHECK (scope IN ('global','source','channel')), \n"
 '\tCONSTRAINT uq_uw_currency_profile_version UNIQUE (scope, scope_reference, version)\n'
 ')',
 'CREATE TABLE uw_listings (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\texternal_primary_id VARCHAR(255) NOT NULL, \n'
 '\texternal_id_type VARCHAR(80) NOT NULL, \n'
 '\tsecondary_identifiers_json JSON NOT NULL, \n'
 '\tsku VARCHAR(255), \n'
 '\tlabel VARCHAR(500) NOT NULL, \n'
 '\tmapping_state VARCHAR(20) NOT NULL, \n'
 '\tmapping_version INTEGER NOT NULL, \n'
 '\tcapability_state_json JSON NOT NULL, \n'
 '\tenabled BOOLEAN NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tupdated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_listing_external_identity UNIQUE (channel_id, external_primary_id), \n'
 "\tCONSTRAINT ck_uw_listing_mapping_state CHECK (mapping_state IN ('resolved','unresolved','conflict')), \n"
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_user_preferences (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\tvisible_channel_ids_json JSON NOT NULL, \n'
 '\tchannel_order_json JSON NOT NULL, \n'
 '\tvisible_fields_json JSON NOT NULL, \n'
 '\tdisplay_name_source VARCHAR(120) NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tupdated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_preference_user UNIQUE (user_id), \n'
 '\tFOREIGN KEY(user_id) REFERENCES flowhub_users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE uw_workspaces (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tname VARCHAR(240) NOT NULL, \n'
 '\tentry_point VARCHAR(20) NOT NULL, \n'
 '\tsource_type VARCHAR(80), \n'
 '\towner_user_id INTEGER NOT NULL, \n'
 '\tstatus VARCHAR(20) NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tupdated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_workspace_entry_point CHECK (entry_point IN ('source','manual')), \n"
 "\tCONSTRAINT ck_uw_workspace_status CHECK (status IN ('active','archived')), \n"
 '\tFOREIGN KEY(owner_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_channel_cache (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tprice_raw VARCHAR(100), \n'
 '\tprice_currency VARCHAR(12), \n'
 '\tprice_unit VARCHAR(24), \n'
 '\tstock_quantity NUMERIC(20, 4), \n'
 '\tstatus VARCHAR(80), \n'
 '\tmanage_stock BOOLEAN, \n'
 '\tcache_version INTEGER NOT NULL, \n'
 '\tchecksum VARCHAR(64) NOT NULL, \n'
 '\tconnector_version VARCHAR(40) NOT NULL, \n'
 '\tfreshness VARCHAR(30) NOT NULL, \n'
 '\tfetch_status VARCHAR(30) NOT NULL, \n'
 '\texternal_updated_at DATETIME, \n'
 '\tfetched_at DATETIME NOT NULL, \n'
 '\terror_category VARCHAR(80), \n'
 '\terror_message TEXT, \n'
 '\tresponse_reference VARCHAR(255), \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_cache_listing UNIQUE (listing_id), \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_mapping_revisions (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\trevision_number INTEGER NOT NULL, \n'
 '\tprevious_canonical_product_id VARCHAR(36), \n'
 '\tproposed_canonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tdecision VARCHAR(20) NOT NULL, \n'
 '\tevidence_json JSON NOT NULL, \n'
 '\treason TEXT NOT NULL, \n'
 '\tapproved_by_user_id INTEGER, \n'
 '\tchecksum VARCHAR(64) NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_mapping_revision_number UNIQUE (listing_id, revision_number), \n'
 "\tCONSTRAINT ck_uw_mapping_decision CHECK (decision IN ('approved','rejected','automatic')), \n"
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(previous_canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(proposed_canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(approved_by_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT, \n'
 '\tUNIQUE (checksum)\n'
 ')',
 'CREATE TABLE uw_workspace_snapshots (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tentry_point VARCHAR(20) NOT NULL, \n'
 '\tsource_type VARCHAR(80), \n'
 '\tcreator_user_id INTEGER NOT NULL, \n'
 '\tschema_version VARCHAR(40) NOT NULL, \n'
 '\tcontent_checksum VARCHAR(64) NOT NULL, \n'
 '\tnormalization_version VARCHAR(40) NOT NULL, \n'
 '\tvalidation_ruleset_version VARCHAR(40) NOT NULL, \n'
 '\tmapping_version INTEGER NOT NULL, \n'
 '\tcurrency_profile_id VARCHAR(36) NOT NULL, \n'
 '\tsource_metadata_json JSON NOT NULL, \n'
 '\tacquisition_metadata_json JSON NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_snapshot_workspace UNIQUE (workspace_id), \n'
 "\tCONSTRAINT ck_uw_snapshot_entry_point CHECK (entry_point IN ('source','manual')), \n"
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(creator_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(currency_profile_id) REFERENCES uw_currency_profiles (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_drafts (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\towner_user_id INTEGER NOT NULL, \n'
 '\tcurrent_revision_id VARCHAR(36), \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tstatus VARCHAR(20) NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tupdated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_draft_status CHECK (status IN ('draft','reviewed','applied')), \n"
 '\tUNIQUE (workspace_id), \n'
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(owner_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(current_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_snapshot_rows (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\trow_number INTEGER NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36), \n'
 '\tlisting_id VARCHAR(36), \n'
 '\tmapping_version INTEGER, \n'
 '\traw_data_json JSON NOT NULL, \n'
 '\tnormalized_data_json JSON NOT NULL, \n'
 '\trow_checksum VARCHAR(64) NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_snapshot_row_number UNIQUE (snapshot_id, row_number), \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_draft_revisions (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tdraft_id VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\trevision_number INTEGER NOT NULL, \n'
 '\tparent_revision_id VARCHAR(36), \n'
 '\trestored_from_revision_id VARCHAR(36), \n'
 '\tcreator_user_id INTEGER NOT NULL, \n'
 '\tchecksum VARCHAR(64) NOT NULL, \n'
 '\tmetadata_json JSON NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_draft_revision_number UNIQUE (draft_id, revision_number), \n'
 '\tCONSTRAINT uq_uw_draft_revision_checksum UNIQUE (draft_id, checksum), \n'
 '\tFOREIGN KEY(draft_id) REFERENCES uw_drafts (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(parent_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(restored_from_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(creator_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_draft_revision_changes (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\trevision_id VARCHAR(36) NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tfield VARCHAR(20) NOT NULL, \n'
 '\ttarget_value TEXT NOT NULL, \n'
 '\tcurrency VARCHAR(12), \n'
 '\tunit VARCHAR(24), \n'
 '\tchange_checksum VARCHAR(64) NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_revision_listing_field UNIQUE (revision_id, listing_id, field), \n'
 "\tCONSTRAINT ck_uw_change_field CHECK (field IN ('price','stock','status')), \n"
 '\tFOREIGN KEY(revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_reviews (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\tdraft_revision_id VARCHAR(36) NOT NULL, \n'
 '\tcreated_by_user_id INTEGER NOT NULL, \n'
 '\tstatus VARCHAR(20) NOT NULL, \n'
 '\truleset_version VARCHAR(40) NOT NULL, \n'
 '\tcapability_digest VARCHAR(64) NOT NULL, \n'
 '\tcurrency_digest VARCHAR(64) NOT NULL, \n'
 '\tmapping_digest VARCHAR(64) NOT NULL, \n'
 '\tchecksum VARCHAR(64) NOT NULL, \n'
 '\tsummary_json JSON NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tinvalidated_at DATETIME, \n'
 '\tstale_reason TEXT, \n'
 '\tselection_version INTEGER NOT NULL, \n'
 '\tselection_checksum VARCHAR(64), \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_review_status CHECK (status IN ('ready','blocked','stale')), \n"
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(draft_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(created_by_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_apply_jobs (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\tdraft_revision_id VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36) NOT NULL, \n'
 '\trequested_by_user_id INTEGER NOT NULL, \n'
 '\tidempotency_key VARCHAR(255) NOT NULL, \n'
 '\tlogical_operation_key VARCHAR(64) NOT NULL, \n'
 '\tcorrelation_id VARCHAR(120) NOT NULL, \n'
 '\tselection_checksum VARCHAR(64) NOT NULL, \n'
 '\trequest_json JSON NOT NULL, \n'
 '\tstatus VARCHAR(30) NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tstarted_at DATETIME, \n'
 '\tcompleted_at DATETIME, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_uw_apply_status CHECK (status IN '
 "('pending','running','partially_applied','applied','failed','cancelled','blocked','stale','reconciliation_required')), \n"
 '\tCONSTRAINT uq_uw_apply_idempotency UNIQUE (idempotency_key), \n'
 '\tCONSTRAINT uq_uw_apply_logical_operation UNIQUE (logical_operation_key), \n'
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(draft_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(requested_by_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_review_cache_versions (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tcache_version INTEGER NOT NULL, \n'
 '\tcache_checksum VARCHAR(64) NOT NULL, \n'
 '\tmapping_version INTEGER NOT NULL, \n'
 '\tcapability_version VARCHAR(40) NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_review_cache_listing UNIQUE (review_id, listing_id), \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_review_items (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36) NOT NULL, \n'
 '\tdraft_change_id VARCHAR(36) NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tfield VARCHAR(20) NOT NULL, \n'
 '\tcurrent_value TEXT, \n'
 '\ttarget_value TEXT NOT NULL, \n'
 '\tnormalized_value_json JSON NOT NULL, \n'
 '\tpayload_summary_json JSON NOT NULL, \n'
 '\tvalidation_state VARCHAR(20) NOT NULL, \n'
 '\twarnings_json JSON NOT NULL, \n'
 '\terrors_json JSON NOT NULL, \n'
 '\teligible BOOLEAN NOT NULL, \n'
 '\tselected BOOLEAN NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_review_change UNIQUE (review_id, draft_change_id), \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(draft_change_id) REFERENCES uw_draft_revision_changes (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_validation_issues (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36), \n'
 '\tcanonical_product_id VARCHAR(36), \n'
 '\tlisting_id VARCHAR(36), \n'
 '\tchannel_id VARCHAR(120), \n'
 '\tcode VARCHAR(120) NOT NULL, \n'
 '\tseverity VARCHAR(20) NOT NULL, \n'
 '\tmessage TEXT NOT NULL, \n'
 '\tmetadata_json JSON NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_issue_severity CHECK (severity IN ('warning','error')), \n"
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_apply_job_items (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tapply_job_id VARCHAR(36) NOT NULL, \n'
 '\treview_item_id VARCHAR(36) NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tfield VARCHAR(20) NOT NULL, \n'
 '\tpayload_hash VARCHAR(64) NOT NULL, \n'
 '\tstatus VARCHAR(30) NOT NULL, \n'
 '\tattempt_number INTEGER NOT NULL, \n'
 '\tretry_eligible BOOLEAN NOT NULL, \n'
 '\tconnector_response_json JSON NOT NULL, \n'
 '\texternal_response_id VARCHAR(255), \n'
 '\terror_category VARCHAR(80), \n'
 '\terror_message TEXT, \n'
 '\tcache_sync_status VARCHAR(40), \n'
 '\tstarted_at DATETIME, \n'
 '\tcompleted_at DATETIME, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_apply_review_item UNIQUE (apply_job_id, review_item_id), \n'
 '\tFOREIGN KEY(apply_job_id) REFERENCES uw_apply_jobs (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(review_item_id) REFERENCES uw_review_items (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_review_selections (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36) NOT NULL, \n'
 '\treview_item_id VARCHAR(36) NOT NULL, \n'
 '\tselected_by_user_id INTEGER NOT NULL, \n'
 '\tselected_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_review_selection_item UNIQUE (review_id, review_item_id), \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(review_item_id) REFERENCES uw_review_items (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(selected_by_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_workspace_locks (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tapply_job_id VARCHAR(36) NOT NULL, \n'
 '\tacquired_at DATETIME NOT NULL, \n'
 '\texpires_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_lock_scope UNIQUE (channel_id, listing_id), \n'
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(apply_job_id) REFERENCES uw_apply_jobs (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE uw_apply_attempts (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tapply_job_id VARCHAR(36) NOT NULL, \n'
 '\tapply_job_item_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tnormalized_payload_json JSON NOT NULL, \n'
 '\tpayload_hash VARCHAR(64) NOT NULL, \n'
 '\tprovider_idempotency_key VARCHAR(120) NOT NULL, \n'
 '\tattempt_number INTEGER NOT NULL, \n'
 '\tcorrelation_id VARCHAR(120) NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_attempt_number UNIQUE (apply_job_item_id, attempt_number), \n'
 '\tCONSTRAINT uq_uw_attempt_provider_key UNIQUE (provider_idempotency_key), \n'
 '\tFOREIGN KEY(apply_job_id) REFERENCES uw_apply_jobs (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(apply_job_item_id) REFERENCES uw_apply_job_items (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_apply_attempt_events (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tattempt_id VARCHAR(36) NOT NULL, \n'
 '\toutcome VARCHAR(40) NOT NULL, \n'
 '\tprovider_response_json JSON NOT NULL, \n'
 '\terror_category VARCHAR(80), \n'
 '\terror_message TEXT, \n'
 '\toccurred_at DATETIME NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_uw_attempt_event_outcome CHECK (outcome IN '
 "('pending','dispatched','provider_accepted','verified_applied','failed','reconciliation_required')), \n"
 '\tFOREIGN KEY(attempt_id) REFERENCES uw_apply_attempts (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE INDEX ix_uw_audit_entries_correlation_id ON uw_audit_entries (correlation_id)',
 'CREATE INDEX ix_uw_audit_entries_event_type ON uw_audit_entries (event_type)',
 'CREATE INDEX ix_uw_audit_entries_occurred_at ON uw_audit_entries (occurred_at)',
 'CREATE INDEX ix_uw_audit_entries_user_id ON uw_audit_entries (user_id)',
 'CREATE INDEX ix_uw_audit_entries_workspace_id ON uw_audit_entries (workspace_id)',
 'CREATE INDEX ix_uw_canonical_products_brand ON uw_canonical_products (brand)',
 'CREATE INDEX ix_uw_canonical_products_category ON uw_canonical_products (category)',
 'CREATE INDEX ix_uw_canonical_products_name ON uw_canonical_products (name)',
 'CREATE INDEX ix_uw_canonical_products_product_type ON uw_canonical_products (product_type)',
 'CREATE INDEX ix_uw_canonical_products_sku ON uw_canonical_products (sku)',
 'CREATE INDEX ix_uw_canonical_products_status ON uw_canonical_products (status)',
 'CREATE INDEX ix_uw_channels_connector_type ON uw_channels (connector_type)',
 'CREATE INDEX ix_uw_channels_implementation_state ON uw_channels (implementation_state)',
 'CREATE INDEX ix_uw_currency_profiles_scope ON uw_currency_profiles (scope)',
 'CREATE INDEX ix_uw_listing_product_channel ON uw_listings (canonical_product_id, channel_id)',
 'CREATE INDEX ix_uw_listings_canonical_product_id ON uw_listings (canonical_product_id)',
 'CREATE INDEX ix_uw_listings_channel_id ON uw_listings (channel_id)',
 'CREATE INDEX ix_uw_listings_mapping_state ON uw_listings (mapping_state)',
 'CREATE INDEX ix_uw_listings_sku ON uw_listings (sku)',
 'CREATE INDEX ix_uw_user_preferences_user_id ON uw_user_preferences (user_id)',
 'CREATE INDEX ix_uw_workspaces_entry_point ON uw_workspaces (entry_point)',
 'CREATE INDEX ix_uw_workspaces_owner_user_id ON uw_workspaces (owner_user_id)',
 'CREATE INDEX ix_uw_workspaces_status ON uw_workspaces (status)',
 'CREATE INDEX ix_uw_channel_cache_channel_id ON uw_channel_cache (channel_id)',
 'CREATE INDEX ix_uw_channel_cache_freshness ON uw_channel_cache (freshness)',
 'CREATE INDEX ix_uw_channel_cache_listing_id ON uw_channel_cache (listing_id)',
 'CREATE INDEX ix_uw_mapping_revisions_listing_id ON uw_mapping_revisions (listing_id)',
 'CREATE INDEX ix_uw_workspace_snapshots_content_checksum ON uw_workspace_snapshots (content_checksum)',
 'CREATE INDEX ix_uw_workspace_snapshots_workspace_id ON uw_workspace_snapshots (workspace_id)',
 'CREATE INDEX ix_uw_drafts_owner_user_id ON uw_drafts (owner_user_id)',
 'CREATE INDEX ix_uw_snapshot_rows_canonical_product_id ON uw_snapshot_rows (canonical_product_id)',
 'CREATE INDEX ix_uw_snapshot_rows_listing_id ON uw_snapshot_rows (listing_id)',
 'CREATE INDEX ix_uw_snapshot_rows_snapshot_id ON uw_snapshot_rows (snapshot_id)',
 'CREATE INDEX ix_uw_draft_revisions_draft_id ON uw_draft_revisions (draft_id)',
 'CREATE INDEX ix_uw_draft_revisions_workspace_id ON uw_draft_revisions (workspace_id)',
 'CREATE INDEX ix_uw_draft_revision_changes_canonical_product_id ON uw_draft_revision_changes (canonical_product_id)',
 'CREATE INDEX ix_uw_draft_revision_changes_channel_id ON uw_draft_revision_changes (channel_id)',
 'CREATE INDEX ix_uw_draft_revision_changes_field ON uw_draft_revision_changes (field)',
 'CREATE INDEX ix_uw_draft_revision_changes_listing_id ON uw_draft_revision_changes (listing_id)',
 'CREATE INDEX ix_uw_draft_revision_changes_revision_id ON uw_draft_revision_changes (revision_id)',
 'CREATE INDEX ix_uw_reviews_checksum ON uw_reviews (checksum)',
 'CREATE INDEX ix_uw_reviews_draft_revision_id ON uw_reviews (draft_revision_id)',
 'CREATE INDEX ix_uw_reviews_status ON uw_reviews (status)',
 'CREATE INDEX ix_uw_reviews_workspace_id ON uw_reviews (workspace_id)',
 'CREATE INDEX ix_uw_apply_jobs_correlation_id ON uw_apply_jobs (correlation_id)',
 'CREATE INDEX ix_uw_apply_jobs_review_id ON uw_apply_jobs (review_id)',
 'CREATE INDEX ix_uw_apply_jobs_status ON uw_apply_jobs (status)',
 'CREATE INDEX ix_uw_apply_jobs_workspace_id ON uw_apply_jobs (workspace_id)',
 'CREATE INDEX ix_uw_review_cache_versions_channel_id ON uw_review_cache_versions (channel_id)',
 'CREATE INDEX ix_uw_review_cache_versions_listing_id ON uw_review_cache_versions (listing_id)',
 'CREATE INDEX ix_uw_review_cache_versions_review_id ON uw_review_cache_versions (review_id)',
 'CREATE INDEX ix_uw_review_item_selection ON uw_review_items (review_id, selected, eligible)',
 'CREATE INDEX ix_uw_review_items_canonical_product_id ON uw_review_items (canonical_product_id)',
 'CREATE INDEX ix_uw_review_items_channel_id ON uw_review_items (channel_id)',
 'CREATE INDEX ix_uw_review_items_listing_id ON uw_review_items (listing_id)',
 'CREATE INDEX ix_uw_review_items_review_id ON uw_review_items (review_id)',
 'CREATE INDEX ix_uw_review_items_validation_state ON uw_review_items (validation_state)',
 'CREATE INDEX ix_uw_validation_issues_code ON uw_validation_issues (code)',
 'CREATE INDEX ix_uw_validation_issues_review_id ON uw_validation_issues (review_id)',
 'CREATE INDEX ix_uw_validation_issues_snapshot_id ON uw_validation_issues (snapshot_id)',
 'CREATE INDEX ix_uw_validation_issues_workspace_id ON uw_validation_issues (workspace_id)',
 'CREATE INDEX ix_uw_apply_job_items_apply_job_id ON uw_apply_job_items (apply_job_id)',
 'CREATE INDEX ix_uw_apply_job_items_canonical_product_id ON uw_apply_job_items (canonical_product_id)',
 'CREATE INDEX ix_uw_apply_job_items_channel_id ON uw_apply_job_items (channel_id)',
 'CREATE INDEX ix_uw_apply_job_items_listing_id ON uw_apply_job_items (listing_id)',
 'CREATE INDEX ix_uw_apply_job_items_status ON uw_apply_job_items (status)',
 'CREATE INDEX ix_uw_review_selections_review_id ON uw_review_selections (review_id)',
 'CREATE INDEX ix_uw_review_selections_review_item_id ON uw_review_selections (review_item_id)',
 'CREATE INDEX ix_uw_workspace_locks_channel_id ON uw_workspace_locks (channel_id)',
 'CREATE INDEX ix_uw_workspace_locks_expires_at ON uw_workspace_locks (expires_at)',
 'CREATE INDEX ix_uw_workspace_locks_listing_id ON uw_workspace_locks (listing_id)',
 'CREATE INDEX ix_uw_workspace_locks_workspace_id ON uw_workspace_locks (workspace_id)',
 'CREATE INDEX ix_uw_apply_attempts_apply_job_id ON uw_apply_attempts (apply_job_id)',
 'CREATE INDEX ix_uw_apply_attempts_apply_job_item_id ON uw_apply_attempts (apply_job_item_id)',
 'CREATE INDEX ix_uw_apply_attempts_channel_id ON uw_apply_attempts (channel_id)',
 'CREATE INDEX ix_uw_apply_attempts_correlation_id ON uw_apply_attempts (correlation_id)',
 'CREATE INDEX ix_uw_apply_attempts_listing_id ON uw_apply_attempts (listing_id)',
 'CREATE INDEX ix_uw_apply_attempt_events_attempt_id ON uw_apply_attempt_events (attempt_id)',
 'CREATE INDEX ix_uw_apply_attempt_events_outcome ON uw_apply_attempt_events (outcome)')

POSTGRESQL_DDL: tuple[str, ...] = ('CREATE TABLE uw_audit_entries (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tcorrelation_id VARCHAR(120) NOT NULL, \n'
 '\tevent_type VARCHAR(120) NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\toccurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tworkspace_id VARCHAR(36), \n'
 '\tsnapshot_id VARCHAR(36), \n'
 '\tdraft_id VARCHAR(36), \n'
 '\tdraft_revision_id VARCHAR(36), \n'
 '\treview_id VARCHAR(36), \n'
 '\tapply_job_id VARCHAR(36), \n'
 '\tcanonical_product_id VARCHAR(36), \n'
 '\tlisting_id VARCHAR(36), \n'
 '\tchannel_id VARCHAR(120), \n'
 '\tchanged_field VARCHAR(20), \n'
 '\tprevious_value TEXT, \n'
 '\ttarget_value TEXT, \n'
 '\tvalidation_result VARCHAR(30), \n'
 '\treview_result VARCHAR(30), \n'
 '\tapply_result VARCHAR(30), \n'
 '\treason TEXT, \n'
 '\trequest_metadata_json JSON NOT NULL, \n'
 '\tmetadata_json JSON NOT NULL, \n'
 '\tmetadata_checksum VARCHAR(64) NOT NULL, \n'
 '\tPRIMARY KEY (id)\n'
 ')',
 'CREATE TABLE uw_canonical_products (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tname VARCHAR(1000) NOT NULL, \n'
 '\tsku VARCHAR(255), \n'
 '\tproduct_type VARCHAR(20) NOT NULL, \n'
 '\tparent_id VARCHAR(36), \n'
 '\tbrand VARCHAR(240), \n'
 '\tcategory VARCHAR(240), \n'
 '\tstatus VARCHAR(20) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_product_type CHECK (product_type IN ('simple','variable','variation')), \n"
 "\tCONSTRAINT ck_uw_product_status CHECK (status IN ('active','inactive','draft')), \n"
 '\tFOREIGN KEY(parent_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_channels (\n'
 '\tid VARCHAR(120) NOT NULL, \n'
 '\tconnector_type VARCHAR(80) NOT NULL, \n'
 '\tname VARCHAR(160) NOT NULL, \n'
 '\timplementation_state VARCHAR(30) NOT NULL, \n'
 '\tcapabilities_json JSON NOT NULL, \n'
 '\tcapability_version VARCHAR(40) NOT NULL, \n'
 '\tenabled BOOLEAN NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id)\n'
 ')',
 'CREATE TABLE uw_currency_profiles (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tscope VARCHAR(20) NOT NULL, \n'
 '\tscope_reference VARCHAR(120) NOT NULL, \n'
 '\tcurrency VARCHAR(12) NOT NULL, \n'
 '\tunit VARCHAR(24) NOT NULL, \n'
 '\tnormalization_currency VARCHAR(12) NOT NULL, \n'
 '\tnormalization_unit VARCHAR(24) NOT NULL, \n'
 '\tconversion_factor NUMERIC(24, 8) NOT NULL, \n'
 '\tconversion_rule VARCHAR(120) NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tenabled BOOLEAN NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_currency_scope CHECK (scope IN ('global','source','channel')), \n"
 '\tCONSTRAINT uq_uw_currency_profile_version UNIQUE (scope, scope_reference, version)\n'
 ')',
 'CREATE TABLE uw_listings (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\texternal_primary_id VARCHAR(255) NOT NULL, \n'
 '\texternal_id_type VARCHAR(80) NOT NULL, \n'
 '\tsecondary_identifiers_json JSON NOT NULL, \n'
 '\tsku VARCHAR(255), \n'
 '\tlabel VARCHAR(500) NOT NULL, \n'
 '\tmapping_state VARCHAR(20) NOT NULL, \n'
 '\tmapping_version INTEGER NOT NULL, \n'
 '\tcapability_state_json JSON NOT NULL, \n'
 '\tenabled BOOLEAN NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_listing_external_identity UNIQUE (channel_id, external_primary_id), \n'
 "\tCONSTRAINT ck_uw_listing_mapping_state CHECK (mapping_state IN ('resolved','unresolved','conflict')), \n"
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_user_preferences (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tuser_id INTEGER NOT NULL, \n'
 '\tvisible_channel_ids_json JSON NOT NULL, \n'
 '\tchannel_order_json JSON NOT NULL, \n'
 '\tvisible_fields_json JSON NOT NULL, \n'
 '\tdisplay_name_source VARCHAR(120) NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_preference_user UNIQUE (user_id), \n'
 '\tFOREIGN KEY(user_id) REFERENCES flowhub_users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE uw_workspaces (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tname VARCHAR(240) NOT NULL, \n'
 '\tentry_point VARCHAR(20) NOT NULL, \n'
 '\tsource_type VARCHAR(80), \n'
 '\towner_user_id INTEGER NOT NULL, \n'
 '\tstatus VARCHAR(20) NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_workspace_entry_point CHECK (entry_point IN ('source','manual')), \n"
 "\tCONSTRAINT ck_uw_workspace_status CHECK (status IN ('active','archived')), \n"
 '\tFOREIGN KEY(owner_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_channel_cache (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tprice_raw VARCHAR(100), \n'
 '\tprice_currency VARCHAR(12), \n'
 '\tprice_unit VARCHAR(24), \n'
 '\tstock_quantity NUMERIC(20, 4), \n'
 '\tstatus VARCHAR(80), \n'
 '\tmanage_stock BOOLEAN, \n'
 '\tcache_version INTEGER NOT NULL, \n'
 '\tchecksum VARCHAR(64) NOT NULL, \n'
 '\tconnector_version VARCHAR(40) NOT NULL, \n'
 '\tfreshness VARCHAR(30) NOT NULL, \n'
 '\tfetch_status VARCHAR(30) NOT NULL, \n'
 '\texternal_updated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tfetched_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\terror_category VARCHAR(80), \n'
 '\terror_message TEXT, \n'
 '\tresponse_reference VARCHAR(255), \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_cache_listing UNIQUE (listing_id), \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_mapping_revisions (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\trevision_number INTEGER NOT NULL, \n'
 '\tprevious_canonical_product_id VARCHAR(36), \n'
 '\tproposed_canonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tdecision VARCHAR(20) NOT NULL, \n'
 '\tevidence_json JSON NOT NULL, \n'
 '\treason TEXT NOT NULL, \n'
 '\tapproved_by_user_id INTEGER, \n'
 '\tchecksum VARCHAR(64) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_mapping_revision_number UNIQUE (listing_id, revision_number), \n'
 "\tCONSTRAINT ck_uw_mapping_decision CHECK (decision IN ('approved','rejected','automatic')), \n"
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(previous_canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(proposed_canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(approved_by_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT, \n'
 '\tUNIQUE (checksum)\n'
 ')',
 'CREATE TABLE uw_workspace_snapshots (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tentry_point VARCHAR(20) NOT NULL, \n'
 '\tsource_type VARCHAR(80), \n'
 '\tcreator_user_id INTEGER NOT NULL, \n'
 '\tschema_version VARCHAR(40) NOT NULL, \n'
 '\tcontent_checksum VARCHAR(64) NOT NULL, \n'
 '\tnormalization_version VARCHAR(40) NOT NULL, \n'
 '\tvalidation_ruleset_version VARCHAR(40) NOT NULL, \n'
 '\tmapping_version INTEGER NOT NULL, \n'
 '\tcurrency_profile_id VARCHAR(36) NOT NULL, \n'
 '\tsource_metadata_json JSON NOT NULL, \n'
 '\tacquisition_metadata_json JSON NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_snapshot_workspace UNIQUE (workspace_id), \n'
 "\tCONSTRAINT ck_uw_snapshot_entry_point CHECK (entry_point IN ('source','manual')), \n"
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(creator_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(currency_profile_id) REFERENCES uw_currency_profiles (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_drafts (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\towner_user_id INTEGER NOT NULL, \n'
 '\tcurrent_revision_id VARCHAR(36), \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tstatus VARCHAR(20) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_draft_status CHECK (status IN ('draft','reviewed','applied')), \n"
 '\tUNIQUE (workspace_id), \n'
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(owner_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_snapshot_rows (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\trow_number INTEGER NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36), \n'
 '\tlisting_id VARCHAR(36), \n'
 '\tmapping_version INTEGER, \n'
 '\traw_data_json JSON NOT NULL, \n'
 '\tnormalized_data_json JSON NOT NULL, \n'
 '\trow_checksum VARCHAR(64) NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_snapshot_row_number UNIQUE (snapshot_id, row_number), \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_draft_revisions (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tdraft_id VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\trevision_number INTEGER NOT NULL, \n'
 '\tparent_revision_id VARCHAR(36), \n'
 '\trestored_from_revision_id VARCHAR(36), \n'
 '\tcreator_user_id INTEGER NOT NULL, \n'
 '\tchecksum VARCHAR(64) NOT NULL, \n'
 '\tmetadata_json JSON NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_draft_revision_number UNIQUE (draft_id, revision_number), \n'
 '\tCONSTRAINT uq_uw_draft_revision_checksum UNIQUE (draft_id, checksum), \n'
 '\tFOREIGN KEY(draft_id) REFERENCES uw_drafts (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(parent_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(restored_from_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(creator_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_draft_revision_changes (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\trevision_id VARCHAR(36) NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tfield VARCHAR(20) NOT NULL, \n'
 '\ttarget_value TEXT NOT NULL, \n'
 '\tcurrency VARCHAR(12), \n'
 '\tunit VARCHAR(24), \n'
 '\tchange_checksum VARCHAR(64) NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_revision_listing_field UNIQUE (revision_id, listing_id, field), \n'
 "\tCONSTRAINT ck_uw_change_field CHECK (field IN ('price','stock','status')), \n"
 '\tFOREIGN KEY(revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_reviews (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\tdraft_revision_id VARCHAR(36) NOT NULL, \n'
 '\tcreated_by_user_id INTEGER NOT NULL, \n'
 '\tstatus VARCHAR(20) NOT NULL, \n'
 '\truleset_version VARCHAR(40) NOT NULL, \n'
 '\tcapability_digest VARCHAR(64) NOT NULL, \n'
 '\tcurrency_digest VARCHAR(64) NOT NULL, \n'
 '\tmapping_digest VARCHAR(64) NOT NULL, \n'
 '\tchecksum VARCHAR(64) NOT NULL, \n'
 '\tsummary_json JSON NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tinvalidated_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tstale_reason TEXT, \n'
 '\tselection_version INTEGER NOT NULL, \n'
 '\tselection_checksum VARCHAR(64), \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_review_status CHECK (status IN ('ready','blocked','stale')), \n"
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(draft_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(created_by_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_apply_jobs (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\tdraft_revision_id VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36) NOT NULL, \n'
 '\trequested_by_user_id INTEGER NOT NULL, \n'
 '\tidempotency_key VARCHAR(255) NOT NULL, \n'
 '\tlogical_operation_key VARCHAR(64) NOT NULL, \n'
 '\tcorrelation_id VARCHAR(120) NOT NULL, \n'
 '\tselection_checksum VARCHAR(64) NOT NULL, \n'
 '\trequest_json JSON NOT NULL, \n'
 '\tstatus VARCHAR(30) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tstarted_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tcompleted_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_uw_apply_status CHECK (status IN '
 "('pending','running','partially_applied','applied','failed','cancelled','blocked','stale','reconciliation_required')), \n"
 '\tCONSTRAINT uq_uw_apply_idempotency UNIQUE (idempotency_key), \n'
 '\tCONSTRAINT uq_uw_apply_logical_operation UNIQUE (logical_operation_key), \n'
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(draft_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(requested_by_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_review_cache_versions (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tcache_version INTEGER NOT NULL, \n'
 '\tcache_checksum VARCHAR(64) NOT NULL, \n'
 '\tmapping_version INTEGER NOT NULL, \n'
 '\tcapability_version VARCHAR(40) NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_review_cache_listing UNIQUE (review_id, listing_id), \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_review_items (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36) NOT NULL, \n'
 '\tdraft_change_id VARCHAR(36) NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tfield VARCHAR(20) NOT NULL, \n'
 '\tcurrent_value TEXT, \n'
 '\ttarget_value TEXT NOT NULL, \n'
 '\tnormalized_value_json JSON NOT NULL, \n'
 '\tpayload_summary_json JSON NOT NULL, \n'
 '\tvalidation_state VARCHAR(20) NOT NULL, \n'
 '\twarnings_json JSON NOT NULL, \n'
 '\terrors_json JSON NOT NULL, \n'
 '\teligible BOOLEAN NOT NULL, \n'
 '\tselected BOOLEAN NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_review_change UNIQUE (review_id, draft_change_id), \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(draft_change_id) REFERENCES uw_draft_revision_changes (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_validation_issues (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tsnapshot_id VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36), \n'
 '\tcanonical_product_id VARCHAR(36), \n'
 '\tlisting_id VARCHAR(36), \n'
 '\tchannel_id VARCHAR(120), \n'
 '\tcode VARCHAR(120) NOT NULL, \n'
 '\tseverity VARCHAR(20) NOT NULL, \n'
 '\tmessage TEXT NOT NULL, \n'
 '\tmetadata_json JSON NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 "\tCONSTRAINT ck_uw_issue_severity CHECK (severity IN ('warning','error')), \n"
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_apply_job_items (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tapply_job_id VARCHAR(36) NOT NULL, \n'
 '\treview_item_id VARCHAR(36) NOT NULL, \n'
 '\tcanonical_product_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tfield VARCHAR(20) NOT NULL, \n'
 '\tpayload_hash VARCHAR(64) NOT NULL, \n'
 '\tstatus VARCHAR(30) NOT NULL, \n'
 '\tattempt_number INTEGER NOT NULL, \n'
 '\tretry_eligible BOOLEAN NOT NULL, \n'
 '\tconnector_response_json JSON NOT NULL, \n'
 '\texternal_response_id VARCHAR(255), \n'
 '\terror_category VARCHAR(80), \n'
 '\terror_message TEXT, \n'
 '\tcache_sync_status VARCHAR(40), \n'
 '\tstarted_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tcompleted_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_apply_review_item UNIQUE (apply_job_id, review_item_id), \n'
 '\tFOREIGN KEY(apply_job_id) REFERENCES uw_apply_jobs (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(review_item_id) REFERENCES uw_review_items (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(canonical_product_id) REFERENCES uw_canonical_products (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_review_selections (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\treview_id VARCHAR(36) NOT NULL, \n'
 '\treview_item_id VARCHAR(36) NOT NULL, \n'
 '\tselected_by_user_id INTEGER NOT NULL, \n'
 '\tselected_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_review_selection_item UNIQUE (review_id, review_item_id), \n'
 '\tFOREIGN KEY(review_id) REFERENCES uw_reviews (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(review_item_id) REFERENCES uw_review_items (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(selected_by_user_id) REFERENCES flowhub_users (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_workspace_locks (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tworkspace_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tapply_job_id VARCHAR(36) NOT NULL, \n'
 '\tacquired_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_lock_scope UNIQUE (channel_id, listing_id), \n'
 '\tFOREIGN KEY(workspace_id) REFERENCES uw_workspaces (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(apply_job_id) REFERENCES uw_apply_jobs (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE uw_apply_attempts (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tapply_job_id VARCHAR(36) NOT NULL, \n'
 '\tapply_job_item_id VARCHAR(36) NOT NULL, \n'
 '\tlisting_id VARCHAR(36) NOT NULL, \n'
 '\tchannel_id VARCHAR(120) NOT NULL, \n'
 '\tnormalized_payload_json JSON NOT NULL, \n'
 '\tpayload_hash VARCHAR(64) NOT NULL, \n'
 '\tprovider_idempotency_key VARCHAR(120) NOT NULL, \n'
 '\tattempt_number INTEGER NOT NULL, \n'
 '\tcorrelation_id VARCHAR(120) NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_uw_attempt_number UNIQUE (apply_job_item_id, attempt_number), \n'
 '\tCONSTRAINT uq_uw_attempt_provider_key UNIQUE (provider_idempotency_key), \n'
 '\tFOREIGN KEY(apply_job_id) REFERENCES uw_apply_jobs (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(apply_job_item_id) REFERENCES uw_apply_job_items (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(listing_id) REFERENCES uw_listings (id) ON DELETE RESTRICT, \n'
 '\tFOREIGN KEY(channel_id) REFERENCES uw_channels (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE TABLE uw_apply_attempt_events (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tattempt_id VARCHAR(36) NOT NULL, \n'
 '\toutcome VARCHAR(40) NOT NULL, \n'
 '\tprovider_response_json JSON NOT NULL, \n'
 '\terror_category VARCHAR(80), \n'
 '\terror_message TEXT, \n'
 '\toccurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT ck_uw_attempt_event_outcome CHECK (outcome IN '
 "('pending','dispatched','provider_accepted','verified_applied','failed','reconciliation_required')), \n"
 '\tFOREIGN KEY(attempt_id) REFERENCES uw_apply_attempts (id) ON DELETE RESTRICT\n'
 ')',
 'CREATE INDEX ix_uw_audit_entries_correlation_id ON uw_audit_entries (correlation_id)',
 'CREATE INDEX ix_uw_audit_entries_event_type ON uw_audit_entries (event_type)',
 'CREATE INDEX ix_uw_audit_entries_occurred_at ON uw_audit_entries (occurred_at)',
 'CREATE INDEX ix_uw_audit_entries_user_id ON uw_audit_entries (user_id)',
 'CREATE INDEX ix_uw_audit_entries_workspace_id ON uw_audit_entries (workspace_id)',
 'CREATE INDEX ix_uw_canonical_products_brand ON uw_canonical_products (brand)',
 'CREATE INDEX ix_uw_canonical_products_category ON uw_canonical_products (category)',
 'CREATE INDEX ix_uw_canonical_products_name ON uw_canonical_products (name)',
 'CREATE INDEX ix_uw_canonical_products_product_type ON uw_canonical_products (product_type)',
 'CREATE INDEX ix_uw_canonical_products_sku ON uw_canonical_products (sku)',
 'CREATE INDEX ix_uw_canonical_products_status ON uw_canonical_products (status)',
 'CREATE INDEX ix_uw_channels_connector_type ON uw_channels (connector_type)',
 'CREATE INDEX ix_uw_channels_implementation_state ON uw_channels (implementation_state)',
 'CREATE INDEX ix_uw_currency_profiles_scope ON uw_currency_profiles (scope)',
 'CREATE INDEX ix_uw_listing_product_channel ON uw_listings (canonical_product_id, channel_id)',
 'CREATE INDEX ix_uw_listings_canonical_product_id ON uw_listings (canonical_product_id)',
 'CREATE INDEX ix_uw_listings_channel_id ON uw_listings (channel_id)',
 'CREATE INDEX ix_uw_listings_mapping_state ON uw_listings (mapping_state)',
 'CREATE INDEX ix_uw_listings_sku ON uw_listings (sku)',
 'CREATE INDEX ix_uw_user_preferences_user_id ON uw_user_preferences (user_id)',
 'CREATE INDEX ix_uw_workspaces_entry_point ON uw_workspaces (entry_point)',
 'CREATE INDEX ix_uw_workspaces_owner_user_id ON uw_workspaces (owner_user_id)',
 'CREATE INDEX ix_uw_workspaces_status ON uw_workspaces (status)',
 'CREATE INDEX ix_uw_channel_cache_channel_id ON uw_channel_cache (channel_id)',
 'CREATE INDEX ix_uw_channel_cache_freshness ON uw_channel_cache (freshness)',
 'CREATE INDEX ix_uw_channel_cache_listing_id ON uw_channel_cache (listing_id)',
 'CREATE INDEX ix_uw_mapping_revisions_listing_id ON uw_mapping_revisions (listing_id)',
 'CREATE INDEX ix_uw_workspace_snapshots_content_checksum ON uw_workspace_snapshots (content_checksum)',
 'CREATE INDEX ix_uw_workspace_snapshots_workspace_id ON uw_workspace_snapshots (workspace_id)',
 'CREATE INDEX ix_uw_drafts_owner_user_id ON uw_drafts (owner_user_id)',
 'CREATE INDEX ix_uw_snapshot_rows_canonical_product_id ON uw_snapshot_rows (canonical_product_id)',
 'CREATE INDEX ix_uw_snapshot_rows_listing_id ON uw_snapshot_rows (listing_id)',
 'CREATE INDEX ix_uw_snapshot_rows_snapshot_id ON uw_snapshot_rows (snapshot_id)',
 'CREATE INDEX ix_uw_draft_revisions_draft_id ON uw_draft_revisions (draft_id)',
 'CREATE INDEX ix_uw_draft_revisions_workspace_id ON uw_draft_revisions (workspace_id)',
 'CREATE INDEX ix_uw_draft_revision_changes_canonical_product_id ON uw_draft_revision_changes (canonical_product_id)',
 'CREATE INDEX ix_uw_draft_revision_changes_channel_id ON uw_draft_revision_changes (channel_id)',
 'CREATE INDEX ix_uw_draft_revision_changes_field ON uw_draft_revision_changes (field)',
 'CREATE INDEX ix_uw_draft_revision_changes_listing_id ON uw_draft_revision_changes (listing_id)',
 'CREATE INDEX ix_uw_draft_revision_changes_revision_id ON uw_draft_revision_changes (revision_id)',
 'CREATE INDEX ix_uw_reviews_checksum ON uw_reviews (checksum)',
 'CREATE INDEX ix_uw_reviews_draft_revision_id ON uw_reviews (draft_revision_id)',
 'CREATE INDEX ix_uw_reviews_status ON uw_reviews (status)',
 'CREATE INDEX ix_uw_reviews_workspace_id ON uw_reviews (workspace_id)',
 'CREATE INDEX ix_uw_apply_jobs_correlation_id ON uw_apply_jobs (correlation_id)',
 'CREATE INDEX ix_uw_apply_jobs_review_id ON uw_apply_jobs (review_id)',
 'CREATE INDEX ix_uw_apply_jobs_status ON uw_apply_jobs (status)',
 'CREATE INDEX ix_uw_apply_jobs_workspace_id ON uw_apply_jobs (workspace_id)',
 'CREATE INDEX ix_uw_review_cache_versions_channel_id ON uw_review_cache_versions (channel_id)',
 'CREATE INDEX ix_uw_review_cache_versions_listing_id ON uw_review_cache_versions (listing_id)',
 'CREATE INDEX ix_uw_review_cache_versions_review_id ON uw_review_cache_versions (review_id)',
 'CREATE INDEX ix_uw_review_item_selection ON uw_review_items (review_id, selected, eligible)',
 'CREATE INDEX ix_uw_review_items_canonical_product_id ON uw_review_items (canonical_product_id)',
 'CREATE INDEX ix_uw_review_items_channel_id ON uw_review_items (channel_id)',
 'CREATE INDEX ix_uw_review_items_listing_id ON uw_review_items (listing_id)',
 'CREATE INDEX ix_uw_review_items_review_id ON uw_review_items (review_id)',
 'CREATE INDEX ix_uw_review_items_validation_state ON uw_review_items (validation_state)',
 'CREATE INDEX ix_uw_validation_issues_code ON uw_validation_issues (code)',
 'CREATE INDEX ix_uw_validation_issues_review_id ON uw_validation_issues (review_id)',
 'CREATE INDEX ix_uw_validation_issues_snapshot_id ON uw_validation_issues (snapshot_id)',
 'CREATE INDEX ix_uw_validation_issues_workspace_id ON uw_validation_issues (workspace_id)',
 'CREATE INDEX ix_uw_apply_job_items_apply_job_id ON uw_apply_job_items (apply_job_id)',
 'CREATE INDEX ix_uw_apply_job_items_canonical_product_id ON uw_apply_job_items (canonical_product_id)',
 'CREATE INDEX ix_uw_apply_job_items_channel_id ON uw_apply_job_items (channel_id)',
 'CREATE INDEX ix_uw_apply_job_items_listing_id ON uw_apply_job_items (listing_id)',
 'CREATE INDEX ix_uw_apply_job_items_status ON uw_apply_job_items (status)',
 'CREATE INDEX ix_uw_review_selections_review_id ON uw_review_selections (review_id)',
 'CREATE INDEX ix_uw_review_selections_review_item_id ON uw_review_selections (review_item_id)',
 'CREATE INDEX ix_uw_workspace_locks_channel_id ON uw_workspace_locks (channel_id)',
 'CREATE INDEX ix_uw_workspace_locks_expires_at ON uw_workspace_locks (expires_at)',
 'CREATE INDEX ix_uw_workspace_locks_listing_id ON uw_workspace_locks (listing_id)',
 'CREATE INDEX ix_uw_workspace_locks_workspace_id ON uw_workspace_locks (workspace_id)',
 'CREATE INDEX ix_uw_apply_attempts_apply_job_id ON uw_apply_attempts (apply_job_id)',
 'CREATE INDEX ix_uw_apply_attempts_apply_job_item_id ON uw_apply_attempts (apply_job_item_id)',
 'CREATE INDEX ix_uw_apply_attempts_channel_id ON uw_apply_attempts (channel_id)',
 'CREATE INDEX ix_uw_apply_attempts_correlation_id ON uw_apply_attempts (correlation_id)',
 'CREATE INDEX ix_uw_apply_attempts_listing_id ON uw_apply_attempts (listing_id)',
 'CREATE INDEX ix_uw_apply_attempt_events_attempt_id ON uw_apply_attempt_events (attempt_id)',
 'CREATE INDEX ix_uw_apply_attempt_events_outcome ON uw_apply_attempt_events (outcome)',
 'ALTER TABLE uw_drafts ADD FOREIGN KEY(current_revision_id) REFERENCES uw_draft_revisions (id) ON DELETE RESTRICT')
