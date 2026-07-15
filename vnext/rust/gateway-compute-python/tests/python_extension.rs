#[test]
fn extension_is_built_by_maturin() {
    assert_eq!(
        gateway_compute_core::double_nullable_i64(&[Some(1)]),
        Ok(vec![Some(2)])
    );
}
