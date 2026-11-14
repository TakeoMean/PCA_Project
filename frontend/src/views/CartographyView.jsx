import { useMemo, useState } from 'react';
import { PanelTitle, RiskHeatmap, Severity } from '../components/Common';
import { CATEGORY_LABELS, LEVEL_LABELS, assessmentFor } from '../riskUtils';

export default function CartographyView({ cartography, departments, onRisk }) {
  const [mode, setMode] = useState('current');
  const [department, setDepartment] = useState('All');
  const [category, setCategory] = useState('All');

  const rows = useMemo(() => cartography.filter((risk) => (
    (department === 'All' || String(risk.department_id) === department)
    && (category === 'All' || risk.category === category)
    && assessmentFor(risk, mode)
  )).map((risk) => {
    const assessment = assessmentFor(risk, mode);
    return { ...risk, ...assessment };
  }), [cartography, department, category, mode]);

  const categories = [...new Set(cartography.map((risk) => risk.category))];

  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">CARTOGRAPHIE DES RISQUES</p><h1>Matrice probabilité × impact</h1><p className="subtle">Comparez l’exposition inhérente, résiduelle ou courante et accédez au détail de chaque risque.</p></div></div>
      <section className="panel matrix-panel">
        <div className="table-toolbar matrix-toolbar">
          <PanelTitle title={`${rows.length} risque(s) cartographié(s)`} detail="Cliquez sur un code pour ouvrir la fiche." />
          <div className="filters">
            <select aria-label="Type d’évaluation" value={mode} onChange={(event) => setMode(event.target.value)}><option value="current">Évaluation courante</option><option value="inherent">Risque inhérent</option><option value="residual">Risque résiduel</option></select>
            <select aria-label="Département" value={department} onChange={(event) => setDepartment(event.target.value)}><option value="All">Tous les départements</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
            <select aria-label="Catégorie" value={category} onChange={(event) => setCategory(event.target.value)}><option value="All">Toutes les catégories</option>{categories.map((item) => <option key={item} value={item}>{CATEGORY_LABELS[item] || item}</option>)}</select>
          </div>
        </div>
        <RiskHeatmap risks={rows} mode="current" onSelect={onRisk} />
        <div className="matrix-legend"><span className="legend-low">Faible</span><span className="legend-moderate">Modéré</span><span className="legend-high">Élevé</span><span className="legend-critical">Critique</span></div>
      </section>
      <section className="panel table-panel">
        <PanelTitle title="Lecture de la carte" detail={`Mode : ${mode === 'inherent' ? 'inhérent' : mode === 'residual' ? 'résiduel' : 'courant'}`} />
        <div className="cartography-list">{rows.sort((a, b) => b.score - a.score).map((risk) => <button type="button" onClick={() => onRisk(risk)} key={risk.id}><strong>{risk.code}</strong><span>{risk.name}</span><small>{risk.department} · {CATEGORY_LABELS[risk.category] || risk.category}</small><span className="cartography-score">{risk.score}/25</span><Severity level={risk.level} /></button>)}</div>
        {!rows.length && <p className="subtle">Aucun risque ne correspond aux filtres ou ne possède cette évaluation.</p>}
      </section>
    </>
  );
}

