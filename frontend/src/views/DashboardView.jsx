import { useMemo } from 'react';
import { Bar } from 'react-chartjs-2';
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from 'chart.js';
import { AlertList, MetricCard, PanelTitle, RiskTable } from '../components/Common';
import { CATEGORY_LABELS } from '../riskUtils';

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

export default function DashboardView({ user, dashboard, alerts, risks, onView, onRisk, canCreate }) {
  const categoryChart = useMemo(() => {
    const counts = dashboard?.breakdown || {};
    return {
      labels: Object.keys(counts).map((name) => CATEGORY_LABELS[name] || name),
      datasets: [{
        data: Object.values(counts),
        backgroundColor: ['#3867d6', '#20a39e', '#e4a11b', '#e66b5b', '#9b6bd3', '#48a9a6', '#65758b'],
        borderRadius: 6,
        maxBarThickness: 36,
      }],
    };
  }, [dashboard]);

  const recentRisks = (dashboard?.recent_risks || []).map((item) => ({
    ...item,
    ...(risks.find((risk) => risk.code === item.code) || {}),
  }));

  return (
    <>
      <div className="page-heading">
        <div><p className="eyebrow">PILOTAGE SMCA</p><h1>Bonjour, {user.full_name.split(' ')[0]}</h1><p className="subtle">Vue consolidée de l’exposition, des échéances et de la continuité d’activité.</p></div>
        {canCreate && <button className="button button-primary" onClick={() => onView('risks')}>＋ Ajouter un risque</button>}
      </div>
      <div className="metric-grid metric-grid-wide">
        <MetricCard label="Risques" value={dashboard?.total_risks || 0} note="Périmètre accessible" icon="◇" tone="blue" />
        <MetricCard label="Critiques" value={dashboard?.critical || 0} note="Action immédiate" icon="!" tone="red" />
        <MetricCard label="Plans en cours" value={dashboard?.treatments_in_progress || 0} note={`${dashboard?.treatments_completed || 0} terminés`} icon="↗" tone="teal" />
        <MetricCard label="Actions en retard" value={dashboard?.actions_overdue || 0} note={`${dashboard?.treatments_overdue || 0} plans échus`} icon="◷" tone="amber" />
        <MetricCard label="Revues échues" value={dashboard?.risk_reviews_due || 0} note="Risques à réévaluer" icon="↻" tone="amber" />
        <MetricCard label="Contrôles à tester" value={dashboard?.control_tests_due || 0} note="Échéance dépassée" icon="✓" tone="blue" />
        <MetricCard label="Incidents ouverts" value={dashboard?.open_incidents || 0} note="Ouverts ou analysés" icon="⚑" tone="red" />
        <MetricCard label="KRI critiques" value={dashboard?.critical_indicators || 0} note="Seuil critique franchi" icon="⌁" tone="red" />
      </div>
      <div className="dashboard-grid">
        <section className="panel chart-panel">
          <PanelTitle title="Répartition des risques" detail="Nombre de risques par catégorie" action={<button className="text-button" onClick={() => onView('cartography')}>Ouvrir la cartographie →</button>} />
          <div className="chart-container">
            {Object.keys(dashboard?.breakdown || {}).length
              ? <Bar data={categoryChart} options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#edf1f5' } } } }} />
              : <p className="subtle">Aucune donnée de risque.</p>}
          </div>
        </section>
        <section className="panel alerts-panel">
          <PanelTitle title="Alertes et échéances" detail={`${alerts.length} élément(s) à surveiller`} />
          <AlertList alerts={alerts.slice(0, 8)} onRisk={onRisk} />
        </section>
      </div>
      <section className="panel table-panel">
        <PanelTitle title="Risques prioritaires" detail="Risques récemment enregistrés" action={<button className="text-button" onClick={() => onView('risks')}>Voir le registre →</button>} />
        <RiskTable risks={recentRisks} onSelect={onRisk} detailed />
      </section>
    </>
  );
}

