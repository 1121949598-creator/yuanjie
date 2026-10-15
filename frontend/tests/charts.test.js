import test from "node:test";
import assert from "node:assert/strict";
import { capabilityProfile, moduleRiskRows } from "../src/charts.js";

test("radar uses maximum observed impact and counts a tool once per axis", () => {
  const profile = capabilityProfile(
    [
      {
        id: "a",
        name: "a",
        capabilities: [
          { capability: "file_read", impact: 2 },
          { capability: "file_write", impact: 4 },
          { capability: "network_access", impact: 2 },
          { capability: "shell_execute", impact: null },
        ],
      },
    ],
    "success",
  );
  assert.equal(profile.axes[1].value, 4);
  assert.equal(profile.axes[1].tools.length, 1);
  assert.equal(profile.axes[0].value, 0);
  assert.equal(profile.axes[2].value, 2);
  assert.equal(profile.omitted, 1);
});
test("unavailable radar is unknown rather than five zero scores", () => {
  assert.ok(
    capabilityProfile([], "unavailable").axes.every((a) => a.value === null),
  );
});
test("risk bars preserve unavailable coverage and aggregate all Agent categories", () => {
  const rows = moduleRiskRows({
    findings: [
      { category: "tool_exposure", severity: "critical" },
      { category: "unresolved", severity: "medium" },
      { category: "agent_security", severity: "medium" },
    ],
    metadata: {
      scanners: {
        agent_security: { status: "partial" },
        license: { status: "unavailable" },
      },
    },
  });
  assert.equal(rows[2].total, 3);
  assert.equal(rows[2].counts.medium, 2);
  assert.equal(rows[1].status, "unavailable");
});
