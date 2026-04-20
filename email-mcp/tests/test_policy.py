import pytest

from app.policy.recipient_policy import RecipientPolicy


def test_allows_primary_domain():
    p = RecipientPolicy(["griddynamics.com"], allow_subdomains=True)
    p.ensure_allowed(["a@griddynamics.com"], [], [])


def test_allows_subdomain_when_enabled():
    p = RecipientPolicy(["griddynamics.com"], allow_subdomains=True)
    p.ensure_allowed(["a@mail.griddynamics.com"], [], [])


def test_rejects_subdomain_when_disabled():
    p = RecipientPolicy(["griddynamics.com"], allow_subdomains=False)
    with pytest.raises(PermissionError):
        p.ensure_allowed(["a@mail.griddynamics.com"], [], [])


def test_plus_addressing_still_allowlisted():
    p = RecipientPolicy(["griddynamics.com"], allow_subdomains=True)
    p.ensure_allowed(["a+b@griddynamics.com"], [], [])


def test_rejects_external():
    p = RecipientPolicy(["griddynamics.com"], allow_subdomains=True)
    with pytest.raises(PermissionError):
        p.ensure_allowed(["x@gmail.com"], [], [])


def test_invalid_email_raises():
    p = RecipientPolicy(["griddynamics.com"], allow_subdomains=True)
    bad = p.validate_recipients(["not-an-email"], [], [])
    assert bad
