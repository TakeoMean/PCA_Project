import { useEffect } from 'react';
import {
  CATEGORY_LABELS,
  LEVEL_LABELS,
  STATUS_LABELS,
  assessmentFor,
  statusClass,
} from '../riskUtils';

export function PanelTitle({ title, detail, action }) {
  return <div className="panel-title"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{action}</div>;
}

export function FormField({ label, hint, className = '', children }) {
  return <label className={`form-field ${className}`}><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}

export function EmptyState({ title, detail }) {
  return <div className="empty-state"><span className="empty-mark">◌</span><strong>{title}</strong><span>{detail}</span></div>;
}

export function Severity({ level }) {
  const normalized = level || 'Unassessed';
  return <span className={`severity severity-${normalized.toLowerCase()}`}><i />{LEVEL_LABELS[normalized] || normalized}</span>;
}

export function StatusChip({ status }) {
  return <span className={`status-chip status-${statusClass(status)}`}>{STATUS_LABELS[status] || status}</span>;
}

export function MetricCard({ label, value, note, icon, tone = 'blue' }) {
  return <section className={`metric-card metric-${tone}`}><div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div><strong>{value}</strong><small>{note}</small></section>;
}

export function Modal({ title, subtitle, children, onClose, wide = false, actions }) {
  useEffect(() => {
    const close = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', close);
    document.body.classList.add('modal-open');
    return () => {
      document.removeEventListener('keydown', close);
      document.body.classList.remove('modal-open');
    };
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className={`modal-card ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button type="button" className="icon-button" aria-label="Fermer" onClick={onClose}>×</button></header>
        <div className="modal-body">{children}</div>
        {actions && <footer className="modal-actions">{actions}</footer>}
      </section>
    </div>
  );
}

export function RiskTable({ risks, onSelect, detailed = true }) {
  if (!risks.length) return <EmptyState title="Aucun risque" detail="Modifiez les filtres ou enregistrez un nouveau risque." />;
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead><tr><th>Risque</th>{detailed && <th>Département</th>}<th>Catégorie</th><th>Évaluation</th><th>Niveau</th>{detailed && <th>Statut</th>}{detailed && <th>Responsable</th>}</tr></thead>
        <tbody>{risks.map((risk) => (
          <tr key={risk.id || risk.code} className={onSelect ? 'clickable-row' : ''} onClick={() => onSelect?.(risk)}>
            <td><strong>{risk.code}</strong><span className="table-subline">{risk.name}</span></td>
            {detailed && <td>{risk.department || '—'}</td>}
            <td>{CATEGORY_LABELS[risk.category] || risk.category}</td>
            <td><span className="score-pill">{risk.score ?? '—'}/25</span><small className="table-subline">P{risk.probability || '—'} × I{risk.impact || '—'}</small></td>
            <td><Severity level={risk.level} /></td>
            {detailed && <td><StatusChip status={risk.status || 'Validated'} /></td>}
            {detailed && <td>{risk.owner || '—'}</td>}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export function RiskHeatmap({ risks, mode = 'current', onSelect }) {
  const cells = [];
  for (let impact = 5; impact >= 1; impact -= 1) {
    for (let probability = 1; probability <= 5; probability += 1) {
      const score = probability * impact;
      const level = score <= 4 ? 'low' : score <= 9 ? 'moderate' : score <= 16 ? 'high' : 'critical';
      const items = risks.filter((risk) => {
        const assessment = assessmentFor(risk, mode);
        return Number(assessment?.probability) === probability && Number(assessment?.impact) === impact;
      });
      cells.push(
        <div className={`matrix-cell matrix-${level}`} key={`${probability}-${impact}`}>
          <span className="matrix-score">{score}</span>
          <div className="matrix-risks">{items.map((risk) => <button type="button" key={risk.id} onClick={() => onSelect?.(risk)} title={risk.name}>{risk.code}</button>)}</div>
        </div>,
      );
    }
  }
  return (
    <div className="matrix-layout">
      <div className="matrix-y-label">Impact →</div>
      <div className="risk-matrix">{cells}</div>
      <div className="matrix-x-label">Probabilité →</div>
    </div>
  );
}

export function AlertList({ alerts, onRisk }) {
  if (!alerts.length) return <EmptyState title="Aucune alerte" detail="Les échéances SMCA sont à jour." />;
  return <div className="alert-list">{alerts.map((item, index) => (
    <button type="button" className={`alert-row alert-${item.severity.toLowerCase()}`} key={`${item.type}-${item.risk_id}-${index}`} onClick={() => item.risk_id && onRisk?.(item.risk_id)}>
      <span className="alert-dot" /><span><strong>{item.title}</strong><small>{item.detail}</small></span>{item.due_at && <time>{new Date(item.due_at).toLocaleDateString('fr-FR')}</time>}
    </button>
  ))}</div>;
}

