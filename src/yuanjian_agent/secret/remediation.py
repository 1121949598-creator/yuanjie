from __future__ import annotations

from .schemas import SecretRemediationResponse


# Text advice only. No source writes, revocation requests or provider API calls.
_REMEDIATION: dict[str, tuple[str, tuple[str, ...]]] = {
    "private_key": ("Rotate or revoke the exposed private key", (
        "Rotate or revoke the affected private key and replace dependent credentials.",
        "Remove the credential from source code and distributed artifacts.",
        "Store the replacement in a secret manager or secure key store.",
        "If committed, investigate exposure and clean the version-control history.",
    )),
    "aws_access_key": ("Review and rotate affected AWS credentials", (
        "Rotate the related AWS credentials after confirming the affected identity.",
        "Review recent credential activity and granted permissions.",
        "Remove hardcoded access credentials from source code.",
        "Use IAM roles, environment injection or a secret manager.",
    )),
    "api_key": ("Rotate the exposed API key", (
        "Rotate or revoke the affected API key with its provider.",
        "Remove plaintext credentials from source code and artifacts.",
        "Inject the replacement through environment configuration or a secret manager.",
    )),
    "database_credential": ("Change the exposed database password", (
        "Change the affected database password and review account access.",
        "Remove plaintext credentials from hardcoded connection strings.",
        "Supply database authentication through a secure configuration system or secret manager.",
    )),
    "jwt": ("Review the exposed token", (
        "Confirm whether the token is still valid and what access it grants.",
        "If exposure is confirmed, revoke the token or rotate relevant keys as appropriate.",
        "Avoid committing long-lived tokens; use short lifetimes and secure runtime injection.",
    )),
    "password": ("Change the exposed password", (
        "Change the affected password and review account activity.",
        "Remove hardcoded passwords from source code.",
        "Inject authentication through secure configuration or a secret manager.",
    )),
    "token": ("Rotate or revoke the exposed token", (
        "Review the token's validity, scope and recent use.",
        "Rotate or revoke the affected token.",
        "Remove it from source code and use secure runtime injection.",
    )),
}
_FALLBACK = ("Review and replace the exposed credential", (
    "Confirm the credential type, affected system and exposure.",
    "Rotate or revoke it using the affected system's supported procedure.",
    "Remove it from source code and inject replacements through a secret manager.",
))


def remediation_for(secret_type: str) -> SecretRemediationResponse:
    title, steps = _REMEDIATION.get(secret_type, _FALLBACK)
    return SecretRemediationResponse(title=title, steps=list(steps))

