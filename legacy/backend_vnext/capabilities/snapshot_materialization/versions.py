from __future__ import annotations

from typing import Final

from ...contracts.versions import (
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SQL_PARSER_VERSION,
    TABLE_RULESET_VERSION,
)


SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION: Final = (
    "backend-vnext/snapshot-materialization/v1"
)
SNAPSHOT_DIGEST_CONTRACT_VERSION: Final = "backend-vnext/snapshot-digest/v1"
SOURCE_PACKAGE_CONTRACT_VERSION: Final = "backend-vnext/source-package/v1"
SOURCE_PACKAGE_ARTIFACT_CONTRACT_VERSION: Final = (
    "backend-vnext/source-package-artifact/v1"
)
SOURCE_PACKAGE_ARTIFACT_KIND: Final = "source-package"
SOURCE_PACKAGE_ENTRY_ARTIFACT_CONTRACT_VERSION: Final = (
    "backend-vnext/source-package-entry-artifact/v1"
)
SOURCE_PACKAGE_ENTRY_ARTIFACT_KIND: Final = "source-package-entry"
SQL_DUMP_SOURCE_CONTRACT_VERSION: Final = "backend-vnext/sql-dump-source/v1"
SQL_DUMP_PARSE_RESULT_SCHEMA_VERSION: Final = (
    "backend-vnext/sql-dump-parse-result/v1"
)
SNAPSHOT_SUMMARY_SCHEMA_VERSION: Final = "backend-vnext/snapshot-summary/v1"
SNAPSHOT_SCHEMA_VERSION: Final = "backend-vnext/snapshot/v1"
SNAPSHOT_TABLE_SET_SCHEMA_VERSION: Final = "backend-vnext/snapshot-table-set/v1"
SNAPSHOT_TABLE_DESCRIPTOR_SCHEMA_VERSION: Final = (
    "backend-vnext/snapshot-table-descriptor/v1"
)
SNAPSHOT_TABLE_COLUMN_SCHEMA_VERSION: Final = (
    "backend-vnext/snapshot-table-column/v1"
)
SNAPSHOT_MATERIALIZATION_INPUT_SCHEMA_VERSION: Final = (
    "backend-vnext/snapshot-materialization-input/v3"
)
FAST_ROW_DIGEST_VERSION: Final = "backend-vnext/fast-row/v1"
ROW_LAYOUT_DIGEST_VERSION: Final = "backend-vnext/row-layout/v1"
