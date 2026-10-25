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

fn parse(sql: &str) -> SqlParseOutput {
    parse_with(sql, 1, DEFAULT_CHUNK_BYTES)
}

fn canonical(output: &SqlParseOutput) -> Vec<u8> {
    encode_parse_canonical(output).unwrap_or_else(|error| error.into_bytes())
}

/// Values of one column as `(mark, payload)` read back from the canonical form.
fn column_values(output: &SqlParseOutput, table: usize, column: usize) -> Vec<(u8, Vec<u8>)> {
    let Some(table) = output.tables.get(table) else {
        return Vec::new();
    };
    let single = SqlParseOutput {
        status: output.status,
        tables: vec![table.clone()],
        diagnostics: Vec::new(),
        timings: ParsePhaseTimings::default(),
    };
    let bytes = canonical(&single);
    let mut pos = 8;
    let read_u32 = |bytes: &[u8], pos: usize| -> usize {
        let mut buf = [0u8; 4];
        buf.copy_from_slice(&bytes[pos..pos + 4]);
        u32::from_be_bytes(buf) as usize
    };
    for _ in 0..2 {
        let length = read_u32(&bytes, pos);
        pos += 4 + length;
    }
    let mut out = Vec::new();
    for current in 0..table.descriptor.columns.len() {
        pos += 5;
        for _ in 0..table.row_count {
            let mark = bytes[pos];
            let length = read_u32(&bytes, pos + 1);
            let payload = bytes[pos + 5..pos + 5 + length].to_vec();
            pos += 5 + length;
            if current == column {
                out.push((mark, payload));
            }
        }
    }
    out
}

fn first_code(output: &SqlParseOutput) -> Option<ParserDiagnosticCode> {
    output.diagnostics.first().map(|d| d.code)
}

const BOILERPLATE: &str = "/*!40101 SET NAMES utf8mb4 */;\n\
SET FOREIGN_KEY_CHECKS=0;\n\
DROP TABLE IF EXISTS `t`;\n\
CREATE TABLE `t` (\n  `id` INT NOT NULL PRIMARY KEY,\n  `name` VARCHAR(16) NULL\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\
LOCK TABLES `t` WRITE;\n\
ALTER TABLE `t` DISABLE KEYS;\n\
INSERT INTO `t` (`id`, `name`) VALUES (1, 'a'), (2, 'b');\n\
ALTER TABLE `t` ENABLE KEYS;\n\
UNLOCK TABLES;\n\
SET FOREIGN_KEY_CHECKS=1;\n";

#[test]
fn golden_boilerplate_dump_parses_two_rows() {
    let output = parse(BOILERPLATE);
    assert_eq!(
        output.status,
        ParseStatus::Complete,
        "{:?}",
        output.diagnostics
    );
    assert_eq!(output.tables.len(), 1);
    let table = &output.tables[0];
    assert_eq!(table.row_count, 2);
    assert_eq!(table.descriptor.primary_key, vec!["id".to_string()]);
    assert_eq!(table.descriptor.columns[0].sql_type, "INT");
    assert!(!table.descriptor.columns[0].nullable);
    assert_eq!(
        column_values(&output, 0, 1),
        vec![(0x20, b"a".to_vec()), (0x20, b"b".to_vec())]
    );
    assert_eq!(
        column_values(&output, 0, 0)[1],
        (0x10, 2i64.to_be_bytes().to_vec())
    );
}

#[test]
fn unsupported_and_incomplete_statements_fail_like_the_reference() {
    let output = parse("REPLACE INTO `t` VALUES (1);");
    assert_eq!(output.status, ParseStatus::Failed);
    assert!(output.tables.is_empty());
    assert_eq!(
        first_code(&output),
        Some(ParserDiagnosticCode::UnsupportedStatement)
    );

    let output = parse(
        "CREATE TABLE `t` (\n  `id` INT NOT NULL PRIMARY KEY,\n  `name` VARCHAR(16) NULL\n);\nINSERT INTO `t` (`id`) VALUES (1);\n",
    );
    assert_eq!(output.status, ParseStatus::Failed);
    assert_eq!(output.tables.len(), 1);
    assert!(!output.tables[0].descriptor.reader_ready);
    assert_eq!(
        output.diagnostics[0].code,
        ParserDiagnosticCode::IncompleteInsert
    );
    assert_eq!(output.diagnostics[0].byte_offset, 97);

    for (sql, code) in [
        (
            "INSERT IGNORE INTO `t` VALUES (1);",
            ParserDiagnosticCode::UnsupportedStatement,
        ),
        ("USE db;", ParserDiagnosticCode::UnsupportedStatement),
        (
            "CREATE DATABASE d;",
            ParserDiagnosticCode::UnsupportedStatement,
        ),
        (
            "UPDATE `t` SET `id`=1;",
            ParserDiagnosticCode::UnsupportedStatement,
        ),
        (
            "CREATE TABLE \"t\" (id INT);",
            ParserDiagnosticCode::UnsupportedStatement,
        ),
        (
            "SET @@saved_cs_client = 1;",
            ParserDiagnosticCode::UnsupportedStatement,
        ),
        (
            "SET @other_client = 1;",
            ParserDiagnosticCode::UnsupportedStatement,
        ),
        (
            "CREATE TABLE t (id INT NULL); INSERT INTO t VALUES (1) ON DUPLICATE KEY UPDATE id=1;",
            ParserDiagnosticCode::UnsupportedStatement,
        ),
        (
            "CREATE TABLE t (id INT NULL); INSERT INTO t VALUES (_binary 'a');",
            ParserDiagnosticCode::MalformedSql,
        ),
        (
            "CREATE TABLE t (id INT NULL); INSERT INTO t VALUES ('a;",
            ParserDiagnosticCode::MalformedSql,
        ),
    ] {
        let output = parse(sql);
        assert_eq!(output.status, ParseStatus::Failed, "{sql}");
        assert!(output.tables.is_empty(), "{sql}");
        assert_eq!(
            output.document_failure().map(|d| d.code),
            Some(code),
            "{sql}"
        );
    }
}

#[test]
fn mysqldump_session_statements_are_accepted() {
    for sql in [
        "/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;",
        "/*!50503 SET NAMES utf8mb4 */;",
        "/*!40103 SET TIME_ZONE='+00:00' */;",
        "/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;",
        "/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;",
        "SET TIME_ZONE=@OLD_TIME_ZONE;",
        "/*!40101 SET @saved_cs_client = @@character_set_client */;",
        "/*!50503 SET character_set_client = utf8mb4 */;",
        "SET @SAVED_CS_CLIENT = 1;",
        "-- comment\r\n# other\r\n/* block */;;",
    ] {
        let output = parse(sql);
        assert_eq!(
            output.status,
            ParseStatus::Complete,
            "{sql}: {:?}",
            output.diagnostics
        );
        assert!(output.diagnostics.is_empty(), "{sql}");
    }
}

#[test]
fn literal_classes_convert_to_canonical_payloads() {
    let sql = "CREATE TABLE t (\
        i INT NULL, u BIGINT UNSIGNED NULL, f FLOAT NULL, d DOUBLE NULL, m DECIMAL(65,30) NULL,\
        s VARCHAR(10) NULL, b BLOB NULL, bt BIT(10) NULL, dt DATETIME(6) NULL, ts TIMESTAMP NULL,\
        tm TIME NULL, e ENUM('x','y') NULL, st SET('a','b','c') NULL, j JSON NULL, bo BOOLEAN NULL, dd DATE NULL);\r\n\
        INSERT INTO t VALUES (-0, 18446744073709551615, -0.0, 1.5e-3, -000123.4500, 'a\\nb''c\u{4e2d}', x'00ff', b'1000000001',\
        '2024-01-02 03:04:05.120000', '2024-01-02 03:04:05', '-838:59:59', 'y', 'c,a', '{\"k\": [1, NaN]}', 1, '2024-02-29'),\
        (NULL, NULL, NULL, NULL, NULL, 'line1\r\nline2', 0x1, 1, NULL, NULL, NULL, NULL, '', NULL, FALSE, NULL);";
    let output = parse(sql);
    assert_eq!(
        output.status,
        ParseStatus::Complete,
        "{:?}",
        output.diagnostics
    );
    let row0: Vec<(u8, Vec<u8>)> = (0..16)
        .map(|c| column_values(&output, 0, c)[0].clone())
        .collect();
    assert_eq!(row0[0], (0x10, 0i64.to_be_bytes().to_vec()));
    assert_eq!(row0[1], (0x11, u64::MAX.to_be_bytes().to_vec()));
    assert_eq!(row0[2], (0x13, 0u32.to_be_bytes().to_vec()));
    assert_eq!(row0[3], (0x14, 1.5e-3f64.to_bits().to_be_bytes().to_vec()));
    assert_eq!(row0[4], (0x12, b"-123.45".to_vec()));
    assert_eq!(row0[5], (0x20, "a\nb'c\u{4e2d}".as_bytes().to_vec()));
    assert_eq!(row0[6], (0x21, vec![0x00, 0xff]));
    assert_eq!(row0[7], (0x22, vec![0x02, 0x01]));
    assert_eq!(row0[8], (0x31, b"2024-01-02T03:04:05.12".to_vec()));
    assert_eq!(row0[9], (0x32, b"2024-01-02T03:04:05Z".to_vec()));
    assert_eq!(row0[10], (0x33, b"-838:59:59".to_vec()));
    assert_eq!(row0[11], (0x20, b"y".to_vec()));
    assert_eq!(row0[12], (0x40, b"a,c".to_vec()));
    assert_eq!(row0[13], (0x20, b"{\"k\": [1, NaN]}".to_vec()));
    assert_eq!(row0[14], (0x01, vec![1]));
    assert_eq!(row0[15], (0x30, b"2024-02-29".to_vec()));
    let row1: Vec<(u8, Vec<u8>)> = (0..16)
        .map(|c| column_values(&output, 0, c)[1].clone())
        .collect();
    assert_eq!(row1[0], (0x00, Vec::new()));
    assert_eq!(row1[5], (0x20, b"line1\r\nline2".to_vec()));
    assert_eq!(row1[6], (0x21, vec![0x01]));
    // A decimal-looking BIT value made of 0/1 digits is read as binary.
    assert_eq!(row1[7], (0x22, vec![0x00, 0x01]));
    assert_eq!(row1[12], (0x40, Vec::new()));
    assert_eq!(row1[14], (0x01, vec![0]));
}

#[test]
fn illegal_values_invalidate_only_their_table() {
    for (column, value) in [
        ("e ENUM('a','b') NOT NULL", "'c'"),
        ("s SET('a','b') NOT NULL", "'c'"),
        ("i INT NOT NULL", "NULL"),
        ("i TINYINT NOT NULL", "9999"),
        ("d DATE NULL", "'0000-00-00'"),
        ("dt DATETIME NULL", "'0000-00-00 00:00:00'"),
        ("j JSON NULL", "'{bad'"),
        ("i INT NULL", "DEFAULT"),
        ("f FLOAT NULL", "1e39"),
        ("s VARCHAR(5) NULL", "'\u{fffe}'"),
    ] {
        let sql = format!(
            "CREATE TABLE ok (id INT NOT NULL PRIMARY KEY); INSERT INTO ok VALUES (1);\
             CREATE TABLE bad ({column}); INSERT INTO bad VALUES ({value});"
        );
        let output = parse(&sql);
        assert_eq!(
            output.status,
            ParseStatus::Partial,
            "{column} {value}: {:?}",
            output.diagnostics
        );
        assert!(output.tables[0].descriptor.reader_ready);
        assert!(!output.tables[1].descriptor.reader_ready);
    }
}

#[test]
fn type_errors_keep_descriptor_without_reader() {
    let output = parse("CREATE TABLE t (`y` YEAR NULL);");
    assert_eq!(output.status, ParseStatus::Failed);
    assert_eq!(
        output.tables[0].descriptor.columns[0].logical_type,
        SqlLogicalType::Unknown
    );
    assert_eq!(
        first_code(&output),
        Some(ParserDiagnosticCode::UnknownSqlType)
    );
    let output = parse("CREATE TABLE t (id INT NOT NULL PRIMARY KEY, PRIMARY KEY (id));");
    assert_eq!(
        first_code(&output),
        Some(ParserDiagnosticCode::DuplicatePrimaryKey)
    );
    let output = parse("CREATE TABLE t (`Id` INT NOT NULL, `id` INT NULL);");
    assert_eq!(
        first_code(&output),
        Some(ParserDiagnosticCode::CanonicalIdentifierCollision)
    );
    let output =
        parse("CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1, 2);");
    assert_eq!(
        first_code(&output),
        Some(ParserDiagnosticCode::RowShapeMismatch)
    );
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
