use std::sync::atomic::AtomicBool;

use proptest::prelude::*;

use super::*;

fn pool(threads: usize) -> rayon::ThreadPool {
    match build_parser_pool(threads) {
        Ok(pool) => pool,
        Err(error) => unreachable!("pool: {error}"),
    }
}

fn parse_with(sql: &str, threads: usize, chunk_bytes: usize) -> SqlParseOutput {
    let options = SqlParseOptions {
        chunk_bytes,
        ..SqlParseOptions::default()
    };
    parse_sql_dump(sql.as_bytes(), &options, &pool(threads))
}

fn canonical(output: &SqlParseOutput) -> Vec<u8> {
    encode_parse_canonical(output).unwrap_or_else(|error| error.into_bytes())
}

#[test]
#[allow(clippy::panic)]
fn parser_panic_boundary_returns_a_stable_internal_fault() -> Result<(), String> {
    let Err(fault) = super::catch_parser_panic::<()>(|| panic!("injected parser panic")) else {
        return Err("panic should be caught at the core boundary".to_string());
    };
    assert_eq!(fault.code, ParserDiagnosticCode::ParserInternalError);
    assert_eq!(fault.offset, 0);
    assert_eq!(fault.message.as_ref(), "parser panicked");
    Ok(())
}

#[test]
fn field_budget_counts_only_while_the_table_is_still_valid() {
    let options = SqlParseOptions {
        budgets: ParserBudgets {
            max_field_bytes: 2,
            ..ParserBudgets::default()
        },
        ..SqlParseOptions::default()
    };
    let pool = pool(2);
    let failing = "CREATE TABLE t (s VARCHAR(9) NULL); INSERT INTO t VALUES ('abc');";
    let output = parse_sql_dump(failing.as_bytes(), &options, &pool);
    assert_eq!(
        output.document_failure().map(|d| d.code),
        Some(ParserDiagnosticCode::ResourceLimitExceeded)
    );
    // After a table error the reference no longer converts values, so the
    // oversized field later in the same table is not a document failure.
    let gated = "CREATE TABLE t (s VARCHAR(9) NOT NULL); INSERT INTO t VALUES (NULL), ('abc');";
    let output = parse_sql_dump(gated.as_bytes(), &options, &pool);
    assert_eq!(output.status, ParseStatus::Failed);
    assert_eq!(output.tables.len(), 1);
}

#[test]
fn row_budget_fault_uses_the_exact_over_limit_tuple_across_chunks() {
    let sql = "CREATE TABLE t (id INT NOT NULL); INSERT INTO t VALUES (1), (2), (3);";
    let expected_offset = sql.find("(2)").unwrap_or(0);
    let options = SqlParseOptions {
        budgets: ParserBudgets {
            max_rows_per_table: 1,
            ..ParserBudgets::default()
        },
        ..SqlParseOptions::default()
    };
    for threads in [1, 4] {
        for chunk_bytes in [1, 8, 1024, usize::MAX] {
            let output = parse_sql_dump(
                sql.as_bytes(),
                &SqlParseOptions {
                    chunk_bytes,
                    ..options.clone()
                },
                &pool(threads),
            );
            let fault = output.document_failure();
            assert_eq!(
                fault.map(|item| item.code),
                Some(ParserDiagnosticCode::ResourceLimitExceeded)
            );
            assert_eq!(fault.map(|item| item.byte_offset), Some(expected_offset));
        }
    }
}

#[test]
fn structural_diagnostics_continue_after_a_table_conversion_failure() {
    let sql =
        "CREATE TABLE t (id INT NOT NULL); INSERT INTO t VALUES ('bad'), (1, 2), (3), (4, 5);";
    let expected = [
        (
            ParserDiagnosticCode::SqlValueIllegal,
            sql.find("('bad')").unwrap_or(0),
        ),
        (
            ParserDiagnosticCode::RowShapeMismatch,
            sql.find("(1, 2)").unwrap_or(0),
        ),
        (
            ParserDiagnosticCode::RowShapeMismatch,
            sql.find("(4, 5)").unwrap_or(0),
        ),
    ];
    for chunk_bytes in [1, 16, usize::MAX] {
        let output = parse_with(sql, 3, chunk_bytes);
        let actual: Vec<_> = output
            .diagnostics
            .iter()
            .map(|diagnostic| (diagnostic.code, diagnostic.byte_offset))
            .collect();
        assert_eq!(actual, expected);
    }
}

#[test]
fn diagnostic_budget_keeps_a_truncation_marker() {
    let sql = "CREATE TABLE t (id INT NOT NULL); INSERT INTO t VALUES (1,2),(3,4),(5,6),(7,8);";
    let output = parse_sql_dump(
        sql.as_bytes(),
        &SqlParseOptions {
            budgets: ParserBudgets {
                max_diagnostics: 2,
                ..ParserBudgets::default()
            },
            chunk_bytes: 1,
            ..SqlParseOptions::default()
        },
        &pool(2),
    );
    assert_eq!(output.diagnostics.len(), 2);
    assert_eq!(
        output.diagnostics[0].code,
        ParserDiagnosticCode::RowShapeMismatch
    );
    assert_eq!(
        output.diagnostics[1].code,
        ParserDiagnosticCode::ParserDiagnosticsTruncated
    );
    assert!(output.diagnostics[1].message.len() <= 4 * 1024);
}

fn big_dump(rows: usize) -> String {
    let mut sql = String::from(
        "CREATE TABLE a (id INT NOT NULL PRIMARY KEY, s VARCHAR(64) NULL, f DOUBLE NULL);\n\
         CREATE TABLE b (k VARCHAR(8) NOT NULL, v BLOB NULL, PRIMARY KEY (k));\n",
    );
    for statement in 0..4 {
        sql.push_str("INSERT INTO a VALUES ");
        for row in 0..rows {
            if row > 0 {
                sql.push(',');
            }
            let id = statement * rows + row;
            sql.push_str(&format!("({id},'r{id}\\'s, (x)\n',{id}.25e-1)"));
        }
        sql.push_str(";\nINSERT INTO b (v, k) VALUES ");
        for row in 0..rows / 3 {
            if row > 0 {
                sql.push_str(", ");
            }
            sql.push_str(&format!("(x'{row:04x}','k{statement}_{row}')"));
        }
        sql.push_str(";\n");
    }
    sql
}

#[test]
fn output_is_identical_across_threads_and_chunk_sizes() {
    let sql = big_dump(500);
    let reference = canonical(&parse_with(&sql, 1, usize::MAX));
    let parsed = parse_with(&sql, 1, usize::MAX);
    assert_eq!(parsed.status, ParseStatus::Complete);
    assert_eq!(parsed.tables[0].row_count, 2000);
    for threads in [1, 2, 4, 8] {
        for chunk_bytes in [1, 7, 64, 4096, DEFAULT_CHUNK_BYTES] {
            let got = canonical(&parse_with(&sql, threads, chunk_bytes));
            assert!(
                got == reference,
                "threads={threads} chunk_bytes={chunk_bytes}"
            );
        }
    }
}

#[test]
fn cancellation_is_a_document_failure() {
    let flag = AtomicBool::new(true);
    let options = SqlParseOptions {
        cancel: Some(&flag),
        ..SqlParseOptions::default()
    };
    let output = parse_sql_dump(big_dump(10).as_bytes(), &options, &pool(2));
    assert_eq!(
        output.document_failure().map(|d| d.code),
        Some(ParserDiagnosticCode::ParserCancelled)
    );
}

#[test]
fn pool_size_is_bounded() {
    assert!(build_parser_pool(0).is_err());
    assert!(build_parser_pool(MAX_PARSER_THREADS + 1).is_err());
}

#[test]
fn invalid_utf8_is_rejected() {
    let output = parse_sql_dump(
        b"CREATE TABLE t (s TEXT); INSERT INTO t VALUES ('\xff');",
        &SqlParseOptions::default(),
        &pool(1),
    );
    assert_eq!(
        output.document_failure().map(|d| d.code),
        Some(ParserDiagnosticCode::InvalidSourceEncoding)
    );
}

const FRAGMENTS: &[&str] = &[
    "CREATE TABLE t (a INT NULL, b VARCHAR(4) NULL, c BIT(3) NULL);",
    "INSERT INTO t VALUES ",
    "(1,'x',b'1')",
    "(NULL,NULL,0)",
    ",",
    ";",
    "'",
    "\\",
    "`",
    "\"",
    "(",
    ")",
    "/*",
    "*/",
    "/*!40000 ",
    "-- ",
    "#",
    "\n",
    "\r\n",
    "x'4",
    "0x",
    "1e",
    "-",
    ".",
    "NULL",
    "DEFAULT",
    "SET NAMES utf8;",
    "LOCK TABLES t WRITE;",
    "\u{e9}",
    "''",
    " ",
];

proptest! {
    #![proptest_config(ProptestConfig { cases: 512, failure_persistence: None, rng_seed: proptest::test_runner::RngSeed::Fixed(0x5636), ..ProptestConfig::default() })]

    /// Arbitrary bytes never panic, and output stays bounded by the input.
    #[test]
    fn arbitrary_bytes_do_not_panic(bytes in proptest::collection::vec(any::<u8>(), 0..512)) {
        let output = parse_sql_dump(&bytes, &SqlParseOptions { chunk_bytes: 3, ..SqlParseOptions::default() }, &pool(2));
        let rows: usize = output.tables.iter().map(|t| t.row_count).sum();
        prop_assert!(rows <= bytes.len());
        prop_assert!(output.diagnostics.len() <= bytes.len() + 2);
        prop_assert!(output.diagnostics.iter().all(|d| d.code != ParserDiagnosticCode::ParserInternalError));
    }

    /// Dump-shaped fragment soup: no panic, and chunking/threads never change the output.
    #[test]
    fn dump_shaped_input_is_deterministic(parts in proptest::collection::vec(0..FRAGMENTS.len(), 0..48)) {
        let sql: String = parts.iter().map(|index| FRAGMENTS[*index]).collect();
        let reference = canonical(&parse_with(&sql, 1, usize::MAX));
        let chunked = parse_with(&sql, 3, 2);
        prop_assert!(chunked.diagnostics.iter().all(|d| d.code != ParserDiagnosticCode::ParserInternalError));
        prop_assert!(canonical(&chunked) == reference);
    }
}

#[test]
fn operation_memory_limit_rejects_before_value_growth_with_a_stable_location() {
    let cases = [
        "CREATE TABLE t (id INT); INSERT INTO t VALUES (1),(2);".to_owned(),
        format!(
            "CREATE TABLE t ({}); INSERT INTO t VALUES ();",
            (0..128)
                .map(|i| format!("c{i} INT"))
                .collect::<Vec<_>>()
                .join(",")
        ),
        format!(
            "CREATE TABLE t (id INT); INSERT INTO t VALUES ({});",
            vec!["0"; 4096].join(",")
        ),
        format!(
            "CREATE TABLE t (id INT); /*!50000 INSERT INTO t VALUES ({}),(1) */;",
            vec!["0"; 4096].join(",")
        ),
    ];
    for threads in [1, 2] {
        let pool = pool(threads);
        for sql in &cases {
            let mut options = SqlParseOptions::default();
            options.budgets.max_live_bytes = 4096;
            let output = parse_sql_dump(sql.as_bytes(), &options, &pool);
            assert_eq!(output.status, ParseStatus::Failed);
            assert!(output.tables.is_empty());
            assert_eq!(output.diagnostics.len(), 1);
            assert_eq!(
                output.diagnostics[0].code,
                ParserDiagnosticCode::ResourceLimitExceeded
            );
            assert_eq!(output.diagnostics[0].byte_offset, 0);
            assert_eq!(output.diagnostics[0].message, "max_live_bytes exceeded");
        }
        let mut options = SqlParseOptions::default();
        options.budgets.max_live_bytes = 1 << 20;
        let output = parse_sql_dump(cases[0].as_bytes(), &options, &pool);
        assert_eq!(output.status, ParseStatus::Complete);
        // Metadata fits; the malformed literal Vec is much wider than the
        // schema and must be refused before its value allocation grows.
        options.budgets.max_live_bytes = 128 << 10;
        let output = parse_sql_dump(cases[2].as_bytes(), &options, &pool);
        assert_eq!(output.status, ParseStatus::Failed);
        assert!(output.tables.is_empty());
        assert_eq!(output.diagnostics[0].message, "max_live_bytes exceeded");
        assert_eq!(output.diagnostics[0].byte_offset, 0);
        let output = parse_sql_dump(cases[2].as_bytes(), &SqlParseOptions::default(), &pool);
        assert!(
            output
                .diagnostics
                .iter()
                .any(|d| d.code == ParserDiagnosticCode::RowShapeMismatch)
        );
    }
}
