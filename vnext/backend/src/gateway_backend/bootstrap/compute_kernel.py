"""Explicit process startup for the shared compute and Arrow thread pools."""

import pyarrow as pa
from gateway_compute._native import _init_kernel_native


def initialize_compute_kernel(threads: int) -> None:
    """Initialize one fixed process pool; conflicting later settings are refused."""
    _init_kernel_native(threads)
    pa.set_cpu_count(threads)
    pa.set_io_thread_count(threads)
