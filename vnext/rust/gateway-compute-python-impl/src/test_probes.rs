//! Test-only panic injection for adapter segment fault matrix (feature `test-probes`).

use std::cell::Cell;

thread_local! {
    static PANIC_STAGE: Cell<u8> = const { Cell::new(PanicStage::None as u8) };
}

/// Adapter segment where a deliberate panic may be injected during tests.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum PanicStage {
    None = 0,
    Import = 1,
    Compute = 2,
    Export = 3,
}

/// Set the adapter segment that should panic on the next native call (test only).
pub fn set_panic_stage(stage: PanicStage) {
    PANIC_STAGE.with(|cell| cell.set(stage as u8));
}

/// Clear any pending panic injection (test only).
pub fn clear_panic_stage() {
    PANIC_STAGE.with(|cell| cell.set(PanicStage::None as u8));
}

pub(crate) fn maybe_panic(stage: PanicStage) {
    let active = PANIC_STAGE.with(|cell| cell.get());
    if active == stage as u8 {
        #[allow(clippy::panic)]
        {
            panic!("deliberate test panic at {stage:?}");
        }
    }
}
