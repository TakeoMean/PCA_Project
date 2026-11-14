import test from 'node:test';
import assert from 'node:assert/strict';

import {
  assessmentFor,
  dateInput,
  indicatorStatus,
  riskLevel,
} from '../src/riskUtils.js';

test('riskLevel follows the configured 5x5 thresholds', () => {
  assert.equal(riskLevel(4), 'Low');
  assert.equal(riskLevel(9), 'Moderate');
  assert.equal(riskLevel(16), 'High');
  assert.equal(riskLevel(25), 'Critical');
});

test('assessmentFor switches between inherent and residual exposure', () => {
  const risk = {
    probability: 3,
    impact: 4,
    score: 12,
    level: 'High',
    inherent: { probability: 4, impact: 5, score: 20, level: 'Critical' },
    residual: { probability: 2, impact: 2, score: 4, level: 'Low' },
  };
  assert.equal(assessmentFor(risk, 'current').score, 12);
  assert.equal(assessmentFor(risk, 'inherent').score, 20);
  assert.equal(assessmentFor(risk, 'residual').score, 4);
});

test('indicatorStatus handles thresholds in both directions', () => {
  assert.equal(indicatorStatus({ direction: 'Above is bad', current_value: 9, warning_threshold: 7, critical_threshold: 10 }), 'Warning');
  assert.equal(indicatorStatus({ direction: 'Above is bad', current_value: 11, warning_threshold: 7, critical_threshold: 10 }), 'Critical');
  assert.equal(indicatorStatus({ direction: 'Below is bad', current_value: 92, warning_threshold: 95, critical_threshold: 90 }), 'Warning');
});

test('dateInput returns an HTML date value', () => {
  assert.equal(dateInput('2026-11-14T10:30:00Z'), '2026-11-14');
  assert.equal(dateInput(null), '');
});

