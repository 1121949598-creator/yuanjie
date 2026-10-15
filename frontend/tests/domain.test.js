import test from "node:test";
import assert from "node:assert/strict";
import {
  coverageSummary,
  severityLabel,
  agentFindings,
  percent,
  summarizeRisk,
} from "../src/domain.js";

test("completed scans with unavailable license do not claim full coverage", () => {
  const result = {
    status: "completed",
    metadata: {
      scanners: {
        secret: { status: "success" },
        license: { status: "unavailable" },
        agent_security: { status: "success" },
      },
    },
  };
  assert.equal(coverageSummary(result).complete, false);
  assert.equal(coverageSummary(result).available, 2);
});
test("null license severity is not an information risk", () =>
  assert.equal(severityLabel(null), "不适用"));
test("all three agent finding categories appear together", () => {
  assert.equal(
    agentFindings([
      { category: "agent_security" },
      { category: "unresolved" },
      { category: "tool_exposure" },
      { category: "license" },
    ]).length,
    3,
  );
});
test("zero confidence stays zero and absent confidence is unknown", () => {
  assert.equal(percent(0), "0%");
  assert.equal(percent(null), "—");
});
test("no finding with unavailable coverage is not called safe", () => {
  assert.equal(
    summarizeRisk({ findings: [], metadata: { scanners: {} } }).label,
    "覆盖待补全",
  );
});
