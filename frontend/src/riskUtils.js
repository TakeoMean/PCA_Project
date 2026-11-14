export const LEVELS = ['Low', 'Moderate', 'High', 'Critical'];
export const CATEGORIES = ['Cybersecurity', 'Technical', 'Operational', 'Financial', 'Human', 'Environmental', 'Supplier'];
export const RISK_STATUSES = ['Draft', 'Validated', 'Under treatment', 'Accepted', 'Closed', 'Archived'];

export const LEVEL_LABELS = {
  Low: 'Faible',
  Moderate: 'Modéré',
  High: 'Élevé',
  Critical: 'Critique',
  Unassessed: 'Non évalué',
};

export const STATUS_LABELS = {
  Draft: 'Brouillon',
  Validated: 'Validé',
  'Under treatment': 'En traitement',
  Accepted: 'Accepté',
  Closed: 'Clos',
  Archived: 'Archivé',
  Proposed: 'Proposé',
  Approved: 'Approuvé',
  'In progress': 'En cours',
  Completed: 'Terminé',
  Cancelled: 'Annulé',
  Rejected: 'Rejeté',
  Planned: 'Planifié',
  Blocked: 'Bloqué',
  Open: 'Ouvert',
  Investigating: 'En analyse',
  Resolved: 'Résolu',
  Active: 'Actif',
  Inactive: 'Inactif',
  Implemented: 'Mis en œuvre',
  'Needs improvement': 'À améliorer',
  Normal: 'Normal',
  Warning: 'Alerte',
};

export const CATEGORY_LABELS = {
  Cybersecurity: 'Cybersécurité',
  Technical: 'Technique',
  Operational: 'Opérationnel',
  Financial: 'Financier',
  Human: 'Humain',
  Environmental: 'Environnemental',
  Supplier: 'Fournisseur',
};

export const PROBABILITY_LABELS = {
  1: 'Rare',
  2: 'Peu probable',
  3: 'Possible',
  4: 'Probable',
  5: 'Presque certain',
};

export const IMPACT_LABELS = {
  1: 'Négligeable',
  2: 'Mineur',
  3: 'Modéré',
  4: 'Majeur',
  5: 'Sévère',
};

export function riskLevel(score) {
  const numeric = Number(score);
  if (!numeric) return 'Unassessed';
  if (numeric <= 4) return 'Low';
  if (numeric <= 9) return 'Moderate';
  if (numeric <= 16) return 'High';
  return 'Critical';
}

export function assessmentFor(risk, mode = 'current') {
  if (!risk) return null;
  if (mode === 'inherent') return risk.inherent || risk.inherent_assessment || null;
  if (mode === 'residual') return risk.residual || risk.residual_assessment || null;
  return risk.probability
    ? { probability: risk.probability, impact: risk.impact, score: risk.score, level: risk.level }
    : risk.residual || risk.inherent || risk.residual_assessment || risk.inherent_assessment || null;
}

export function dateInput(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toISOString().slice(0, 10);
}

export function dateTimeInput(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function formatDate(value, includeTime = false) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return includeTime
    ? date.toLocaleString('fr-FR')
    : date.toLocaleDateString('fr-FR');
}

export function statusClass(value) {
  return (value || 'unknown').toLowerCase().replaceAll(' ', '-').replaceAll('é', 'e');
}

export function formObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

export function numberOrNull(value) {
  return value === '' || value === null || value === undefined ? null : Number(value);
}

export function isoOrNull(value) {
  return value ? new Date(value).toISOString() : null;
}

export function indicatorStatus(indicator) {
  if (indicator?.status) return indicator.status;
  if (!indicator) return 'Normal';
  if (indicator.direction === 'Below is bad') {
    if (indicator.current_value <= indicator.critical_threshold) return 'Critical';
    if (indicator.current_value <= indicator.warning_threshold) return 'Warning';
    return 'Normal';
  }
  if (indicator.current_value >= indicator.critical_threshold) return 'Critical';
  if (indicator.current_value >= indicator.warning_threshold) return 'Warning';
  return 'Normal';
}

