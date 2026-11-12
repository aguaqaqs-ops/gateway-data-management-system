"""Stdlib host adapter for the application-owned processing-group document model."""
from __future__ import annotations

import importlib

import host_runtime_config

_configuration = importlib.import_module(host_runtime_config.configuration.__package__ + ".processing_group_config")
DeviceDirectory = _configuration.DeviceDirectory
DeviceDirectoryEntry = _configuration.DeviceDirectoryEntry
ProcessingGroupsConfig = _configuration.ProcessingGroupsConfig
EntryDeployment = _configuration.EntryDeployment
GroupDeployment = _configuration.GroupDeployment
GroupImages = _configuration.GroupImages
