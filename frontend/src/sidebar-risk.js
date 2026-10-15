import { agentFindings } from './domain.js';
import { relationCounts } from './component-security.js';

export function sidebarRiskCounts(scan, componentSecurity) {
  const findings = scan?.findings || [];
  const total = findings.length;
  return {
    workspace: total,
    overview: total,
    report: total,
    secrets: findings.filter(f => f.category === 'secret').length,
    licenses: findings.filter(f => f.category === 'license').length,
    agents: agentFindings(findings).length,
    // Mere inventory entries, capabilities and pending relation reviews are not risk findings.
    components: scan?.id && componentSecurity?.scan_id === scan.id
      ? relationCounts(componentSecurity).inconsistent : 0,
  };
}
