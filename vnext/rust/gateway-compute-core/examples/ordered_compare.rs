//! IPC measurement/differential harness for comparison::ordered.
//!
//! This example owns all filesystem access. The core crate only receives
//! in-memory Arrow RecordBatches. It prints names, counts, positions, type
//! markers, and opaque digests; it never prints cell values or row identities.

use std::collections::BTreeSet;
use std::collections::HashMap;
use std::error::Error;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::time::Instant;

use arrow_array::RecordBatch;
use arrow_ipc::reader::FileReader;
use arrow_schema::SchemaRef;
use arrow_select::concat::concat_batches;
use gateway_compute_core::comparison::{
    BlankProvenance, OrderedCompareOptions, OrderedCompareResult, OrderedTablePair, SchemaChanges,
    build_ordered_pool, compare_ordered_table, compare_ordered_tables_parallel,
};
use serde::Deserialize;
use serde_json::{Value, json};

const INPUT_FORMAT: &str = "gateway.comparison.ordered-inputs";

#[derive(Debug, Deserialize)]
struct InputManifest {
    format: String,
    version: u32,
    cases: Vec<InputCase>,
}

#[derive(Debug, Deserialize)]
struct InputCase {
    case_id: String,
    corpus: String,
    table_name: String,
    before_ipc: Option<String>,
    current_ipc: Option<String>,
    expected_ocf: String,
    policy: InputPolicy,
}

#[derive(Debug, Deserialize)]
struct InputPolicy {
    policy_version: String,
    policy_digest: Option<String>,
    value_columns: Vec<String>,
    #[serde(default)]
    digest_value_columns: Vec<String>,
    compare_excluded_columns: Vec<String>,
    include_add_delete_records: bool,
    schema_changed: bool,
    raw_content_changed: bool,
    schema_changes: SchemaChanges,
    before_blank_provenance: String,
    current_blank_provenance: String,
    max_rows: usize,
}

struct LoadedCase {
    input: InputCase,
    before: Option<RecordBatch>,
    current: Option<RecordBatch>,
    options: OrderedCompareOptions,
}

struct Arguments {
    manifest: PathBuf,
    out_dir: PathBuf,
    threads: usize,
    warmups: usize,
    runs: usize,
    verify: bool,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("ordered_compare: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let arguments = parse_arguments()?;
    if arguments.runs == 0 {
        return Err("--runs must be positive".into());
    }
    let manifest_bytes = fs::read(&arguments.manifest)?;
    let manifest: InputManifest = serde_json::from_slice(&manifest_bytes)?;
    if manifest.format != INPUT_FORMAT || manifest.version != 1 {
        return Err("unsupported ordered input manifest".into());
    }
    let root = arguments
        .manifest
        .parent()
        .ok_or("manifest has no parent directory")?;
    let mut loaded = Vec::with_capacity(manifest.cases.len());
    for input in manifest.cases {
        loaded.push(load_case(root, input)?);
    }
    let pairs: Vec<OrderedTablePair<'_>> = loaded
        .iter()
        .map(|case| OrderedTablePair {
            before: case.before.as_ref(),
            current: case.current.as_ref(),
            options: &case.options,
        })
        .collect();
    let pool = build_ordered_pool(arguments.threads)?;

    let unique_table_names = loaded
        .iter()
        .map(|case| case.input.table_name.as_str())
        .collect::<BTreeSet<_>>()
        .len()
        == loaded.len();
    let mut group_times = Vec::with_capacity(arguments.runs);
    let mut latest = Vec::new();
    for iteration in 0..arguments.warmups.saturating_add(arguments.runs) {
        let started = Instant::now();
        let result = if unique_table_names {
            compare_ordered_tables_parallel(&pairs, &pool)?
        } else {
            let mut sequential = Vec::with_capacity(pairs.len());
            for pair in &pairs {
                sequential.push(compare_ordered_table(OrderedTablePair {
                    before: pair.before,
                    current: pair.current,
                    options: pair.options,
                })?);
            }
            sequential
        };
        let elapsed = started.elapsed().as_secs_f64();
        if iteration >= arguments.warmups {
            group_times.push(elapsed);
        }
        latest = result;
    }

    let mut per_case_times: Vec<Vec<f64>> = (0..loaded.len())
        .map(|_| Vec::with_capacity(arguments.runs))
        .collect();
    for iteration in 0..arguments.warmups.saturating_add(arguments.runs) {
        for (index, pair) in pairs.iter().enumerate() {
            let started = Instant::now();
            let _result = compare_ordered_table(OrderedTablePair {
                before: pair.before,
                current: pair.current,
                options: pair.options,
            })?;
            if iteration >= arguments.warmups
                && let Some(times) = per_case_times.get_mut(index)
            {
                times.push(started.elapsed().as_secs_f64());
            }
        }
    }

    if arguments.verify {
        private_dir(&arguments.out_dir)?;
    }
    let mut cases_json = Vec::with_capacity(latest.len());
    let mut differences = 0usize;
    let latest_by_name: HashMap<&str, &OrderedCompareResult> = if unique_table_names {
        latest
            .iter()
            .map(|result| (result.table_name.as_str(), result))
            .collect()
    } else {
        HashMap::new()
    };
    for (index, ordered_result) in latest.iter().enumerate() {
        let input = loaded
            .get(index)
            .ok_or("result index does not match loaded cases")?;
        let result = if unique_table_names {
            latest_by_name
                .get(input.input.table_name.as_str())
                .copied()
                .ok_or("parallel result is missing a table")?
        } else {
            ordered_result
        };
        let canonical = result.canonical_bytes()?;
        let expected_path = root.join(&input.input.expected_ocf);
        let equal = if arguments.verify {
            let expected = fs::read(expected_path)?;
            let output_path = arguments
                .out_dir
                .join(format!("{}.rust.ocf", input.input.case_id));
            write_private(&output_path, &canonical)?;
            expected == canonical
        } else {
            true
        };
        if !equal {
            differences = differences.saturating_add(1);
        }
        let time_summary = per_case_times.get(index).map(|values| {
            json!({
                "serial_median_seconds": median(values),
                "serial_min_seconds": values.iter().copied().fold(f64::INFINITY, f64::min),
                "serial_max_seconds": values.iter().copied().fold(0.0, f64::max),
            })
        });
        cases_json.push(case_summary(
            result,
            &canonical,
            equal,
            time_summary,
            &input.input,
        ));
    }
    let summary = json!({
        "format": "gateway.comparison.ordered-measurement",
        "version": 1,
        "manifest": arguments.manifest.file_name().and_then(|name| name.to_str()).unwrap_or("manifest"),
        "threads": arguments.threads,
        "warmups": arguments.warmups,
        "runs": arguments.runs,
        "group_median_seconds": median(&group_times),
        "group_min_seconds": group_times.iter().copied().fold(f64::INFINITY, f64::min),
        "group_max_seconds": group_times.iter().copied().fold(0.0, f64::max),
        "peak_rss_kib": peak_rss_kib(),
        "table_count": latest.len(),
        "difference_count": differences,
        "cases": cases_json,
    });
    println!("{}", serde_json::to_string(&summary)?);
    if differences != 0 {
        std::process::exit(1);
    }
    Ok(())
}

fn load_case(root: &Path, input: InputCase) -> Result<LoadedCase, Box<dyn Error>> {
    let before = input
        .before_ipc
        .as_deref()
        .map(|path| read_ipc_batch(&root.join(path)))
        .transpose()?;
    let current = input
        .current_ipc
        .as_deref()
        .map(|path| read_ipc_batch(&root.join(path)))
        .transpose()?;
    let mut options = OrderedCompareOptions::new(input.table_name.clone());
    options.policy_version = input.policy.policy_version.clone();
    options.policy_digest = input.policy.policy_digest.clone();
    options
        .value_columns
        .clone_from(&input.policy.value_columns);
    options
        .digest_value_columns
        .clone_from(&input.policy.digest_value_columns);
    options
        .compare_excluded_columns
        .clone_from(&input.policy.compare_excluded_columns);
    options.include_add_delete_records = input.policy.include_add_delete_records;
    options.schema_changed = input.policy.schema_changed;
    options.raw_content_changed = input.policy.raw_content_changed;
    options.schema_changes = input.policy.schema_changes.clone();
    options.before_blank_provenance = blank_provenance(&input.policy.before_blank_provenance)?;
    options.current_blank_provenance = blank_provenance(&input.policy.current_blank_provenance)?;
    options.max_rows = input.policy.max_rows;
    Ok(LoadedCase {
        input,
        before,
        current,
        options,
    })
}

fn read_ipc_batch(path: &Path) -> Result<RecordBatch, Box<dyn Error>> {
    let file = File::open(path)?;
    let mut reader = FileReader::try_new(file, None)?;
    let schema: SchemaRef = reader.schema();
    let mut batches = Vec::new();
    for batch in &mut reader {
        batches.push(batch?);
    }
    if batches.is_empty() {
        return Ok(RecordBatch::new_empty(schema));
    }
    Ok(concat_batches(&schema, &batches)?)
}

fn blank_provenance(value: &str) -> Result<BlankProvenance, Box<dyn Error>> {
    match value {
        "MISSING" => Ok(BlankProvenance::Missing),
        "SOURCE_MISSING_STABLE_KEY" => Ok(BlankProvenance::SourceMissingStableKey),
        "CANONICAL_PSEUDO_GID" => Ok(BlankProvenance::CanonicalPseudoGid),
        _ => Err(format!("unsupported blank provenance {value}").into()),
    }
}

fn case_summary(
    result: &OrderedCompareResult,
    canonical: &[u8],
    equal: bool,
    times: Option<Value>,
    input: &InputCase,
) -> Value {
    let mut markers = BTreeSet::new();
    let mut positions = Vec::new();
    for record in &result.records {
        markers_in_values(&record.before_values, &mut markers);
        markers_in_values(&record.current_values, &mut markers);
        for change in &record.field_changes {
            markers.insert(change.before.type_marker);
            markers.insert(change.current.type_marker);
        }
    }
    for record in &result.ordered_extension.records {
        markers_in_values(&record.before_values, &mut markers);
        markers_in_values(&record.current_values, &mut markers);
        if positions.len() < 16
            && let Some(position) = record.before_position
        {
            positions.push(position);
        }
        if positions.len() < 16
            && let Some(position) = record.current_position
        {
            positions.push(position);
        }
    }
    for record in &result.blank_extension.records {
        if positions.len() >= 16 {
            break;
        }
        for position in [
            record.interval.before_start,
            record.interval.before_end,
            record.interval.current_start,
            record.interval.current_end,
        ]
        .into_iter()
        .flatten()
        {
            positions.push(position);
            if positions.len() >= 16 {
                break;
            }
        }
    }
    json!({
        "case_id": input.case_id,
        "corpus": input.corpus,
        "table_name": result.table_name,
        "status": result.status,
        "same_as_reference": equal,
        "row_count_before": result.row_count_before,
        "row_count_current": result.row_count_current,
        "row_added_count": result.row_added_count,
        "row_deleted_count": result.row_deleted_count,
        "row_modified_count": result.row_modified_count,
        "suppressed_added_count": result.suppressed_added_count,
        "suppressed_deleted_count": result.suppressed_deleted_count,
        "standard_record_count": result.records.len(),
        "ordered_record_count": result.ordered_extension.records.len(),
        "blank_record_count": result.blank_extension.records.len(),
        "sample_positions": positions,
        "type_markers": markers,
        "normal_form_bytes": canonical.len(),
        "timing": times,
    })
}

fn markers_in_values(
    values: &[gateway_compute_core::comparison::CanonicalValue],
    output: &mut BTreeSet<u8>,
) {
    output.extend(values.iter().map(|value| value.type_marker));
}

fn median(values: &[f64]) -> f64 {
    let mut ordered = values.to_vec();
    ordered.sort_by(f64::total_cmp);
    match ordered.len() {
        0 => 0.0,
        length if length % 2 == 0 => (ordered[length / 2 - 1] + ordered[length / 2]) / 2.0,
        length => ordered[length / 2],
    }
}

fn peak_rss_kib() -> Option<u64> {
    let mut status = String::new();
    File::open("/proc/self/status")
        .ok()?
        .read_to_string(&mut status)
        .ok()?;
    status.lines().find_map(|line| {
        line.strip_prefix("VmHWM:")
            .and_then(|value| value.split_whitespace().next())
            .and_then(|value| value.parse::<u64>().ok())
    })
}

fn private_dir(path: &Path) -> Result<(), Box<dyn Error>> {
    let mut builder = fs::DirBuilder::new();
    builder.recursive(true).mode(0o700).create(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    Ok(())
}

fn write_private(path: &Path, bytes: &[u8]) -> Result<(), Box<dyn Error>> {
    let parent = path.parent().ok_or("private output path has no parent")?;
    private_dir(parent)?;
    let mut file = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .mode(0o600)
        .open(path)?;
    file.write_all(bytes)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    Ok(())
}

fn parse_arguments() -> Result<Arguments, Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let mut manifest = None;
    let mut out_dir = None;
    let mut threads = 1usize;
    let mut warmups = 1usize;
    let mut runs = 3usize;
    let mut verify = false;
    while let Some(argument) = args.next() {
        match argument.as_str() {
            "--manifest" => manifest = args.next().map(PathBuf::from),
            "--out-dir" => out_dir = args.next().map(PathBuf::from),
            "--threads" => threads = parse_next(&mut args, "--threads")?,
            "--warmups" => warmups = parse_next(&mut args, "--warmups")?,
            "--runs" => runs = parse_next(&mut args, "--runs")?,
            "--verify" => verify = true,
            "--help" | "-h" => {
                println!(
                    "ordered_compare --manifest PATH --out-dir DIR [--threads N] [--warmups N] [--runs N] [--verify]"
                );
                std::process::exit(0);
            }
            other => return Err(format!("unknown argument {other}").into()),
        }
    }
    Ok(Arguments {
        manifest: manifest.ok_or("--manifest is required")?,
        out_dir: out_dir.ok_or("--out-dir is required")?,
        threads,
        warmups,
        runs,
        verify,
    })
}

fn parse_next<T: std::str::FromStr>(
    args: &mut impl Iterator<Item = String>,
    label: &str,
) -> Result<T, Box<dyn Error>>
where
    T::Err: Error + 'static,
{
    args.next()
        .ok_or_else(|| format!("{label} requires a value"))?
        .parse::<T>()
        .map_err(|error| Box::new(error) as Box<dyn Error>)
}
