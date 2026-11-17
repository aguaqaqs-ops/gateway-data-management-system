"""Single baseline for disposable telemetry; never applied to the control DB.

Creation/verification and connections are owned by the statistics store. A schema
mismatch disables telemetry and requires explicit operator repair, never migration.
"""

SCHEMA_VERSION = 1
PAGE_SIZE = 4096

SCHEMA_SQL = """
CREATE TABLE storage_observations (
 id INTEGER PRIMARY KEY, source_event_id TEXT NOT NULL UNIQUE,
 environment_id TEXT NOT NULL, group_id TEXT NOT NULL, repository_id TEXT,
 service_owner TEXT NOT NULL,
 category TEXT NOT NULL CHECK(category IN ('repository','durable','canonical','comparison','export','scratch','metadata','public_unknown','filesystem')),
 object_count INTEGER CHECK(object_count >= 0), logical_bytes INTEGER CHECK(logical_bytes >= 0),
 allocated_bytes INTEGER CHECK(allocated_bytes >= 0),
 unverified_reference_bytes INTEGER CHECK(unverified_reference_bytes >= 0),
 filesystem_id TEXT, total_bytes INTEGER CHECK(total_bytes >= 0),
 available_bytes INTEGER CHECK(available_bytes >= 0), available_inodes INTEGER CHECK(available_inodes >= 0),
 window_start_us INTEGER CHECK(window_start_us >= 0), window_end_us INTEGER NOT NULL CHECK(window_end_us >= 0),
 generated_at_us INTEGER NOT NULL CHECK(generated_at_us >= 0), quality TEXT NOT NULL, reason TEXT,
 CHECK((category='filesystem' AND repository_id IS NULL AND filesystem_id IS NOT NULL
 AND object_count IS NULL AND logical_bytes IS NULL AND allocated_bytes IS NULL AND unverified_reference_bytes IS NULL)
 OR (category!='filesystem' AND filesystem_id IS NULL AND total_bytes IS NULL AND available_bytes IS NULL AND available_inodes IS NULL))
) STRICT;
CREATE INDEX storage_repository_window ON storage_observations(repository_id,category,window_end_us,id);
CREATE INDEX storage_repository_time ON storage_observations(repository_id,window_end_us,id);
CREATE INDEX storage_current ON storage_observations(repository_id,category,service_owner,filesystem_id,window_end_us,id);
CREATE INDEX storage_filesystem_window ON storage_observations(category,filesystem_id,window_end_us,id);
CREATE INDEX storage_retention ON storage_observations(window_end_us,id);
CREATE TABLE execution_summaries (
 environment_id TEXT NOT NULL, group_id TEXT NOT NULL,
 operation_id TEXT NOT NULL, step_id TEXT NOT NULL, claim_version INTEGER NOT NULL CHECK(claim_version >= 0),
 attempt_count INTEGER NOT NULL CHECK(attempt_count >= 0), process_instance_id TEXT NOT NULL, worker_id TEXT NOT NULL,
 repository_id TEXT, submit_attempt_id TEXT, started_at_us INTEGER CHECK(started_at_us >= 0),
 ended_at_us INTEGER CHECK(ended_at_us >= 0), duration_ms INTEGER CHECK(duration_ms >= 0),
 recorded_at_us INTEGER NOT NULL CHECK(recorded_at_us >= 0), observed_outcome TEXT NOT NULL,
 cpu_time_us INTEGER CHECK(cpu_time_us >= 0), rss_peak_bytes INTEGER CHECK(rss_peak_bytes >= 0),
 cgroup_peak_bytes INTEGER CHECK(cgroup_peak_bytes >= 0), read_bytes INTEGER CHECK(read_bytes >= 0),
 write_bytes INTEGER CHECK(write_bytes >= 0), scratch_peak_bytes INTEGER CHECK(scratch_peak_bytes >= 0),
 revision TEXT, config_digest TEXT, rules_digest TEXT, input_digest TEXT,
 metrics_json TEXT CHECK(metrics_json IS NULL OR (json_valid(metrics_json) AND length(CAST(metrics_json AS BLOB)) <= 12288)),
 quality TEXT NOT NULL, reason TEXT, PRIMARY KEY(operation_id,step_id,claim_version)
) STRICT;
CREATE INDEX execution_repository_recorded ON execution_summaries(repository_id,recorded_at_us,operation_id,step_id,claim_version);
CREATE INDEX execution_attempt_window ON execution_summaries(operation_id,step_id,attempt_count,claim_version);
CREATE INDEX execution_operation_recorded ON execution_summaries(operation_id,recorded_at_us,step_id,claim_version);
CREATE INDEX execution_retention ON execution_summaries(recorded_at_us);
CREATE TABLE resource_samples (
 id INTEGER PRIMARY KEY, source_event_id TEXT NOT NULL UNIQUE,
 environment_id TEXT NOT NULL, group_id TEXT NOT NULL, role TEXT NOT NULL, process_instance_id TEXT NOT NULL,
 operation_id TEXT, step_id TEXT, attempt_count INTEGER CHECK(attempt_count >= 0), claim_version INTEGER CHECK(claim_version >= 0),
 sampled_at_us INTEGER NOT NULL CHECK(sampled_at_us >= 0), cpu_time_us INTEGER CHECK(cpu_time_us >= 0),
 rss_bytes INTEGER CHECK(rss_bytes >= 0), cgroup_bytes INTEGER CHECK(cgroup_bytes >= 0),
 read_bytes INTEGER CHECK(read_bytes >= 0), write_bytes INTEGER CHECK(write_bytes >= 0), quality TEXT NOT NULL, reason TEXT,
 CHECK((operation_id IS NULL AND step_id IS NULL AND attempt_count IS NULL AND claim_version IS NULL)
 OR (operation_id IS NOT NULL AND step_id IS NOT NULL AND attempt_count IS NOT NULL AND claim_version IS NOT NULL))
) STRICT;
CREATE INDEX resource_process_window ON resource_samples(role,process_instance_id,sampled_at_us,id);
CREATE INDEX resource_role_window ON resource_samples(role,sampled_at_us,id);
CREATE INDEX resource_execution_window ON resource_samples(operation_id,step_id,claim_version,sampled_at_us,id);
CREATE INDEX resource_retention ON resource_samples(sampled_at_us,id);
CREATE TABLE write_observations (
 observation_id TEXT PRIMARY KEY NOT NULL, environment_id TEXT NOT NULL, group_id TEXT NOT NULL,
 repository_id TEXT NOT NULL, rs_operation_id TEXT NOT NULL, process_instance_id TEXT NOT NULL,
 operation_id TEXT, submission_id TEXT, before_commit TEXT, after_commit TEXT,
 before_start_us INTEGER CHECK(before_start_us >= 0), before_end_us INTEGER CHECK(before_end_us >= 0),
 after_start_us INTEGER CHECK(after_start_us >= 0), after_end_us INTEGER CHECK(after_end_us >= 0),
 before_logical_bytes INTEGER CHECK(before_logical_bytes >= 0), after_logical_bytes INTEGER CHECK(after_logical_bytes >= 0),
 before_allocated_bytes INTEGER CHECK(before_allocated_bytes >= 0), after_allocated_bytes INTEGER CHECK(after_allocated_bytes >= 0),
 logical_net_change_bytes INTEGER, allocated_net_change_bytes INTEGER,
 observed_outcome TEXT NOT NULL, quality TEXT NOT NULL, reason TEXT,
 recorded_at_us INTEGER NOT NULL CHECK(recorded_at_us >= 0)
) STRICT;
CREATE INDEX write_repository_recorded ON write_observations(repository_id,recorded_at_us,observation_id);
CREATE INDEX write_operation ON write_observations(rs_operation_id);
CREATE INDEX write_retention ON write_observations(recorded_at_us);
PRAGMA user_version=1;
"""
