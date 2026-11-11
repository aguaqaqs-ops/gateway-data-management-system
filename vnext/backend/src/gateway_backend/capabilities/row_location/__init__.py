"""Final-file row positions bound to the comparison identity owner."""
from .contracts import LOCATOR_SCHEMA, RowLocationResult
from .producer import identity_batches, prepare_row_locations, publish_row_locations

__all__ = ["LOCATOR_SCHEMA", "RowLocationResult", "identity_batches", "prepare_row_locations", "publish_row_locations"]
