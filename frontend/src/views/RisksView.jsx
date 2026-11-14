import { useMemo, useState } from 'react';
import { FormField, PanelTitle, RiskTable } from '../components/Common';
import {
  CATEGORIES,
  CATEGORY_LABELS,
  IMPACT_LABELS,
  LEVELS,
  LEVEL_LABELS,
  PROBABILITY_LABELS,
  STATUS_LABELS,
  formObject,
  isoOrNull,
  numberOrNull,
  riskLevel,
} from '../riskUtils';

export default function RisksView({ risks, departments, activities, users, threats, canCreate, busy, apiFetch, run, onRisk }) {
  const [departmentId, setDepartmentId] = useState('');
  const [probability, setProbability] = useState(3);
  const [impact, setImpact] = useState(3);
  const [filter, setFilter] = useState({ query: '', level: 'All', category: 'All', status: 'All' });
  const [importFile, setImportFile] = useState(null);
  const [importReport, setImportReport] = useState(null);

  const filtered = useMemo(() => risks.filter((risk) => {
    const term = filter.query.trim().toLowerCase();
    return (!term || `${risk.code} ${risk.name} ${risk.department} ${risk.threat || ''}`.toLowerCase().includes(term))
      && (filter.level === 'All' || risk.level === filter.level)
      && (filter.category === 'All' || risk.category === filter.category)
      && (filter.status === 'All' || risk.status === filter.status);
  }), [risks, filter]);

  const submitRisk = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formObject(form);
    payload.department_id = Number(payload.department_id);
    payload.activity_id = numberOrNull(payload.activity_id);
    payload.owner_id = numberOrNull(payload.owner_id);
    payload.probability = Number(payload.probability);
    payload.impact = Number(payload.impact);
    payload.review_date = isoOrNull(payload.review_date);
    return run(async () => {
      await apiFetch('/api/risks', { method: 'POST', body: payload });
      form.reset();
      setDepartmentId('');
      setProbability(3);
      setImpact(3);
    }, 'Risque ajouté au registre.');
  };

  const importRisks = async (event) => {
    event.preventDefault();
    if (!importFile) return run(() => Promise.reject(new Error('Sélectionnez un fichier CSV ou XLSX.')), '');
    const form = event.currentTarget;
    const body = new FormData();
    body.append('file', importFile);
    return run(async () => {
      const result = await apiFetch('/api/risks/import', { method: 'POST', body });
      setImportReport(result);
      setImportFile(null);
      form.reset();
    }, 'Import terminé.');
  };

  const downloadTemplate = () => {
    const csv = [
      ['code', 'name', 'department', 'category', 'description', 'probability', 'impact', 'owner', 'threat', 'vulnerability', 'consequence', 'activity', 'source', 'causes', 'existing_measures'],
      ['RISK-101', 'Indisponibilité du service', 'IT', 'Technical', 'Interruption du service de production', '4', '5', 'admin', 'Panne matérielle', 'Redondance insuffisante', 'Arrêt des applications critiques', 'Application Hosting', 'Atelier BIA', 'Défaillance serveur', 'Sauvegardes quotidiennes'],
    ].map((row) => row.join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'modele-import-risques.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const score = probability * impact;

  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">IDENTIFICATION ET ÉVALUATION</p><h1>Registre des risques</h1><p className="subtle">Documentez les scénarios, responsabilités, mesures existantes et échéances de revue.</p></div></div>
      {canCreate && <div className="stacked-forms">
        <details className="panel form-panel">
          <summary className="form-summary"><span><strong>Enregistrer un risque</strong><small>Formulez le scénario sous la forme cause → événement → conséquence.</small></span><span className="summary-plus">＋</span></summary>
          <form className="form-grid" onSubmit={submitRisk}>
            <FormField label="Identifiant"><input name="code" required placeholder="RISK-004" /></FormField>
            <FormField label="Intitulé"><input name="name" required placeholder="Interruption du service de paiement" /></FormField>
            <FormField label="Catégorie"><select name="category">{CATEGORIES.map((item) => <option value={item} key={item}>{CATEGORY_LABELS[item]}</option>)}</select></FormField>
            <FormField label="Département"><select name="department_id" required value={departmentId} onChange={(event) => setDepartmentId(event.target.value)}><option value="" disabled>Choisir</option>{departments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></FormField>
            <FormField label="Activité critique"><select name="activity_id"><option value="">Non liée</option>{activities.filter((item) => String(item.department_id) === departmentId).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></FormField>
            <FormField label="Responsable"><select name="owner_id"><option value="">Utilisateur connecté</option>{users.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></FormField>
            <FormField label="Menace"><input name="threat" list="threat-library" placeholder="Événement redouté" /><datalist id="threat-library">{threats.map((item) => <option value={item.name} key={item.id}>{item.description}</option>)}</datalist></FormField>
            <FormField label="Source"><input name="source" placeholder="BIA, audit, incident, atelier…" /></FormField>
            <FormField label="Prochaine revue"><input type="date" name="review_date" /></FormField>
            <FormField label="Probabilité"><select name="probability" value={probability} onChange={(event) => setProbability(Number(event.target.value))}>{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value} · {PROBABILITY_LABELS[value]}</option>)}</select></FormField>
            <FormField label="Impact"><select name="impact" value={impact} onChange={(event) => setImpact(Number(event.target.value))}>{[1, 2, 3, 4, 5].map((value) => <option value={value} key={value}>{value} · {IMPACT_LABELS[value]}</option>)}</select></FormField>
            <div className={`live-score live-score-${riskLevel(score).toLowerCase()}`}><small>Score calculé</small><strong>{score}/25</strong><span>{LEVEL_LABELS[riskLevel(score)]}</span></div>
            <FormField label="Description du scénario" className="field-wide"><textarea name="description" rows="3" required placeholder="Dans le contexte de…, en raison de…, il existe un risque que…, entraînant…" /></FormField>
            <FormField label="Causes" className="field-wide"><textarea name="causes" rows="2" placeholder="Causes internes et externes" /></FormField>
            <FormField label="Vulnérabilités" className="field-wide"><textarea name="vulnerability" rows="2" placeholder="Faiblesses favorisant le scénario" /></FormField>
            <FormField label="Conséquences potentielles" className="field-wide"><textarea name="consequence" rows="2" placeholder="Impacts opérationnels, financiers, légaux, humains et réputationnels" /></FormField>
            <FormField label="Mesures existantes" className="field-wide"><textarea name="existing_measures" rows="2" placeholder="Prévention, détection, correction et preuves disponibles" /></FormField>
            <div className="form-actions"><button className="button button-primary" disabled={busy}>Enregistrer le risque</button></div>
          </form>
        </details>
        <details className="panel form-panel">
          <summary className="form-summary"><span><strong>Importer un registre</strong><small>Import contrôlé au format CSV ou XLSX, limité à 5 Mo.</small></span><span className="summary-plus">＋</span></summary>
          <form className="form-grid" onSubmit={importRisks}>
            <FormField label="Fichier" className="field-wide"><input type="file" accept=".csv,.xlsx" onChange={(event) => setImportFile(event.target.files?.[0] || null)} /></FormField>
            <div className="form-actions field-wide"><button type="button" className="button button-secondary" onClick={downloadTemplate}>Télécharger le modèle</button><button className="button button-primary" disabled={busy}>Importer</button></div>
          </form>
          {importReport && <div className="import-report"><strong>{importReport.created} risque(s) importé(s)</strong><small>{importReport.total_rows} ligne(s) · {importReport.errors.length} anomalie(s)</small>{importReport.errors.length > 0 && <ul>{importReport.errors.slice(0, 8).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>}</div>}
        </details>
      </div>}
      <section className="panel table-panel">
        <div className="table-toolbar"><PanelTitle title={`Tous les risques · ${filtered.length}`} detail="Cliquez sur une ligne pour consulter, réévaluer ou enrichir le risque." /><div className="filters"><input aria-label="Rechercher" placeholder="Rechercher…" value={filter.query} onChange={(event) => setFilter({ ...filter, query: event.target.value })} /><select value={filter.level} onChange={(event) => setFilter({ ...filter, level: event.target.value })}><option value="All">Tous les niveaux</option>{LEVELS.map((item) => <option value={item} key={item}>{LEVEL_LABELS[item]}</option>)}</select><select value={filter.category} onChange={(event) => setFilter({ ...filter, category: event.target.value })}><option value="All">Toutes les catégories</option>{CATEGORIES.map((item) => <option value={item} key={item}>{CATEGORY_LABELS[item]}</option>)}</select><select value={filter.status} onChange={(event) => setFilter({ ...filter, status: event.target.value })}><option value="All">Tous les statuts</option>{[...new Set(risks.map((risk) => risk.status))].map((item) => <option value={item} key={item}>{STATUS_LABELS[item] || item}</option>)}</select></div></div>
        <RiskTable risks={filtered} onSelect={onRisk} />
      </section>
    </>
  );
}

