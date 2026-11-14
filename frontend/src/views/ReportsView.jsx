import { useMemo, useState } from 'react';
import { downloadFile } from '../api';
import { EmptyState, PanelTitle } from '../components/Common';
import { formatDate } from '../riskUtils';

export default function ReportsView({ auditLogs, run }) {
  const [filter, setFilter] = useState('');
  const rows = useMemo(() => auditLogs.filter((item) => `${item.action} ${item.details} ${item.user} ${item.risk_code || ''}`.toLowerCase().includes(filter.toLowerCase())), [auditLogs, filter]);
  const exportReport = (format) => run(() => downloadFile(`/api/reports/export?format=${format}`, `rapport-risques-smca.${format === 'excel' ? 'xlsx' : 'pdf'}`), 'Rapport généré.', false);
  return <>
    <div className="page-heading"><div><p className="eyebrow">GOUVERNANCE ET TRAÇABILITÉ</p><h1>Rapports et audit</h1><p className="subtle">Exports limités au périmètre autorisé et journal des événements métier.</p></div></div>
    <section className="panel export-panel"><div><h2>Registre consolidé</h2><p className="subtle">Les exports comprennent les scores inhérent, résiduel et courant, les statuts et les échéances.</p></div><div className="export-actions"><button className="button button-secondary" onClick={() => exportReport('pdf')}>↓ Export PDF</button><button className="button button-primary" onClick={() => exportReport('excel')}>↓ Export Excel</button></div></section>
    <section className="panel table-panel"><div className="table-toolbar"><PanelTitle title="Journal d’audit" detail={`${rows.length} événement(s) chargé(s)`} /><input aria-label="Filtrer le journal" placeholder="Filtrer les événements…" value={filter} onChange={(event) => setFilter(event.target.value)} /></div><div className="data-table-wrap"><table className="data-table"><thead><tr><th>Événement</th><th>Détails</th><th>Risque</th><th>Utilisateur</th><th>Date</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id}><td><span className="audit-event">{item.action.replaceAll('_', ' ')}</span></td><td>{item.details}</td><td>{item.risk_code || '—'}</td><td>{item.user}</td><td>{formatDate(item.created_at, true)}</td></tr>)}</tbody></table></div>{!rows.length && <EmptyState title="Aucun événement" detail="Les changements importants sont enregistrés ici." />}</section>
  </>;
}

