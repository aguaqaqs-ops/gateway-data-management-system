"""Concrete process composition package for backend-owned worker roles.

The package initializer is deliberately side-effect free.  In particular, it must not import the
``operation_worker`` module before ``python -m gateway_backend.bootstrap.operation_worker`` has
asked ``runpy`` to execute that module as ``__main__``.
"""

__all__: list[str] = []
