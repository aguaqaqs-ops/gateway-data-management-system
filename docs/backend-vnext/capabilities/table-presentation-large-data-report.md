# Large Dataset Table Presentation Report

- Ruleset version: `backend-vnext/table-presentation-rules/v2`
- Dataset path: `/home/issac/test-dir/business-benchmark-data/business_large/large/sql/dbcfg.sql`
- Snapshot tables: `311`
- Snapshot rows: `246359`
- Consumed tables: `197`
- Unparsed tables excluded: `114`
- Sampling cap per table/group: `2048` rows
- Width formula: `clamp(max(title_width, p95_value_width) * 8 + 24, 56, 420)` for ordinary text; JSON/long-text columns may use a higher cap when present.

## Column Recommendations

| table/table-pattern | column | sample_count | p50 | p95 | max | recommended_width | reason |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| agc_cfg | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| agc_cfg | page_no | 0 |  |  |  | 96 | no sampled non-null values for page_no; fallback width 96 |
| agc_cfg | page_name | 0 |  |  |  | 200 | no sampled non-null values for page_name; fallback width 200 |
| agc_cfg | option_name | 0 |  |  |  | 200 | no sampled non-null values for option_name; fallback width 200 |
| agc_cfg | option_desc | 0 |  |  |  | 200 | no sampled non-null values for option_desc; fallback width 200 |
| agc_cfg | val_type | 0 |  |  |  | 132 | no sampled non-null values for val_type; fallback width 132 |
| agc_cfg | value | 0 |  |  |  | 200 | no sampled non-null values for value; fallback width 200 |
| agc_cfg | enum_set | 0 |  |  |  | 200 | no sampled non-null values for enum_set; fallback width 200 |
| agc_cfg | max | 0 |  |  |  | 200 | no sampled non-null values for max; fallback width 200 |
| agc_cfg | min | 0 |  |  |  | 200 | no sampled non-null values for min; fallback width 200 |
| app_cfg | app_name | 24 | 8 | 17 | 18 | 160 | title_width=8, p95_width=17, raw_width=160, cap=420, recommended_width=160, max_width=18 |
| app_cfg | enable | 24 | 4 | 4 | 5 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88, max_width=5 |
| app_cfg | run_board | 24 | 1 | 7 | 7 | 88 | title_width=8, p95_width=7, raw_width=88, cap=420, recommended_width=88 |
| app_cfg | table_cfg | 24 | 9 | 17 | 17 | 160 | title_width=8, p95_width=17, raw_width=160, cap=420, recommended_width=160 |
| app_cfg | exe | 24 | 5 | 13 | 13 | 128 | title_width=8, p95_width=13, raw_width=128, cap=420, recommended_width=128 |
| app_cfg | exea | 24 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| app_cfg | exep | 24 | 1 | 2 | 2 | 104 | title_width=10, p95_width=2, raw_width=104, cap=420, recommended_width=104 |
| clfile_cfg | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| clfile_cfg | page_no | 0 |  |  |  | 96 | no sampled non-null values for page_no; fallback width 96 |
| clfile_cfg | page_name | 0 |  |  |  | 200 | no sampled non-null values for page_name; fallback width 200 |
| clfile_cfg | option_name | 0 |  |  |  | 200 | no sampled non-null values for option_name; fallback width 200 |
| clfile_cfg | option_desc | 0 |  |  |  | 200 | no sampled non-null values for option_desc; fallback width 200 |
| clfile_cfg | val_type | 0 |  |  |  | 132 | no sampled non-null values for val_type; fallback width 132 |
| clfile_cfg | value | 0 |  |  |  | 200 | no sampled non-null values for value; fallback width 200 |
| clfile_cfg | enum_set | 0 |  |  |  | 200 | no sampled non-null values for enum_set; fallback width 200 |
| clfile_cfg | max | 0 |  |  |  | 200 | no sampled non-null values for max; fallback width 200 |
| clfile_cfg | min | 0 |  |  |  | 200 | no sampled non-null values for min; fallback width 200 |
| cnt_manage_cfg | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| cnt_manage_cfg | page_no | 0 |  |  |  | 96 | no sampled non-null values for page_no; fallback width 96 |
| cnt_manage_cfg | page_name | 0 |  |  |  | 200 | no sampled non-null values for page_name; fallback width 200 |
| cnt_manage_cfg | option_desc | 0 |  |  |  | 200 | no sampled non-null values for option_desc; fallback width 200 |
| cnt_manage_cfg | option_name | 0 |  |  |  | 200 | no sampled non-null values for option_name; fallback width 200 |
| cnt_manage_cfg | val_type | 0 |  |  |  | 132 | no sampled non-null values for val_type; fallback width 132 |
| cnt_manage_cfg | value | 0 |  |  |  | 200 | no sampled non-null values for value; fallback width 200 |
| cnt_manage_cfg | min | 0 |  |  |  | 200 | no sampled non-null values for min; fallback width 200 |
| cnt_manage_cfg | max | 0 |  |  |  | 200 | no sampled non-null values for max; fallback width 200 |
| cnt_manage_cfg | enum_set | 0 |  |  |  | 200 | no sampled non-null values for enum_set; fallback width 200 |
| cnt_manage_cfg | config_type | 0 |  |  |  | 132 | no sampled non-null values for config_type; fallback width 132 |
| cnt_manage_cfg | tips | 0 |  |  |  | 200 | no sampled non-null values for tips; fallback width 200 |
| ^b\d+_n\d+_dev104_cfg$ | no | 62 | 1 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_dev104_cfg$ | page_no | 62 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_dev104_cfg$ | page_name | 62 | 8 | 10 | 10 | 104 | title_width=6, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_dev104_cfg$ | option_desc | 62 | 18 | 24 | 24 | 216 | title_width=12, p95_width=24, raw_width=216, cap=420, recommended_width=216 |
| ^b\d+_n\d+_dev104_cfg$ | option_name | 62 | 18 | 24 | 24 | 216 | title_width=12, p95_width=24, raw_width=216, cap=420, recommended_width=216 |
| ^b\d+_n\d+_dev104_cfg$ | val_type | 62 | 5 | 6 | 6 | 104 | title_width=10, p95_width=6, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_dev104_cfg$ | value | 62 | 5 | 32 | 44 | 280 | title_width=2, p95_width=32, raw_width=280, cap=420, recommended_width=280, max_width=44 |
| ^b\d+_n\d+_dev104_cfg$ | min | 62 | 0 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_dev104_cfg$ | max | 62 | 0 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_dev104_cfg$ | enum_set | 62 | 0 | 35 | 109 | 304 | title_width=6, p95_width=35, raw_width=304, cap=560, recommended_width=304, max_width=109 |
| ^b\d+_n\d+_dev104_cfg$ | config_type | 62 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_dev104_cfg$ | tips | 62 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_dev104_dev_cfg$ | gid | 1 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_dev104_dev_cfg$ | dev_addr | 1 | 3 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_dev104_dev_cfg$ | description | 1 | 8 | 8 | 8 | 88 | title_width=8, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_dev104_dev_cfg$ | port | 1 | 4 | 4 | 4 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_dev104_dev_cfg$ | ip1 | 1 | 13 | 13 | 13 | 128 | title_width=7, p95_width=13, raw_width=128, cap=420, recommended_width=128 |
| ^b\d+_n\d+_dev104_dev_cfg$ | ip2 | 1 | 13 | 13 | 13 | 128 | title_width=7, p95_width=13, raw_width=128, cap=420, recommended_width=128 |
| ^b\d+_n\d+_dev104_dev_cfg$ | sp_dir | 1 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_dev104_dev_cfg$ | sc_pass | 1 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_dev104_dev_cfg$ | jhqx_pass | 1 | 1 | 1 | 1 | 120 | title_width=12, p95_width=1, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_dev104_dev_cfg$ | asdu116_pass | 1 | 1 | 1 | 1 | 144 | title_width=15, p95_width=1, raw_width=144, cap=420, recommended_width=144 |
| device | gid | 153 | 5 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| device | dev_addr | 153 | 2 | 3 | 5 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88, max_width=5 |
| device | map_addr | 153 | 2 | 3 | 5 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88, max_width=5 |
| device | description | 153 | 39 | 56 | 58 | 420 | title_width=8, p95_width=56, raw_width=472, cap=420, recommended_width=420, max_width=58 |
| device | model | 153 | 21 | 28 | 28 | 248 | title_width=8, p95_width=28, raw_width=248, cap=420, recommended_width=248 |
| device | scl_model | 153 | 21 | 28 | 28 | 248 | title_width=7, p95_width=28, raw_width=248, cap=420, recommended_width=248 |
| device | type | 153 | 6 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| device | version | 153 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device | ied_name | 153 | 6 | 7 | 7 | 80 | title_width=7, p95_width=7, raw_width=80, cap=420, recommended_width=80 |
| device | ip1 | 153 | 13 | 13 | 13 | 128 | title_width=3, p95_width=13, raw_width=128, cap=420, recommended_width=128 |
| device | ip2 | 153 | 13 | 13 | 13 | 128 | title_width=3, p95_width=13, raw_width=128, cap=420, recommended_width=128 |
| device | model_type | 153 | 7 | 7 | 7 | 88 | title_width=8, p95_width=7, raw_width=88, cap=420, recommended_width=88 |
| device | done_flag | 153 | 14 | 14 | 14 | 136 | title_width=8, p95_width=14, raw_width=136, cap=420, recommended_width=136 |
| device | board | 153 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device | ied_file | 142 | 31 | 31 | 35 | 272 | title_width=6, p95_width=31, raw_width=272, cap=420, recommended_width=272, max_width=35 |
| device | dev_state | 0 |  |  |  | 132 | no sampled non-null values for dev_state; fallback width 132 |
| device | bay_gid | 153 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device | equipment_type | 0 |  |  |  | 132 | no sampled non-null values for equipment_type; fallback width 132 |
| device | equipment_gid | 153 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device | csg_gid | 153 | 0 | 0 | 0 | 80 | title_width=7, p95_width=0, raw_width=80, cap=420, recommended_width=80 |
| device | reserve1 | 0 |  |  |  | 200 | no sampled non-null values for reserve1; fallback width 200 |
| device | reserve2 | 0 |  |  |  | 200 | no sampled non-null values for reserve2; fallback width 200 |
| device_cfg | no | 258 | 3 | 3 | 3 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56 |
| device_cfg | gid | 258 | 5 | 5 | 5 | 80 | title_width=7, p95_width=5, raw_width=80, cap=420, recommended_width=80 |
| device_cfg | page_no | 258 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| device_cfg | page_name | 258 | 8 | 10 | 10 | 104 | title_width=4, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| device_cfg | option_name | 258 | 16 | 20 | 24 | 184 | title_width=10, p95_width=20, raw_width=184, cap=420, recommended_width=184, max_width=24 |
| device_cfg | option_desc | 258 | 16 | 20 | 24 | 184 | title_width=8, p95_width=20, raw_width=184, cap=420, recommended_width=184, max_width=24 |
| device_cfg | val_type | 258 | 8 | 8 | 8 | 104 | title_width=10, p95_width=8, raw_width=104, cap=420, recommended_width=104 |
| device_cfg | value | 258 | 7 | 41 | 75 | 352 | title_width=2, p95_width=41, raw_width=352, cap=560, recommended_width=352, max_width=75 |
| device_cfg | enum_set | 258 | 0 | 19 | 33 | 176 | title_width=8, p95_width=19, raw_width=176, cap=560, recommended_width=176, max_width=33 |
| device_cfg | max | 258 | 0 | 4 | 5 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72, max_width=5 |
| device_cfg | min | 258 | 0 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| device_cnt | gid | 273 | 5 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| device_cnt | name | 273 | 6 | 7 | 7 | 80 | title_width=4, p95_width=7, raw_width=80, cap=420, recommended_width=80 |
| device_cnt | fcda | 273 | 0 | 0 | 0 | 56 | title_width=4, p95_width=0, raw_width=56, cap=420, recommended_width=56 |
| device_cnt | dev_addr | 273 | 3 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | grp_name | 273 | 4 | 4 | 4 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72 |
| device_cnt | grp_type | 273 | 7 | 7 | 7 | 80 | title_width=6, p95_width=7, raw_width=80, cap=420, recommended_width=80 |
| device_cnt | cpu_no | 273 | 1 | 1 | 1 | 64 | title_width=5, p95_width=1, raw_width=64, cap=420, recommended_width=64 |
| device_cnt | org_group | 273 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | grp | 273 | 3 | 3 | 3 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56 |
| device_cnt | entry | 273 | 3 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| device_cnt | fun | 273 | 1 | 1 | 1 | 56 | title_width=3, p95_width=1, raw_width=48, cap=420, recommended_width=56 |
| device_cnt | inf | 273 | 1 | 1 | 1 | 56 | title_width=3, p95_width=1, raw_width=48, cap=420, recommended_width=56 |
| device_cnt | type | 0 |  |  |  | 132 | no sampled non-null values for type; fallback width 132 |
| device_cnt | recv_time | 0 |  |  |  | 168 | no sampled non-null values for recv_time; fallback width 168 |
| device_cnt | recv_ms | 0 |  |  |  | 96 | no sampled non-null values for recv_ms; fallback width 96 |
| device_cnt | value | 0 |  |  |  | 96 | no sampled non-null values for value; fallback width 96 |
| device_cnt | save_period | 0 |  |  |  | 96 | no sampled non-null values for save_period; fallback width 96 |
| device_cnt | his_save | 273 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | cdc | 273 | 0 | 0 | 0 | 56 | title_width=3, p95_width=0, raw_width=48, cap=420, recommended_width=56 |
| device_cnt | point_model_id | 0 |  |  |  | 96 | no sampled non-null values for point_model_id; fallback width 96 |
| device_cnt | csg_gid | 273 | 0 | 0 | 0 | 80 | title_width=7, p95_width=0, raw_width=80, cap=420, recommended_width=80 |
| device_cnt | srouce_gid | 273 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_cnt | usr_name | 0 |  |  |  | 200 | no sampled non-null values for usr_name; fallback width 200 |
| device_cnt | deal_enable | 273 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | alarm_enable | 273 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | alarm_level | 273 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | alarm_ring | 273 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | equipment_type | 0 |  |  |  | 132 | no sampled non-null values for equipment_type; fallback width 132 |
| device_cnt | equipment_gid | 273 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | bay_gid | 273 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | err_chk | 273 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | update_chk | 273 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | stat_enable | 273 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_cnt | primary_val | 0 |  |  |  | 112 | no sampled non-null values for primary_val; fallback width 112 |
| device_cnt | secondary_val | 0 |  |  |  | 112 | no sampled non-null values for secondary_val; fallback width 112 |
| device_cnt | k | 273 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| device_cnt | b | 273 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| device_cnt | peak_limit | 0 |  |  |  | 112 | no sampled non-null values for peak_limit; fallback width 112 |
| device_cnt | day_limit | 0 |  |  |  | 112 | no sampled non-null values for day_limit; fallback width 112 |
| device_cnt | month_limit | 0 |  |  |  | 112 | no sampled non-null values for month_limit; fallback width 112 |
| device_cnt | ioa | 273 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_cnt | dc_redun | 273 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_co | gid | 2048 | 5 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| device_co | name | 2048 | 15 | 27 | 32 | 240 | title_width=4, p95_width=27, raw_width=240, cap=420, recommended_width=240, max_width=32 |
| device_co | fcda | 2048 | 31 | 37 | 39 | 320 | title_width=4, p95_width=37, raw_width=320, cap=420, recommended_width=320, max_width=39 |
| device_co | dev_addr | 2048 | 2 | 3 | 5 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88, max_width=5 |
| device_co | grp_name | 2048 | 4 | 4 | 12 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72, max_width=12 |
| device_co | grp_type | 2048 | 7 | 7 | 7 | 80 | title_width=6, p95_width=7, raw_width=80, cap=420, recommended_width=80 |
| device_co | cpu_no | 2048 | 1 | 1 | 1 | 64 | title_width=5, p95_width=1, raw_width=64, cap=420, recommended_width=64 |
| device_co | org_group | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_co | grp | 2048 | 1 | 3 | 3 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56 |
| device_co | entry | 2048 | 2 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| device_co | fun | 2048 | 1 | 2 | 3 | 56 | title_width=3, p95_width=2, raw_width=48, cap=420, recommended_width=56, max_width=3 |
| device_co | inf | 2048 | 2 | 3 | 3 | 56 | title_width=3, p95_width=3, raw_width=48, cap=420, recommended_width=56 |
| device_co | type | 0 |  |  |  | 132 | no sampled non-null values for type; fallback width 132 |
| device_co | open_rule | 2048 | 0 | 0 | 0 | 120 | title_width=12, p95_width=0, raw_width=120, cap=420, recommended_width=120 |
| device_co | close_rule | 2048 | 0 | 0 | 0 | 120 | title_width=12, p95_width=0, raw_width=120, cap=420, recommended_width=120 |
| device_co | his_save | 2048 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_co | ctlmodel | 2048 | 26 | 27 | 27 | 240 | title_width=8, p95_width=27, raw_width=240, cap=420, recommended_width=240 |
| device_co | tapchg | 2048 | 0 | 4 | 6 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72, max_width=6 |
| device_co | cdc | 2048 | 3 | 3 | 3 | 56 | title_width=3, p95_width=3, raw_width=48, cap=420, recommended_width=56 |
| device_co | point_model_id | 0 |  |  |  | 96 | no sampled non-null values for point_model_id; fallback width 96 |
| device_co | csg_gid | 2048 | 0 | 0 | 0 | 80 | title_width=7, p95_width=0, raw_width=80, cap=420, recommended_width=80 |
| device_co | srouce_gid | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_co | trigger_st | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_co | usr_name | 0 |  |  |  | 200 | no sampled non-null values for usr_name; fallback width 200 |
| device_co | deal_enable | 2048 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_co | alarm_enable | 2048 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_co | alarm_level | 2048 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_co | alarm_ring | 2048 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_co | equipment_type | 0 |  |  |  | 132 | no sampled non-null values for equipment_type; fallback width 132 |
| device_co | equipment_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_co | bay_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_co | st_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_co | mx_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_co | wf_chk | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_co | code_chk | 2048 | 4 | 4 | 4 | 120 | title_width=12, p95_width=4, raw_width=120, cap=420, recommended_width=120 |
| device_co | co_code | 0 |  |  |  | 200 | no sampled non-null values for co_code; fallback width 200 |
| device_co | ioa | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_co | dc_redun | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_mx | gid | 2048 | 5 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| device_mx | name | 2048 | 13 | 37 | 37 | 320 | title_width=4, p95_width=37, raw_width=320, cap=420, recommended_width=320 |
| device_mx | fcda | 2048 | 31 | 36 | 43 | 312 | title_width=4, p95_width=36, raw_width=312, cap=420, recommended_width=312, max_width=43 |
| device_mx | dev_addr | 2048 | 3 | 3 | 5 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88, max_width=5 |
| device_mx | grp_name | 2048 | 4 | 8 | 14 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88, max_width=14 |
| device_mx | grp_type | 2048 | 7 | 11 | 11 | 112 | title_width=6, p95_width=11, raw_width=112, cap=420, recommended_width=112 |
| device_mx | cpu_no | 2048 | 1 | 1 | 1 | 64 | title_width=5, p95_width=1, raw_width=64, cap=420, recommended_width=64 |
| device_mx | org_group | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_mx | grp | 2048 | 1 | 2 | 3 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56, max_width=3 |
| device_mx | entry | 2048 | 2 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| device_mx | fun | 2048 | 1 | 2 | 3 | 56 | title_width=3, p95_width=2, raw_width=48, cap=420, recommended_width=56, max_width=3 |
| device_mx | inf | 2048 | 2 | 3 | 3 | 56 | title_width=3, p95_width=3, raw_width=48, cap=420, recommended_width=56 |
| device_mx | type | 0 |  |  |  | 132 | no sampled non-null values for type; fallback width 132 |
| device_mx | unit | 2048 | 1 | 3 | 4 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56, max_width=4 |
| device_mx | recv_time | 0 |  |  |  | 168 | no sampled non-null values for recv_time; fallback width 168 |
| device_mx | recv_ms | 0 |  |  |  | 96 | no sampled non-null values for recv_ms; fallback width 96 |
| device_mx | value | 0 |  |  |  | 112 | no sampled non-null values for value; fallback width 112 |
| device_mx | primary_val | 0 |  |  |  | 112 | no sampled non-null values for primary_val; fallback width 112 |
| device_mx | secondary_val | 0 |  |  |  | 112 | no sampled non-null values for secondary_val; fallback width 112 |
| device_mx | k | 2048 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| device_mx | b | 2048 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| device_mx | save_period | 0 |  |  |  | 96 | no sampled non-null values for save_period; fallback width 96 |
| device_mx | his_save | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_mx | cdc | 2048 | 2 | 3 | 3 | 56 | title_width=3, p95_width=3, raw_width=48, cap=420, recommended_width=56 |
| device_mx | point_model_id | 0 |  |  |  | 96 | no sampled non-null values for point_model_id; fallback width 96 |
| device_mx | csg_gid | 2048 | 0 | 0 | 0 | 80 | title_width=7, p95_width=0, raw_width=80, cap=420, recommended_width=80 |
| device_mx | fresh_hold | 2048 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_mx | srouce_gid | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_mx | usr_name | 0 |  |  |  | 200 | no sampled non-null values for usr_name; fallback width 200 |
| device_mx | deal_enable | 2048 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_mx | alarm_enable | 2048 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_mx | alarm_level | 2048 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_mx | alarm_ring | 2048 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_mx | equipment_type | 0 |  |  |  | 132 | no sampled non-null values for equipment_type; fallback width 132 |
| device_mx | equipment_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_mx | bay_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_mx | abs | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_mx | overturn | 2048 | 4 | 4 | 4 | 56 | title_width=4, p95_width=4, raw_width=56, cap=420, recommended_width=56 |
| device_mx | co_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_mx | trend_enable | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_mx | stat_enable | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_mx | mutate_chk | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_mx | mutate_alarm | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_mx | update_chk | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_mx | limit_chk | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_mx | up2_limit | 0 |  |  |  | 112 | no sampled non-null values for up2_limit; fallback width 112 |
| device_mx | up_limit | 0 |  |  |  | 112 | no sampled non-null values for up_limit; fallback width 112 |
| device_mx | down_limit | 0 |  |  |  | 112 | no sampled non-null values for down_limit; fallback width 112 |
| device_mx | down2_limit | 0 |  |  |  | 112 | no sampled non-null values for down2_limit; fallback width 112 |
| device_mx | ioa | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_mx | dc_redun | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_sg | gid | 2048 | 5 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| device_sg | name | 2048 | 16 | 23 | 27 | 208 | title_width=4, p95_width=23, raw_width=208, cap=420, recommended_width=208, max_width=27 |
| device_sg | fcda | 2048 | 31 | 36 | 38 | 312 | title_width=4, p95_width=36, raw_width=312, cap=420, recommended_width=312, max_width=38 |
| device_sg | dev_addr | 2048 | 2 | 2 | 2 | 88 | title_width=8, p95_width=2, raw_width=88, cap=420, recommended_width=88 |
| device_sg | grp_name | 2048 | 4 | 4 | 4 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72 |
| device_sg | grp_type | 2048 | 7 | 7 | 7 | 80 | title_width=6, p95_width=7, raw_width=80, cap=420, recommended_width=80 |
| device_sg | cpu_no | 2048 | 1 | 1 | 1 | 64 | title_width=5, p95_width=1, raw_width=64, cap=420, recommended_width=64 |
| device_sg | org_group | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_sg | grp | 2048 | 2 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| device_sg | entry | 2048 | 2 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| device_sg | type | 0 |  |  |  | 132 | no sampled non-null values for type; fallback width 132 |
| device_sg | unit | 2048 | 1 | 3 | 3 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56 |
| device_sg | min | 1236 | 3 | 5 | 9 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72, max_width=9 |
| device_sg | max | 1236 | 5 | 7 | 10 | 80 | title_width=6, p95_width=7, raw_width=80, cap=420, recommended_width=80, max_width=10 |
| device_sg | step | 1236 | 4 | 4 | 8 | 56 | title_width=4, p95_width=4, raw_width=56, cap=420, recommended_width=56, max_width=8 |
| device_sg | precision | 2048 | 3 | 3 | 3 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56 |
| device_sg | recv_time | 0 |  |  |  | 168 | no sampled non-null values for recv_time; fallback width 168 |
| device_sg | recv_ms | 0 |  |  |  | 96 | no sampled non-null values for recv_ms; fallback width 96 |
| device_sg | val_type | 2048 | 7 | 7 | 7 | 88 | title_width=8, p95_width=7, raw_width=88, cap=420, recommended_width=88 |
| device_sg | val_gdd | 2048 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| device_sg | value | 2048 | 0 | 0 | 0 | 56 | title_width=2, p95_width=0, raw_width=40, cap=420, recommended_width=56 |
| device_sg | bit_des | 2048 | 0 | 0 | 0 | 104 | title_width=10, p95_width=0, raw_width=104, cap=420, recommended_width=104 |
| device_sg | his_save | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_sg | cdc | 2048 | 3 | 3 | 3 | 56 | title_width=3, p95_width=3, raw_width=48, cap=420, recommended_width=56 |
| device_sg | point_model_id | 0 |  |  |  | 96 | no sampled non-null values for point_model_id; fallback width 96 |
| device_sg | csg_gid | 2048 | 0 | 0 | 0 | 80 | title_width=7, p95_width=0, raw_width=80, cap=420, recommended_width=80 |
| device_sg | srouce_gid | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_sg | usr_name | 0 |  |  |  | 200 | no sampled non-null values for usr_name; fallback width 200 |
| device_sg | ioa | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_sg | dc_redun | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_sn | gid | 162 | 5 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| device_sn | name | 162 | 12 | 12 | 12 | 120 | title_width=4, p95_width=12, raw_width=120, cap=420, recommended_width=120 |
| device_sn | fcda | 162 | 24 | 24 | 24 | 216 | title_width=4, p95_width=24, raw_width=216, cap=420, recommended_width=216 |
| device_sn | dev_addr | 162 | 2 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| device_sn | grp_name | 162 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| device_sn | grp_type | 162 | 11 | 11 | 11 | 112 | title_width=6, p95_width=11, raw_width=112, cap=420, recommended_width=112 |
| device_sn | cpu_no | 162 | 1 | 1 | 1 | 64 | title_width=5, p95_width=1, raw_width=64, cap=420, recommended_width=64 |
| device_sn | org_group | 162 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_sn | grp | 162 | 2 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| device_sn | entry | 162 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| device_sn | type | 0 |  |  |  | 132 | no sampled non-null values for type; fallback width 132 |
| device_sn | min | 162 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| device_sn | max | 162 | 2 | 2 | 2 | 72 | title_width=6, p95_width=2, raw_width=72, cap=420, recommended_width=72 |
| device_sn | step | 162 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| device_sn | recv_time | 0 |  |  |  | 168 | no sampled non-null values for recv_time; fallback width 168 |
| device_sn | recv_ms | 0 |  |  |  | 96 | no sampled non-null values for recv_ms; fallback width 96 |
| device_sn | value | 0 |  |  |  | 96 | no sampled non-null values for value; fallback width 96 |
| device_sn | his_save | 162 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_sn | cdc | 162 | 2 | 2 | 2 | 56 | title_width=3, p95_width=2, raw_width=48, cap=420, recommended_width=56 |
| device_sn | point_model_id | 0 |  |  |  | 96 | no sampled non-null values for point_model_id; fallback width 96 |
| device_sn | csg_gid | 162 | 0 | 0 | 0 | 80 | title_width=7, p95_width=0, raw_width=80, cap=420, recommended_width=80 |
| device_sn | srouce_gid | 162 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_sn | usr_name | 0 |  |  |  | 200 | no sampled non-null values for usr_name; fallback width 200 |
| device_sn | ioa | 162 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_sn | dc_redun | 162 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_sp | gid | 2048 | 5 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| device_sp | name | 2048 | 13 | 18 | 22 | 168 | title_width=4, p95_width=18, raw_width=168, cap=420, recommended_width=168, max_width=22 |
| device_sp | fcda | 2048 | 29 | 33 | 35 | 288 | title_width=4, p95_width=33, raw_width=288, cap=420, recommended_width=288, max_width=35 |
| device_sp | dev_addr | 2048 | 2 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| device_sp | grp_name | 2048 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| device_sp | grp_type | 2048 | 11 | 11 | 11 | 112 | title_width=6, p95_width=11, raw_width=112, cap=420, recommended_width=112 |
| device_sp | cpu_no | 2048 | 1 | 1 | 1 | 64 | title_width=5, p95_width=1, raw_width=64, cap=420, recommended_width=64 |
| device_sp | org_group | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_sp | grp | 2048 | 1 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| device_sp | entry | 2048 | 1 | 2 | 2 | 72 | title_width=6, p95_width=2, raw_width=72, cap=420, recommended_width=72 |
| device_sp | type | 0 |  |  |  | 132 | no sampled non-null values for type; fallback width 132 |
| device_sp | unit | 2048 | 1 | 2 | 4 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56, max_width=4 |
| device_sp | min | 1865 | 5 | 8 | 9 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88, max_width=9 |
| device_sp | max | 1865 | 8 | 11 | 12 | 112 | title_width=6, p95_width=11, raw_width=112, cap=420, recommended_width=112, max_width=12 |
| device_sp | step | 1865 | 5 | 8 | 8 | 88 | title_width=4, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| device_sp | precision | 1983 | 3 | 3 | 3 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56 |
| device_sp | recv_time | 0 |  |  |  | 168 | no sampled non-null values for recv_time; fallback width 168 |
| device_sp | recv_ms | 0 |  |  |  | 96 | no sampled non-null values for recv_ms; fallback width 96 |
| device_sp | val_type | 2048 | 7 | 7 | 9 | 88 | title_width=8, p95_width=7, raw_width=88, cap=420, recommended_width=88, max_width=9 |
| device_sp | val_gdd | 2048 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| device_sp | value | 2048 | 0 | 0 | 0 | 56 | title_width=2, p95_width=0, raw_width=40, cap=420, recommended_width=56 |
| device_sp | his_save | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_sp | cdc | 2048 | 3 | 3 | 3 | 56 | title_width=3, p95_width=3, raw_width=48, cap=420, recommended_width=56 |
| device_sp | point_model_id | 0 |  |  |  | 96 | no sampled non-null values for point_model_id; fallback width 96 |
| device_sp | csg_gid | 2048 | 0 | 0 | 0 | 80 | title_width=7, p95_width=0, raw_width=80, cap=420, recommended_width=80 |
| device_sp | srouce_gid | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_sp | usr_name | 0 |  |  |  | 200 | no sampled non-null values for usr_name; fallback width 200 |
| device_sp | ioa | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_sp | dc_redun | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_st | gid | 2048 | 5 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| device_st | name | 2048 | 18 | 36 | 58 | 312 | title_width=4, p95_width=36, raw_width=312, cap=420, recommended_width=312, max_width=58 |
| device_st | fcda | 2048 | 29 | 35 | 35 | 304 | title_width=4, p95_width=35, raw_width=304, cap=420, recommended_width=304 |
| device_st | dev_addr | 2048 | 2 | 3 | 5 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88, max_width=5 |
| device_st | grp_name | 2048 | 4 | 8 | 16 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88, max_width=16 |
| device_st | grp_type | 2048 | 6 | 10 | 10 | 104 | title_width=6, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| device_st | cpu_no | 2048 | 1 | 1 | 1 | 64 | title_width=5, p95_width=1, raw_width=64, cap=420, recommended_width=64 |
| device_st | org_group | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_st | grp | 2048 | 2 | 2 | 3 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56, max_width=3 |
| device_st | entry | 2048 | 2 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| device_st | fun | 2048 | 2 | 2 | 3 | 56 | title_width=3, p95_width=2, raw_width=48, cap=420, recommended_width=56, max_width=3 |
| device_st | inf | 2048 | 2 | 3 | 3 | 56 | title_width=3, p95_width=3, raw_width=48, cap=420, recommended_width=56 |
| device_st | type | 0 |  |  |  | 132 | no sampled non-null values for type; fallback width 132 |
| device_st | recv_time | 0 |  |  |  | 168 | no sampled non-null values for recv_time; fallback width 168 |
| device_st | recv_ms | 0 |  |  |  | 96 | no sampled non-null values for recv_ms; fallback width 96 |
| device_st | value | 0 |  |  |  | 96 | no sampled non-null values for value; fallback width 96 |
| device_st | his_save | 2048 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_st | cdc | 2048 | 3 | 3 | 3 | 56 | title_width=3, p95_width=3, raw_width=48, cap=420, recommended_width=56 |
| device_st | point_model_id | 0 |  |  |  | 96 | no sampled non-null values for point_model_id; fallback width 96 |
| device_st | csg_gid | 2048 | 0 | 0 | 0 | 80 | title_width=7, p95_width=0, raw_width=80, cap=420, recommended_width=80 |
| device_st | srouce_gid | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_st | usr_name | 0 |  |  |  | 200 | no sampled non-null values for usr_name; fallback width 200 |
| device_st | deal_enable | 2048 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_st | alarm_enable | 2048 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_st | alarm_level | 2048 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_st | alarm_ring | 2048 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_st | equipment_type | 0 |  |  |  | 132 | no sampled non-null values for equipment_type; fallback width 132 |
| device_st | equipment_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_st | bay_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_st | overturn | 2048 | 4 | 4 | 4 | 56 | title_width=4, p95_width=4, raw_width=56, cap=420, recommended_width=56 |
| device_st | dpi_gid | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_st | co_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_st | mx_gid | 2048 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_st | stat_enable | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_st | count_alarm | 2048 | 1 | 1 | 1 | 120 | title_width=12, p95_width=1, raw_width=120, cap=420, recommended_width=120 |
| device_st | timer_alarm | 2048 | 1 | 1 | 1 | 144 | title_width=15, p95_width=1, raw_width=144, cap=420, recommended_width=144 |
| device_st | reset_gid | 2048 | 1 | 1 | 1 | 120 | title_width=12, p95_width=1, raw_width=120, cap=420, recommended_width=120 |
| device_st | auto_off_time | 2048 | 1 | 1 | 1 | 144 | title_width=15, p95_width=1, raw_width=144, cap=420, recommended_width=144 |
| device_st | delay_time | 2048 | 1 | 1 | 1 | 144 | title_width=15, p95_width=1, raw_width=144, cap=420, recommended_width=144 |
| device_st | trip1_gid | 2048 | 1 | 1 | 1 | 128 | title_width=13, p95_width=1, raw_width=128, cap=420, recommended_width=128 |
| device_st | trip2_gid | 2048 | 1 | 1 | 1 | 128 | title_width=13, p95_width=1, raw_width=128, cap=420, recommended_width=128 |
| device_st | ioa | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_st | dc_redun | 2048 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| device_tap | gid | 146 | 5 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| device_tap | name | 146 | 10 | 10 | 10 | 104 | title_width=4, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| device_tap | fcda | 146 | 35 | 35 | 35 | 304 | title_width=4, p95_width=35, raw_width=304, cap=420, recommended_width=304 |
| device_tap | dev_addr | 146 | 2 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| device_tap | grp_name | 146 | 4 | 4 | 4 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72 |
| device_tap | grp_type | 146 | 7 | 7 | 7 | 80 | title_width=6, p95_width=7, raw_width=80, cap=420, recommended_width=80 |
| device_tap | cpu_no | 146 | 1 | 1 | 1 | 64 | title_width=5, p95_width=1, raw_width=64, cap=420, recommended_width=64 |
| device_tap | org_group | 146 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_tap | grp | 146 | 2 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| device_tap | entry | 146 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| device_tap | fun | 146 | 2 | 2 | 2 | 56 | title_width=3, p95_width=2, raw_width=48, cap=420, recommended_width=56 |
| device_tap | inf | 146 | 1 | 1 | 1 | 56 | title_width=3, p95_width=1, raw_width=48, cap=420, recommended_width=56 |
| device_tap | type | 0 |  |  |  | 132 | no sampled non-null values for type; fallback width 132 |
| device_tap | recv_time | 0 |  |  |  | 168 | no sampled non-null values for recv_time; fallback width 168 |
| device_tap | recv_ms | 0 |  |  |  | 96 | no sampled non-null values for recv_ms; fallback width 96 |
| device_tap | value | 0 |  |  |  | 96 | no sampled non-null values for value; fallback width 96 |
| device_tap | his_save | 146 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_tap | cdc | 146 | 3 | 3 | 3 | 56 | title_width=3, p95_width=3, raw_width=48, cap=420, recommended_width=56 |
| device_tap | point_model_id | 0 |  |  |  | 96 | no sampled non-null values for point_model_id; fallback width 96 |
| device_tap | csg_gid | 146 | 0 | 0 | 0 | 80 | title_width=7, p95_width=0, raw_width=80, cap=420, recommended_width=80 |
| device_tap | srouce_gid | 146 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_tap | usr_name | 0 |  |  |  | 200 | no sampled non-null values for usr_name; fallback width 200 |
| device_tap | deal_enable | 146 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_tap | alarm_enable | 146 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| device_tap | alarm_level | 146 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_tap | alarm_ring | 146 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| device_tap | equipment_type | 0 |  |  |  | 132 | no sampled non-null values for equipment_type; fallback width 132 |
| device_tap | equipment_gid | 146 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_tap | bay_gid | 146 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_tap | co_gid | 146 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| device_tap | ioa | 146 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| device_tap | dc_redun | 146 | 4 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| fault_msg_cfg | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| fault_msg_cfg | dev_addr | 0 |  |  |  | 96 | no sampled non-null values for dev_addr; fallback width 96 |
| fault_msg_cfg | oid | 0 |  |  |  | 96 | no sampled non-null values for oid; fallback width 96 |
| fault_msg_cfg | grp | 0 |  |  |  | 96 | no sampled non-null values for grp; fallback width 96 |
| fault_msg_cfg | entry | 0 |  |  |  | 96 | no sampled non-null values for entry; fallback width 96 |
| fault_msg_cfg | name | 0 |  |  |  | 200 | no sampled non-null values for name; fallback width 200 |
| fault_msg_cfg | fault_type | 0 |  |  |  | 132 | no sampled non-null values for fault_type; fallback width 132 |
| fault_msg_cfg | unit | 0 |  |  |  | 200 | no sampled non-null values for unit; fallback width 200 |
| fault_msg_cfg | pri_id | 0 |  |  |  | 96 | no sampled non-null values for pri_id; fallback width 96 |
| fault_msg_cfg | gid | 0 |  |  |  | 96 | no sampled non-null values for gid; fallback width 96 |
| ^b\d+_n\d+_iec104_cfg$ | no | 2048 | 2 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec104_cfg$ | page_no | 2048 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec104_cfg$ | page_name | 2048 | 8 | 10 | 10 | 104 | title_width=6, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_cfg$ | option_desc | 2048 | 20 | 36 | 38 | 312 | title_width=12, p95_width=36, raw_width=312, cap=420, recommended_width=312, max_width=38 |
| ^b\d+_n\d+_iec104_cfg$ | option_name | 2048 | 20 | 36 | 38 | 312 | title_width=12, p95_width=36, raw_width=312, cap=420, recommended_width=312, max_width=38 |
| ^b\d+_n\d+_iec104_cfg$ | val_type | 2048 | 6 | 8 | 8 | 104 | title_width=10, p95_width=8, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_cfg$ | value | 2048 | 5 | 34 | 44 | 296 | title_width=2, p95_width=34, raw_width=296, cap=420, recommended_width=296, max_width=44 |
| ^b\d+_n\d+_iec104_cfg$ | min | 2048 | 0 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_cfg$ | max | 2048 | 0 | 3 | 5 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72, max_width=5 |
| ^b\d+_n\d+_iec104_cfg$ | enum_set | 2048 | 0 | 277 | 366 | 560 | title_width=6, p95_width=277, raw_width=2240, cap=560, recommended_width=560, max_width=366 |
| ^b\d+_n\d+_iec104_cfg$ | config_type | 2048 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_cfg$ | tips | 2048 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_dyk_list$ | gid | 0 |  |  |  | 96 | no sampled non-null values for gid; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | dev_addr | 0 |  |  |  | 96 | no sampled non-null values for dev_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | name | 0 |  |  |  | 200 | no sampled non-null values for name; fallback width 200 |
| ^b\d+_n\d+_iec104_dyk_list$ | inf_addr | 0 |  |  |  | 96 | no sampled non-null values for inf_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | op_attri | 0 |  |  |  | 200 | no sampled non-null values for op_attri; fallback width 200 |
| ^b\d+_n\d+_iec104_dyk_list$ | relation_bi | 0 |  |  |  | 96 | no sampled non-null values for relation_bi; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | relation_st | 0 |  |  |  | 132 | no sampled non-null values for relation_st; fallback width 132 |
| ^b\d+_n\d+_iec104_dyk_list$ | no_chk_jump | 0 |  |  |  | 96 | no sampled non-null values for no_chk_jump; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | syn_chk_jump | 0 |  |  |  | 96 | no sampled non-null values for syn_chk_jump; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | volt_chk_jump | 0 |  |  |  | 96 | no sampled non-null values for volt_chk_jump; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | merge_chk_jump | 0 |  |  |  | 96 | no sampled non-null values for merge_chk_jump; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | grp | 0 |  |  |  | 96 | no sampled non-null values for grp; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | entry | 0 |  |  |  | 96 | no sampled non-null values for entry; fallback width 96 |
| ^b\d+_n\d+_iec104_dyk_list$ | fcda | 0 |  |  |  | 200 | no sampled non-null values for fcda; fallback width 200 |
| ^b\d+_n\d+_iec104_dyx_list$ | gid | 0 |  |  |  | 96 | no sampled non-null values for gid; fallback width 96 |
| ^b\d+_n\d+_iec104_dyx_list$ | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| ^b\d+_n\d+_iec104_dyx_list$ | dev_addr | 0 |  |  |  | 96 | no sampled non-null values for dev_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_dyx_list$ | name | 0 |  |  |  | 200 | no sampled non-null values for name; fallback width 200 |
| ^b\d+_n\d+_iec104_dyx_list$ | inf_addr | 0 |  |  |  | 96 | no sampled non-null values for inf_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_dyx_list$ | modify | 0 |  |  |  | 132 | no sampled non-null values for modify; fallback width 132 |
| ^b\d+_n\d+_iec104_dyx_list$ | cos | 0 |  |  |  | 132 | no sampled non-null values for cos; fallback width 132 |
| ^b\d+_n\d+_iec104_dyx_list$ | soe | 0 |  |  |  | 132 | no sampled non-null values for soe; fallback width 132 |
| ^b\d+_n\d+_iec104_dyx_list$ | grp | 0 |  |  |  | 96 | no sampled non-null values for grp; fallback width 96 |
| ^b\d+_n\d+_iec104_dyx_list$ | entry | 0 |  |  |  | 96 | no sampled non-null values for entry; fallback width 96 |
| ^b\d+_n\d+_iec104_dyx_list$ | fcda | 0 |  |  |  | 200 | no sampled non-null values for fcda; fallback width 200 |
| ^b\d+_n\d+_iec104_sc_list$ | gid | 0 |  |  |  | 96 | no sampled non-null values for gid; fallback width 96 |
| ^b\d+_n\d+_iec104_sc_list$ | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| ^b\d+_n\d+_iec104_sc_list$ | dev_addr | 0 |  |  |  | 96 | no sampled non-null values for dev_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_sc_list$ | name | 0 |  |  |  | 200 | no sampled non-null values for name; fallback width 200 |
| ^b\d+_n\d+_iec104_sc_list$ | inf_addr | 0 |  |  |  | 96 | no sampled non-null values for inf_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_sc_list$ | relation_bi | 0 |  |  |  | 96 | no sampled non-null values for relation_bi; fallback width 96 |
| ^b\d+_n\d+_iec104_sc_list$ | relation_st | 0 |  |  |  | 132 | no sampled non-null values for relation_st; fallback width 132 |
| ^b\d+_n\d+_iec104_sc_list$ | grp | 0 |  |  |  | 96 | no sampled non-null values for grp; fallback width 96 |
| ^b\d+_n\d+_iec104_sc_list$ | entry | 0 |  |  |  | 96 | no sampled non-null values for entry; fallback width 96 |
| ^b\d+_n\d+_iec104_syk_list$ | gid | 1464 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_syk_list$ | no | 1536 | 3 | 3 | 3 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec104_syk_list$ | dev_addr | 1464 | 2 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_syk_list$ | name | 1464 | 47 | 65 | 65 | 420 | title_width=4, p95_width=65, raw_width=544, cap=420, recommended_width=420 |
| ^b\d+_n\d+_iec104_syk_list$ | inf_addr | 1536 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_syk_list$ | op_attri | 1536 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_syk_list$ | relation_bi | 1536 | 1 | 1 | 1 | 120 | title_width=12, p95_width=1, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_iec104_syk_list$ | relation_st | 1536 | 4 | 4 | 4 | 120 | title_width=12, p95_width=4, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_iec104_syk_list$ | no_chk_jump | 1536 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_syk_list$ | syn_chk_jump | 1536 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_syk_list$ | volt_chk_jump | 1536 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_syk_list$ | merge_chk_jump | 1536 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_syk_list$ | grp | 1464 | 1 | 1 | 2 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56, max_width=2 |
| ^b\d+_n\d+_iec104_syk_list$ | entry | 1464 | 2 | 2 | 2 | 72 | title_width=6, p95_width=2, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_syk_list$ | fcda | 1464 | 29 | 36 | 36 | 312 | title_width=4, p95_width=36, raw_width=312, cap=420, recommended_width=312 |
| ^b\d+_n\d+_iec104_syx_list$ | gid | 1848 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_syx_list$ | no | 2048 | 4 | 4 | 4 | 56 | title_width=4, p95_width=4, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec104_syx_list$ | dev_addr | 1832 | 2 | 3 | 5 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88, max_width=5 |
| ^b\d+_n\d+_iec104_syx_list$ | name | 1848 | 54 | 78 | 92 | 420 | title_width=4, p95_width=78, raw_width=648, cap=420, recommended_width=420, max_width=92 |
| ^b\d+_n\d+_iec104_syx_list$ | inf_addr | 2048 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_syx_list$ | modify | 2048 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_syx_list$ | cos | 2048 | 5 | 5 | 5 | 80 | title_width=7, p95_width=5, raw_width=80, cap=420, recommended_width=80 |
| ^b\d+_n\d+_iec104_syx_list$ | soe | 2048 | 5 | 5 | 5 | 80 | title_width=7, p95_width=5, raw_width=80, cap=420, recommended_width=80 |
| ^b\d+_n\d+_iec104_syx_list$ | grp | 1832 | 2 | 2 | 3 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56, max_width=3 |
| ^b\d+_n\d+_iec104_syx_list$ | entry | 1832 | 2 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_syx_list$ | fcda | 1848 | 28 | 31 | 35 | 272 | title_width=4, p95_width=31, raw_width=272, cap=420, recommended_width=272, max_width=35 |
| ^b\d+_n\d+_iec104_yc_list$ | gid | 1780 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_yc_list$ | no | 1832 | 3 | 3 | 3 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec104_yc_list$ | dev_addr | 1756 | 2 | 3 | 5 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88, max_width=5 |
| ^b\d+_n\d+_iec104_yc_list$ | name | 1780 | 36 | 59 | 73 | 420 | title_width=4, p95_width=59, raw_width=496, cap=420, recommended_width=420, max_width=73 |
| ^b\d+_n\d+_iec104_yc_list$ | inf_addr | 1832 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_yc_list$ | coef_k | 1832 | 3 | 4 | 4 | 88 | title_width=8, p95_width=4, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_yc_list$ | coef_b | 1832 | 1 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_yc_list$ | valve_type | 1832 | 9 | 9 | 9 | 120 | title_width=12, p95_width=9, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_iec104_yc_list$ | valve_val | 1832 | 3 | 3 | 3 | 104 | title_width=10, p95_width=3, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_yc_list$ | asdu_type | 1832 | 8 | 8 | 8 | 88 | title_width=8, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_yc_list$ | upper_val | 1832 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_yc_list$ | lower_val | 1832 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_yc_list$ | limitvalue_flag | 1832 | 4 | 4 | 4 | 104 | title_width=10, p95_width=4, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_yc_list$ | supres_val | 1832 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_yc_list$ | grp | 1756 | 1 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec104_yc_list$ | entry | 1756 | 2 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_yc_list$ | fcda | 1780 | 29 | 37 | 37 | 320 | title_width=4, p95_width=37, raw_width=320, cap=420, recommended_width=320 |
| ^b\d+_n\d+_iec104_yc_list$ | balance_group | 1832 | 1 | 1 | 1 | 120 | title_width=12, p95_width=1, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_iec104_yc_list$ | balance_level | 1832 | 1 | 1 | 1 | 120 | title_width=12, p95_width=1, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_iec104_ym_list$ | gid | 0 |  |  |  | 96 | no sampled non-null values for gid; fallback width 96 |
| ^b\d+_n\d+_iec104_ym_list$ | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| ^b\d+_n\d+_iec104_ym_list$ | dev_addr | 0 |  |  |  | 96 | no sampled non-null values for dev_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_ym_list$ | name | 0 |  |  |  | 200 | no sampled non-null values for name; fallback width 200 |
| ^b\d+_n\d+_iec104_ym_list$ | inf_addr | 0 |  |  |  | 96 | no sampled non-null values for inf_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_ym_list$ | coef_k | 0 |  |  |  | 200 | no sampled non-null values for coef_k; fallback width 200 |
| ^b\d+_n\d+_iec104_ym_list$ | coef_b | 0 |  |  |  | 200 | no sampled non-null values for coef_b; fallback width 200 |
| ^b\d+_n\d+_iec104_ym_list$ | cycle | 0 |  |  |  | 132 | no sampled non-null values for cycle; fallback width 132 |
| ^b\d+_n\d+_iec104_ym_list$ | grp | 0 |  |  |  | 96 | no sampled non-null values for grp; fallback width 96 |
| ^b\d+_n\d+_iec104_ym_list$ | entry | 0 |  |  |  | 96 | no sampled non-null values for entry; fallback width 96 |
| ^b\d+_n\d+_iec104_ym_list$ | fcda | 0 |  |  |  | 200 | no sampled non-null values for fcda; fallback width 200 |
| ^b\d+_n\d+_iec104_yp_list$ | gid | 0 |  |  |  | 96 | no sampled non-null values for gid; fallback width 96 |
| ^b\d+_n\d+_iec104_yp_list$ | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| ^b\d+_n\d+_iec104_yp_list$ | dev_addr | 0 |  |  |  | 96 | no sampled non-null values for dev_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_yp_list$ | name | 0 |  |  |  | 200 | no sampled non-null values for name; fallback width 200 |
| ^b\d+_n\d+_iec104_yp_list$ | inf_addr | 0 |  |  |  | 96 | no sampled non-null values for inf_addr; fallback width 96 |
| ^b\d+_n\d+_iec104_yp_list$ | grp | 0 |  |  |  | 96 | no sampled non-null values for grp; fallback width 96 |
| ^b\d+_n\d+_iec104_yp_list$ | entry | 0 |  |  |  | 96 | no sampled non-null values for entry; fallback width 96 |
| ^b\d+_n\d+_iec104_yp_list$ | fcda | 0 |  |  |  | 200 | no sampled non-null values for fcda; fallback width 200 |
| ^b\d+_n\d+_iec104_yt_list$ | gid | 810 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_yt_list$ | no | 810 | 2 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec104_yt_list$ | dev_addr | 810 | 2 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_yt_list$ | name | 810 | 61 | 71 | 72 | 420 | title_width=4, p95_width=71, raw_width=592, cap=420, recommended_width=420, max_width=72 |
| ^b\d+_n\d+_iec104_yt_list$ | inf_addr | 810 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_yt_list$ | coef_k | 810 | 3 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec104_yt_list$ | coef_b | 810 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_yt_list$ | metering | 810 | 1 | 1 | 1 | 104 | title_width=10, p95_width=1, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec104_yt_list$ | upper_val | 810 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_yt_list$ | lower_val | 810 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_yt_list$ | grp | 810 | 2 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec104_yt_list$ | entry | 810 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec104_yt_list$ | fcda | 810 | 23 | 23 | 23 | 208 | title_width=4, p95_width=23, raw_width=208, cap=420, recommended_width=208 |
| ^b\d+_n\d+_iec61850c_cfg$ | no | 30 | 2 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec61850c_cfg$ | page_no | 30 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_iec61850c_cfg$ | page_name | 30 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec61850c_cfg$ | option_desc | 30 | 26 | 37 | 48 | 320 | title_width=12, p95_width=37, raw_width=320, cap=420, recommended_width=320, max_width=48 |
| ^b\d+_n\d+_iec61850c_cfg$ | option_name | 30 | 20 | 27 | 28 | 240 | title_width=12, p95_width=27, raw_width=240, cap=420, recommended_width=240, max_width=28 |
| ^b\d+_n\d+_iec61850c_cfg$ | val_type | 30 | 6 | 8 | 8 | 104 | title_width=10, p95_width=8, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec61850c_cfg$ | value | 30 | 4 | 14 | 19 | 136 | title_width=2, p95_width=14, raw_width=136, cap=420, recommended_width=136, max_width=19 |
| ^b\d+_n\d+_iec61850c_cfg$ | min | 30 | 0 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec61850c_cfg$ | max | 30 | 0 | 6 | 8 | 72 | title_width=6, p95_width=6, raw_width=72, cap=420, recommended_width=72, max_width=8 |
| ^b\d+_n\d+_iec61850c_cfg$ | enum_set | 30 | 4 | 84 | 474 | 560 | title_width=6, p95_width=84, raw_width=696, cap=560, recommended_width=560, max_width=474 |
| ^b\d+_n\d+_iec61850c_cfg$ | config_type | 30 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec61850c_cfg$ | tips | 30 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | gid | 142 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | dev_addr | 142 | 2 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | description | 142 | 39 | 57 | 58 | 420 | title_width=8, p95_width=57, raw_width=480, cap=420, recommended_width=420, max_width=58 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | type | 142 | 6 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | ip1 | 142 | 13 | 13 | 13 | 128 | title_width=7, p95_width=13, raw_width=128, cap=420, recommended_width=128 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | ip2 | 142 | 13 | 13 | 13 | 128 | title_width=7, p95_width=13, raw_width=128, cap=420, recommended_width=128 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | ip1_bak | 142 | 7 | 7 | 7 | 112 | title_width=11, p95_width=7, raw_width=112, cap=420, recommended_width=112 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | ip2_bak | 142 | 7 | 7 | 7 | 112 | title_width=11, p95_width=7, raw_width=112, cap=420, recommended_width=112 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | ied_name | 142 | 6 | 7 | 7 | 80 | title_width=7, p95_width=7, raw_width=80, cap=420, recommended_width=80 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | ld_name | 142 | 3 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | brcb_no | 142 | 3 | 3 | 3 | 104 | title_width=10, p95_width=3, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | urcb_no | 142 | 3 | 3 | 3 | 104 | title_width=10, p95_width=3, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | net_mode | 142 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | wave_dir | 142 | 8 | 8 | 8 | 120 | title_width=12, p95_width=8, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | wave_type | 142 | 13 | 13 | 13 | 128 | title_width=8, p95_width=13, raw_width=128, cap=420, recommended_width=128 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | scl_model | 142 | 21 | 28 | 28 | 248 | title_width=8, p95_width=28, raw_width=248, cap=420, recommended_width=248 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | wave_name_type | 142 | 10 | 10 | 10 | 120 | title_width=12, p95_width=10, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | wave_list_call_time | 142 | 3 | 3 | 3 | 184 | title_width=20, p95_width=3, raw_width=184, cap=420, recommended_width=184 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | wave_path | 0 |  |  |  | 200 | no sampled non-null values for wave_path; fallback width 200 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | rcb_attr_dyn | 142 | 4 | 4 | 5 | 200 | title_width=22, p95_width=4, raw_width=200, cap=420, recommended_width=200, max_width=5 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | rcb_para_indep | 142 | 12 | 12 | 12 | 232 | title_width=26, p95_width=12, raw_width=232, cap=420, recommended_width=232 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | file_suff_capital | 142 | 4 | 4 | 4 | 152 | title_width=16, p95_width=4, raw_width=152, cap=420, recommended_width=152 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | brcb_intgpd | 142 | 2 | 2 | 2 | 264 | title_width=30, p95_width=2, raw_width=264, cap=420, recommended_width=264 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | urcb_intgpd | 142 | 2 | 2 | 2 | 264 | title_width=30, p95_width=2, raw_width=264, cap=420, recommended_width=264 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | brcb_optflds | 142 | 4 | 4 | 4 | 280 | title_width=32, p95_width=4, raw_width=280, cap=420, recommended_width=280 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | urcb_optflds | 142 | 4 | 4 | 4 | 280 | title_width=32, p95_width=4, raw_width=280, cap=420, recommended_width=280 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | brcb_trgops | 142 | 2 | 2 | 2 | 272 | title_width=31, p95_width=2, raw_width=272, cap=420, recommended_width=272 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | urcb_trgops | 142 | 2 | 2 | 2 | 272 | title_width=31, p95_width=2, raw_width=272, cap=420, recommended_width=272 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | brcb_gi | 142 | 2 | 2 | 2 | 248 | title_width=28, p95_width=2, raw_width=248, cap=420, recommended_width=248 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | urcb_gi | 142 | 2 | 2 | 2 | 248 | title_width=28, p95_width=2, raw_width=248, cap=420, recommended_width=248 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | lcb_intgpd | 142 | 5 | 5 | 5 | 256 | title_width=29, p95_width=5, raw_width=256, cap=420, recommended_width=256 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | lcb_optflds | 142 | 4 | 4 | 4 | 272 | title_width=31, p95_width=4, raw_width=272, cap=420, recommended_width=272 |
| ^b\d+_n\d+_iec61850c_dev_cfg$ | lcb_trgops | 142 | 2 | 2 | 2 | 264 | title_width=30, p95_width=2, raw_width=264, cap=420, recommended_width=264 |
| jdxx_cfg | no | 3 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| jdxx_cfg | page_no | 3 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| jdxx_cfg | page_name | 3 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| jdxx_cfg | option_desc | 3 | 12 | 12 | 12 | 120 | title_width=12, p95_width=12, raw_width=120, cap=420, recommended_width=120 |
| jdxx_cfg | option_name | 3 | 9 | 13 | 13 | 128 | title_width=12, p95_width=13, raw_width=128, cap=420, recommended_width=128 |
| jdxx_cfg | val_type | 3 | 5 | 6 | 6 | 104 | title_width=10, p95_width=6, raw_width=104, cap=420, recommended_width=104 |
| jdxx_cfg | value | 3 | 3 | 6 | 6 | 72 | title_width=2, p95_width=6, raw_width=72, cap=420, recommended_width=72 |
| jdxx_cfg | min | 3 | 0 | 0 | 0 | 72 | title_width=6, p95_width=0, raw_width=72, cap=420, recommended_width=72 |
| jdxx_cfg | max | 3 | 0 | 0 | 0 | 72 | title_width=6, p95_width=0, raw_width=72, cap=420, recommended_width=72 |
| jdxx_cfg | enum_set | 3 | 0 | 15 | 17 | 144 | title_width=6, p95_width=15, raw_width=144, cap=560, recommended_width=144, max_width=17 |
| jdxx_cfg | config_type | 3 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| jdxx_cfg | tips | 3 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_nbridge_cfg$ | no | 176 | 1 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_nbridge_cfg$ | page_no | 176 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_nbridge_cfg$ | page_name | 176 | 16 | 16 | 18 | 152 | title_width=6, p95_width=16, raw_width=152, cap=420, recommended_width=152, max_width=18 |
| ^b\d+_n\d+_nbridge_cfg$ | option_desc | 176 | 15 | 20 | 24 | 184 | title_width=12, p95_width=20, raw_width=184, cap=420, recommended_width=184, max_width=24 |
| ^b\d+_n\d+_nbridge_cfg$ | option_name | 176 | 15 | 20 | 24 | 184 | title_width=12, p95_width=20, raw_width=184, cap=420, recommended_width=184, max_width=24 |
| ^b\d+_n\d+_nbridge_cfg$ | val_type | 176 | 6 | 8 | 8 | 104 | title_width=10, p95_width=8, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_nbridge_cfg$ | value | 176 | 5 | 13 | 19 | 128 | title_width=2, p95_width=13, raw_width=128, cap=420, recommended_width=128, max_width=19 |
| ^b\d+_n\d+_nbridge_cfg$ | min | 176 | 0 | 1 | 2 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72, max_width=2 |
| ^b\d+_n\d+_nbridge_cfg$ | max | 176 | 0 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| ^b\d+_n\d+_nbridge_cfg$ | enum_set | 176 | 0 | 178 | 196 | 560 | title_width=6, p95_width=178, raw_width=1448, cap=560, recommended_width=560, max_width=196 |
| ^b\d+_n\d+_nbridge_cfg$ | config_type | 176 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_nbridge_cfg$ | tips | 176 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| net_cfg | no | 23 | 2 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| net_cfg | index | 23 | 5 | 5 | 5 | 64 | title_width=4, p95_width=5, raw_width=64, cap=420, recommended_width=64 |
| net_cfg | board | 23 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| net_cfg | link_no | 23 | 2 | 2 | 2 | 72 | title_width=6, p95_width=2, raw_width=72, cap=420, recommended_width=72 |
| net_cfg | port | 23 | 4 | 4 | 4 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72 |
| net_cfg | net_card_a | 23 | 7 | 7 | 7 | 80 | title_width=3, p95_width=7, raw_width=80, cap=420, recommended_width=80 |
| net_cfg | net_card_b | 23 | 6 | 7 | 7 | 80 | title_width=3, p95_width=7, raw_width=80, cap=420, recommended_width=80 |
| net_cfg | net_card_c | 23 | 6 | 6 | 6 | 72 | title_width=3, p95_width=6, raw_width=72, cap=420, recommended_width=72 |
| net_cfg | net_card_d | 23 | 6 | 6 | 6 | 72 | title_width=3, p95_width=6, raw_width=72, cap=420, recommended_width=72 |
| net_cfg | protocol_no | 23 | 2 | 3 | 4 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72, max_width=4 |
| net_cfg | protocol_name | 23 | 15 | 18 | 23 | 168 | title_width=8, p95_width=18, raw_width=168, cap=420, recommended_width=168, max_width=23 |
| net_cfg | channel_desc | 23 | 14 | 18 | 18 | 168 | title_width=8, p95_width=18, raw_width=168, cap=420, recommended_width=168 |
| net_cfg | pro_cfg_file | 23 | 0 | 0 | 0 | 120 | title_width=12, p95_width=0, raw_width=120, cap=420, recommended_width=120 |
| net_cfg | dev_num | 23 | 1 | 1 | 3 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88, max_width=3 |
| net_cfg | tab_num | 23 | 2 | 2 | 2 | 104 | title_width=10, p95_width=2, raw_width=104, cap=420, recommended_width=104 |
| net_cfg | exe | 23 | 6 | 7 | 9 | 88 | title_width=8, p95_width=7, raw_width=88, cap=420, recommended_width=88, max_width=9 |
| net_cfg | exea | 23 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| net_cfg | exep | 23 | 2 | 2 | 2 | 104 | title_width=10, p95_width=2, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_nr103d_cfg$ | no | 41 | 2 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_nr103d_cfg$ | page_no | 41 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| ^b\d+_n\d+_nr103d_cfg$ | page_name | 41 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_nr103d_cfg$ | option_desc | 41 | 20 | 25 | 34 | 224 | title_width=12, p95_width=25, raw_width=224, cap=420, recommended_width=224, max_width=34 |
| ^b\d+_n\d+_nr103d_cfg$ | option_name | 41 | 20 | 25 | 34 | 224 | title_width=12, p95_width=25, raw_width=224, cap=420, recommended_width=224, max_width=34 |
| ^b\d+_n\d+_nr103d_cfg$ | val_type | 41 | 8 | 8 | 8 | 104 | title_width=10, p95_width=8, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_nr103d_cfg$ | value | 41 | 15 | 15 | 15 | 144 | title_width=2, p95_width=15, raw_width=144, cap=420, recommended_width=144 |
| ^b\d+_n\d+_nr103d_cfg$ | min | 41 | 0 | 1 | 2 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72, max_width=2 |
| ^b\d+_n\d+_nr103d_cfg$ | max | 41 | 0 | 3 | 5 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72, max_width=5 |
| ^b\d+_n\d+_nr103d_cfg$ | enum_set | 41 | 0 | 10 | 10 | 104 | title_width=6, p95_width=10, raw_width=104, cap=560, recommended_width=104 |
| ^b\d+_n\d+_nr103d_cfg$ | config_type | 41 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_nr103d_cfg$ | tips | 41 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_nr103d_dev_cfg$ | gid | 6 | 5 | 5 | 5 | 88 | title_width=8, p95_width=5, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_nr103d_dev_cfg$ | dev_addr | 6 | 3 | 3 | 3 | 88 | title_width=8, p95_width=3, raw_width=88, cap=420, recommended_width=88 |
| ^b\d+_n\d+_nr103d_dev_cfg$ | description | 6 | 15 | 19 | 19 | 176 | title_width=8, p95_width=19, raw_width=176, cap=420, recommended_width=176 |
| ^b\d+_n\d+_nr103d_dev_cfg$ | type | 6 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_nr103d_dev_cfg$ | yk_form | 6 | 7 | 7 | 7 | 120 | title_width=12, p95_width=7, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_nr103d_dev_cfg$ | yt_form | 6 | 7 | 7 | 7 | 120 | title_width=12, p95_width=7, raw_width=120, cap=420, recommended_width=120 |
| ^b\d+_n\d+_nr103d_dev_cfg$ | wavelist | 6 | 6 | 6 | 6 | 152 | title_width=16, p95_width=6, raw_width=152, cap=420, recommended_width=152 |
| ^b\d+_n\d+_nr103d_dev_cfg$ | res_rsc | 6 | 5 | 5 | 5 | 104 | title_width=10, p95_width=5, raw_width=104, cap=420, recommended_width=104 |
| ^b\d+_n\d+_nr103d_dev_cfg$ | check_msg | 6 | 5 | 5 | 5 | 152 | title_width=16, p95_width=5, raw_width=152, cap=420, recommended_width=152 |
| project | no | 590 | 3 | 3 | 3 | 56 | title_width=4, p95_width=3, raw_width=56, cap=420, recommended_width=56 |
| project | page_no | 590 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| project | page_name | 590 | 8 | 8 | 10 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88, max_width=10 |
| project | option_desc | 590 | 24 | 25 | 25 | 224 | title_width=12, p95_width=25, raw_width=224, cap=420, recommended_width=224 |
| project | option_name | 590 | 13 | 17 | 17 | 160 | title_width=12, p95_width=17, raw_width=160, cap=420, recommended_width=160 |
| project | val_type | 590 | 8 | 8 | 8 | 104 | title_width=10, p95_width=8, raw_width=104, cap=420, recommended_width=104 |
| project | value | 590 | 7 | 13 | 38 | 128 | title_width=2, p95_width=13, raw_width=128, cap=420, recommended_width=128, max_width=38 |
| project | min | 590 | 0 | 0 | 0 | 72 | title_width=6, p95_width=0, raw_width=72, cap=420, recommended_width=72 |
| project | max | 590 | 0 | 0 | 0 | 72 | title_width=6, p95_width=0, raw_width=72, cap=420, recommended_width=72 |
| project | enum_set | 590 | 0 | 0 | 0 | 72 | title_width=6, p95_width=0, raw_width=72, cap=560, recommended_width=72 |
| project | config_type | 590 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| project | tips | 590 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| prot_list | id | 6 | 2 | 2 | 2 | 56 | title_width=2, p95_width=2, raw_width=40, cap=420, recommended_width=56 |
| prot_list | prot_name | 6 | 16 | 22 | 23 | 200 | title_width=8, p95_width=22, raw_width=200, cap=420, recommended_width=200, max_width=23 |
| prot_list | prot_no | 6 | 3 | 4 | 4 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72 |
| prot_list | prot_type | 6 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| prot_list | port_type | 6 | 6 | 6 | 6 | 88 | title_width=8, p95_width=6, raw_width=88, cap=420, recommended_width=88 |
| prot_list | pro_cfg_file | 6 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| prot_list | exe | 6 | 6 | 8 | 9 | 88 | title_width=8, p95_width=8, raw_width=88, cap=420, recommended_width=88, max_width=9 |
| prot_list | exea | 6 | 1 | 1 | 1 | 88 | title_width=8, p95_width=1, raw_width=88, cap=420, recommended_width=88 |
| prot_list | exep | 6 | 2 | 2 | 2 | 104 | title_width=10, p95_width=2, raw_width=104, cap=420, recommended_width=104 |
| rdb_cfg | no | 11 | 1 | 2 | 2 | 56 | title_width=4, p95_width=2, raw_width=56, cap=420, recommended_width=56 |
| rdb_cfg | page_no | 11 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| rdb_cfg | page_name | 11 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| rdb_cfg | option_desc | 11 | 16 | 22 | 22 | 200 | title_width=12, p95_width=22, raw_width=200, cap=420, recommended_width=200 |
| rdb_cfg | option_name | 11 | 14 | 18 | 18 | 168 | title_width=12, p95_width=18, raw_width=168, cap=420, recommended_width=168 |
| rdb_cfg | val_type | 11 | 6 | 6 | 6 | 104 | title_width=10, p95_width=6, raw_width=104, cap=420, recommended_width=104 |
| rdb_cfg | value | 11 | 4 | 8 | 10 | 88 | title_width=2, p95_width=8, raw_width=88, cap=420, recommended_width=88, max_width=10 |
| rdb_cfg | min | 11 | 0 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| rdb_cfg | max | 11 | 0 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| rdb_cfg | enum_set | 11 | 10 | 18 | 23 | 168 | title_width=6, p95_width=18, raw_width=168, cap=560, recommended_width=168, max_width=23 |
| rdb_cfg | config_type | 11 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| rdb_cfg | tips | 11 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| sc_cfg | no | 8 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| sc_cfg | page_no | 8 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| sc_cfg | page_name | 8 | 6 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| sc_cfg | option_desc | 8 | 4 | 19 | 20 | 176 | title_width=12, p95_width=19, raw_width=176, cap=420, recommended_width=176, max_width=20 |
| sc_cfg | option_name | 8 | 8 | 19 | 20 | 176 | title_width=12, p95_width=19, raw_width=176, cap=420, recommended_width=176, max_width=20 |
| sc_cfg | val_type | 8 | 5 | 6 | 6 | 104 | title_width=10, p95_width=6, raw_width=104, cap=420, recommended_width=104 |
| sc_cfg | value | 8 | 1 | 10 | 12 | 104 | title_width=2, p95_width=10, raw_width=104, cap=420, recommended_width=104, max_width=12 |
| sc_cfg | min | 8 | 0 | 0 | 0 | 72 | title_width=6, p95_width=0, raw_width=72, cap=420, recommended_width=72 |
| sc_cfg | max | 8 | 0 | 0 | 0 | 72 | title_width=6, p95_width=0, raw_width=72, cap=420, recommended_width=72 |
| sc_cfg | enum_set | 8 | 0 | 51 | 71 | 432 | title_width=6, p95_width=51, raw_width=432, cap=560, recommended_width=432, max_width=71 |
| sc_cfg | config_type | 8 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| sc_cfg | tips | 8 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| scada_cfg | no | 8 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| scada_cfg | page_no | 8 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| scada_cfg | page_name | 8 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| scada_cfg | option_desc | 8 | 14 | 17 | 17 | 160 | title_width=12, p95_width=17, raw_width=160, cap=420, recommended_width=160 |
| scada_cfg | option_name | 8 | 12 | 15 | 15 | 144 | title_width=12, p95_width=15, raw_width=144, cap=420, recommended_width=144 |
| scada_cfg | val_type | 8 | 6 | 9 | 11 | 104 | title_width=10, p95_width=9, raw_width=104, cap=420, recommended_width=104, max_width=11 |
| scada_cfg | value | 8 | 4 | 5 | 5 | 64 | title_width=2, p95_width=5, raw_width=64, cap=420, recommended_width=64 |
| scada_cfg | min | 8 | 0 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| scada_cfg | max | 8 | 0 | 5 | 5 | 72 | title_width=6, p95_width=5, raw_width=72, cap=420, recommended_width=72 |
| scada_cfg | enum_set | 8 | 10 | 10 | 10 | 104 | title_width=6, p95_width=10, raw_width=104, cap=560, recommended_width=104 |
| scada_cfg | config_type | 8 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| scada_cfg | tips | 8 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| sg_manage_cfg | no | 3 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| sg_manage_cfg | page_no | 3 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| sg_manage_cfg | page_name | 3 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| sg_manage_cfg | option_desc | 3 | 14 | 16 | 16 | 152 | title_width=12, p95_width=16, raw_width=152, cap=420, recommended_width=152 |
| sg_manage_cfg | option_name | 3 | 15 | 15 | 15 | 144 | title_width=12, p95_width=15, raw_width=144, cap=420, recommended_width=144 |
| sg_manage_cfg | val_type | 3 | 6 | 6 | 6 | 104 | title_width=10, p95_width=6, raw_width=104, cap=420, recommended_width=104 |
| sg_manage_cfg | value | 3 | 4 | 4 | 4 | 56 | title_width=2, p95_width=4, raw_width=56, cap=420, recommended_width=56 |
| sg_manage_cfg | min | 3 | 0 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| sg_manage_cfg | max | 3 | 0 | 4 | 5 | 72 | title_width=6, p95_width=4, raw_width=72, cap=420, recommended_width=72, max_width=5 |
| sg_manage_cfg | enum_set | 3 | 10 | 10 | 10 | 104 | title_width=6, p95_width=10, raw_width=104, cap=560, recommended_width=104 |
| sg_manage_cfg | config_type | 3 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| sg_manage_cfg | tips | 3 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| vlink_cfg | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| vlink_cfg | page_no | 0 |  |  |  | 96 | no sampled non-null values for page_no; fallback width 96 |
| vlink_cfg | page_name | 0 |  |  |  | 200 | no sampled non-null values for page_name; fallback width 200 |
| vlink_cfg | option_name | 0 |  |  |  | 200 | no sampled non-null values for option_name; fallback width 200 |
| vlink_cfg | option_desc | 0 |  |  |  | 200 | no sampled non-null values for option_desc; fallback width 200 |
| vlink_cfg | val_type | 0 |  |  |  | 132 | no sampled non-null values for val_type; fallback width 132 |
| vlink_cfg | value | 0 |  |  |  | 200 | no sampled non-null values for value; fallback width 200 |
| vlink_cfg | enum_set | 0 |  |  |  | 200 | no sampled non-null values for enum_set; fallback width 200 |
| vlink_cfg | max | 0 |  |  |  | 200 | no sampled non-null values for max; fallback width 200 |
| vlink_cfg | min | 0 |  |  |  | 200 | no sampled non-null values for min; fallback width 200 |
| vqc_cfg | no | 8 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| vqc_cfg | page_no | 8 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| vqc_cfg | page_name | 8 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| vqc_cfg | option_desc | 8 | 17 | 27 | 27 | 240 | title_width=12, p95_width=27, raw_width=240, cap=420, recommended_width=240 |
| vqc_cfg | option_name | 8 | 17 | 27 | 27 | 240 | title_width=12, p95_width=27, raw_width=240, cap=420, recommended_width=240 |
| vqc_cfg | val_type | 8 | 5 | 7 | 8 | 104 | title_width=10, p95_width=7, raw_width=104, cap=420, recommended_width=104, max_width=8 |
| vqc_cfg | value | 8 | 2 | 8 | 10 | 88 | title_width=2, p95_width=8, raw_width=88, cap=420, recommended_width=88, max_width=10 |
| vqc_cfg | min | 8 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| vqc_cfg | max | 8 | 2 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| vqc_cfg | enum_set | 8 | 0 | 22 | 28 | 200 | title_width=6, p95_width=22, raw_width=200, cap=560, recommended_width=200, max_width=28 |
| vqc_cfg | config_type | 8 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| vqc_cfg | tips | 8 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| wave_cfg | no | 3 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| wave_cfg | page_no | 3 | 1 | 1 | 1 | 56 | title_width=4, p95_width=1, raw_width=56, cap=420, recommended_width=56 |
| wave_cfg | page_name | 3 | 8 | 8 | 8 | 88 | title_width=6, p95_width=8, raw_width=88, cap=420, recommended_width=88 |
| wave_cfg | option_desc | 3 | 16 | 16 | 16 | 152 | title_width=12, p95_width=16, raw_width=152, cap=420, recommended_width=152 |
| wave_cfg | option_name | 3 | 10 | 12 | 12 | 120 | title_width=12, p95_width=12, raw_width=120, cap=420, recommended_width=120 |
| wave_cfg | val_type | 3 | 5 | 6 | 6 | 104 | title_width=10, p95_width=6, raw_width=104, cap=420, recommended_width=104 |
| wave_cfg | value | 3 | 2 | 4 | 4 | 56 | title_width=2, p95_width=4, raw_width=56, cap=420, recommended_width=56 |
| wave_cfg | min | 3 | 1 | 1 | 1 | 72 | title_width=6, p95_width=1, raw_width=72, cap=420, recommended_width=72 |
| wave_cfg | max | 3 | 2 | 3 | 3 | 72 | title_width=6, p95_width=3, raw_width=72, cap=420, recommended_width=72 |
| wave_cfg | enum_set | 3 | 0 | 9 | 10 | 96 | title_width=6, p95_width=9, raw_width=96, cap=560, recommended_width=96, max_width=10 |
| wave_cfg | config_type | 3 | 10 | 10 | 10 | 104 | title_width=8, p95_width=10, raw_width=104, cap=420, recommended_width=104 |
| wave_cfg | tips | 3 | 0 | 0 | 0 | 88 | title_width=8, p95_width=0, raw_width=88, cap=420, recommended_width=88 |
| wf_cfg | no | 0 |  |  |  | 96 | no sampled non-null values for no; fallback width 96 |
| wf_cfg | page_no | 0 |  |  |  | 96 | no sampled non-null values for page_no; fallback width 96 |
| wf_cfg | page_name | 0 |  |  |  | 200 | no sampled non-null values for page_name; fallback width 200 |
| wf_cfg | option_desc | 0 |  |  |  | 200 | no sampled non-null values for option_desc; fallback width 200 |
| wf_cfg | option_name | 0 |  |  |  | 200 | no sampled non-null values for option_name; fallback width 200 |
| wf_cfg | val_type | 0 |  |  |  | 132 | no sampled non-null values for val_type; fallback width 132 |
| wf_cfg | value | 0 |  |  |  | 200 | no sampled non-null values for value; fallback width 200 |
| wf_cfg | min | 0 |  |  |  | 200 | no sampled non-null values for min; fallback width 200 |
| wf_cfg | max | 0 |  |  |  | 200 | no sampled non-null values for max; fallback width 200 |
| wf_cfg | enum_set | 0 |  |  |  | 200 | no sampled non-null values for enum_set; fallback width 200 |
| wf_cfg | config_type | 0 |  |  |  | 132 | no sampled non-null values for config_type; fallback width 132 |
| wf_cfg | tips | 0 |  |  |  | 200 | no sampled non-null values for tips; fallback width 200 |

## Groups

### `agc_cfg`

- Table count: `1`
- Members: `agc_cfg`

### `app_cfg`

- Table count: `1`
- Members: `app_cfg`

### `clfile_cfg`

- Table count: `1`
- Members: `clfile_cfg`

### `cnt_manage_cfg`

- Table count: `1`
- Members: `cnt_manage_cfg`

### `^b\d+_n\d+_dev104_cfg$`

- Table count: `1`
- Members: `b1_n10_dev104_cfg`

### `^b\d+_n\d+_dev104_dev_cfg$`

- Table count: `1`
- Members: `b1_n10_dev104_dev_cfg`

### `device`

- Table count: `1`
- Members: `device`

### `device_cfg`

- Table count: `1`
- Members: `device_cfg`

### `device_cnt`

- Table count: `1`
- Members: `device_cnt`

### `device_co`

- Table count: `1`
- Members: `device_co`

### `device_mx`

- Table count: `1`
- Members: `device_mx`

### `device_sg`

- Table count: `1`
- Members: `device_sg`

### `device_sn`

- Table count: `1`
- Members: `device_sn`

### `device_sp`

- Table count: `1`
- Members: `device_sp`

### `device_st`

- Table count: `1`
- Members: `device_st`

### `device_tap`

- Table count: `1`
- Members: `device_tap`

### `fault_msg_cfg`

- Table count: `1`
- Members: `fault_msg_cfg`

### `^b\d+_n\d+_iec104_cfg$`

- Table count: `16`
- Members: `b1_n11_iec104_cfg`, `b1_n12_iec104_cfg`, `b1_n13_iec104_cfg`, `b1_n14_iec104_cfg`, `b1_n15_iec104_cfg`, `b1_n16_iec104_cfg`, `b1_n17_iec104_cfg`, `b1_n18_iec104_cfg`, `b1_n20_iec104_cfg`, `b1_n3_iec104_cfg`, `b1_n4_iec104_cfg`, `b1_n5_iec104_cfg`, `b1_n6_iec104_cfg`, `b1_n7_iec104_cfg`, `b1_n8_iec104_cfg`, `b1_n9_iec104_cfg`

### `^b\d+_n\d+_iec104_dyk_list$`

- Table count: `16`
- Members: `b1_n11_iec104_dyk_list`, `b1_n12_iec104_dyk_list`, `b1_n13_iec104_dyk_list`, `b1_n14_iec104_dyk_list`, `b1_n15_iec104_dyk_list`, `b1_n16_iec104_dyk_list`, `b1_n17_iec104_dyk_list`, `b1_n18_iec104_dyk_list`, `b1_n20_iec104_dyk_list`, `b1_n3_iec104_dyk_list`, `b1_n4_iec104_dyk_list`, `b1_n5_iec104_dyk_list`, `b1_n6_iec104_dyk_list`, `b1_n7_iec104_dyk_list`, `b1_n8_iec104_dyk_list`, `b1_n9_iec104_dyk_list`

### `^b\d+_n\d+_iec104_dyx_list$`

- Table count: `16`
- Members: `b1_n11_iec104_dyx_list`, `b1_n12_iec104_dyx_list`, `b1_n13_iec104_dyx_list`, `b1_n14_iec104_dyx_list`, `b1_n15_iec104_dyx_list`, `b1_n16_iec104_dyx_list`, `b1_n17_iec104_dyx_list`, `b1_n18_iec104_dyx_list`, `b1_n20_iec104_dyx_list`, `b1_n3_iec104_dyx_list`, `b1_n4_iec104_dyx_list`, `b1_n5_iec104_dyx_list`, `b1_n6_iec104_dyx_list`, `b1_n7_iec104_dyx_list`, `b1_n8_iec104_dyx_list`, `b1_n9_iec104_dyx_list`

### `^b\d+_n\d+_iec104_sc_list$`

- Table count: `16`
- Members: `b1_n11_iec104_sc_list`, `b1_n12_iec104_sc_list`, `b1_n13_iec104_sc_list`, `b1_n14_iec104_sc_list`, `b1_n15_iec104_sc_list`, `b1_n16_iec104_sc_list`, `b1_n17_iec104_sc_list`, `b1_n18_iec104_sc_list`, `b1_n20_iec104_sc_list`, `b1_n3_iec104_sc_list`, `b1_n4_iec104_sc_list`, `b1_n5_iec104_sc_list`, `b1_n6_iec104_sc_list`, `b1_n7_iec104_sc_list`, `b1_n8_iec104_sc_list`, `b1_n9_iec104_sc_list`

### `^b\d+_n\d+_iec104_syk_list$`

- Table count: `16`
- Members: `b1_n11_iec104_syk_list`, `b1_n12_iec104_syk_list`, `b1_n13_iec104_syk_list`, `b1_n14_iec104_syk_list`, `b1_n15_iec104_syk_list`, `b1_n16_iec104_syk_list`, `b1_n17_iec104_syk_list`, `b1_n18_iec104_syk_list`, `b1_n20_iec104_syk_list`, `b1_n3_iec104_syk_list`, `b1_n4_iec104_syk_list`, `b1_n5_iec104_syk_list`, `b1_n6_iec104_syk_list`, `b1_n7_iec104_syk_list`, `b1_n8_iec104_syk_list`, `b1_n9_iec104_syk_list`

### `^b\d+_n\d+_iec104_syx_list$`

- Table count: `16`
- Members: `b1_n11_iec104_syx_list`, `b1_n12_iec104_syx_list`, `b1_n13_iec104_syx_list`, `b1_n14_iec104_syx_list`, `b1_n15_iec104_syx_list`, `b1_n16_iec104_syx_list`, `b1_n17_iec104_syx_list`, `b1_n18_iec104_syx_list`, `b1_n20_iec104_syx_list`, `b1_n3_iec104_syx_list`, `b1_n4_iec104_syx_list`, `b1_n5_iec104_syx_list`, `b1_n6_iec104_syx_list`, `b1_n7_iec104_syx_list`, `b1_n8_iec104_syx_list`, `b1_n9_iec104_syx_list`

### `^b\d+_n\d+_iec104_yc_list$`

- Table count: `16`
- Members: `b1_n11_iec104_yc_list`, `b1_n12_iec104_yc_list`, `b1_n13_iec104_yc_list`, `b1_n14_iec104_yc_list`, `b1_n15_iec104_yc_list`, `b1_n16_iec104_yc_list`, `b1_n17_iec104_yc_list`, `b1_n18_iec104_yc_list`, `b1_n20_iec104_yc_list`, `b1_n3_iec104_yc_list`, `b1_n4_iec104_yc_list`, `b1_n5_iec104_yc_list`, `b1_n6_iec104_yc_list`, `b1_n7_iec104_yc_list`, `b1_n8_iec104_yc_list`, `b1_n9_iec104_yc_list`

### `^b\d+_n\d+_iec104_ym_list$`

- Table count: `16`
- Members: `b1_n11_iec104_ym_list`, `b1_n12_iec104_ym_list`, `b1_n13_iec104_ym_list`, `b1_n14_iec104_ym_list`, `b1_n15_iec104_ym_list`, `b1_n16_iec104_ym_list`, `b1_n17_iec104_ym_list`, `b1_n18_iec104_ym_list`, `b1_n20_iec104_ym_list`, `b1_n3_iec104_ym_list`, `b1_n4_iec104_ym_list`, `b1_n5_iec104_ym_list`, `b1_n6_iec104_ym_list`, `b1_n7_iec104_ym_list`, `b1_n8_iec104_ym_list`, `b1_n9_iec104_ym_list`

### `^b\d+_n\d+_iec104_yp_list$`

- Table count: `16`
- Members: `b1_n11_iec104_yp_list`, `b1_n12_iec104_yp_list`, `b1_n13_iec104_yp_list`, `b1_n14_iec104_yp_list`, `b1_n15_iec104_yp_list`, `b1_n16_iec104_yp_list`, `b1_n17_iec104_yp_list`, `b1_n18_iec104_yp_list`, `b1_n20_iec104_yp_list`, `b1_n3_iec104_yp_list`, `b1_n4_iec104_yp_list`, `b1_n5_iec104_yp_list`, `b1_n6_iec104_yp_list`, `b1_n7_iec104_yp_list`, `b1_n8_iec104_yp_list`, `b1_n9_iec104_yp_list`

### `^b\d+_n\d+_iec104_yt_list$`

- Table count: `16`
- Members: `b1_n11_iec104_yt_list`, `b1_n12_iec104_yt_list`, `b1_n13_iec104_yt_list`, `b1_n14_iec104_yt_list`, `b1_n15_iec104_yt_list`, `b1_n16_iec104_yt_list`, `b1_n17_iec104_yt_list`, `b1_n18_iec104_yt_list`, `b1_n20_iec104_yt_list`, `b1_n3_iec104_yt_list`, `b1_n4_iec104_yt_list`, `b1_n5_iec104_yt_list`, `b1_n6_iec104_yt_list`, `b1_n7_iec104_yt_list`, `b1_n8_iec104_yt_list`, `b1_n9_iec104_yt_list`

### `^b\d+_n\d+_iec61850c_cfg$`

- Table count: `1`
- Members: `b1_n1_iec61850c_cfg`

### `^b\d+_n\d+_iec61850c_dev_cfg$`

- Table count: `1`
- Members: `b1_n1_iec61850c_dev_cfg`

### `jdxx_cfg`

- Table count: `1`
- Members: `jdxx_cfg`

### `^b\d+_n\d+_nbridge_cfg$`

- Table count: `4`
- Members: `b1_n21_nbridge_cfg`, `b1_n22_nbridge_cfg`, `b1_n23_nbridge_cfg`, `b1_n24_nbridge_cfg`

### `net_cfg`

- Table count: `1`
- Members: `net_cfg`

### `^b\d+_n\d+_nr103d_cfg$`

- Table count: `1`
- Members: `b1_n2_nr103d_cfg`

### `^b\d+_n\d+_nr103d_dev_cfg$`

- Table count: `1`
- Members: `b1_n2_nr103d_dev_cfg`

### `project`

- Table count: `1`
- Members: `project`

### `prot_list`

- Table count: `1`
- Members: `prot_list`

### `rdb_cfg`

- Table count: `1`
- Members: `rdb_cfg`

### `sc_cfg`

- Table count: `1`
- Members: `sc_cfg`

### `scada_cfg`

- Table count: `1`
- Members: `scada_cfg`

### `sg_manage_cfg`

- Table count: `1`
- Members: `sg_manage_cfg`

### `vlink_cfg`

- Table count: `1`
- Members: `vlink_cfg`

### `vqc_cfg`

- Table count: `1`
- Members: `vqc_cfg`

### `wave_cfg`

- Table count: `1`
- Members: `wave_cfg`

### `wf_cfg`

- Table count: `1`
- Members: `wf_cfg`
