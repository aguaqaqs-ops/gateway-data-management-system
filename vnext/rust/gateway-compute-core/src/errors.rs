use arrow_schema::ArrowError;
use gateway_shared_kernel::{CanonicalEncodingError, canonicalize_jcs};
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ComputeFailureCode {
    ComputeRequestSchemaInvalid,
    ComputeBoundaryVersionUnsupported,
    ComputeCanonicalVersionUnsupported,
    ComputeArrowMappingVersionUnsupported,
    ArrowStreamImportFailed,
    ArrowTypeUnsupported,
    ArrowSchemaMismatch,
    CanonicalValueInvalid,
    RowHashComputeFailed,
    ResourceLimitExceeded,
    ArrowStreamExportFailed,
    NativePanic,
}

impl ComputeFailureCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ComputeRequestSchemaInvalid => "COMPUTE_REQUEST_SCHEMA_INVALID",
            Self::ComputeBoundaryVersionUnsupported => "COMPUTE_BOUNDARY_VERSION_UNSUPPORTED",
            Self::ComputeCanonicalVersionUnsupported => "COMPUTE_CANONICAL_VERSION_UNSUPPORTED",
            Self::ComputeArrowMappingVersionUnsupported => {
                "COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED"
            }
            Self::ArrowStreamImportFailed => "ARROW_STREAM_IMPORT_FAILED",
            Self::ArrowTypeUnsupported => "ARROW_TYPE_UNSUPPORTED",
            Self::ArrowSchemaMismatch => "ARROW_SCHEMA_MISMATCH",
            Self::CanonicalValueInvalid => "CANONICAL_VALUE_INVALID",
            Self::RowHashComputeFailed => "ROW_HASH_COMPUTE_FAILED",
            Self::ResourceLimitExceeded => "RESOURCE_LIMIT_EXCEEDED",
            Self::ArrowStreamExportFailed => "ARROW_STREAM_EXPORT_FAILED",
            Self::NativePanic => "NATIVE_PANIC",
        }
    }

    pub const fn message(self) -> &'static str {
        match self {
            Self::ComputeRequestSchemaInvalid => "compute request schema is invalid",
            Self::ComputeBoundaryVersionUnsupported => "compute boundary version is unsupported",
            Self::ComputeCanonicalVersionUnsupported => "canonical encoding version is unsupported",
            Self::ComputeArrowMappingVersionUnsupported => "Arrow mapping version is unsupported",
            Self::ArrowStreamImportFailed => "Arrow stream import failed",
            Self::ArrowTypeUnsupported => "Arrow type is unsupported",
            Self::ArrowSchemaMismatch => "input Arrow schema does not match declared fields",
            Self::CanonicalValueInvalid => "canonical value is invalid",
            Self::RowHashComputeFailed => "canonical row hash computation failed",
            Self::ResourceLimitExceeded => "compute resource limit exceeded",
            Self::ArrowStreamExportFailed => "Arrow stream export failed",
            Self::NativePanic => "native compute panicked",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ComputeFailure {
    pub code: ComputeFailureCode,
}

impl ComputeFailure {
    pub fn new(code: ComputeFailureCode) -> Self {
        Self { code }
    }

    pub fn to_envelope_jcs(&self) -> Result<Vec<u8>, ComputeFailure> {
        let envelope = FailureEnvelope {
            code: self.code.as_str().to_string(),
            message: self.code.message().to_string(),
        };
        let json = serde_json::to_vec(&envelope)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
        canonicalize_jcs(&json)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))
    }
}

impl From<CanonicalEncodingError> for ComputeFailure {
    fn from(_: CanonicalEncodingError) -> Self {
        Self::new(ComputeFailureCode::CanonicalValueInvalid)
    }
}

impl From<ArrowError> for ComputeFailure {
    fn from(_: ArrowError) -> Self {
        Self::new(ComputeFailureCode::ArrowStreamImportFailed)
    }
}

#[derive(Debug, Serialize)]
struct FailureEnvelope {
    code: String,
    message: String,
}

#[cfg(test)]
mod tests {
    use super::{ComputeFailure, ComputeFailureCode};

    #[test]
    fn failure_has_only_owning_fields() -> Result<(), String> {
        let failure = ComputeFailure::new(ComputeFailureCode::ArrowSchemaMismatch);
        let wire = failure
            .to_envelope_jcs()
            .map_err(|error| format!("{error:?}"))?;
        let text = String::from_utf8(wire).map_err(|error| error.to_string())?;
        assert!(text.contains("ARROW_SCHEMA_MISMATCH"));
        assert!(text.contains("\"message\":"));
        assert!(!text.contains("contract_binding"));
        Ok(())
    }
}
