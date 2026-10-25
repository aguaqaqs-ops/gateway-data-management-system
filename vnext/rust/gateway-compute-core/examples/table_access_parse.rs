#![forbid(unsafe_code)]
//! Test and measurement entry for the Table Access SQL parser (Phase 6 V6).
//! Not a production entry point: it reads one SQL file, parses it with each
//! requested `(threads, chunk_bytes)` configuration, and prints a JSON summary
//! (timings, table names and row counts, digests). It never prints values.
//!
//! ```text
//! table_access_parse --input dump.sql [--threads 1,8] [--chunk-bytes 1048576,4096]
//!     [--repeat 3] [--canonical sha|none|write] [--canonical-out out.pcf]
//!     [--summary-out summary.json]
//! ```
//!
//! With `--canonical write`, the canonical form of the first configuration is
//! written to `--canonical-out`. Every configuration's canonical digest is
//! reported; `deterministic` is true when they are all equal.

use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

use gateway_compute_core::table_access::{
    SqlParseOptions, SqlParseOutput, build_parser_pool, encode_parse_canonical, parse_sql_dump,
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

#[derive(Clone, Copy, PartialEq, Eq)]
enum CanonicalMode {
    None,
    Sha,
    Write,
}

struct Args {
    input: PathBuf,
    threads: Vec<usize>,
    chunk_bytes: Vec<usize>,
    repeat: usize,
    canonical: CanonicalMode,
    canonical_out: Option<PathBuf>,
    summary_out: Option<PathBuf>,
}

fn parse_list(text: &str) -> Result<Vec<usize>, String> {
    text.split(',')
        .map(|item| {
            item.trim()
                .parse::<usize>()
                .map_err(|e| format!("bad number {item:?}: {e}"))
        })
        .collect()
}

fn parse_args() -> Result<Args, String> {
    let mut input = None;
    let mut threads = vec![1];
    let mut chunk_bytes = vec![gateway_compute_core::table_access::DEFAULT_CHUNK_BYTES];
    let mut repeat = 1;
    let mut canonical = CanonicalMode::Sha;
    let mut canonical_out = None;
    let mut summary_out = None;
    let mut args = std::env::args().skip(1);
    while let Some(flag) = args.next() {
        let mut value = || args.next().ok_or_else(|| format!("{flag} needs a value"));
        match flag.as_str() {
            "--input" => input = Some(PathBuf::from(value()?)),
            "--threads" => threads = parse_list(&value()?)?,
            "--chunk-bytes" => chunk_bytes = parse_list(&value()?)?,
            "--repeat" => repeat = value()?.parse().map_err(|e| format!("bad --repeat: {e}"))?,
            "--canonical" => {
                canonical = match value()?.as_str() {
                    "none" => CanonicalMode::None,
                    "sha" => CanonicalMode::Sha,
                    "write" => CanonicalMode::Write,
                    other => return Err(format!("bad --canonical {other:?}")),
                }
            }
            "--canonical-out" => canonical_out = Some(PathBuf::from(value()?)),
            "--summary-out" => summary_out = Some(PathBuf::from(value()?)),
            other => return Err(format!("unknown argument {other:?}")),
        }
    }
    let input = input.ok_or("--input is required")?;
    if canonical == CanonicalMode::Write && canonical_out.is_none() {
        return Err("--canonical write needs --canonical-out".to_string());
    }
    if repeat == 0 || threads.is_empty() || chunk_bytes.is_empty() {
        return Err("--repeat, --threads and --chunk-bytes must be non-empty".to_string());
    }
    Ok(Args {
        input,
        threads,
        chunk_bytes,
        repeat,
        canonical,
        canonical_out,
        summary_out,
    })
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Peak resident set size of this process (VmHWM), in KiB.
fn peak_rss_kib() -> Option<u64> {
    let status = fs::read_to_string("/proc/self/status").ok()?;
    status
        .lines()
        .find(|line| line.starts_with("VmHWM:"))
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|value| value.parse().ok())
}

fn describe(output: &SqlParseOutput) -> Value {
    let tables: Vec<Value> = output
        .tables
        .iter()
        .map(|table| {
            json!({
                "name": table.descriptor.canonical_name,
                "ready": table.descriptor.reader_ready,
                "rows": table.row_count,
                "columns": table.descriptor.columns.len(),
            })
        })
        .collect();
    let diagnostics: Vec<Value> = output
        .diagnostics
        .iter()
        .map(|d| json!({"code": d.code.as_str(), "byte_offset": d.byte_offset, "table": d.table}))
        .collect();
    json!({
        "status": output.status.as_str(),
        "table_count": output.tables.len(),
        "ready_tables": output.tables.iter().filter(|t| t.descriptor.reader_ready).count(),
        "total_rows": output.tables.iter().map(|t| t.row_count).sum::<usize>(),
        "document_failure": output.document_failure().map(|d| json!({"code": d.code.as_str(), "byte_offset": d.byte_offset})),
        "tables": tables,
        "diagnostics": diagnostics,
    })
}

fn run() -> Result<(Value, Option<PathBuf>), String> {
    let args = parse_args()?;
    let sql = fs::read(&args.input).map_err(|e| format!("cannot read input: {e}"))?;
    let input_sha = hex(&Sha256::digest(&sql));
    let mut configs = Vec::new();
    let mut digests = Vec::new();
    let mut first_description = None;
    let mut wrote_canonical = false;
    for &threads in &args.threads {
        let pool = build_parser_pool(threads).map_err(|e| e.to_string())?;
        for &chunk_bytes in &args.chunk_bytes {
            let options = SqlParseOptions {
                chunk_bytes,
                ..SqlParseOptions::default()
            };
            let mut seconds = Vec::new();
            let mut phases = Vec::new();
            let mut last = None;
            for _ in 0..args.repeat {
                // Drop the previous result first so peak memory reflects one parse.
                drop(last.take());
                let started = Instant::now();
                let output = parse_sql_dump(&sql, &options, &pool);
                seconds.push(started.elapsed().as_secs_f64());
                let timings = output.timings;
                phases.push(json!({
                    "validate": timings.validate.as_secs_f64(),
                    "scan": timings.scan.as_secs_f64(),
                    "values": timings.values.as_secs_f64(),
                    "merge": timings.merge.as_secs_f64(),
                }));
                last = Some(output);
            }
            let output = last.ok_or("no parse result")?;
            let mut config = json!({
                "threads": threads,
                "chunk_bytes": chunk_bytes,
                "parse_seconds": seconds,
                "phase_seconds": phases,
            });
            if args.canonical != CanonicalMode::None {
                let started = Instant::now();
                let bytes = encode_parse_canonical(&output)?;
                let digest = hex(&Sha256::digest(&bytes));
                config["canonical_seconds"] = json!(started.elapsed().as_secs_f64());
                config["canonical_bytes"] = json!(bytes.len());
                config["canonical_sha256"] = json!(digest.clone());
                digests.push(digest);
                if args.canonical == CanonicalMode::Write
                    && !wrote_canonical
                    && let Some(path) = &args.canonical_out
                {
                    fs::write(path, &bytes)
                        .map_err(|e| format!("cannot write canonical output: {e}"))?;
                    wrote_canonical = true;
                }
            }
            if first_description.is_none() {
                first_description = Some(describe(&output));
            }
            configs.push(config);
        }
    }
    let deterministic = digests.windows(2).all(|pair| pair[0] == pair[1]);
    let summary = json!({
        "tool": "table_access_parse",
        "input_bytes": sql.len(),
        "input_sha256": input_sha,
        "configs": configs,
        "deterministic": if digests.is_empty() { Value::Null } else { json!(deterministic) },
        "result": first_description,
        "peak_rss_kib": peak_rss_kib(),
    });
    Ok((summary, args.summary_out))
}

fn main() -> ExitCode {
    match run() {
        Ok((summary, summary_out)) => {
            let text = match serde_json::to_string_pretty(&summary) {
                Ok(text) => text,
                Err(error) => {
                    eprintln!("cannot encode summary: {error}");
                    return ExitCode::from(2);
                }
            };
            match summary_out {
                Some(path) => {
                    if let Err(error) = fs::write(&path, text.as_bytes()) {
                        eprintln!("cannot write summary: {error}");
                        return ExitCode::from(2);
                    }
                }
                None => println!("{text}"),
            }
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("table_access_parse: {error}");
            ExitCode::from(2)
        }
    }
}
