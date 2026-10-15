import { reactive } from "vue";
import { api, encode } from "./api";
export const state = reactive({
  system: null,
  systemError: "",
  scan: null,
  componentSecurity: null,
  componentError: "",
  scanLoading: false,
  scanError: "",
  history: [],
  historyError: "",
});
let scanRequest = 0;
export function resetScanSession() {
  // Invalidate requests started before returning home so they cannot restore old results.
  ++scanRequest;
  state.scan = null;
  state.componentSecurity = null;
  state.componentError = "";
  state.scanError = "";
  state.scanLoading = false;
  try {
    localStorage.removeItem("yuanjian.lastScan");
  } catch {}
}
export async function loadSystem() {
  try {
    state.system = await api("/system");
    state.systemError = "";
  } catch (e) {
    state.system = null;
    state.systemError = e.message;
  }
}
export async function loadScan(id) {
  const request = ++scanRequest;
  state.scanLoading = true;
  state.scanError = "";
  state.scan = null;
  state.componentSecurity = null;
  state.componentError = "";
  try {
    const [reportResult, componentResult] = await Promise.allSettled([
      api(`/scans/${encode(id)}/report`),
      api(`/scans/${encode(id)}/component-security`),
    ]);
    if (reportResult.status === "rejected") throw reportResult.reason;
    const scan = reportResult.value;
    if (request === scanRequest) {
      state.componentSecurity =
        componentResult.status === "fulfilled" ? componentResult.value : null;
      state.componentError =
        componentResult.status === "rejected"
          ? componentResult.reason.message
          : "";
    }
    if (request === scanRequest) {
      state.scan = scan;
      try {
        localStorage.setItem("yuanjian.lastScan", id);
      } catch {}
    }
  } catch (e) {
    if (request === scanRequest) state.scanError = e.message;
  } finally {
    if (request === scanRequest) state.scanLoading = false;
  }
}
export async function loadHistory() {
  try {
    state.history = (await api("/scans?limit=100")).items;
    state.historyError = "";
  } catch (e) {
    state.historyError = e.message;
  }
}
