"""Load bounded host reservations only for startup seed and management acceptance."""

from pathlib import Path
from gateway_backend.processing_group_config import DeviceDirectory, ProcessingGroupsConfig


def reserved_directory(
    groups_file: Path, directory_file: Path, *, environment: str, group: str
) -> DeviceDirectory:
    groups = ProcessingGroupsConfig.load(groups_file)
    if groups.environment_id != environment or group not in {
        item.group_id for item in groups.groups
    }:
        raise ValueError("processing-group identity differs")
    directory = DeviceDirectory.load(
        directory_file, known_groups={item.group_id for item in groups.groups}
    )
    if directory.environment_id != environment:
        raise ValueError("device-directory environment differs")
    return directory
