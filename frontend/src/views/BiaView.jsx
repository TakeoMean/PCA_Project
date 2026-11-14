import { useMemo, useState } from 'react';
import { EmptyState, FormField, PanelTitle } from '../components/Common';
import { formatDate, formObject, numberOrNull } from '../riskUtils';

export default function BiaView({ bia, activities, dependencies, canManage, busy, apiFetch, run }) {
  const [activityId, setActivityId] = useState('');

  const submitBia = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formObject(form);
    ['financial_impact', 'operational_impact', 'legal_impact', 'reputational_impact', 'rto_hours', 'rpo_hours', 'mtpd_hours'].forEach((key) => { payload[key] = Number(payload[key]); });
    return run(async () => {
      await apiFetch(`/api/activities/${activityId}/bia`, { method: 'POST', body: payload });
      form.reset();
      setActivityId('');
    }, 'Analyse d’impact enregistrée.');
  };

  const submitDependency = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formObject(form);
    payload.source_activity_id = Number(payload.source_activity_id);
    payload.target_activity_id = Number(payload.target_activity_id);
    payload.criticality = Number(payload.criticality);
    payload.recovery_order = numberOrNull(payload.recovery_order);
    return run(async () => {
      await apiFetch('/api/activity-dependencies', { method: 'POST', body: payload });
      form.reset();
    }, 'Dépendance ajoutée.');
  };

  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">BUSINESS IMPACT ANALYSIS</p><h1>Activités critiques et dépendances</h1><p className="subtle">Déterminez la criticité, la durée maximale d’interruption et les objectifs de reprise.</p></div></div>
      {canManage && <details className="panel form-panel">
        <summary className="form-summary"><span><strong>Réaliser une BIA</strong><small>Une nouvelle version est conservée à chaque évaluation.</small></span><span className="summary-plus">＋</span></summary>
        <form className="form-grid" onSubmit={submitBia}>
          <FormField label="Activité"><select required value={activityId} onChange={(event) => setActivityId(event.target.value)}><option value="" disabled>Choisir une activité</option>{activities.map((item) => <option value={item.id} key={item.id}>{item.department} · {item.name}</option>)}</select></FormField>
          {['financial', 'operational', 'legal', 'reputational'].map((dimension) => <FormField label={`Impact ${dimension === 'financial' ? 'financier' : dimension === 'operational' ? 'opérationnel' : dimension === 'legal' ? 'juridique' : 'réputationnel'}`} key={dimension}><select name={`${dimension}_impact`} defaultValue="3">{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value}/5</option>)}</select></FormField>)}
          <FormField label="MTPD (heures)" hint="Durée maximale tolérable d’interruption."><input name="mtpd_hours" type="number" min="1" max="17520" required /></FormField>
          <FormField label="RTO (heures)" hint="Objectif de délai de reprise."><input name="rto_hours" type="number" min="0" max="8760" required /></FormField>
          <FormField label="RPO (heures)" hint="Perte de données maximale admissible."><input name="rpo_hours" type="number" min="0" max="8760" required /></FormField>
          <FormField label="Dépendances" className="field-wide"><textarea name="dependencies" rows="2" placeholder="Technologies, fournisseurs, personnes, données, sites…" /></FormField>
          <FormField label="Exigences de reprise" className="field-wide"><textarea name="recovery_requirements" rows="2" placeholder="Ressources minimales, ordre de reprise et solutions de secours" /></FormField>
          <FormField label="Commentaires" className="field-wide"><textarea name="comments" rows="2" /></FormField>
          <div className="form-actions"><button className="button button-primary" disabled={busy || !activityId}>Enregistrer la BIA</button></div>
        </form>
      </details>}
      <section className="bia-grid">{bia.map((item) => <article className="panel bia-card" key={item.id}><div className="bia-card-head"><div><span>{item.department}</span><h2>{item.activity}</h2></div><strong className={`criticality criticality-${item.criticality}`}>{item.criticality}/5</strong></div><div className="recovery-metrics"><span><small>MTPD</small><strong>{item.mtpd_hours} h</strong></span><span><small>RTO</small><strong>{item.rto_hours} h</strong></span><span><small>RPO</small><strong>{item.rpo_hours} h</strong></span></div><div className="impact-bars">{[['Financier', item.financial_impact], ['Opérationnel', item.operational_impact], ['Juridique', item.legal_impact], ['Réputation', item.reputational_impact]].map(([label, value]) => <div key={label}><span>{label}</span><i><b style={{ width: `${value * 20}%` }} /></i><strong>{value}</strong></div>)}</div><p>{item.recovery_requirements || 'Exigences de reprise non documentées.'}</p><small>Évalué par {item.assessed_by} le {formatDate(item.assessed_at)} · version {item.assessment_count}</small></article>)}</section>
      {!bia.length && <section className="panel"><EmptyState title="Aucune BIA" detail="Évaluez au moins une activité pour définir les priorités de continuité." /></section>}

      <section className="panel dependency-panel">
        <PanelTitle title="Cartographie des dépendances" detail="Visualisez les activités qui conditionnent la reprise." />
        <DependencyGraph activities={activities} dependencies={dependencies} />
        {canManage && <form className="dependency-form" onSubmit={submitDependency}><select name="source_activity_id" required defaultValue=""><option value="" disabled>Activité dépendante</option>{activities.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><span>dépend de</span><select name="target_activity_id" required defaultValue=""><option value="" disabled>Activité requise</option>{activities.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><select name="dependency_type"><option>Technology</option><option>Supplier</option><option>People</option><option>Site</option><option>Data</option><option>Process</option><option>Utility</option><option>Other</option></select><select name="criticality" defaultValue="3">{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>Criticité {value}</option>)}</select><input name="recovery_order" type="number" min="1" placeholder="Ordre" /><input name="description" placeholder="Description" /><button className="button button-secondary" disabled={busy}>Ajouter</button></form>}
        <div className="dependency-list">{dependencies.map((item) => <article key={item.id}><span className={`criticality criticality-${item.criticality}`}>{item.criticality}</span><div><strong>{item.source_activity}</strong><small>dépend de {item.target_activity} · {item.dependency_type}</small><p>{item.description}</p></div>{canManage && <button className="text-button danger-text" onClick={() => run(() => apiFetch(`/api/activity-dependencies/${item.id}`, { method: 'DELETE' }), 'Dépendance supprimée.')}>Supprimer</button>}</article>)}</div>
      </section>
    </>
  );
}

function DependencyGraph({ activities, dependencies }) {
  const nodes = useMemo(() => {
    const used = new Set(dependencies.flatMap((item) => [item.source_activity_id, item.target_activity_id]));
    return activities.filter((item) => used.has(item.id));
  }, [activities, dependencies]);
  if (!nodes.length) return <EmptyState title="Aucune dépendance structurée" detail="Ajoutez un lien entre deux activités pour construire la carte." />;
  const width = 760;
  const height = 360;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.36;
  const positions = new Map(nodes.map((node, index) => [node.id, {
    x: centerX + radius * Math.cos((index / nodes.length) * Math.PI * 2 - Math.PI / 2),
    y: centerY + radius * Math.sin((index / nodes.length) * Math.PI * 2 - Math.PI / 2),
  }]));
  return <div className="dependency-graph"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Graphe des dépendances"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#8da2b5" /></marker></defs>{dependencies.map((item) => { const start = positions.get(item.source_activity_id); const end = positions.get(item.target_activity_id); if (!start || !end) return null; return <g key={item.id}><line x1={start.x} y1={start.y} x2={end.x} y2={end.y} className={`dependency-line dependency-line-${item.criticality}`} markerEnd="url(#arrow)" /><text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - 5}>{item.dependency_type}</text></g>; })}{nodes.map((node) => { const point = positions.get(node.id); return <g className="dependency-node" key={node.id}><circle cx={point.x} cy={point.y} r="39" /><text x={point.x} y={point.y - 4}>{node.name.slice(0, 18)}</text><text className="department-label" x={point.x} y={point.y + 12}>{node.department}</text></g>; })}</svg></div>;
}

