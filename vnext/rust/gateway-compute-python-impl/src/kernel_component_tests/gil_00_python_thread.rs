use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use pyo3::prelude::*;
use pyo3::types::PyCFunction;
use pyo3::types::{PyAnyMethods, PyDict};

use crate::adapter::test_hooks::{self, AdapterStage};

use super::gil_controller::DETACHED_MIN_SUCCESSES;
use super::support::with_python;

const STAGE_TIMEOUT: Duration = Duration::from_secs(5);
const ATTACHED_OBSERVE_DURATION: Duration = Duration::from_millis(500);

struct PythonCounterProbe {
    stop_event: Py<PyAny>,
    probe_thread: Py<PyAny>,
    started: Arc<AtomicBool>,
}

struct PythonProbeGuard {
    probe: Option<PythonCounterProbe>,
}

impl PythonProbeGuard {
    fn new(probe: PythonCounterProbe) -> Self {
        Self { probe: Some(probe) }
    }

    fn wait_until_started(&self, counter: &Arc<AtomicU64>) -> Result<(), String> {
        let deadline = Instant::now() + STAGE_TIMEOUT;
        while Instant::now() < deadline {
            if self
                .probe
                .as_ref()
                .is_some_and(|probe| probe.started.load(Ordering::SeqCst))
                && read_counter(counter) > 0
            {
                return Ok(());
            }
            thread::yield_now();
        }
        Err("python counter thread did not start before stage entry".to_string())
    }

    fn stop_and_join(py: Python<'_>, mut this: Self) -> Result<(), String> {
        let probe = this
            .probe
            .take()
            .ok_or_else(|| "python probe already stopped".to_string())?;
        stop_counter_probe(py, &probe)?;
        Ok(())
    }
}

impl Drop for PythonProbeGuard {
    fn drop(&mut self) {
        if let Some(probe) = self.probe.take() {
            let _ = Python::try_attach(|py| {
                let _ = stop_counter_probe(py, &probe);
            });
        }
        test_hooks::clear_hold();
    }
}

fn spawn_counter_probe(
    py: Python<'_>,
    counter: Arc<AtomicU64>,
    may_run: &Bound<'_, PyAny>,
) -> PyResult<PythonCounterProbe> {
    let threading = py.import("threading")?;
    let stop_event = threading.getattr("Event")?.call0()?;
    let started = Arc::new(AtomicBool::new(false));
    let started_for_bump = Arc::clone(&started);
    let counter_for_bump = Arc::clone(&counter);
    let bump = PyCFunction::new_closure(py, None, None, move |_args, _kwargs| -> PyResult<()> {
        started_for_bump.store(true, Ordering::SeqCst);
        counter_for_bump.fetch_add(1, Ordering::Relaxed);
        Ok(())
    })?;

    let locals = PyDict::new(py);
    locals.set_item("stop_event", &stop_event)?;
    locals.set_item("may_run", may_run)?;
    locals.set_item("bump", bump)?;
    py.run(
        std::ffi::CString::new(
            "def _make_runner(stop_event, may_run, bump):\n    def run():\n        may_run.wait()\n        while not stop_event.is_set():\n            bump()\n    return run\n",
        )
        .map_err(|error| PyErr::new::<pyo3::exceptions::PyValueError, _>(error.to_string()))?
        .as_c_str(),
        Some(&locals),
        Some(&locals),
    )?;

    let make_runner = locals
        .get_item("_make_runner")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("missing _make_runner"))?;
    let bump_fn = locals
        .get_item("bump")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("missing bump"))?;
    let target = make_runner.call1((&stop_event, may_run, bump_fn))?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("target", target)?;
    kwargs.set_item("daemon", false)?;
    let probe_thread = threading.call_method("Thread", (), Some(&kwargs))?;
    probe_thread.call_method0("start")?;

    Ok(PythonCounterProbe {
        stop_event: stop_event.unbind(),
        probe_thread: probe_thread.unbind(),
        started,
    })
}

fn read_counter(counter: &Arc<AtomicU64>) -> u64 {
    counter.load(Ordering::Relaxed)
}

fn stop_counter_probe(py: Python<'_>, probe: &PythonCounterProbe) -> Result<(), String> {
    let stop_event = probe.stop_event.bind(py);
    let probe_thread = probe.probe_thread.bind(py);
    stop_event
        .call_method0("set")
        .map_err(|error| error.to_string())?;
    probe_thread
        .call_method1("join", (STAGE_TIMEOUT.as_secs_f64(),))
        .map_err(|error| error.to_string())?;
    let alive = probe_thread
        .getattr("is_alive")
        .map_err(|error| error.to_string())?
        .call0()
        .map_err(|error| error.to_string())?
        .extract::<bool>()
        .map_err(|error| error.to_string())?;
    if alive {
        return Err("python counter thread still alive after join timeout".to_string());
    }
    Ok(())
}

fn wait_for_progress(
    counter: &Arc<AtomicU64>,
    baseline: u64,
    min_successes: u64,
    timeout: Duration,
) -> u64 {
    let deadline = Instant::now() + timeout;
    let mut observed = 0u64;
    while Instant::now() < deadline {
        observed = read_counter(counter).saturating_sub(baseline);
        if observed >= min_successes {
            break;
        }
        thread::yield_now();
    }
    observed
}

fn observe_hold_delta(counter: &Arc<AtomicU64>, baseline: u64, timeout: Duration) -> u64 {
    let deadline = Instant::now() + timeout;
    let mut observed = 0u64;
    while Instant::now() < deadline {
        observed = read_counter(counter).saturating_sub(baseline);
        thread::yield_now();
    }
    observed
}

/// Detached: hold-period progress >= DETACHED_MIN_SUCCESSES.
/// Attached: hold-period progress == 0, then post-release progress >= DETACHED_MIN_SUCCESSES.
fn probe_python_thread_progress<F>(
    py: Python<'_>,
    stage: AdapterStage,
    expect_detached_progress: bool,
    work: F,
) -> Result<(), String>
where
    F: FnOnce(Python<'_>) -> Result<(), String>,
{
    let counter = Arc::new(AtomicU64::new(0));
    let threading = py.import("threading").map_err(|error| error.to_string())?;
    let may_run = threading
        .getattr("Event")
        .map_err(|error| error.to_string())?
        .call0()
        .map_err(|error| error.to_string())?;
    // Allow the worker to run; start() itself does not guarantee the target has bumped yet.
    may_run
        .call_method0("set")
        .map_err(|error| error.to_string())?;
    let probe = spawn_counter_probe(py, Arc::clone(&counter), &may_run)
        .map_err(|error| error.to_string())?;
    let guard = PythonProbeGuard::new(probe);
    // Release GIL while waiting so the Python target can make progress after start().
    py.detach(|| guard.wait_until_started(&counter))?;

    let (entered_tx, entered_rx) = mpsc::channel();
    let (release_tx, release_rx) = mpsc::channel();
    test_hooks::set_hold(stage, entered_tx, release_rx);

    let counter_for_controller = Arc::clone(&counter);
    let controller = thread::spawn(move || -> Result<(), String> {
        let release_guard = ReleaseOnDrop(Some(release_tx));
        entered_rx
            .recv_timeout(STAGE_TIMEOUT)
            .map_err(|error| format!("stage {stage:?} not entered within timeout: {error}"))?;

        let baseline = read_counter(&counter_for_controller);
        if expect_detached_progress {
            let observed = wait_for_progress(
                &counter_for_controller,
                baseline,
                DETACHED_MIN_SUCCESSES,
                STAGE_TIMEOUT,
            );
            if observed < DETACHED_MIN_SUCCESSES {
                return Err(format!(
                    "detached stage {stage:?} expected >= {DETACHED_MIN_SUCCESSES} python thread ticks during hold, got {observed}"
                ));
            }
        } else {
            let observed =
                observe_hold_delta(&counter_for_controller, baseline, ATTACHED_OBSERVE_DURATION);
            if observed != 0 {
                return Err(format!(
                    "attached stage {stage:?} must have zero python thread progress during hold, got {observed}"
                ));
            }
        }
        drop(release_guard);
        Ok(())
    });

    let work_result = work(py);
    let controller_result = controller
        .join()
        .map_err(|_| "python-thread controller panicked".to_string())
        .and_then(|inner| inner);

    let post_release_result = if !expect_detached_progress && controller_result.is_ok() {
        let post_baseline = read_counter(&counter);
        let post = py.detach(|| {
            wait_for_progress(
                &counter,
                post_baseline,
                DETACHED_MIN_SUCCESSES,
                STAGE_TIMEOUT,
            )
        });
        if post < DETACHED_MIN_SUCCESSES {
            Err(format!(
                "attached stage {stage:?} expected >= {DETACHED_MIN_SUCCESSES} python thread ticks after release, got {post}"
            ))
        } else {
            Ok(())
        }
    } else {
        Ok(())
    };

    let stop_result = PythonProbeGuard::stop_and_join(py, guard);
    test_hooks::clear_hold();

    match (
        work_result,
        controller_result,
        post_release_result,
        stop_result,
    ) {
        (Ok(()), Ok(()), Ok(()), Ok(())) => {
            if !test_hooks::hold_is_clear() {
                return Err("hold was not cleared after python thread probe".to_string());
            }
            Ok(())
        }
        (Err(error), _, _, _)
        | (_, Err(error), _, _)
        | (_, _, Err(error), _)
        | (_, _, _, Err(error)) => Err(error),
    }
}

struct ReleaseOnDrop(Option<mpsc::Sender<()>>);

impl Drop for ReleaseOnDrop {
    fn drop(&mut self) {
        if let Some(tx) = self.0.take() {
            let _ = tx.send(());
        }
    }
}

fn empty_batch_reader() -> Box<dyn arrow_array::RecordBatchReader + Send> {
    use arrow_array::{RecordBatch, RecordBatchReader};
    use arrow_schema::{ArrowError, Schema};
    use std::sync::Arc;

    struct EmptyBatchReader {
        schema: Arc<Schema>,
        done: bool,
    }

    impl EmptyBatchReader {
        fn new() -> Self {
            Self {
                schema: Arc::new(Schema::empty()),
                done: false,
            }
        }
    }

    impl RecordBatchReader for EmptyBatchReader {
        fn schema(&self) -> Arc<Schema> {
            self.schema.clone()
        }
    }

    impl Iterator for EmptyBatchReader {
        type Item = Result<RecordBatch, ArrowError>;

        fn next(&mut self) -> Option<Self::Item> {
            if self.done {
                return None;
            }
            self.done = true;
            Some(Ok(RecordBatch::new_empty(self.schema.clone())))
        }
    }

    Box::new(EmptyBatchReader::new())
}

pub(crate) fn run_python_thread_progress_suite() -> Result<(), String> {
    use pyo3_arrow::PyRecordBatchReader;

    use crate::adapter::{self, test_invoke_export_hold_probe, test_invoke_import_hold_probe};

    for (stage, label) in [
        (AdapterStage::Parse, "parse"),
        (AdapterStage::Compute, "compute"),
    ] {
        with_python(|py| {
            let stream = PyRecordBatchReader::new(empty_batch_reader())
                .into_pyarrow(py)
                .map_err(|error| error.to_string())?
                .unbind();
            probe_python_thread_progress(py, stage, true, |py| {
                adapter::canonical_row_hashes_v1_native(
                    py,
                    super::support::minimal_empty_request_jcs(),
                    stream.bind(py),
                )
                .map(|_| ())
                .map_err(|error| error.to_string())
            })
            .map_err(|error| format!("{label}: {error}"))
        })?;
    }

    with_python(|py| {
        let stream = PyRecordBatchReader::new(empty_batch_reader())
            .into_pyarrow(py)
            .map_err(|error| error.to_string())?;
        probe_python_thread_progress(py, AdapterStage::Import, false, |py| {
            test_invoke_import_hold_probe(py, &stream)
                .map(|_| ())
                .map_err(|error| format!("{error:?}"))
        })
        .map_err(|error| format!("import attached: {error}"))
    })?;

    with_python(|py| {
        probe_python_thread_progress(py, AdapterStage::Export, false, |py| {
            test_invoke_export_hold_probe(py, Vec::new())
                .map(|_| ())
                .map_err(|error| format!("{error:?}"))
        })
        .map_err(|error| format!("export attached: {error}"))
    })?;

    // Negative: attached protocol against a truly detached stage must fail.
    let negative = with_python(|py| {
        let stream = PyRecordBatchReader::new(empty_batch_reader())
            .into_pyarrow(py)
            .map_err(|error| error.to_string())?
            .unbind();
        probe_python_thread_progress(py, AdapterStage::Parse, false, |py| {
            adapter::canonical_row_hashes_v1_native(
                py,
                super::support::minimal_empty_request_jcs(),
                stream.bind(py),
            )
            .map(|_| ())
            .map_err(|error| error.to_string())
        })
    });
    match negative {
        Err(error) if error.contains("must have zero python thread progress") => Ok(()),
        Err(error) => Err(format!(
            "expected attached-protocol failure on detached Parse, got: {error}"
        )),
        Ok(()) => Err(
            "attached protocol unexpectedly passed on detached Parse (Export-in-detached regression)"
                .to_string(),
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_probe_cleanup_joins_thread_on_controller_failure() -> Result<(), String> {
        with_python(|py| {
            let counter = Arc::new(AtomicU64::new(0));
            let threading = py.import("threading").map_err(|error| error.to_string())?;
            let may_run = threading
                .getattr("Event")
                .map_err(|error| error.to_string())?
                .call0()
                .map_err(|error| error.to_string())?;
            may_run
                .call_method0("set")
                .map_err(|error| error.to_string())?;
            let probe = spawn_counter_probe(py, Arc::clone(&counter), &may_run)
                .map_err(|error| error.to_string())?;
            let guard = PythonProbeGuard::new(probe);
            py.detach(|| guard.wait_until_started(&counter))?;

            let (entered_tx, entered_rx) = mpsc::channel();
            let (release_tx, release_rx) = mpsc::channel();
            test_hooks::set_hold(AdapterStage::Import, entered_tx, release_rx);

            let controller = thread::spawn(move || -> Result<(), String> {
                let _release = ReleaseOnDrop(Some(release_tx));
                let _ = entered_rx.recv_timeout(Duration::from_millis(10));
                Err("deliberate controller failure".to_string())
            });

            let controller_result = controller
                .join()
                .map_err(|_| "controller panicked".to_string())
                .and_then(|inner| inner);
            let stop_result = PythonProbeGuard::stop_and_join(py, guard);
            test_hooks::clear_hold();

            if controller_result.is_ok() {
                return Err("expected controller failure".to_string());
            }
            stop_result?;
            if !test_hooks::hold_is_clear() {
                return Err("hold not cleared after controller failure cleanup".to_string());
            }
            Ok(())
        })
    }

    #[test]
    fn python_probe_start_sync_succeeds_when_target_blocked_until_after_start() -> Result<(), String>
    {
        with_python(|py| {
            let counter = Arc::new(AtomicU64::new(0));
            let threading = py.import("threading").map_err(|error| error.to_string())?;
            let may_run = threading
                .getattr("Event")
                .map_err(|error| error.to_string())?
                .call0()
                .map_err(|error| error.to_string())?;
            // Intentionally leave may_run clear so Thread.start() cannot complete the first bump.
            let probe = spawn_counter_probe(py, Arc::clone(&counter), &may_run)
                .map_err(|error| error.to_string())?;
            if read_counter(&counter) != 0 {
                return Err(
                    "expected zero progress after start while may_run is blocked".to_string(),
                );
            }
            let guard = PythonProbeGuard::new(probe);
            let may_run = may_run.unbind();
            py.detach(|| -> Result<(), String> {
                // Re-attach briefly to release the barrier only after GIL is dropped for waiting.
                Python::attach(|py| {
                    may_run
                        .bind(py)
                        .call_method0("set")
                        .map(|_| ())
                        .map_err(|error| error.to_string())
                })?;
                guard.wait_until_started(&counter)
            })?;
            PythonProbeGuard::stop_and_join(py, guard)?;
            Ok(())
        })
    }
}
