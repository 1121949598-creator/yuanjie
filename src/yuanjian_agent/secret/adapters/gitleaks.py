from ...external.process import ExternalScannerAdapter
from ..models import SecretEvidence


class GitleaksAdapter(ExternalScannerAdapter[SecretEvidence]):
    name = "gitleaks"
