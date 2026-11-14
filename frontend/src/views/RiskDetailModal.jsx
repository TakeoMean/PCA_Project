import { useEffect, useMemo, useState } from 'react';
import { downloadFile } from '../api';
import { FormField, Modal, PanelTitle, Severity, StatusChip } from '../components/Common';
import {
  CATEGORIES,
  CATEGORY_LABELS,
  IMPACT_LABELS,
  PROBABILITY_LABELS,
  RISK_STATUSES,
  STATUS_LABELS,
  dateInput,
  formatDate,
  formObject,
  isoOrNull,
  numberOrNull,
} from '../riskUtils';

export default function RiskDetailModal({ risk, departments, activities, users, controls, indicators, incidents, auditLogs, canEdit, canAssess, canControl, canIndicator, busy, apiFetch, run, onClose }) {
  const [tab, setTab] = useState('overview');
  const [form, setForm] = useState({});
  const [attachments, setAttachments] = useState([]);

  useEffect(() => {
    if (!risk) return;
    setForm({ ...risk, review_date: dateInput(risk.review_date) });
    apiFetch(`/api/risks/${risk.id}/attachments`).then(setAttachments).catch(() => setAttachments([]));
  }, [risk?.id, risk?.updated_at]);

  const riskControls = useMemo(() => controls.filter((item) => item.risk_id === risk.id), [controls, risk.id]);
  const riskIndicators = useMemo(() => indicators.filter((item) => item.risk_id === risk.id), [indicators, risk.id]);
  const riskIncidents = useMemo(() => incidents.filter((item) => item.risk_id === risk.id), [incidents, risk.id]);
  const riskLogs = useMemo(() => auditLogs.filter((item) => item.risk_code === risk.code), [auditLogs, risk.code]);

  const updateRisk = (event) => {
    event.preventDefault();
    const payload = {
      code: form.code,
      name: form.name,
      description: form.description,
      category: form.category,
      department_id: Number(form.department_id),
      activity_id: numberOrNull(form.activity_id),
      owner_id: numberOrNull(form.owner_id),
      threat: form.threat || null,
      vulnerability: form.vulnerability || null,
      consequence: form.consequence || null,
      source: form.source || null,
      causes: form.causes || null,
      existing_measures: form.existing_measures || null,
      review_date: isoOrNull(form.review_date),
      status: form.status,
      acceptance_justification: form.acceptance_justification || null,
    };
    return run(() => apiFetch(`/api/risks/${risk.id}`, { method: 'PATCH', body: payload }), 'Fiche risque mise à jour.');
  };

  const reassess = (event) => {
    event.preventDefault();
    const payload = formObject(event.currentTarget);
    payload.probability = Number(payload.probability);
    payload.impact = Number(payload.impact);
    return run(async () => {
      await apiFetch(`/api/risks/${risk.id}/assessments`, { method: 'POST', body: payload });
      event.currentTarget.reset();
    }, 'Évaluation inhérente enregistrée.');
  };

  const addIndicator = (event) => {
    event.preventDefault();
    const payload = formObject(event.currentTarget);
    ['warning_threshold', 'critical_threshold', 'current_value'].forEach((key) => { payload[key] = Number(payload[key]); });
    payload.owner_id = numberOrNull(payload.owner_id);
    return run(async () => {
      await apiFetch(`/api/risks/${risk.id}/indicators`, { method: 'POST', body: payload });
      event.currentTarget.reset();
    }, 'Indicateur KRI ajouté.');
  };

  const addControl = (event) => {
    event.preventDefault();
    const payload = formObject(event.currentTarget);
    payload.effectiveness = Number(payload.effectiveness);
    payload.owner_id = numberOrNull(payload.owner_id);
    payload.last_tested_at = isoOrNull(payload.last_tested_at);
    payload.next_test_date = isoOrNull(payload.next_test_date);
    return run(async () => {
      await apiFetch(`/api/risks/${risk.id}/controls`, { method: 'POST', body: payload });
      event.currentTarget.reset();
    }, 'Mesure de maîtrise ajoutée.');
  };

  const uploadAttachment = (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const body = new FormData(formElement);
    return run(async () => {
      await apiFetch(`/api/risks/${risk.id}/attachments`, { method: 'POST', body });
      setAttachments(await apiFetch(`/api/risks/${risk.id}/attachments`));
      formElement.reset();
    }, 'Pièce justificative ajoutée.');
  };

  const deleteAttachment = (attachmentId) => run(async () => {
    await apiFetch(`/api/risk-attachments/${attachmentId}`, { method: 'DELETE' });
    setAttachments(await apiFetch(`/api/risks/${risk.id}/attachments`));
  }, 'Pièce supprimée.');

  return (
    <Modal title={`${risk.code} · ${risk.name}`} subtitle={`${risk.department} · ${risk.activity || 'Aucune activité liée'}`} onClose={onClose} wide>
      <div className="risk-detail-head"><div><Severity level={risk.level} /><span className="score-pill">{risk.score}/25</span><StatusChip status={risk.status} /></div><div><span>Responsable</span><strong>{risk.owner}</strong></div><div><span>Prochaine revue</span><strong>{formatDate(risk.review_date)}</strong></div></div>
      <nav className="tab-nav" aria-label="Fiche risque">{[['overview', 'Fiche'], ['assessments', 'Évaluations'], ['controls', `Contrôles (${riskControls.length})`], ['indicators', `KRI (${riskIndicators.length})`], ['evidence', `Preuves (${attachments.length})`], ['history', 'Historique']].map(([id, label]) => <button type="button" className={tab === id ? 'selected' : ''} onClick={() => setTab(id)} key={id}>{label}</button>)}</nav>

      {tab === 'overview' && <form className="form-grid modal-form" onSubmit={updateRisk}>
        <FormField label="Code"><input disabled={!canEdit} value={form.code || ''} onChange={(event) => setForm({ ...form, code: event.target.value })} /></FormField>
        <FormField label="Intitulé"><input disabled={!canEdit} value={form.name || ''} onChange={(event) => setForm({ ...form, name: event.target.value })} /></FormField>
        <FormField label="Catégorie"><select disabled={!canEdit} value={form.category || ''} onChange={(event) => setForm({ ...form, category: event.target.value })}>{CATEGORIES.map((item) => <option value={item} key={item}>{CATEGORY_LABELS[item]}</option>)}</select></FormField>
        <FormField label="Département"><select disabled={!canEdit} value={form.department_id || ''} onChange={(event) => setForm({ ...form, department_id: event.target.value, activity_id: '' })}>{departments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></FormField>
        <FormField label="Activité"><select disabled={!canEdit} value={form.activity_id || ''} onChange={(event) => setForm({ ...form, activity_id: event.target.value })}><option value="">Non liée</option>{activities.filter((item) => String(item.department_id) === String(form.department_id)).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></FormField>
        <FormField label="Responsable"><select disabled={!canEdit} value={form.owner_id || ''} onChange={(event) => setForm({ ...form, owner_id: event.target.value })}>{users.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></FormField>
        <FormField label="Statut"><select disabled={!canEdit} value={form.status || 'Draft'} onChange={(event) => setForm({ ...form, status: event.target.value })}>{RISK_STATUSES.map((item) => <option value={item} key={item}>{STATUS_LABELS[item] || item}</option>)}</select></FormField>
        <FormField label="Prochaine revue"><input disabled={!canEdit} type="date" value={form.review_date || ''} onChange={(event) => setForm({ ...form, review_date: event.target.value })} /></FormField>
        <FormField label="Source"><input disabled={!canEdit} value={form.source || ''} onChange={(event) => setForm({ ...form, source: event.target.value })} /></FormField>
        <FormField label="Description" className="field-wide"><textarea disabled={!canEdit} rows="3" value={form.description || ''} onChange={(event) => setForm({ ...form, description: event.target.value })} /></FormField>
        <FormField label="Menace" className="field-wide"><textarea disabled={!canEdit} rows="2" value={form.threat || ''} onChange={(event) => setForm({ ...form, threat: event.target.value })} /></FormField>
        <FormField label="Causes" className="field-wide"><textarea disabled={!canEdit} rows="2" value={form.causes || ''} onChange={(event) => setForm({ ...form, causes: event.target.value })} /></FormField>
        <FormField label="Vulnérabilités" className="field-wide"><textarea disabled={!canEdit} rows="2" value={form.vulnerability || ''} onChange={(event) => setForm({ ...form, vulnerability: event.target.value })} /></FormField>
        <FormField label="Conséquences" className="field-wide"><textarea disabled={!canEdit} rows="2" value={form.consequence || ''} onChange={(event) => setForm({ ...form, consequence: event.target.value })} /></FormField>
        <FormField label="Mesures existantes" className="field-wide"><textarea disabled={!canEdit} rows="2" value={form.existing_measures || ''} onChange={(event) => setForm({ ...form, existing_measures: event.target.value })} /></FormField>
        {(form.status === 'Accepted' || form.acceptance_justification) && <FormField label="Justification d’acceptation" className="field-wide"><textarea disabled={!canEdit} required={form.status === 'Accepted'} minLength="10" rows="2" value={form.acceptance_justification || ''} onChange={(event) => setForm({ ...form, acceptance_justification: event.target.value })} /></FormField>}
        {canEdit && <div className="form-actions"><button className="button button-primary" disabled={busy}>Enregistrer</button></div>}
      </form>}

      {tab === 'assessments' && <div className="detail-section"><div className="assessment-comparison"><AssessmentCard title="Inhérent" assessment={risk.inherent_assessment} /><AssessmentCard title="Résiduel" assessment={risk.residual_assessment} /></div>{canAssess && <form className="panel inset-panel form-grid" onSubmit={reassess}><PanelTitle title="Nouvelle évaluation inhérente" detail="Une nouvelle entrée horodatée est ajoutée à l’historique." /><FormField label="Probabilité"><select name="probability" defaultValue="3">{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value} · {PROBABILITY_LABELS[value]}</option>)}</select></FormField><FormField label="Impact"><select name="impact" defaultValue="3">{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value} · {IMPACT_LABELS[value]}</option>)}</select></FormField><FormField label="Commentaire"><input name="comments" placeholder="Motif et hypothèses" /></FormField><div className="form-actions"><button className="button button-primary" disabled={busy}>Enregistrer l’évaluation</button></div></form>}<div className="timeline">{risk.assessment_history?.map((item) => <div key={item.id}><i /><span><strong>{item.type} · {item.score}/25</strong><small>{formatDate(item.assessment_date, true)} · {item.comments || 'Sans commentaire'}</small></span><Severity level={item.level} /></div>)}</div></div>}

      {tab === 'controls' && <div className="detail-section"><div className="card-list">{riskControls.map((item) => <article className="mini-card" key={item.id}><div><strong>{item.name}</strong><small>{item.control_type} · efficacité {item.effectiveness}/5</small></div><StatusChip status={item.status} /><p>{item.description}</p><small>Dernier test : {formatDate(item.last_tested_at)} · prochain : {formatDate(item.next_test_date)}</small></article>)}</div>{canControl && <form className="panel inset-panel form-grid" onSubmit={addControl}><PanelTitle title="Ajouter une mesure de maîtrise" /><FormField label="Nom"><input name="name" required minLength="3" /></FormField><FormField label="Type"><select name="control_type"><option value="Preventive">Préventif</option><option value="Detective">Détectif</option><option value="Corrective">Correctif</option></select></FormField><FormField label="Responsable"><select name="owner_id"><option value="">Non assigné</option>{users.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></FormField><FormField label="Efficacité"><select name="effectiveness" defaultValue="3">{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value}/5</option>)}</select></FormField><FormField label="Statut"><select name="status"><option>Implemented</option><option>Planned</option><option>Needs improvement</option><option>Inactive</option></select></FormField><FormField label="Dernier test"><input type="date" name="last_tested_at" /></FormField><FormField label="Prochain test"><input type="date" name="next_test_date" /></FormField><FormField label="Description" className="field-wide"><textarea name="description" required rows="2" /></FormField><FormField label="Référence de preuve" className="field-wide"><input name="evidence_reference" /></FormField><div className="form-actions"><button className="button button-primary" disabled={busy}>Ajouter le contrôle</button></div></form>}</div>}

      {tab === 'indicators' && <div className="detail-section"><div className="card-list">{riskIndicators.map((item) => <article className={`mini-card indicator-${item.status.toLowerCase()}`} key={item.id}><div><strong>{item.name}</strong><small>{item.owner} · {item.frequency}</small></div><StatusChip status={item.status} /><p className="indicator-value">{item.current_value} {item.unit}</p><small>Alerte {item.warning_threshold} · critique {item.critical_threshold} · {item.direction}</small>{canIndicator && <div className="mini-actions"><form onSubmit={(event) => { event.preventDefault(); const currentValue = Number(new FormData(event.currentTarget).get('current_value')); return run(() => apiFetch(`/api/risk-indicators/${item.id}`, { method: 'PATCH', body: { current_value: currentValue } }), 'Valeur KRI mise à jour.'); }}><input aria-label={`Nouvelle valeur de ${item.name}`} type="number" step="any" name="current_value" defaultValue={item.current_value} /><button className="text-button">Actualiser</button></form><button className="text-button danger-text" onClick={() => run(() => apiFetch(`/api/risk-indicators/${item.id}`, { method: 'DELETE' }), 'KRI supprimé.')}>Supprimer</button></div>}</article>)}</div>{canIndicator && <form className="panel inset-panel form-grid" onSubmit={addIndicator}><PanelTitle title="Ajouter un indicateur KRI" /><FormField label="Indicateur"><input name="name" required /></FormField><FormField label="Unité"><input name="unit" required placeholder="%, minutes, incidents…" /></FormField><FormField label="Sens du risque"><select name="direction"><option value="Above is bad">Une valeur haute est défavorable</option><option value="Below is bad">Une valeur basse est défavorable</option></select></FormField><FormField label="Seuil d’alerte"><input type="number" step="any" name="warning_threshold" required /></FormField><FormField label="Seuil critique"><input type="number" step="any" name="critical_threshold" required /></FormField><FormField label="Valeur actuelle"><input type="number" step="any" name="current_value" required /></FormField><FormField label="Fréquence"><select name="frequency"><option value="Daily">Quotidienne</option><option value="Weekly">Hebdomadaire</option><option value="Monthly">Mensuelle</option><option value="Quarterly">Trimestrielle</option></select></FormField><FormField label="Responsable"><select name="owner_id"><option value="">Non assigné</option>{users.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></FormField><div className="form-actions"><button className="button button-primary" disabled={busy}>Ajouter le KRI</button></div></form>}</div>}

      {tab === 'evidence' && <div className="detail-section"><div className="attachment-list">{attachments.map((item) => <article key={item.id}><span>▧</span><div><strong>{item.original_name}</strong><small>{Math.ceil(item.size_bytes / 1024)} Ko · {item.uploaded_by} · {formatDate(item.created_at)}</small><p>{item.description}</p></div><button className="text-button" onClick={() => downloadFile(`/api/risk-attachments/${item.id}/download`, item.original_name)}>Télécharger</button>{canEdit && <button className="text-button danger-text" onClick={() => deleteAttachment(item.id)}>Supprimer</button>}</article>)}</div>{canEdit && <form className="panel inset-panel form-grid" onSubmit={uploadAttachment}><PanelTitle title="Ajouter une preuve" detail="PDF, image, document Office ou fichier texte · 10 Mo maximum." /><FormField label="Fichier"><input type="file" name="file" required accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.xlsx,.docx,.pptx" /></FormField><FormField label="Description" className="field-wide"><input name="description" /></FormField><div className="form-actions"><button className="button button-primary" disabled={busy}>Téléverser</button></div></form>}</div>}

      {tab === 'history' && <div className="detail-section"><PanelTitle title="Incidents liés" detail={`${riskIncidents.length} incident(s)`} /><div className="card-list">{riskIncidents.map((item) => <article className="mini-card" key={item.id}><div><strong>{item.code} · {item.title}</strong><small>{formatDate(item.occurred_at)} · {item.severity}</small></div><StatusChip status={item.status} /><p>{item.impact || item.description}</p></article>)}</div><PanelTitle title="Journal d’audit" detail={`${riskLogs.length} événement(s) chargé(s)`} /><div className="timeline audit-timeline">{riskLogs.map((item) => <div key={item.id}><i /><span><strong>{item.action.replaceAll('_', ' ')}</strong><small>{item.details} · {item.user} · {formatDate(item.created_at, true)}</small></span></div>)}</div></div>}
    </Modal>
  );
}

function AssessmentCard({ title, assessment }) {
  return <article className="assessment-card"><span>{title}</span>{assessment ? <><strong>{assessment.score}/25</strong><small>P{assessment.probability} × I{assessment.impact}</small><Severity level={assessment.level} /></> : <small>Non disponible</small>}</article>;
}

