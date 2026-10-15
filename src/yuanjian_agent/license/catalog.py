"""源界's small engineering review catalog, not legal advice.

Authored locally; no ScanCode database or ORT classification file is vendored.
Unlisted valid SPDX identifiers deliberately remain unknown.
"""
from types import MappingProxyType


CATALOG_VERSION = "1"
LICENSE_CATEGORIES = MappingProxyType({
    **dict.fromkeys(("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "Zlib"), "permissive"),
    **dict.fromkeys(("MPL-2.0", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
                     "LGPL-3.0-or-later", "EPL-2.0", "CDDL-1.0"), "weak_copyleft"),
    **dict.fromkeys(("GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later"), "strong_copyleft"),
    **dict.fromkeys(("AGPL-3.0-only", "AGPL-3.0-or-later"), "network_copyleft"),
})

CATEGORY_RANK = {"permissive": 0, "unknown": 1, "weak_copyleft": 2,
                 "strong_copyleft": 3, "network_copyleft": 4}
