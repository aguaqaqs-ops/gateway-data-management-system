//! Kernel component probes compiled only under `#[cfg(test)]`.

#[cfg(test)]
mod support;

#[cfg(test)]
mod gil_00_python_thread;

#[cfg(test)]
mod gil_controller;

#[cfg(test)]
mod panic_matrix;

#[cfg(test)]
mod gil_probe;
