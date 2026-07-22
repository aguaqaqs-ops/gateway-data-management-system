use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use pyo3::prelude::*;

use crate::adapter::test_hooks::{self, AdapterStage};

pub const DETACHED_MIN_SUCCESSES: u64 = 16;
const STAGE_TIMEOUT: Duration = Duration::from_secs(5);
/// Attached smoke only waits briefly; authoritative attached proof is Python-thread progress.
const ATTACHED_SMOKE_HOLD: Duration = Duration::from_millis(50);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GilExpectation {
    AttachedBlocksProgress,
    DetachedAllowsProgress,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ProbeReply {
    Attached,
    NotAttached,
    DetachedDone(u64),
    ShutdownAck,
}

enum ProbeCmd {
    TryOnceBlocking,
    DetachUntil {
        deadline: Instant,
        min_successes: u64,
    },
    Shutdown,
}

struct ProbeWorker {
    cmd_tx: Sender<ProbeCmd>,
    reply_rx: Option<Receiver<ProbeReply>>,
    join_handle: Option<JoinHandle<()>>,
    exited: Arc<AtomicBool>,
}

fn probe_try_attach_blocking() -> ProbeReply {
    if Python::try_attach(|_| ()).is_some() {
        ProbeReply::Attached
    } else {
        ProbeReply::NotAttached
    }
}

impl ProbeWorker {
    fn spawn() -> Self {
        let (cmd_tx, cmd_rx) = mpsc::channel::<ProbeCmd>();
        let (reply_tx, reply_rx) = mpsc::channel::<ProbeReply>();
        let exited = Arc::new(AtomicBool::new(false));
        let exited_flag = Arc::clone(&exited);
        let join_handle = thread::spawn(move || {
            while let Ok(cmd) = cmd_rx.recv() {
                match cmd {
                    ProbeCmd::TryOnceBlocking => {
                        let reply = probe_try_attach_blocking();
                        let _ = reply_tx.send(reply);
                    }
                    ProbeCmd::DetachUntil {
                        deadline,
                        min_successes,
                    } => {
                        let mut count = 0u64;
                        while Instant::now() < deadline {
                            if Python::try_attach(|_| count += 1).is_some() {
                                // counted
                            } else {
                                thread::yield_now();
                            }
                            if count >= min_successes {
                                break;
                            }
                        }
                        let _ = reply_tx.send(ProbeReply::DetachedDone(count));
                    }
                    ProbeCmd::Shutdown => {
                        let _ = reply_tx.send(ProbeReply::ShutdownAck);
                        break;
                    }
                }
            }
            exited_flag.store(true, Ordering::SeqCst);
        });
        Self {
            cmd_tx,
            reply_rx: Some(reply_rx),
            join_handle: Some(join_handle),
            exited,
        }
    }

    fn worker_exited(&self) -> bool {
        self.exited.load(Ordering::SeqCst)
    }

    fn shutdown(mut self) -> Result<(), String> {
        let _ = self
            .cmd_tx
            .send(ProbeCmd::Shutdown)
            .map_err(|error| format!("probe worker shutdown command failed: {error}"));
        if let Some(reply_rx) = self.reply_rx.take() {
            match recv_reply(&reply_rx, "shutdown") {
                Ok(ProbeReply::ShutdownAck) => {}
                Ok(other) => {
                    return Err(format!("unexpected probe reply during shutdown: {other:?}"));
                }
                Err(_) => {
                    // Best-effort shutdown after controller failure.
                }
            }
        }
        if let Some(handle) = self.join_handle.take() {
            handle
                .join()
                .map_err(|_| "probe worker thread panicked".to_string())?;
        }
        if !self.worker_exited() {
            return Err("probe worker did not mark exit after join".to_string());
        }
        Ok(())
    }
}

fn recv_reply(rx: &Receiver<ProbeReply>, label: &str) -> Result<ProbeReply, String> {
    rx.recv_timeout(STAGE_TIMEOUT).map_err(|error| {
        format!("probe worker {label} reply timed out after {STAGE_TIMEOUT:?}: {error}")
    })
}

type ControllerJoinResult = Result<(Receiver<ProbeReply>, ()), String>;
type ControllerHandle = JoinHandle<ControllerJoinResult>;

struct ProbeStageGuard {
    worker: Option<ProbeWorker>,
    controller: Option<ControllerHandle>,
}

impl ProbeStageGuard {
    fn begin(stage: AdapterStage, expectation: GilExpectation) -> Result<Self, String> {
        let (entered_tx, entered_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel();
        test_hooks::set_hold(stage, entered_tx, release_rx);

        let mut worker = ProbeWorker::spawn();
        let reply_rx = worker
            .reply_rx
            .take()
            .ok_or_else(|| "probe worker reply channel unavailable".to_string())?;
        let cmd_tx = worker.cmd_tx.clone();
        let controller = thread::spawn(move || -> ControllerJoinResult {
            entered_rx
                .recv_timeout(STAGE_TIMEOUT)
                .map_err(|error| format!("stage {stage:?} not entered within timeout: {error}"))?;

            match expectation {
                GilExpectation::AttachedBlocksProgress => {
                    // Smoke only: authoritative attached proof is Python-thread progress (M1).
                    thread::sleep(ATTACHED_SMOKE_HOLD);
                }
                GilExpectation::DetachedAllowsProgress => {
                    let deadline = Instant::now() + STAGE_TIMEOUT;
                    cmd_tx
                        .send(ProbeCmd::DetachUntil {
                            deadline,
                            min_successes: DETACHED_MIN_SUCCESSES,
                        })
                        .map_err(|error| format!("probe worker command channel closed: {error}"))?;
                    let observed = match recv_reply(&reply_rx, "detach_until")? {
                        ProbeReply::DetachedDone(count) => count,
                        other => {
                            return Err(format!(
                                "unexpected probe reply during detach_until: {other:?}"
                            ));
                        }
                    };
                    if observed < DETACHED_MIN_SUCCESSES {
                        return Err(format!(
                            "detached stage {stage:?} should allow probe progress, got {observed} successes"
                        ));
                    }
                }
            }

            release_tx
                .send(())
                .map_err(|error| format!("failed to release hold for {stage:?}: {error}"))?;
            Ok((reply_rx, ()))
        });

        Ok(Self {
            worker: Some(worker),
            controller: Some(controller),
        })
    }

    fn join_controller(&mut self) -> Result<Receiver<ProbeReply>, String> {
        let controller = self
            .controller
            .take()
            .ok_or_else(|| "controller already joined".to_string())?;
        controller
            .join()
            .map_err(|_| "controller thread panicked".to_string())?
            .map(|(reply_rx, ())| reply_rx)
    }

    fn shutdown_worker(&mut self) -> Result<(), String> {
        let worker = self
            .worker
            .take()
            .ok_or_else(|| "probe worker already taken".to_string())?;
        worker.shutdown()
    }
}

impl Drop for ProbeStageGuard {
    fn drop(&mut self) {
        test_hooks::clear_hold();
        if let Some(mut worker) = self.worker.take() {
            let _ = worker.cmd_tx.send(ProbeCmd::Shutdown);
            if let Some(handle) = worker.join_handle.take() {
                let _ = handle.join();
            }
        }
        if let Some(controller) = self.controller.take() {
            let _ = controller.join();
        }
    }
}

fn prefer_primary(primary: Option<String>, secondary: Result<(), String>) -> Result<(), String> {
    match (primary, secondary) {
        (Some(error), _) => Err(error),
        (None, Ok(())) => Ok(()),
        (None, Err(error)) => Err(error),
    }
}

pub fn probe_stage<F>(
    py: Python<'_>,
    stage: AdapterStage,
    expectation: GilExpectation,
    work: F,
) -> Result<(), String>
where
    F: FnOnce() -> Result<(), String>,
{
    let mut guard = ProbeStageGuard::begin(stage, expectation)?;
    let worker_exited = guard
        .worker
        .as_ref()
        .map(|worker| Arc::clone(&worker.exited))
        .ok_or_else(|| "probe worker unavailable".to_string())?;

    let work_result = work();
    let controller_result = guard.join_controller();

    let mut primary_error = None;
    match controller_result {
        Ok(reply_rx) => {
            if let Some(worker) = guard.worker.as_mut() {
                worker.reply_rx = Some(reply_rx);
            }
        }
        Err(controller_error) => {
            primary_error = Some(controller_error);
        }
    }
    if let Err(work_error) = work_result {
        // Prefer work error when both fail; still keep reply_rx installed above.
        primary_error = Some(work_error);
    }

    if primary_error.is_none()
        && matches!(expectation, GilExpectation::AttachedBlocksProgress)
        && let Some(worker) = guard.worker.as_mut()
    {
        let cmd_tx = worker.cmd_tx.clone();
        let reply_rx = worker
            .reply_rx
            .take()
            .ok_or_else(|| "probe worker reply channel unavailable".to_string())?;
        match py.detach(
            move || -> Result<(ProbeReply, Receiver<ProbeReply>), String> {
                cmd_tx
                    .send(ProbeCmd::TryOnceBlocking)
                    .map_err(|error| format!("probe worker command channel closed: {error}"))?;
                let reply = recv_reply(&reply_rx, "post_release")?;
                Ok((reply, reply_rx))
            },
        ) {
            Ok((attached, reply_rx)) => {
                if let Some(worker) = guard.worker.as_mut() {
                    worker.reply_rx = Some(reply_rx);
                }
                if attached != ProbeReply::Attached {
                    primary_error = Some(format!(
                        "attached stage {stage:?} should allow probe attach after release, got {attached:?}"
                    ));
                }
            }
            Err(error) => {
                primary_error = Some(error);
            }
        }
    }

    test_hooks::clear_hold();
    let shutdown_result = guard.shutdown_worker();
    // Worker already shut down; Drop must not join again.
    drop(guard);

    prefer_primary(primary_error, shutdown_result)?;
    assert_worker_joined(&worker_exited)?;
    if !test_hooks::hold_is_clear() {
        return Err("hold was not cleared after probe_stage".to_string());
    }
    Ok(())
}

fn assert_worker_joined(exited: &Arc<AtomicBool>) -> Result<(), String> {
    if exited.load(Ordering::SeqCst) {
        Ok(())
    } else {
        Err("probe worker was not joined before returning from probe_stage".to_string())
    }
}

pub fn probe_stage_expect_failure<F>(
    stage: AdapterStage,
    expectation: GilExpectation,
    work: F,
) -> Result<(String, Arc<AtomicBool>), String>
where
    F: FnOnce() -> Result<(), String>,
{
    let mut guard = ProbeStageGuard::begin(stage, expectation)?;
    let worker_exited = guard
        .worker
        .as_ref()
        .map(|worker| Arc::clone(&worker.exited))
        .ok_or_else(|| "probe worker unavailable".to_string())?;
    let work_result = work();
    let controller_result = guard.join_controller();
    drop(guard);
    assert_worker_joined(&worker_exited)?;
    if !test_hooks::hold_is_clear() {
        return Err("hold was not cleared after probe_stage_expect_failure".to_string());
    }

    match (work_result, controller_result) {
        (Ok(()), Ok(_)) => Err("expected probe_stage failure but succeeded".to_string()),
        (Err(error), _) | (_, Err(error)) => Ok((error, worker_exited)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::adapter::test_hooks::AdapterStage;

    #[test]
    fn probe_stage_failure_joins_worker_on_work_error() -> Result<(), String> {
        let (error, exited) = probe_stage_expect_failure(
            AdapterStage::Import,
            GilExpectation::AttachedBlocksProgress,
            || Err("deliberate work failure".to_string()),
        )?;
        if !error.contains("deliberate work failure") {
            return Err(format!("unexpected failure error: {error}"));
        }
        if !exited.load(Ordering::SeqCst) {
            return Err("worker not exited after work error".to_string());
        }
        Ok(())
    }

    #[test]
    fn probe_stage_failure_joins_worker_on_stage_miss() -> Result<(), String> {
        let (error, exited) = probe_stage_expect_failure(
            AdapterStage::Parse,
            GilExpectation::DetachedAllowsProgress,
            || Ok(()),
        )?;
        if !error.contains("stage Parse not entered") {
            return Err(format!("unexpected stage-miss error: {error}"));
        }
        if !exited.load(Ordering::SeqCst) {
            return Err("worker not exited after stage miss".to_string());
        }
        Ok(())
    }
}
