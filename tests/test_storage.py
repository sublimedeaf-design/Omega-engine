from omega.storage import input_fingerprint


def test_fingerprint_is_order_independent_and_sensitive():
    assert input_fingerprint({"b": 2, "a": 1}) == input_fingerprint({"a": 1, "b": 2})
    assert input_fingerprint({"a": 1}) != input_fingerprint({"a": 2})
