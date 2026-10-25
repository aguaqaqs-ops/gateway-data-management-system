# Phase 6 前置验证 V8：门禁耗时剖析

## 运行范围与来源

| 项目 | 记录 |
| --- | --- |
| 主运行节点 | `ct108-gw-dms-05`，`gw-dms-test-05.lan` |
| 命令 | `GATEWAY_TEST_PACKAGES=backend,repository_service ./vnext/scripts/run-tests.sh --durations=0`；环境使用 `PATH=/home/dev/.cargo/bin:$PATH`、`TMPDIR=/home/dev/gdds-test-tmp` |
| 主运行 HEAD | 起止均为 `92d9439d65aba0507928feb9c8d970d50dc274e0`；起止 worktree clean；exit code `0` |
| 主运行时间 | `2026-10-25T08:09:35Z` 至 `2026-10-25T08:48:01Z`，墙钟 `38m26s` |
| 主运行日志 | `/home/dev/gdds-p6-logs/v8/v8-gate-profile-current-main-20261025.log`（节点 05） |
| 分段样本 | HEAD `6e7dece6864c66053134a30b2a214e4672f6a5eb`，在节点 05 于 `07:30:22Z–08:05:43Z` 采集；`6e7dece686..92d9439d65` 只增加/调整文档提交，`vnext/` tree 未变化 |
| 分段日志与数据 | `/home/dev/gdds-p6-logs/v8/compose-timing-segments-20261025.{log,jsonl}`、`compose-timing-direct-down-20261025.{log,jsonl}`；临时 pytest 插件位于同目录 |
| 当前 HEAD 的逐例阶段数据 | `/tmp/p6-v8-phases-current.tsv`（开发主机；244 个串行用例，另用 collect-only 清单核对收集数量） |
| 独立运行后核对 | owner 确认节点 05 无残留 Compose 栈或 Dolt 进程、8000 端口空闲且 main clean；本报告不重复访问节点 05 |

主运行是当前 main 的一次测量，不是正式门禁结论。分段子样本运行在较早 HEAD；由于它与当前 HEAD 之间的代码树 `vnext/` 完全相同，分段用于解释运行阶段，不将其表述为在当前 HEAD 上执行。分段 jsonl 共 23 行，其中 4 个用例为直接 down 计时改进后重复采集；下表按 nodeid 取最后一次记录，共 19 个唯一用例。

## Runner 结果与逐例耗时

| 批次 | 用例数 | 结果 | pytest 墙钟 | runner 记录 |
| --- | ---: | --- | ---: | ---: |
| backend 并行主体 | 2,917 | 2,917 passed，64 warnings | 46.55 s | 47 s |
| backend 串行组 | 39 | 39 passed，2,917 deselected，1 warning | 1,589.10 s | 1,590 s |
| repository_service 并行主体 | 1,740 | 1,739 passed，1 skipped | 48.04 s | 48 s |
| repository_service 串行组 | 205 | 205 passed，1,740 deselected | 585.55 s | 587 s |

`--durations=0` 的输出精度不足以显示低于 5 ms 的 phase；表中 `<0.005` 表示可见输出的上界，不能当成精确零值。每个串行用例均列出 setup、call、teardown。

### backend 串行批次（39 个用例）

| 用例 | setup (s) | call (s) | teardown (s) |
| --- | ---: | ---: | ---: |
| `test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect` | <0.005 | 218.500 | <0.005 |
| `test_archive_http.py::test_archive_body_middleware_returns_on_client_disconnect` | <0.005 | <0.005 | <0.005 |
| `test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` | <0.005 | 1.040 | <0.005 |
| `test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service` | <0.005 | 12.440 | <0.005 |
| `test_history_compose_e2e.py::test_compose_history_compare_journey_zero_write_restart` | <0.005 | 425.860 | <0.005 |
| `test_http_admission_shutdown_process.py::test_http_server_subprocess_fails_closed_when_repository_unreachable` | <0.005 | 0.840 | <0.005 |
| `test_http_admission_shutdown_process.py::test_uvicorn_sigterm_rejects_new_submit_before_exit` | <0.005 | 1.150 | <0.005 |
| `test_http_admission_shutdown_process.py::test_uvicorn_sigterm_rejects_new_history_compare_while_reads_remain` | <0.005 | 2.220 | <0.005 |
| `test_operation_http.py::test_operation_gets_remain_available_while_control_db_writer_holds_lock` | 0.090 | 5.190 | <0.005 |
| `test_operation_recovery_process.py::test_process_startup_takeover_moves_expired_running_to_retry_wait` | <0.005 | 0.720 | <0.005 |
| `test_operation_worker_integration.py::test_empty_file_backed_worker_reaches_ready_drains_and_reopens_wal` | <0.005 | 0.050 | <0.005 |
| `test_operation_worker_integration.py::test_registered_key_reaches_ready_with_empty_queue` | <0.005 | 0.050 | <0.005 |
| `test_operation_worker_integration.py::test_file_backed_heartbeat_and_concurrent_cancel_are_read_back` | <0.005 | 0.110 | <0.005 |
| `test_operation_worker_process.py::test_module_worker_bootstraps_empty_db_and_drains_on_sigterm` | <0.005 | 0.760 | <0.005 |
| `test_operation_worker_process.py::test_module_worker_failure_is_nonzero_and_redacted[corrupt]` | <0.005 | 0.690 | <0.005 |
| `test_operation_worker_process.py::test_module_worker_failure_is_nonzero_and_redacted[structure_mismatch]` | <0.005 | 0.750 | <0.005 |
| `test_operation_worker_process.py::test_missing_handler_failure_redacts_payload_token_path_and_sql` | <0.005 | 0.790 | <0.005 |
| `test_operation_worker_process.py::test_process_termination_respects_checkpoint_commit_barrier[before_checkpoint-1]` | <0.005 | 0.630 | <0.005 |
| `test_operation_worker_process.py::test_process_termination_respects_checkpoint_commit_barrier[after_checkpoint-2]` | <0.005 | 0.630 | <0.005 |
| `test_operation_worker_scheduler.py::test_committed_terminal_operation_is_not_heartbeat_lease_loss` | <0.005 | <0.005 | <0.005 |
| `test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey` | <0.005 | 192.900 | <0.005 |
| `test_ordered_submit_bisect_compose.py::test_ordered_submit_bisect_control_cases` | <0.005 | 223.140 | <0.005 |
| `test_ordered_submit_bisect_compose.py::test_preview_worker_restart_takes_over_expired_running_operation` | <0.005 | 130.410 | <0.005 |
| `test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey` | <0.005 | 71.940 | <0.005 |
| `test_sqlite_operation_store_integration.py::test_file_backed_writer_contention_maps_to_store_busy` | <0.005 | 0.050 | <0.005 |
| `test_sqlite_operation_store_integration.py::test_file_backed_process_termination_rolls_back_uncommitted_probe` | <0.005 | 0.640 | <0.005 |
| `test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart` | <0.005 | 21.590 | <0.005 |
| `test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` | <0.005 | 71.440 | <0.005 |
| `test_submit_compose_e2e.py::test_compose_submit_removes_deleted_user_and_sibling_tables` | <0.005 | 191.080 | <0.005 |
| `test_submit_job_effect.py::test_await_import_result_timeout_uses_bounded_submit_poll_sessions[1-RETRY_WAIT-RUNNING]` | <0.005 | 0.490 | <0.005 |
| `test_submit_job_effect.py::test_await_import_result_timeout_uses_bounded_submit_poll_sessions[2-RETRY_WAIT-RUNNING]` | <0.005 | 0.530 | <0.005 |
| `test_submit_job_effect.py::test_await_import_result_timeout_uses_bounded_submit_poll_sessions[3-MANUAL_RECOVERY_REQUIRED-MANUAL_RECOVERY_REQUIRED]` | <0.005 | 0.610 | <0.005 |
| `test_submit_job_effect.py::test_await_import_result_timeout_retries_until_repository_operation_is_terminal` | <0.005 | 0.760 | <0.005 |
| `test_submit_recovery.py::test_await_import_result_consumes_matching_terminal_after_repository_restart` | <0.005 | 7.060 | <0.005 |
| `test_submit_worker.py::test_submit_worker_reaches_ready_with_live_repository_service` | <0.005 | 0.600 | <0.005 |
| `test_submit_worker_process.py::test_module_worker_bootstraps_submit_registry_and_drains_on_sigterm` | <0.005 | 0.770 | <0.005 |
| `test_submit_worker_process.py::test_submit_process_termination_respects_checkpoint_commit_barrier[before_checkpoint-1]` | <0.005 | 0.610 | <0.005 |
| `test_submit_worker_process.py::test_submit_process_termination_respects_checkpoint_commit_barrier[after_checkpoint-2]` | <0.005 | 0.630 | <0.005 |
| `test_upload_streaming.py::test_stalled_body_times_out_while_waiting_for_next_chunk` | <0.005 | 0.010 | <0.005 |

### repository_service 串行批次（205 个用例）

| 用例 | setup (s) | call (s) | teardown (s) |
| --- | ---: | ---: | ---: |
| `test_admission.py::test_concurrent_release_does_not_over_issue_permits` | <0.005 | <0.005 | <0.005 |
| `test_admission.py::test_same_lease_concurrent_release_is_atomic` | <0.005 | <0.005 | <0.005 |
| `test_artifact_cleaner.py::test_shutdown_leaves_no_cleaner_thread` | 0.050 | <0.005 | <0.005 |
| `test_artifact_cleaner.py::test_cleanup_retries_after_notification` | 0.050 | 0.020 | <0.005 |
| `test_artifact_cleaner.py::test_held_recover_iterators_close_on_stop_and_restart` | 0.050 | 1.080 | <0.005 |
| `test_artifact_cleaner.py::test_admission_pin_blocks_cleaner_thread_until_released` | 0.320 | 0.060 | <0.005 |
| `test_artifact_cleaner.py::test_cleanup_failure_retries_after_interval_fallback` | 0.040 | 1.020 | <0.005 |
| `test_artifact_cleaner.py::test_join_timeout_raises` | 0.040 | 0.050 | <0.005 |
| `test_artifact_cleanup_integration.py::test_legal_ttl_delete_survives_restart_readiness` | <0.005 | 0.920 | <0.005 |
| `test_auth_lifecycle.py::TestDynamicReadiness::test_unavailable_control_db_makes_runtime_not_ready` | <0.005 | 0.220 | <0.005 |
| `test_compose_lifecycle_harness.py::test_wait_healthy_times_out_when_readiness_missing` | <0.005 | <0.005 | <0.005 |
| `test_compose_lifecycle_harness.py::test_wait_hold_container_ready_times_out_without_ready_json` | <0.005 | <0.005 | <0.005 |
| `test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up` | <0.005 | 19.990 | <0.005 |
| `test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up` | <0.005 | 11.540 | <0.005 |
| `test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up` | <0.005 | 15.070 | <0.005 |
| `test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up` | <0.005 | 1.830 | <0.005 |
| `test_dolt_runner_shutdown.py::test_terminate_and_reap_sends_term_then_kill` | <0.005 | 0.010 | <0.005 |
| `test_dolt_runner_shutdown.py::test_terminate_active_children_reaps_all_registered` | <0.005 | 0.010 | <0.005 |
| `test_import_admin_cli.py::test_root_lock_busy_exit_3` | <0.005 | 0.380 | <0.005 |
| `test_import_admin_cli.py::test_root_lock_busy_with_missing_db_exit_3` | <0.005 | 0.380 | <0.005 |
| `test_import_admin_cli.py::test_manual_barrier_cleared_after_apply_allows_dispatch` | <0.005 | 3.880 | <0.005 |
| `test_import_admission_crash.py::test_crash_after_pending_commit_restarts_to_succeeded` | <0.005 | 4.050 | <0.005 |
| `test_import_admission_crash.py::test_crash_after_pending_commit_aborts_on_restart` | <0.005 | 1.680 | <0.005 |
| `test_import_admission_crash.py::test_crash_after_queued_publish_replay_returns_same_202` | <0.005 | 4.640 | <0.005 |
| `test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | <0.005 | 23.670 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_running_claim]` | <0.005 | 4.750 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_package_extracted]` | <0.005 | 4.730 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_private_ref_created]` | <0.005 | 3.640 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_replay_before_marker]` | <0.005 | 5.480 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_marker_before_verification]` | <0.005 | 5.690 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_verification_before_second_main_check]` | <0.005 | 5.740 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_second_main_check_before_publish]` | <0.005 | 5.860 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_main_publish_before_succeeded]` | <0.005 | 5.290 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_succeeded_before_private_ref_cleanup]` | <0.005 | 4.900 | <0.005 |
| `test_import_dolt_crash.py::test_dolt_crash_recovery[after_succeeded_before_artifact_cleanup]` | <0.005 | 4.720 | <0.005 |
| `test_import_http.py::test_submit_rejects_queued_when_ready_file_removed_before_insert` | 0.050 | 0.040 | 0.010 |
| `test_import_http.py::test_submit_rejects_queued_when_ready_file_removed_after_finalize` | 0.050 | 0.040 | 0.010 |
| `test_import_http.py::test_submit_admission_pin_blocks_cooperative_cleanup` | 0.050 | 0.040 | 0.010 |
| `test_import_http.py::test_submit_same_key_during_pending_waits_for_resolution` | 0.050 | 0.040 | 0.010 |
| `test_import_http.py::test_submit_rejects_different_fingerprint_immediately_while_pending` | 0.050 | 0.040 | 0.010 |
| `test_import_http.py::test_submit_publish_sqlite_fault_returns_service_not_ready_not_404` | 0.060 | 0.040 | 0.010 |
| `test_import_http.py::test_submit_claim_before_abort_does_not_return_false_404` | 0.050 | 0.040 | 0.010 |
| `test_import_http.py::test_submit_abort_failure_replays_when_operation_already_claimed` | 0.050 | 0.040 | 0.010 |
| `test_import_marker_capacity.py::test_marker_query_count_is_branch_independent` | <0.005 | 15.370 | <0.005 |
| `test_import_provider.py::test_concurrent_streams_with_over_128k_field` | 0.170 | 5.960 | <0.005 |
| `test_import_recovery.py::test_crash_after_automatic_replay_increment_preserves_count` | <0.005 | 1.920 | <0.005 |
| `test_import_recovery.py::test_subprocess_crash_then_runtime_restart_recovers` | <0.005 | 4.090 | <0.005 |
| `test_import_recovery.py::test_startup_blocks_when_running_operation_provider_unreadable` | <0.005 | 0.510 | <0.005 |
| `test_import_shutdown.py::test_worker_threads_are_not_daemon` | <0.005 | 0.150 | <0.005 |
| `test_import_shutdown.py::test_shutdown_stops_claim_and_preserves_running` | <0.005 | 0.580 | <0.005 |
| `test_import_shutdown.py::test_stop_reports_join_timeout` | <0.005 | 0.320 | <0.005 |
| `test_import_shutdown.py::test_shutdown_preserves_running_when_replay_cancelled` | <0.005 | 0.370 | <0.005 |
| `test_import_shutdown.py::test_runtime_shutdown_preserves_running_during_active_import` | <0.005 | 0.170 | <0.005 |
| `test_import_shutdown.py::test_runtime_shutdown_closes_cleanly` | <0.005 | 0.240 | <0.005 |
| `test_import_shutdown.py::test_runtime_shutdown_retains_ownership_when_worker_hangs` | <0.005 | 0.560 | <0.005 |
| `test_import_shutdown.py::test_runtime_shutdown_propagates_bridge_shutdown_error_after_releasing_resources` | <0.005 | 1.330 | <0.005 |
| `test_import_submission.py::test_pending_admission_resolution_sqlite_fault_maps_to_service_not_ready` | 0.050 | 0.040 | 0.010 |
| `test_import_worker.py::test_manual_barrier_skips_queued_operation` | 0.040 | 0.530 | 0.070 |
| `test_import_worker.py::test_dispatcher_does_not_double_claim_same_repository` | 0.040 | 1.040 | 0.110 |
| `test_import_worker.py::test_same_repository_running_mutex_observed` | <0.005 | 0.420 | <0.005 |
| `test_import_worker.py::test_same_repository_fifo_completion_order` | <0.005 | 0.370 | <0.005 |
| `test_import_worker.py::test_cross_repository_respects_global_worker_bound` | <0.005 | 1.130 | <0.005 |
| `test_import_worker.py::test_context_load_failure_releases_reservation_and_in_flight` | <0.005 | 0.170 | <0.005 |
| `test_import_worker.py::test_context_load_failure_logs_transition_rejection` | <0.005 | 1.110 | <0.005 |
| `test_import_worker.py::test_dispatcher_survives_storage_glitch` | <0.005 | 0.350 | <0.005 |
| `test_import_worker.py::test_dispatcher_idle_does_not_poll` | <0.005 | 0.580 | <0.005 |
| `test_import_worker.py::test_notification_generation_prevents_lost_wakeup` | <0.005 | 0.080 | <0.005 |
| `test_import_worker.py::test_manual_barrier_allows_other_repository_to_succeed` | 0.040 | 0.050 | 0.060 |
| `test_import_worker.py::test_dispatcher_and_mutation_store_do_not_nested_transaction` | <0.005 | 0.060 | <0.005 |
| `test_import_worker.py::test_repository_lock_eviction_preserves_mutual_exclusion` | <0.005 | 0.100 | <0.005 |
| `test_import_worker.py::test_repository_lock_does_not_block_other_repositories` | <0.005 | 0.050 | <0.005 |
| `test_import_worker.py::test_worker_rejects_when_import_disk_admission_fails` | <0.005 | 0.170 | <0.005 |
| `test_import_worker.py::test_import_worker_pool_partial_start_joins_started_threads` | <0.005 | 0.150 | <0.005 |
| `test_import_worker.py::test_full_scan_timeout_cancels_and_reaps` | <0.005 | 0.940 | <0.005 |
| `test_import_worker_integration.py::test_dolt_worker_happy_path` | 0.200 | 3.040 | 0.070 |
| `test_import_worker_integration.py::test_multirepo_running_interrupt_restart_recovery` | <0.005 | 7.810 | <0.005 |
| `test_import_worker_integration.py::test_restart_recovery_multirepo_concurrent_claim` | <0.005 | 4.260 | <0.005 |
| `test_mutation_readiness.py::test_consumed_artifact_missing_bytes_does_not_block_readiness` | <0.005 | 3.720 | <0.005 |
| `test_p2_r1_audit_corrective.py::test_internal_rss_monitor_cannot_sample_after_stop_before_reap[stream]` | <0.005 | 0.030 | <0.005 |
| `test_p2_r1_audit_corrective.py::test_internal_rss_monitor_cannot_sample_after_stop_before_reap[discard]` | <0.005 | 0.030 | <0.005 |
| `test_p2_r1_audit_corrective.py::test_process_stream_timeout_during_blocked_wait` | <0.005 | 2.020 | <0.005 |
| `test_p2_r1_audit_corrective.py::test_process_stream_rejects_unterminated_oversized_line` | <0.005 | 1.030 | <0.005 |
| `test_p2_r1_audit_corrective.py::test_process_tree_and_cgroup_measurement_scope` | <0.005 | <0.005 | <0.005 |
| `test_p2_r1_audit_corrective.py::test_discard_runner_attaches_stdout_directly_to_devnull` | <0.005 | 0.020 | <0.005 |
| `test_row_stream_admission.py::test_permit_held_until_bridge_cleanup_and_released_on_aclose_error` | <0.005 | <0.005 | <0.005 |
| `test_row_stream_admission.py::test_route_construction_failure_closes_bridge_before_releasing_permit` | <0.005 | 0.010 | <0.005 |
| `test_row_stream_admission.py::test_route_construction_failure_propagates_cleanup_error_after_release` | <0.005 | 0.010 | <0.005 |
| `test_row_stream_admission.py::test_real_rows_route_rejects_ninth_before_response_start` | <0.005 | 0.010 | <0.005 |
| `test_runtime_admission_ownership.py::test_shutdown_cancels_active_upload_and_drains_permit_before_db` | <0.005 | 0.030 | <0.005 |
| `test_runtime_admission_ownership.py::test_shutdown_drains_row_stream_permit_before_db` | <0.005 | 1.060 | <0.005 |
| `test_runtime_admission_ownership.py::test_shutdown_noncooperative_upload_retains_durable_ownership` | <0.005 | 0.320 | <0.005 |
| `test_runtime_admission_ownership.py::test_shutdown_noncooperative_row_stream_retains_durable_ownership` | <0.005 | 0.300 | <0.005 |
| `test_snapshot_admin.py::test_missing_command_exits_2` | <0.005 | 0.330 | <0.005 |
| `test_snapshot_admin.py::test_unknown_command_exits_2` | <0.005 | 0.330 | <0.005 |
| `test_snapshot_admin.py::test_missing_data_root_exits_4` | <0.005 | 0.330 | <0.005 |
| `test_snapshot_admin.py::test_uninitialized_layout_exits_4` | <0.005 | 0.330 | <0.005 |
| `test_snapshot_admin.py::test_malformed_control_db_exits_4_without_create_or_migrate[missing]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_malformed_control_db_exits_4_without_create_or_migrate[garbage]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_malformed_control_db_exits_4_without_create_or_migrate[older]` | <0.005 | 0.400 | <0.005 |
| `test_snapshot_admin.py::test_malformed_control_db_exits_4_without_create_or_migrate[newer]` | <0.005 | 0.400 | <0.005 |
| `test_snapshot_admin.py::test_symlink_layout_component_exits_4` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_admin_requires_existing_regular_root_lock[missing-hold]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_admin_requires_existing_regular_root_lock[missing-check]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_admin_requires_existing_regular_root_lock[symlink-hold]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_admin_requires_existing_regular_root_lock[symlink-check]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_admin_rejects_symlink_data_root[hold]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_admin_rejects_symlink_data_root[check]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_admin_rejects_control_database_symlink[hold]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_admin_rejects_control_database_symlink[check]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_hold_checkpoints_and_holds_root_lock` | <0.005 | 0.750 | <0.005 |
| `test_snapshot_admin.py::test_running_holder_makes_hold_fail_closed` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_active_sqlite_writer_makes_checkpoint_fail_closed` | <0.005 | 0.590 | <0.005 |
| `test_snapshot_admin.py::test_ready_signal_releases_lock[2]` | <0.005 | 0.410 | <0.005 |
| `test_snapshot_admin.py::test_ready_signal_releases_lock[15]` | <0.005 | 0.400 | <0.005 |
| `test_snapshot_admin.py::test_signal_before_ready_fails_closed_and_releases_lock` | <0.005 | 0.050 | <0.005 |
| `test_snapshot_admin.py::test_broken_stdout_fails_closed_and_releases_lock` | <0.005 | 0.410 | <0.005 |
| `test_snapshot_admin.py::test_ready_json_omits_host_paths_and_secrets` | <0.005 | 0.410 | <0.005 |
| `test_snapshot_admin.py::test_check_passes_empty_initialized_root` | <0.005 | 0.390 | <0.005 |
| `test_snapshot_admin.py::test_dolt_initialization_failure_is_redacted_content_error` | <0.005 | 0.400 | <0.005 |
| `test_snapshot_admin.py::test_signal_during_dolt_check_reaps_child_and_releases_lock` | <0.005 | 0.410 | <0.005 |
| `test_snapshot_admin.py::test_check_allows_eligible_missing_artifact_bytes` | <0.005 | 0.390 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[layout_marker_garbage]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[component_symlink]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[component_cross_root]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[component_missing]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[optional_component_symlink]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[control_db_missing]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[control_db_garbage]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[control_db_older]` | <0.005 | 0.400 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[control_db_newer]` | <0.005 | 0.400 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[control_db_schema]` | <0.005 | 0.400 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[control_db_fk]` | <0.005 | 0.400 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[control_db_nonquiescent_wal]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[artifact_missing_required]` | <0.005 | 0.400 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[artifact_digest_mismatch]` | <0.005 | 0.390 | <0.005 |
| `test_snapshot_admin.py::test_check_faults_fail_closed_without_passed_json[artifact_symlink]` | <0.005 | 0.390 | <0.005 |
| `test_snapshot_admin.py::test_check_passes_valid_whole_root` | <0.005 | 1.420 | <0.005 |
| `test_snapshot_admin.py::test_running_service_makes_check_fail_before_provider` | <0.005 | 0.540 | <0.005 |
| `test_snapshot_admin.py::test_multi_repository_check_does_not_omit_and_hides_paths[dolt_unreadable]` | <0.005 | 1.360 | <0.005 |
| `test_snapshot_admin.py::test_dolt_probe_failure_reaps_children_and_query_temp` | <0.005 | 0.970 | <0.005 |
| `test_snapshot_admin.py::test_restore_procedure_rejects_live_root` | <0.005 | 0.290 | <0.005 |
| `test_snapshot_admin.py::test_incomplete_restore_copy_fails_check[sqlite_only]` | <0.005 | 0.380 | <0.005 |
| `test_snapshot_admin.py::test_incomplete_restore_copy_fails_check[partial_component]` | <0.005 | 0.390 | <0.005 |
| `test_snapshot_admin.py::test_incomplete_restore_copy_fails_check_with_dolt[single_dolt]` | <0.005 | 1.560 | <0.005 |
| `test_snapshot_admin.py::test_whole_root_restore_preserves_public_facts` | <0.005 | 6.370 | <0.005 |
| `test_upload_concurrency_admission.py::test_concurrent_same_key_loser_is_409_without_consuming_permit` | <0.005 | 0.020 | <0.005 |
| `test_uv_consume_script.py::test_real_uv_stale_lock_fails_on_controlled_run` | <0.005 | 1.340 | <0.005 |
| `test_uv_consume_script.py::test_real_uv_no_sync_cross_project_py_fails_before_run` | <0.005 | 0.040 | <0.005 |
| `test_uv_consume_script.py::test_real_uv_stale_lock_no_sync_controlled_fails_before_run` | <0.005 | 0.060 | <0.005 |
| `test_uv_consume_script.py::test_real_uv_native_no_sync_may_succeed_on_stale_lock_without_changing_lock` | <0.005 | 0.050 | <0.005 |
| `test_versioned_fixture_consumer_e2e.py::test_public_versioned_fixture_consumer_c1_c2_immutable_reads` | <0.005 | 7.880 | <0.005 |
| `test_versioned_fixture_consumer_harness.py::test_run_fixture_consumer_subprocess_kills_on_timeout` | <0.005 | 1.020 | <0.005 |
| `test_versioned_fixture_consumer_harness.py::test_stop_fixture_consumer_process_reaps_running_child` | <0.005 | 0.020 | <0.005 |
| `test_versioned_fixture_consumer_harness.py::test_stop_fixture_consumer_process_kills_exited_parent_group_child` | <0.005 | 10.030 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_arrow_bridge_backpressure_blocks_producer_until_consumer_reads` | <0.005 | 0.010 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_arrow_bridge_eos_enqueue_cancel_preserves_failure_terminal` | <0.005 | 0.100 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_arrow_bridge_queue_full_cancel_preserves_failure_terminal` | <0.005 | 0.100 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_arrow_bridge_close_sync_is_idempotent_for_concurrent_callers` | <0.005 | 0.050 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_close_sync_join_runs_outside_worker_condition_lock` | <0.005 | <0.005 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_close_sync_join_timeout_terminates_only_bridge_owned_children` | <0.005 | 0.110 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_close_sync_does_not_close_iterator_from_close_thread` | <0.005 | 1.010 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_close_sync_concurrent_timeout_escalates_once` | <0.005 | 0.160 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_close_sync_terminate_owned_failure_still_joins_worker` | <0.005 | 1.010 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_bridge_registry_close_all_aggregates_errors_and_survivors` | <0.005 | 0.010 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_request_close_sets_cancellation_before_worker_join` | <0.005 | 0.050 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_aclose_sets_cancellation_before_thread_cleanup` | <0.005 | 0.060 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_aclose_completes_cleanup_when_awaiting_task_cancelled` | <0.005 | 0.400 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_aclose_completes_cleanup_under_anyio_cancel_scope` | <0.005 | 0.010 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_streaming_response_waits_cleanup_under_anyio_cancel_scope` | <0.005 | 0.010 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_sustained_cancel_cleanup_does_not_spin_event_loop` | <0.005 | 0.300 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_close_all_waits_for_worker_thread_not_false_survivor` | <0.005 | 0.250 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_join_timeout_keeps_alive_worker_registered_until_exit` | <0.005 | 0.150 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_close_sync_follower_waits_when_worker_joins_during_escalation` | <0.005 | 0.310 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_close_sync_chains_terminate_error_under_join_timeout` | <0.005 | 0.110 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_terminate_and_reap_gate_dedupes_concurrent_callers` | <0.005 | 0.010 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_terminate_and_reap_unregisters_already_exited_process` | <0.005 | <0.005 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_terminate_and_reap_gate_table_stable_across_repeated_success` | <0.005 | <0.005 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_terminate_and_reap_propagates_leader_failure_to_waiter` | <0.005 | <0.005 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_terminate_and_reap_retries_after_leader_failure` | <0.005 | <0.005 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_terminate_owned_races_process_stream_close_path` | <0.005 | <0.005 | <0.005 |
| `test_versioned_read_arrow_bridge.py::test_close_sync_long_deadline_follower_wakes_on_published_outcome` | <0.005 | 0.310 | <0.005 |
| `test_versioned_read_arrow_slow_streams.py::test_bridge_test_probe_is_instance_scoped` | <0.005 | 0.200 | <0.005 |
| `test_versioned_read_arrow_slow_streams.py::test_slow_streams_do_not_poll_default_executor[1]` | <0.005 | 0.250 | <0.005 |
| `test_versioned_read_arrow_slow_streams.py::test_slow_streams_do_not_poll_default_executor[4]` | <0.005 | 0.250 | <0.005 |
| `test_versioned_read_arrow_slow_streams.py::test_slow_streams_do_not_poll_default_executor[8]` | <0.005 | 0.250 | <0.005 |
| `test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | <0.005 | 19.390 | <0.005 |
| `test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | <0.005 | 18.460 | <0.005 |
| `test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle` | <0.005 | 58.210 | <0.005 |
| `test_versioned_read_http_integration.py::test_http_branch_movement_keeps_pinned_rows` | 0.240 | 1.300 | 0.010 |
| `test_versioned_read_http_integration.py::test_http_large_table_emits_multiple_batches` | 0.230 | 15.150 | 0.010 |
| `test_versioned_read_http_integration.py::test_http_midstream_failure_aborts_transport` | 0.230 | 14.980 | 0.010 |
| `test_versioned_read_http_integration.py::test_http_disconnect_cancels_worker_and_cleans_query_files` | 0.230 | 15.330 | 0.010 |
| `test_versioned_read_http_integration.py::test_http_disconnect_reports_command_result_cancelled` | 0.230 | 113.940 | 0.010 |
| `test_versioned_read_http_integration.py::test_http_runtime_shutdown_closes_active_row_stream` | 0.230 | 14.870 | <0.005 |
| `test_versioned_read_http_integration.py::test_http_disconnect_does_not_break_concurrent_stream` | 0.230 | 15.010 | 0.010 |
| `test_versioned_read_http_integration.py::test_http_concurrent_row_streams_do_not_interfere` | 0.230 | 15.070 | 0.010 |
| `test_versioned_read_http_socket.py::test_http_socket_midstream_failure_aborts_without_eos` | 0.230 | 15.460 | 0.010 |
| `test_versioned_read_process.py::test_process_stream_cancellation_reaps_child` | 0.140 | <0.005 | <0.005 |
| `test_versioned_read_process.py::test_process_stream_cancel_before_start_raises` | 0.150 | <0.005 | <0.005 |
| `test_versioned_read_process.py::test_process_stream_close_is_idempotent` | 0.140 | <0.005 | <0.005 |
| `test_versioned_read_process.py::test_process_stream_concurrent_close_is_single_cleanup` | 0.140 | <0.005 | <0.005 |
| `test_versioned_read_process.py::test_process_stream_close_timed_out_sets_result_flag` | 0.140 | <0.005 | <0.005 |
| `test_versioned_read_process.py::test_dolt_runner_stream_close_on_cancel_sends_term` | 0.140 | 0.010 | <0.005 |
| `test_versioned_read_process.py::test_process_stream_callback_exception_still_reaps_child` | 0.140 | <0.005 | <0.005 |
| `test_versioned_read_provider.py::test_branch_movement_keeps_pinned_commit_immutable` | 0.180 | 2.050 | <0.005 |

逐例 phase 汇总与 runner 墙钟略有差异：backend 串行组可见 phase 合计约 1,588.2 s，repository_service 串行组约 586.9 s；pytest/runner 的剩余时间来自进程调度、报告与未显示的短 phase。它不改变排序结论。

## Compose 旅程分段

分段计时覆盖 19 个 Compose 相关用例（含 backend 两个容器门禁）。`image/build` 是缓存命中的构建动作和镜像身份校验，不是冷构建；`stack start` 是栈启动/readiness；`journey remainder` 是 pytest call 中扣除已计时项后的剩余部分，包括用例数据准备、请求/断言、等待和测试自身的生命周期逻辑；`teardown` 是容器与 Compose 清理。它不能解释为纯业务 endpoint 时间。

| 用例 | call (s) | image/build (s) | stack start (s) | journey remainder (s) | teardown (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect` | 218.509 | 1.343 | 14.146 | 199.693 | 3.327 |
| `test_backend_http_container_gate.py::test_backend_container_ready_and_stops_cleanly_with_repository_service` | 12.374 | 0.961 | 0.000 | 11.412 | 0.000 |
| `test_backend_http_container_gate.py::test_backend_image_builds_with_http_server_entrypoint` | 1.048 | 0.995 | 0.000 | 0.052 | 0.000 |
| `test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up` | 13.010 | 0.076 | 1.476 | 0.022 | 11.437 |
| `test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up` | 1.826 | 0.078 | 0.000 | 0.947 | 0.801 |
| `test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up` | 12.253 | 0.141 | 7.537 | 1.376 | 3.199 |
| `test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up` | 11.387 | 0.083 | 7.558 | 0.521 | 3.226 |
| `test_history_compose_e2e.py::test_compose_history_compare_journey_zero_write_restart` | 425.794 | 1.361 | 14.070 | 407.120 | 3.243 |
| `test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | 23.647 | 0.079 | 15.205 | 5.079 | 3.285 |
| `test_ordered_compare_compose.py::test_ordered_history_compare_compose_journey` | 192.924 | 1.348 | 14.079 | 174.135 | 3.362 |
| `test_ordered_submit_bisect_compose.py::test_ordered_submit_bisect_control_cases` | 223.209 | 4.071 | 42.203 | 166.864 | 10.071 |
| `test_ordered_submit_bisect_compose.py::test_preview_worker_restart_takes_over_expired_running_operation` | 128.427 | 1.342 | 14.068 | 109.624 | 3.394 |
| `test_review_compose_e2e.py::test_compose_submit_to_review_approve_journey` | 71.918 | 1.366 | 14.064 | 53.163 | 3.324 |
| `test_submit_compose_e2e.py::test_compose_accept_upload_import_poll_t3_read_journey` | 71.411 | 1.353 | 14.056 | 52.624 | 3.378 |
| `test_submit_compose_e2e.py::test_compose_submit_removes_deleted_user_and_sibling_tables` | 190.806 | 1.357 | 14.084 | 172.135 | 3.230 |
| `test_submit_compose_e2e.py::test_compose_three_process_submit_stack_smoke_and_backend_restart` | 21.489 | 1.371 | 14.047 | 2.671 | 3.399 |
| `test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | 18.406 | 0.078 | 7.543 | 7.536 | 3.249 |
| `test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | 19.339 | 0.141 | 7.558 | 8.443 | 3.197 |
| `test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle` | 58.146 | 0.077 | 31.251 | 22.082 | 4.736 |
| **合计（19 个唯一用例）** | **1715.923** | **17.621** | **232.945** | **1395.499** | **69.858** |

总计中缓存构建/镜像校验约 17.6 s、栈启动约 232.9 s、journey remainder 约 1,395.5 s、teardown 约 69.9 s。backend 的 9 个 Compose 旅程（不含两个容器门禁）在当前 main 串行主运行中 call 合计约 1,546.9 s；其中主要工作在旅程本体与等待，不在 image build。

### Archive 运行间方差

Archive call 在早先 HEAD `6e7dece686` 的完整 runner 中约 470.34 s；两次分段复测分别约 218.627 s、218.509 s；当前 main 完整 runner 为 218.50 s。完整 runner 的早先样本比当前值多约 251.8 s（约 2.15 倍）。当前及两次复测彼此接近，表明 470 s 是运行间异常值；本次没有证据确认成因，缓存/文件系统状态等只能作为待查假设。所有节省估算以下面的当前 main 主运行数据为准，不把异常值外推。

## 三个门禁耗时候选方向（DC48 第 3 项）

### 1. 动态端口与唯一项目名，允许 Compose 旅程同机并行

测试 harness 已为每次 Compose 旅程派生独立项目名；当前限制主要是固定 host 端口 8000 与全局串行保护。对当前 main 的 9 个 backend Compose 旅程 call 耗时做 LPT 贪心分配，假定无争用且 3 个 worker lane 可用：串行总和 1,546.86 s，2 lane 预计 makespan 776.10 s，节省 770.76 s；3 lane 预计 makespan 541.81 s，节省 1,005.05 s。以当前完整 runner 2,306 s 为分母，理论总门禁缩短约 33.4%（2 lane）或 43.6%（3 lane）；4 lane 的理想估值约 48.6%。

因此，动态端口方向在 3 lane 理想模型中达到“约 40% 以上”，但没有在本次验证中实际并行运行，43.6% 是上限型排程估算，不是已测收益。容器、Dolt、磁盘与 worker CPU 争用都可能降低收益；采用前需在节点上验证并发隔离与实际墙钟。2 lane 单独不足 40%。

### 2. 同一模块旅程共用一套栈

19 个用例的聚合栈启动与 teardown 为 302.8 s（约占整次 runner 13.1%），这是不现实的绝对上限：它假设所有边界都可合并。按 backend 9 个旅程，startup+teardown 约 191.5 s；如果粗略假设整组只启动/拆除一次，最多可省约 174 s（约 7.5%），且还未计为隔离状态增加的重置成本。repository_service 的 Compose 用例包含错误 readiness/token/network、非空 restore、import restart、fresh restore/restart 等专门验证生命周期与清理的场景，不应共用会掩盖这些边界的栈。backend 用例还使用各自的固定业务 ID/种子、会重启 worker/backend，并检查 repository effect；要共用栈需逐项证明 control DB、Dolt 仓库、artifact、凭据、operation ID、worker 重启状态可隔离。预计单独方向达不到 40%，且实际可实现收益会低于上述上限。

逐项隔离审查清单（本次没有实施栈复用）：

| 模块 | 必须审查的用例 | 需要保留的隔离/生命周期事实 |
| --- | --- | --- |
| backend | `test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect` | 双 actor、归档副作用、重启前后状态与固定业务种子 |
| backend | `test_compose_history_compare_journey_zero_write_restart` | History 状态、只读语义、重启恢复 |
| backend | `test_ordered_history_compare_compose_journey` | ordered 基线与提交读取状态 |
| backend | `test_ordered_submit_bisect_control_cases` | 多控制场景间独立基线与仓库状态 |
| backend | `test_preview_worker_restart_takes_over_expired_running_operation` | worker 接管、租约与过期 operation |
| backend | `test_compose_submit_to_review_approve_journey` | Submit/Review 状态与审核事实 |
| backend | `test_compose_accept_upload_import_poll_t3_read_journey` | 上传、导入与后续读路径的 operation/artifact 状态 |
| backend | `test_compose_submit_removes_deleted_user_and_sibling_tables` | 变化集、Dolt 写入与用户/表隔离 |
| backend | `test_compose_three_process_submit_stack_smoke_and_backend_restart` | 三进程启动、backend 重启和 ready 边界 |
| backend | `test_backend_image_builds_with_http_server_entrypoint`、`test_backend_container_ready_and_stops_cleanly_with_repository_service` | image identity/build gate 与容器停止/readiness 断言 |
| repository_service | `test_compose_missing_readiness_cleans_up`、`test_compose_wrong_token_cleans_up`、`test_compose_wrong_network_cleans_up` | 故障配置、授权/网络拒绝与失败清理必须各自独立 |
| repository_service | `test_compose_non_empty_restore_target_cleans_up` | restore 前置状态与拒绝清理 |
| repository_service | `test_compose_repository_service_import_restart_replay` | 导入 replay、restart 与持久化状态 |
| repository_service | `test_compose_remote_client_commit_pinned_read_inside_network`、`test_compose_remote_client_commit_pinned_read_from_gate_host` | 两种 client 路径、网络边界、临时 client 与只读 commit 状态 |
| repository_service | `test_compose_repository_service_fresh_restart_restored_lifecycle` | fresh restore、命名卷复制及重启后的恢复事实 |

### 3. repository_service 串行组转为 `parallel_safe`

本次只做耗时剖析，没有对 205 个用例逐项修改或重分类。当前耗时最高的串行候选均有排除理由：Compose 用例依赖网络、容器、Dolt 与共享宿主资源；HTTP row-stream 用例依赖网络、worker/process/取消时序；worker、Dolt integration、snapshot admin 用例依赖 subprocess、Dolt 或持久化根；bridge/admission/shutdown 用例覆盖线程、取消和固定时间预算。按现有 `parallel_safe` 标准，这些都不能仅凭耗时数据归入并行组。当前可确认候选为 0，可确认收益为 0 s；在逐项源代码隔离审查前，不建议从串行组挪用例。

### DC48 门槛判断

候选 1 只有在至少 3 个 Compose lane 并发且资源争用可控时，模型才超过 40%；候选 2 与 3 单独均不接近门槛。综合判断：测试基础设施改动有达到门槛的可行路径，但尚未实测证明；是否插入阶段应以动态端口实现后的 3 lane 端到端复测为准，不能把本次 43.6% 估值当成已验证结果。

## 异常、限制与后续清理

- 分段时间是缓存命中环境，build 值不能代表冷构建；journey remainder 还含 fixture、准备、请求、等待与校验。
- Archive 早期约 470 s 样本原因未明；本次没有重跑来追查，也不从测试日志推断根因。
- 本报告基于主运行日志及分段 JSONL 汇总；不包含原始测量 payload。真实数据未写入 Git。
- owner 已完成节点 05 的 Compose/Dolt/端口/worktree 独立核对；本报告未执行清理。

需要 owner 后续清理的测量材料：

- 节点 05：`/home/dev/gdds-p6-logs/v8/` 下的 V8 日志、JSONL 与临时插件。
- 节点 05 与开发主机：`/home/dev/gdds-p6-v8-current-main.bundle`、`/tmp/gdds-p6-v8-current-main.bundle`。
- 开发主机：`/tmp/p6-v8-phases-current.tsv`、`/tmp/p6-v8-components.jsonl`、`/tmp/p6-v8-phases.tsv`。
- 节点 05：远程 ref `refs/remotes/p6-local/main`。
