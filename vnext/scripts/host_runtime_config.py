"""Load stdlib deployment adapters without bootstrapping the HTTP application."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

# The ordinary backend package exports create_app and imports the application.
# This standalone host tool loads only its two stdlib adapter modules, under a
# private namespace, preserving the application's established import order.
_NAMESPACE = "_gateway_host_deployment"
package = ModuleType(_NAMESPACE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "backend/src/gateway_backend")]
sys.modules[_NAMESPACE] = package
configuration = importlib.import_module(_NAMESPACE + ".deployment_config")
preflight = importlib.import_module(_NAMESPACE + ".runtime_preflight")
DeploymentConfig = configuration.DeploymentConfig
RuntimePreflight = preflight.RuntimePreflight
check_host = preflight.check_host
initialize_host = preflight.initialize_host
mounts = preflight.mounts
