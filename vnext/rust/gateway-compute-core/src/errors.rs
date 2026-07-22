use arrow_schema::ArrowError;
use gateway_shared_kernel::{CanonicalEncodingError, canonicalize_jcs};
use serde::Serialize;

use crate::contract::{CONTRACT_ID, FAILURE_SCHEMA_VERSION, SEMANTIC_VERSION};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ComputeFailureCode {
    ComputeRequestSchemaInvalid,
    ComputeContractVersionUnsupported,
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
            Self::ComputeContractVersionUnsupported => "COMPUTE_CONTRACT_VERSION_UNSUPPORTED",
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

    pub const fn stage(self) -> &'static str {
        match self {
            Self::ComputeRequestSchemaInvalid
            | Self::ComputeContractVersionUnsupported
            | Self::ComputeCanonicalVersionUnsupported
            | Self::ComputeArrowMappingVersionUnsupported => "request",
            Self::ArrowStreamImportFailed => "arrow-import",
            Self::ArrowTypeUnsupported | Self::ArrowSchemaMismatch => "schema",
            Self::CanonicalValueInvalid => "canonicalize",
            Self::RowHashComputeFailed | Self::ResourceLimitExceeded | Self::NativePanic => {
                "compute"
            }
            Self::ArrowStreamExportFailed => "arrow-export",
        }
    }

    pub const fn effect(self) -> &'static str {
        "NONE"
    }

    pub const fn retry_class(self) -> &'static str {
        match self {
            Self::ResourceLimitExceeded | Self::NativePanic => "SAFE_WITH_POLICY",
            _ => "NEVER",
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
            failure_schema_version: FAILURE_SCHEMA_VERSION,
            contract_binding: ContractBinding {
                contract_id: CONTRACT_ID.to_string(),
                semantic_version: SEMANTIC_VERSION.to_string(),
            },
            code: self.code.as_str().to_string(),
            stage: self.code.stage().to_string(),
            effect: self.code.effect().to_string(),
            retry_class: self.code.retry_class().to_string(),
            diagnostics: Vec::<String>::new(),
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
    failure_schema_version: u32,
    contract_binding: ContractBinding,
    code: String,
    stage: String,
    effect: String,
    retry_class: String,
    diagnostics: Vec<String>,
}

#[derive(Debug, Serialize)]
struct ContractBinding {
    contract_id: String,
    semantic_version: String,
}

#[cfg(test)]
mod tests {
    use super::{ComputeFailure, ComputeFailureCode};

    #[test]
    fn failure_envelope_has_empty_diagnostics() -> Result<(), String> {
        let failure = ComputeFailure::new(ComputeFailureCode::ArrowSchemaMismatch);
        let wire = failure
            .to_envelope_jcs()
            .map_err(|error| format!("{error:?}"))?;
        let text = String::from_utf8(wire).map_err(|error| error.to_string())?;
        assert!(text.contains("\"diagnostics\":[]"));
        assert!(text.contains("ARROW_SCHEMA_MISMATCH"));
        Ok(())
    }
}
