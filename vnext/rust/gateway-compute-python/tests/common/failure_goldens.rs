//! Independent hardcoded failure JCS goldens for the v2 minimal failure contract.

use gateway_compute_core::ComputeFailureCode;

pub fn golden_envelope(code: ComputeFailureCode) -> &'static [u8] {
    match code {
        ComputeFailureCode::ComputeRequestSchemaInvalid => {
            br#"{"code":"COMPUTE_REQUEST_SCHEMA_INVALID","message":"compute request schema is invalid"}"#
        }
        ComputeFailureCode::ComputeBoundaryVersionUnsupported => {
            br#"{"code":"COMPUTE_BOUNDARY_VERSION_UNSUPPORTED","message":"compute boundary version is unsupported"}"#
        }
        ComputeFailureCode::ComputeCanonicalVersionUnsupported => {
            br#"{"code":"COMPUTE_CANONICAL_VERSION_UNSUPPORTED","message":"canonical encoding version is unsupported"}"#
        }
        ComputeFailureCode::ComputeArrowMappingVersionUnsupported => {
            br#"{"code":"COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED","message":"Arrow mapping version is unsupported"}"#
        }
        ComputeFailureCode::ArrowStreamImportFailed => {
            br#"{"code":"ARROW_STREAM_IMPORT_FAILED","message":"Arrow stream import failed"}"#
        }
        ComputeFailureCode::ArrowTypeUnsupported => {
            br#"{"code":"ARROW_TYPE_UNSUPPORTED","message":"Arrow type is unsupported"}"#
        }
        ComputeFailureCode::ArrowSchemaMismatch => {
            br#"{"code":"ARROW_SCHEMA_MISMATCH","message":"input Arrow schema does not match declared fields"}"#
        }
        ComputeFailureCode::CanonicalValueInvalid => {
            br#"{"code":"CANONICAL_VALUE_INVALID","message":"canonical value is invalid"}"#
        }
        ComputeFailureCode::RowHashComputeFailed => {
            br#"{"code":"ROW_HASH_COMPUTE_FAILED","message":"canonical row hash computation failed"}"#
        }
        ComputeFailureCode::ResourceLimitExceeded => {
            br#"{"code":"RESOURCE_LIMIT_EXCEEDED","message":"compute resource limit exceeded"}"#
        }
        ComputeFailureCode::ArrowStreamExportFailed => {
            br#"{"code":"ARROW_STREAM_EXPORT_FAILED","message":"Arrow stream export failed"}"#
        }
        ComputeFailureCode::NativePanic => {
            br#"{"code":"NATIVE_PANIC","message":"native compute panicked"}"#
        }
    }
}

pub fn golden_exception_type(code: ComputeFailureCode) -> &'static str {
    match code {
        ComputeFailureCode::CanonicalValueInvalid => "CanonicalValueError",
        ComputeFailureCode::RowHashComputeFailed | ComputeFailureCode::NativePanic => {
            "ComputeError"
        }
        ComputeFailureCode::ResourceLimitExceeded => "ResourceLimitError",
        _ => "ComputeRequestError",
    }
}
