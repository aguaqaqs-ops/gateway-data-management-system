//! Strict JSON object loader rejecting duplicates and non-JSON constants (test-only).

use std::fmt;

use serde::de::{self, DeserializeSeed, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StrictJsonError {
    DuplicateMember(String),
    NonJsonConstant(String),
    NotObject,
    TrailingContent,
    InvalidJson(String),
}

impl fmt::Display for StrictJsonError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::DuplicateMember(key) => write!(f, "duplicate JSON member {key:?}"),
            Self::NonJsonConstant(name) => write!(f, "non-JSON constant {name:?} is not allowed"),
            Self::NotObject => f.write_str("JSON document must be an object"),
            Self::TrailingContent => f.write_str("trailing JSON content after document end"),
            Self::InvalidJson(message) => write!(f, "invalid JSON: {message}"),
        }
    }
}

impl std::error::Error for StrictJsonError {}

/// Parse a JSON document that must be a single object without duplicate keys at any depth.
pub fn loads_object_rejecting_duplicates(
    text: &str,
) -> Result<serde_json::Map<String, Value>, StrictJsonError> {
    let mut de = serde_json::Deserializer::from_str(text);
    let value = StrictValueVisitor
        .deserialize(&mut de)
        .map_err(map_deserializer_error)?;
    de.end().map_err(|error| {
        let message = error.to_string();
        if message.contains("trailing") {
            StrictJsonError::TrailingContent
        } else {
            StrictJsonError::InvalidJson(message)
        }
    })?;
    match value {
        Value::Object(map) => Ok(map),
        _ => Err(StrictJsonError::NotObject),
    }
}

struct StrictValueVisitor;

impl<'de> DeserializeSeed<'de> for StrictValueVisitor {
    type Value = Value;

    fn deserialize<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(self)
    }
}

impl<'de> Visitor<'de> for StrictValueVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value")
    }

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Bool(value))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Number(value.into()))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Number(value.into()))
    }

    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        if value.is_nan() {
            return Err(de::Error::custom("non-JSON constant 'NaN' is not allowed"));
        }
        if value.is_infinite() {
            let name = if value.is_sign_positive() {
                "Infinity"
            } else {
                "-Infinity"
            };
            return Err(de::Error::custom(format!(
                "non-JSON constant '{name}' is not allowed"
            )));
        }
        serde_json::Number::from_f64(value)
            .map(Value::Number)
            .ok_or_else(|| de::Error::custom("number is not JSON-representable"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::String(value.to_string()))
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::String(value))
    }

    fn visit_none<E>(self) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Null)
    }

    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        StrictValueVisitor.deserialize(deserializer)
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Null)
    }

    fn visit_seq<A>(self, mut access: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut items = Vec::new();
        while let Some(value) = access.next_element_seed(StrictValueVisitor)? {
            items.push(value);
        }
        Ok(Value::Array(items))
    }

    fn visit_map<A>(self, mut access: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut map = serde_json::Map::new();
        while let Some(key) = access.next_key::<String>()? {
            if map.contains_key(&key) {
                return Err(de::Error::custom(format!("duplicate JSON member '{key}'")));
            }
            let value = access.next_value_seed(StrictValueVisitor)?;
            map.insert(key, value);
        }
        Ok(Value::Object(map))
    }
}

fn map_deserializer_error(error: serde_json::Error) -> StrictJsonError {
    let message = error.to_string();
    if message.contains("duplicate JSON member")
        && let Some(key) = message.split('\'').nth(1)
    {
        return StrictJsonError::DuplicateMember(key.to_string());
    }
    if message.contains("non-JSON constant")
        && let Some(name) = message.split('\'').nth(1)
    {
        return StrictJsonError::NonJsonConstant(name.to_string());
    }
    StrictJsonError::InvalidJson(message)
}

#[cfg(test)]
mod tests {
    use super::{StrictJsonError, loads_object_rejecting_duplicates};

    #[test]
    fn rejects_top_level_duplicate() -> Result<(), String> {
        match loads_object_rejecting_duplicates(r#"{"a":1,"a":2}"#) {
            Err(StrictJsonError::DuplicateMember(key)) if key == "a" => Ok(()),
            other => Err(format!("expected duplicate a, got {other:?}")),
        }
    }

    #[test]
    fn rejects_nested_duplicate() -> Result<(), String> {
        let text = r#"{"contract_binding":{"contract_id":"x","contract_id":"y"}}"#;
        match loads_object_rejecting_duplicates(text) {
            Err(StrictJsonError::DuplicateMember(key)) if key == "contract_id" => Ok(()),
            other => Err(format!("expected nested duplicate, got {other:?}")),
        }
    }

    #[test]
    fn rejects_trailing_json() -> Result<(), String> {
        match loads_object_rejecting_duplicates(r#"{"a":1}{"b":2}"#) {
            Err(StrictJsonError::TrailingContent) => Ok(()),
            Err(StrictJsonError::InvalidJson(message)) if message.contains("trailing") => Ok(()),
            other => Err(format!("expected trailing content, got {other:?}")),
        }
    }
}
