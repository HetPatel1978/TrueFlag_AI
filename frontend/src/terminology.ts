/** Presentation only. API keys, frozen scientific identifiers and decisions stay unchanged. */
export const TERMS = Object.freeze({
  alerts: 'Alerts & Cases',
  caseOverview: 'Case overview',
  assessment: 'Alert Risk Assessment',
  drivers: 'Key Risk Drivers',
  recommendation: 'Review Recommendation',
  factors: 'Contributing Risk Factors',
  investigation: 'Investigation',
  summary: 'Investigation Summary',
  evidence: 'Supporting Evidence',
  activity: 'Transaction Activity Analysis',
  sources: 'Evidence Source Details',
  processing: 'Processing Status',
  history: 'Activity History',
  regulatory: 'Regulatory Guidance',
  findings: 'AI-Assisted Findings',
  resolution: 'Case Resolution',
  advanced: 'Advanced model details',
  customer: 'Customer Profile',
  requestAssessment: 'Request assessment',
  requestSummary: 'Generate summary',
});

/** The 27 model input fields of the frozen feature contract (datarobot_provisional_v1). */
export const MODEL_FEATURES: readonly string[] = Object.freeze([
  'kycRiskScore',
  'income',
  'tenureMonths',
  'creditScore',
  'state',
  'nbrPurchases90d',
  'avgTxnSize90d',
  'totalSpend90d',
  'nbrDistinctMerch90d',
  'nbrMerchCredits90d',
  'nbrMerchCreditsRndDollarAmt90d',
  'totalMerchCred90d',
  'nbrMerchCreditsWoOffsettingPurch',
  'nbrPayments90d',
  'totalPaymentAmt90d',
  'overpaymentAmt90d',
  'overpaymentInd90d',
  'nbrCustReqRefunds90d',
  'totalRefundsToCust90d',
  'nbrPaymentsCashLike90d',
  'maxRevolveLine',
  'indOwnsHome',
  'nbrInquiries1y',
  'nbrCollections3y',
  'nbrWebLogins90d',
  'nbrPointRed90d',
  'PEP',
]);
export const FEATURE_LABELS: Readonly<Record<string, string>> = Object.freeze({
  kycRiskScore: 'Customer risk rating (KYC, 0–6)',
  income: 'Annual income',
  tenureMonths: 'Customer tenure (months)',
  creditScore: 'Credit score',
  state: 'Recorded state',
  nbrPurchases90d: 'Purchases · 90 days',
  avgTxnSize90d: 'Average transaction amount · 90 days',
  totalSpend90d: 'Total spending · 90 days',
  nbrDistinctMerch90d: 'Distinct merchants · 90 days',
  nbrMerchCredits90d: 'Merchant credits · 90 days',
  nbrMerchCreditsRndDollarAmt90d: 'Round-dollar merchant credits · 90 days',
  totalMerchCred90d: 'Merchant credit amount · 90 days',
  nbrMerchCreditsWoOffsettingPurch:
    'Merchant credits without offsetting purchases',
  nbrPayments90d: 'Payments · 90 days',
  totalPaymentAmt90d: 'Payment amount · 90 days',
  overpaymentAmt90d: 'Overpayment amount · 90 days',
  overpaymentInd90d: 'Overpayment indicator · 90 days',
  nbrCustReqRefunds90d: 'Customer refund requests · 90 days',
  totalRefundsToCust90d: 'Customer refund amount · 90 days',
  nbrPaymentsCashLike90d: 'Cash-like payments · 90 days',
  maxRevolveLine: 'Maximum revolving credit line',
  indOwnsHome: 'Home ownership',
  nbrInquiries1y: 'Credit inquiries · 1 year',
  nbrCollections3y: 'Collections · source period unconfirmed',
  nbrWebLogins90d: 'Online logins · 90 days',
  nbrPointRed90d: 'Points redemptions · 90 days',
  PEP: 'Politically exposed person (PEP)',
});

const LABELS: Readonly<Record<string, string>> = Object.freeze({
  pending: 'Pending',
  running: 'In progress',
  succeeded: 'Completed',
  abstained: 'Further evidence needed',
  failed: 'Failed',
  invalidated: 'No longer current',
  not_requested: 'Not assessed',
  retain_human_review: 'Continue analyst review',
  review_reduction_candidate: 'Review prioritization suggested',
  packet_ready: 'Ready for review',
  deterministic_evidence_only: 'Evidence-based analysis',
  source_numeric_reference_checks_passed:
    'Evidence and financial checks passed',
  complete_declared_window: 'Complete for the stated period',
  partial: 'Partial coverage',
  unavailable: 'Unavailable',
  observed_only: 'Available observations only',
  insufficient_evidence: 'Insufficient evidence',
  gross_observations: 'Recorded activity before settlement adjustments',
  count_totals: 'Transaction volume',
  incoming_outgoing: 'Incoming and outgoing activity',
  velocity: 'Transaction frequency',
  concentration: 'Counterparty concentration',
  credit: 'Incoming',
  debit: 'Outgoing',
  not_recorded: 'Not recorded',
  matches_declared_inputs: 'Consistent with declared alert information',
  synthetic_observations_only: 'Synthetic records for demonstration only',
  settlement_status_not_recorded: 'Settlement status is not available',
  sampling_metadata_not_recorded:
    'Coverage sampling information is not available',
  rf_inputs_not_transaction_derivations:
    'Assessment inputs are declared separately from these transactions',
  comparable_expected_activity: 'Comparable expected customer activity',
  curated_documents: 'Supporting documents',
  curated_documents_not_admitted: 'Supporting documents are not available',
  sampling_metadata: 'Coverage sampling information',
  settlement_status: 'Settlement status',
  deterministic_foundation_not_validated_ai_investigator:
    'Structured analysis; an AI investigator has not been activated',
  gross_observations_not_settled_cashflow:
    'Recorded activity does not establish settled cash flow',
  observations_include_all_authorized_times_calculations_use_requested_window:
    'Calculations use the selected period; references may include records outside it',
  no_external_or_regulatory_context:
    'External information and regulatory guidance have not been applied',
  human_semantic_review_required:
    'An analyst must review the meaning of these observations',
  no_money_laundering_violation_or_sar_conclusion:
    'No conclusion about money laundering, a regulatory violation or SAR filing is made',
  obtain_comparable_declared_activity_expectations:
    'Obtain the customer’s expected activity for comparison',
  review_authorized_source_observations: 'Review the supporting source records',
  obtain_complete_requested_window:
    'Obtain records covering the full selected period',
  contradictory_kyc_observations:
    'Customer profile records contain conflicting observations',
  processing_unavailable: 'Processing is temporarily unavailable',
  input_invalidated: 'Information changed; request a fresh summary',
  authorization_revoked: 'Access has changed',
  lease_expired: 'Processing was interrupted',
  execution_timeout: 'Processing exceeded its time limit',
  verification_failed: 'Evidence verification did not pass',
  invalid_provider_output:
    'The AI response did not match the required format, so no findings were accepted',
  provider_unavailable: 'The AI service was unavailable',
  provider_timeout: 'The AI service did not respond in time',
  resource_limit: 'Processing limit reached',
  worker_revoked: 'Processing service is unavailable',
});
export const displayLabel = (value: string) =>
  LABELS[value] ??
  value.replaceAll('_', ' ').replace(/^./, (s) => s.toUpperCase());
export const featureLabel = (value: string) =>
  FEATURE_LABELS[value] ?? value.replace(/([a-z])([A-Z])/g, '$1 $2');

/** Format decimal strings for reading without Number conversion, rounding or loss of scale. */
export function decimalMoney(value: string | null, currency: string): string {
  if (value === null) return 'Not available';
  if (!/^-?\d+(?:\.\d+)?$/.test(value)) return `${currency} ${value}`;
  const [whole, fraction] = value.split('.');
  return `${currency} ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}${fraction === undefined ? '' : '.' + fraction}`;
}
