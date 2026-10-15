from __future__ import annotations

import html
import json
from pathlib import Path

from .models import ScanResult


def render_html_report(result: ScanResult) -> str:
    rows = []
    for finding in result.findings:
        location = finding.evidence[0].source_span if finding.evidence else None
        location_text = f"{location.path}:{location.start_line}" if location else "unknown"
        rationale = "<br>".join(html.escape(item) for item in finding.rationale)
        remediation = "<br>".join(html.escape(item) for item in finding.remediation)
        excerpt = html.escape(finding.evidence[0].masked_excerpt if finding.evidence else "")
        rows.append(
            "<tr>"
            f"<td>{html.escape(finding.severity.value)}</td>"
            f"<td>{html.escape(finding.category.value)}</td>"
            f"<td>{html.escape(finding.title)}</td>"
            f"<td>{html.escape(location_text)}</td>"
            f"<td><code>{excerpt}</code></td>"
            f"<td>{finding.confidence:.2f}</td>"
            f"<td>{rationale}</td>"
            f"<td>{remediation}</td>"
            "</tr>"
        )
    warnings = "".join(f"<li>{html.escape(item)}</li>" for item in result.warnings)
    comparison = html.escape(json.dumps(result.comparison, ensure_ascii=False)) if result.comparison else "None"
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>源界 Report</title>
<style>
body{{font-family:Arial,sans-serif;margin:32px;color:#172033}} h1,h2{{color:#111827}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border:1px solid #d9d9d9;padding:8px;vertical-align:top}}
th{{background:#17365d;color:white}} code{{background:#f3f4f6;padding:2px 4px}} .summary{{display:flex;gap:16px}}
.summary div{{border:1px solid #d9d9d9;padding:12px;min-width:110px}}
</style></head>
<body><h1>源界 Security Report</h1>
<p>Project: <strong>{html.escape(result.project_name)}</strong> | Scan: <code>{html.escape(result.id)}</code></p>
<div class="summary"><div>Total<br><strong>{result.summary.total_findings}</strong></div>
<div>Secrets<br><strong>{result.summary.secrets}</strong></div>
<div>Tool exposure<br><strong>{result.summary.tool_exposures}</strong></div>
<div>Unresolved<br><strong>{result.summary.unresolved}</strong></div></div>
<h2>Findings</h2><table><thead><tr><th>Severity</th><th>Category</th><th>Finding</th><th>Location</th><th>Masked evidence</th><th>Confidence</th><th>Rationale</th><th>Remediation</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>Comparison</h2><p>{comparison}</p><h2>Warnings</h2><ul>{warnings}</ul>
</body></html>"""


def write_report(result: ScanResult, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html_report(result), encoding="utf-8")
    return output
