from ...external.process import ExternalScannerAdapter
from ..models import SecretEvidence


class TruffleHogAdapter(ExternalScannerAdapter[SecretEvidence]):
    name = "trufflehog"
