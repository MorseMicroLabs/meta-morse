import pytest

from dsup.checks import Checks

pytestmark = [pytest.mark.host, pytest.mark.selftest]


def test_failures_are_collected_and_do_not_stop_the_test():
    c = Checks()
    c.eq("a", 1, 1)
    c.eq("b", 1, 2)
    c.ok("c", False)
    c.le("d", 2, 3)
    assert c.count == 4
    assert len(c.failures) == 3
    assert "b: expected '1', got '2'" in c.failures[0]


def test_le_and_ge_accept_numbers_given_as_text_and_reject_garbage():
    c = Checks()
    assert c.le("x", 15, "12.9")
    assert c.ge("y", 1, "3")
    assert not c.le("z", 15, "")
    assert not c.ge("w", 1, None)


def test_has_and_lacks_use_regular_expressions_per_line():
    c = Checks()
    text = "first line\nsecond: name owner changed\n"
    assert c.has("h", text, r"^second: name owner")
    assert not c.lacks("l", text, "name owner changed")
    assert "second: name owner changed" in c.failures[0]    # the offending line is quoted


def test_count_eq_counts_matching_lines():
    c = Checks()
    assert c.count_eq("two", 2, "a CreateInterface\nb\nc CreateInterface\n", "CreateInterface")
    assert not c.count_eq("one", 1, "a CreateInterface\nc CreateInterface\n", "CreateInterface")


def test_secrets_are_redacted_in_the_log():
    c = Checks(redact=lambda t: t.replace("secret", "****"))
    c.info("password is secret")
    c.eq("key", "secret", "other")
    assert "secret" not in c.render()
    assert "secret" not in c.failure_text()
