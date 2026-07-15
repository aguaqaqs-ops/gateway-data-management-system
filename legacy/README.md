# Legacy Oracle

`backend_vnext/` is frozen legacy source retained only for oracle behavior,
fixtures, golden outputs, digests, benchmarks, and manual reference.

Do not add new product behavior here. New code under `vnext/` must not import
`legacy` or `backend_vnext`. To run an explicitly selected legacy command, set
`PYTHONPATH=$PWD/legacy` and use its separately recorded environment.
