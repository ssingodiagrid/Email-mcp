from __future__ import annotations

from dataclasses import dataclass

from email_validator import EmailNotValidError, validate_email


@dataclass(frozen=True)
class PolicyViolation:
    address: str
    reason: str


class RecipientPolicy:
    """Allowlist validation for To/Cc/Bcc."""

    def __init__(self, allowed_domains: list[str], *, allow_subdomains: bool = True) -> None:
        self._allowed = [d.lower().lstrip("@") for d in allowed_domains]
        self._allow_subdomains = allow_subdomains

    def normalize_address(self, raw: str) -> str:
        s = raw.strip()
        try:
            parsed = validate_email(s, check_deliverability=False)
        except EmailNotValidError as e:
            raise ValueError(f"Invalid email address: {raw!r} ({e})") from e
        return parsed.normalized

    def is_allowed(self, address: str) -> bool:
        normalized = self.normalize_address(address)
        _, _, domain = normalized.partition("@")
        domain = domain.lower()
        for allowed in self._allowed:
            if domain == allowed:
                return True
            if self._allow_subdomains and domain.endswith(f".{allowed}"):
                return True
        return False

    def validate_recipients(self, *lists: list[str]) -> list[PolicyViolation]:
        violations: list[PolicyViolation] = []
        for bucket in lists:
            for addr in bucket:
                try:
                    if not self.is_allowed(addr):
                        violations.append(
                            PolicyViolation(address=addr.strip(), reason="domain_not_allowlisted")
                        )
                except ValueError as e:
                    violations.append(PolicyViolation(address=addr.strip(), reason=str(e)))
        return violations

    def ensure_allowed(self, to: list[str], cc: list[str] | None = None, bcc: list[str] | None = None) -> None:
        cc = cc or []
        bcc = bcc or []
        bad = self.validate_recipients(to, cc, bcc)
        if bad:
            msg = "; ".join(f"{v.address}: {v.reason}" for v in bad)
            raise PermissionError(f"Recipient policy violation: {msg}")
