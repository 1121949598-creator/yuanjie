const OVERVIEW_KEYS = [
  "page", "page_size", "classification", "severity", "manual_review_required",
  "package_name", "license_expression", "file_path",
];

export class LicenseApiError extends Error {
  constructor(status, detail) {
    super(detail || "License results could not be loaded");
    this.name = "LicenseApiError";
    this.status = status;
  }
}

export function overviewParams(input = new URLSearchParams()) {
  const source = input instanceof URLSearchParams ? input : new URLSearchParams(input);
  const result = new URLSearchParams();
  for (const key of OVERVIEW_KEYS) {
    const value = source.get(key);
    if (value !== null && value.trim() !== "") result.set(key, value.trim());
  }
  return result;
}

export function overviewEndpoint(scanId, input) {
  const query = overviewParams(input).toString();
  const endpoint = `/api/scans/${encodeURIComponent(scanId)}/licenses`;
  return query ? `${endpoint}?${query}` : endpoint;
}

export function detailEndpoint(scanId, assessmentId) {
  return `/api/scans/${encodeURIComponent(scanId)}/licenses/${encodeURIComponent(assessmentId)}`;
}

async function requestJson(endpoint, fetchImpl = globalThis.fetch) {
  let response;
  try {
    response = await fetchImpl(endpoint, { method: "GET", headers: { Accept: "application/json" } });
  } catch {
    throw new LicenseApiError(0, "Network request failed");
  }
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) throw new LicenseApiError(response.status, payload.detail);
  return payload;
}

export function getLicenseOverview(scanId, params, fetchImpl) {
  return requestJson(overviewEndpoint(scanId, params), fetchImpl);
}

export function getLicenseDetail(scanId, assessmentId, fetchImpl) {
  return requestJson(detailEndpoint(scanId, assessmentId), fetchImpl);
}
