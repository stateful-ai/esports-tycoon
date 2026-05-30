"""Smoke tests for esports_tycoon.cast_lock.spec."""

from esports_tycoon.cast_lock.spec import load_save, validate_save

def test_load_save():
    save_data = load_save()
    assert isinstance(save_data, dict)
    assert "players" in save_data
    assert "clash_pairs" in save_data
    assert "rivals" in save_data

def test_validate_save():
    save_data = load_save()
    result = validate_save(save_data)
    assert result.ok, f"Validation failed: {result.failures}"
