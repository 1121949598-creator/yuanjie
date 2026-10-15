from ...external.process import ExternalScannerAdapter
from ..models import SecretEvidence


class DetectSecretsAdapter(ExternalScannerAdapter[SecretEvidence]):
    name = "detect_secrets"
