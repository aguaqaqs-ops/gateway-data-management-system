use gateway_compute_core::table_access::{
    ParseStatus, SqlParseOptions, build_parser_pool, parse_sql_dump,
};

#[test]
fn configuration_time_uses_closed_utc_grammar() {
    let cases = [
        ("2026-11-07 12:00:00", Some("2026-11-07T12:00:00Z")),
        ("2026-11-07T12:00:00Z", Some("2026-11-07T12:00:00Z")),
        (
            " \\t2026-11-07T12:00:00Z\\r\\n",
            Some("2026-11-07T12:00:00Z"),
        ),
        ("2026-11-07T00:30:00+01:00", Some("2026-11-06T23:30:00Z")),
        (
            "2026-11-07T12:00:00.120000-00:00",
            Some("2026-11-07T12:00:00.12Z"),
        ),
        ("2026-11-07T00:00:00+14:00", Some("2026-11-06T10:00:00Z")),
        ("2024-02-29T00:00:00", Some("2024-02-29T00:00:00Z")),
        ("0001-01-01T00:00:00Z", Some("0001-01-01T00:00:00Z")),
        (
            "9999-12-31T23:59:59.999999Z",
            Some("9999-12-31T23:59:59.999999Z"),
        ),
        (
            "2026-11-07T00:00:00.000000+00:00",
            Some("2026-11-07T00:00:00Z"),
        ),
        (
            "2026-11-07T00:00:00.000001-14:00",
            Some("2026-11-07T14:00:00.000001Z"),
        ),
        ("2026-11-07T00:00:00+14:01", None),
        ("2026-11-07T00:00:00+15:00", None),
        ("2026-02-29T00:00:00", None),
        ("2026-11-07", None),
        ("2026-11-07t12:00:00z", None),
        ("2026-11-07T12:00:00.1234567", None),
        ("2026-11-07T12:00:00.0000000", None),
        ("2026-11-07T12:00:60Z", None),
        ("2026-11-07T24:00:00Z", None),
        ("0001-01-01T00:00:00+00:01", None),
        ("9999-12-31T23:59:59-00:01", None),
        ("2026-11-07\\t12:00:00Z", None),
        ("2026-11-07  12:00:00Z", None),
        ("\u{00a0}2026-11-07T12:00:00Z", None),
        ("2026-11-07T12:00:00Z\u{000b}", None),
        ("２０２６-11-07T12:00:00Z", None),
        ("2026-11-07T12:00:00+0000", None),
        ("2026-11-07T12:00:00+00:00:00", None),
        ("2026-11-07T12:00:00Europe/London", None),
        ("0000-01-01T00:00:00Z", None),
        ("2026-00-01T00:00:00Z", None),
        ("2026-04-31T00:00:00Z", None),
        ("2026-11-07T12:00:00.", None),
        ("1794052800", None),
    ];
    let pool = build_parser_pool(1).unwrap();
    for (value, expected) in cases {
        let sql = format!(
            "CREATE TABLE version_manager(saved_time TEXT); INSERT INTO version_manager VALUES ('{value}');"
        );
        let parsed = parse_sql_dump(sql.as_bytes(), &SqlParseOptions::default(), &pool);
        assert_eq!(parsed.status, ParseStatus::Complete, "{value}");
        let facts = parsed.configuration_generated_time.unwrap();
        assert_eq!(facts.selected_time_utc().as_deref(), expected, "{value}");
        assert_eq!(facts.max_valid_time_utc().as_deref(), expected, "{value}");
        assert_eq!(
            facts.invalid_count,
            usize::from(expected.is_none()),
            "{value}"
        );
    }
}

#[test]
fn configuration_time_preserves_source_order_across_inserts_and_chunks() {
    let sql = b"CREATE TABLE version_manager(id INT PRIMARY KEY, saved_time TEXT);\
        INSERT INTO version_manager VALUES (90,'2026-11-07T12:00:00Z'),(80,NULL),(70,'2026-11-07');\
        INSERT INTO version_manager(saved_time,id) VALUES ('2026-11-07T11:00:00Z',1),('2026-11-07T11:00:00.0000000Z',0);";
    let mut previous = None;
    for threads in [1, 4] {
        let pool = build_parser_pool(threads).unwrap();
        for chunk_bytes in [1, 64, 1024] {
            let options = SqlParseOptions {
                chunk_bytes,
                ..SqlParseOptions::default()
            };
            let parsed = parse_sql_dump(sql, &options, &pool);
            assert_eq!(parsed.status, ParseStatus::Complete);
            let facts = parsed.configuration_generated_time.unwrap();
            assert_eq!(
                facts.selected_time_utc().as_deref(),
                Some("2026-11-07T11:00:00Z")
            );
            assert_eq!(
                facts.max_valid_time_utc().as_deref(),
                Some("2026-11-07T12:00:00Z")
            );
            assert_eq!(
                (facts.valid_count, facts.empty_count, facts.invalid_count),
                (2, 1, 2)
            );
            assert_eq!(
                (facts.last_valid_source_row, facts.max_valid_source_row),
                (Some(4), Some(1))
            );
            assert!(facts.last_not_max());
            if let Some(previous) = &previous {
                assert_eq!(previous, &facts);
            }
            previous = Some(facts);
        }
    }
    let equal = b"CREATE TABLE version_manager(saved_time TEXT); INSERT INTO version_manager VALUES ('2026-11-07T12:00:00Z'),('2026-11-07T13:00:00+01:00');";
    let facts = parse_sql_dump(
        equal,
        &SqlParseOptions::default(),
        &build_parser_pool(2).unwrap(),
    )
    .configuration_generated_time
    .unwrap();
    assert_eq!(
        (facts.last_valid_source_row, facts.max_valid_source_row),
        (Some(2), Some(1))
    );
    assert!(!facts.last_not_max());
}

#[test]
fn configuration_time_distinguishes_missing_business_values_and_typed_failures() {
    let pool = build_parser_pool(1).unwrap();
    for (sql, status, counts) in [
        ("CREATE TABLE other(v TEXT);", "TABLE_ABSENT", (0, 0, 0)),
        (
            "CREATE TABLE version_manager(other TEXT); INSERT INTO version_manager VALUES ('x');",
            "COLUMN_ABSENT",
            (0, 0, 0),
        ),
        (
            "CREATE TABLE version_manager(saved_time TEXT);",
            "NO_ROWS",
            (0, 0, 0),
        ),
        (
            "CREATE TABLE version_manager(saved_time TEXT); INSERT INTO version_manager VALUES (NULL),(''),(' \\t\\r\\n');",
            "NO_VALUE",
            (0, 3, 0),
        ),
        (
            "CREATE TABLE version_manager(saved_time TEXT); INSERT INTO version_manager VALUES (NULL),('bad');",
            "NO_VALID_VALUE",
            (0, 1, 1),
        ),
        (
            "CREATE TABLE version_manager(saved_time BIGINT); INSERT INTO version_manager VALUES (1794052800);",
            "NO_VALID_VALUE",
            (0, 0, 1),
        ),
    ] {
        let parsed = parse_sql_dump(sql.as_bytes(), &SqlParseOptions::default(), &pool);
        assert_eq!(parsed.status, ParseStatus::Complete);
        let facts = parsed.configuration_generated_time.unwrap();
        assert_eq!(facts.status, status);
        assert_eq!(
            (facts.valid_count, facts.empty_count, facts.invalid_count),
            counts
        );
        assert_eq!(facts.last_valid_source_row, None);
        assert_eq!(facts.max_valid_source_row, None);
    }
    for sql in [
        "CREATE TABLE version_manager(saved_time TIMESTAMP); INSERT INTO version_manager VALUES ('2026-11-07T12:00:00+01:00');",
        "CREATE TABLE version_manager(saved_time DATETIME); INSERT INTO version_manager VALUES ('2026-11-07T12:00:00+01:00');",
    ] {
        let parsed = parse_sql_dump(sql.as_bytes(), &SqlParseOptions::default(), &pool);
        assert_eq!(parsed.status, ParseStatus::Failed);
        assert!(parsed.configuration_generated_time.is_none());
    }
}
