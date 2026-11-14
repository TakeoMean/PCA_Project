import { useEffect, useMemo, useState } from 'react';
import { FormField, PanelTitle } from '../components/Common';
import { dateInput } from '../riskUtils';

const EMPTY_SCOPE = {
  name: '', description: '', objectives: '', exclusions: '', stakeholders: '', status: 'Draft', review_date: '', acceptance_threshold: 9,
};

export default function SmcaView({ scope, methodology, bia, risks, controls, treatments, threats, canEdit, busy, run, apiFetch }) {
  const [form, setForm] = useState(EMPTY_SCOPE);
  useEffect(() => {
    setForm(scope ? { ...EMPTY_SCOPE, ...scope, review_date: dateInput(scope.review_date) } : EMPTY_SCOPE);
  }, [scope]);

  const steps = useMemo(() => [
    { title: '1. Contexte et périmètre', detail: 'Objectifs, parties intéressées et exclusions.', done: Boolean(scope?.name && scope?.description) },
    { title: '2. Analyse d’impact (BIA)', detail: 'Criticité, MTPD, RTO, RPO et dépendances.', done: bia.length > 0 },
    { title: '3. Identification', detail: 'Menaces, vulnérabilités, causes et conséquences.', done: risks.length > 0 },
    { title: '4. Évaluation et cartographie', detail: 'Probabilité × impact, inhérent et résiduel.', done: risks.some((risk) => risk.inherent_assessment) },
    { title: '5. Maîtrise et traitement', detail: 'Contrôles, plans, actions et validation séparée.', done: controls.length > 0 && treatments.length > 0 },
    { title: '6. Surveillance et amélioration', detail: 'KRI, incidents, revues et enseignements.', done: risks.some((risk) => risk.residual_assessment || risk.review_date) },
  ], [scope, bia, risks, controls, treatments]);

  const submit = (event) => {
    event.preventDefault();
    return run(
      () => apiFetch('/api/smca/scope', { method: 'PUT', body: { ...form, acceptance_threshold: Number(form.acceptance_threshold), review_date: form.review_date ? new Date(form.review_date).toISOString() : null } }),
      'Périmètre SMCA enregistré.',
    );
  };

  const submitThreat = (event) => {
    event.preventDefault();
    const threatForm = event.currentTarget;
    const payload = Object.fromEntries(new FormData(threatForm).entries());
    payload.default_probability = Number(payload.default_probability);
    return run(async () => {
      await apiFetch('/api/threat-library', { method: 'POST', body: payload });
      threatForm.reset();
    }, 'Scénario de menace ajouté.');
  };

  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">ISO 22301 · PDCA</p><h1>Parcours SMCA</h1><p className="subtle">Un processus traçable depuis le contexte jusqu’à l’amélioration continue.</p></div><span className="completion-badge">{steps.filter((step) => step.done).length}/{steps.length} étapes renseignées</span></div>
      <section className="process-grid">{steps.map((step) => <article className={`panel process-step ${step.done ? 'process-done' : ''}`} key={step.title}><span>{step.done ? '✓' : '○'}</span><div><h2>{step.title}</h2><p>{step.detail}</p></div></article>)}</section>
      <div className="two-column-layout">
        <section className="panel form-panel always-open">
          <PanelTitle title="Périmètre du SMCA" detail="Définissez ce que couvre le système de management." />
          <form className="form-grid" onSubmit={submit}>
            <FormField label="Nom du périmètre"><input required minLength="3" disabled={!canEdit} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></FormField>
            <FormField label="Statut"><select disabled={!canEdit} value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value="Draft">Brouillon</option><option value="Under review">En revue</option><option value="Approved">Approuvé</option></select></FormField>
            <FormField label="Seuil d’acceptation" hint="Score maximal accepté sans traitement renforcé."><input type="number" min="1" max="25" disabled={!canEdit} value={form.acceptance_threshold} onChange={(event) => setForm({ ...form, acceptance_threshold: event.target.value })} /></FormField>
            <FormField label="Description" className="field-wide"><textarea required minLength="10" rows="4" disabled={!canEdit} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></FormField>
            <FormField label="Objectifs" className="field-wide"><textarea rows="3" disabled={!canEdit} value={form.objectives || ''} onChange={(event) => setForm({ ...form, objectives: event.target.value })} /></FormField>
            <FormField label="Parties intéressées" className="field-wide"><textarea rows="3" disabled={!canEdit} value={form.stakeholders || ''} onChange={(event) => setForm({ ...form, stakeholders: event.target.value })} /></FormField>
            <FormField label="Exclusions" className="field-wide"><textarea rows="2" disabled={!canEdit} value={form.exclusions || ''} onChange={(event) => setForm({ ...form, exclusions: event.target.value })} /></FormField>
            <FormField label="Prochaine revue"><input type="date" disabled={!canEdit} value={form.review_date} onChange={(event) => setForm({ ...form, review_date: event.target.value })} /></FormField>
            {canEdit && <div className="form-actions"><button className="button button-primary" disabled={busy}>Enregistrer le périmètre</button></div>}
          </form>
        </section>
        <section className="panel methodology-panel">
          <PanelTitle title="Méthode d’évaluation" detail={methodology?.formula || 'Probabilité × Impact'} />
          <div className="scale-list"><h3>Probabilité</h3>{methodology?.probability_scale?.map((item) => <div key={item.score}><strong>{item.score} · {item.label}</strong><span>{item.description}</span></div>)}</div>
          <div className="scale-list"><h3>Impact</h3>{methodology?.impact_scale?.map((item) => <div key={item.score}><strong>{item.score} · {item.label}</strong><span>{item.description}</span></div>)}</div>
          <div className="level-legend">{methodology?.levels?.map((item) => <div className={`legend-${item.name.toLowerCase()}`} key={item.name}><strong>{item.name} · {item.min}–{item.max}</strong><span>{item.response}</span></div>)}</div>
        </section>
      </div>
      <section className="panel threat-library-panel">
        <PanelTitle title="Bibliothèque de menaces" detail={`${threats.length} scénario(s) réutilisable(s) pour les ateliers d’identification`} />
        <div className="threat-grid">{threats.map((item) => <article key={item.id}><span>{item.category}</span><h3>{item.name}</h3><p>{item.description}</p><small>Causes : {item.common_causes || '—'}</small><small>Vulnérabilités : {item.common_vulnerabilities || '—'}</small><b>Probabilité indicative : {item.default_probability}/5</b></article>)}</div>
        {canEdit && <form className="form-grid threat-form" onSubmit={submitThreat}><FormField label="Nom"><input name="name" required minLength="3" /></FormField><FormField label="Catégorie"><input name="category" required /></FormField><FormField label="Probabilité indicative"><select name="default_probability" defaultValue="3">{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value}/5</option>)}</select></FormField><FormField label="Description" className="field-wide"><textarea name="description" required rows="2" /></FormField><FormField label="Causes fréquentes" className="field-wide"><input name="common_causes" /></FormField><FormField label="Vulnérabilités fréquentes" className="field-wide"><input name="common_vulnerabilities" /></FormField><div className="form-actions"><button className="button button-secondary" disabled={busy}>Ajouter à la bibliothèque</button></div></form>}
      </section>
    </>
  );
}

