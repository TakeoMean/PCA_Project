import { FormField, PanelTitle } from '../components/Common';
import { formObject } from '../riskUtils';

export default function OrganizationView({ departments, activities, resources, canEdit, busy, apiFetch, run }) {
  const submitDepartment = (event) => submit(event, '/api/departments', 'Département créé.');
  const submitActivity = (event) => submit(event, '/api/activities', 'Activité créée.', ['department_id']);
  const submitResource = (event) => submit(event, '/api/resources', 'Ressource créée.', ['activity_id']);
  const submit = (event, path, message, numeric = []) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formObject(form);
    numeric.forEach((key) => { payload[key] = Number(payload[key]); });
    return run(async () => { await apiFetch(path, { method: 'POST', body: payload }); form.reset(); }, message);
  };
  return <>
    <div className="page-heading"><div><p className="eyebrow">CONTEXTE DE L’ORGANISATION</p><h1>Départements, activités et ressources</h1><p className="subtle">Structurez le périmètre métier utilisé par la BIA et la cartographie des risques.</p></div></div>
    {canEdit && <section className="quick-create-grid panel"><form onSubmit={submitDepartment}><strong>Nouveau département</strong><input name="name" required placeholder="Nom" /><input name="description" placeholder="Description" /><button className="button button-secondary" disabled={busy}>Créer</button></form><form onSubmit={submitActivity}><strong>Nouvelle activité</strong><select name="department_id" required defaultValue=""><option value="" disabled>Département</option>{departments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><input name="name" required placeholder="Nom de l’activité" /><input name="description" placeholder="Description" /><button className="button button-secondary" disabled={busy}>Créer</button></form><form onSubmit={submitResource}><strong>Nouvelle ressource</strong><select name="activity_id" required defaultValue=""><option value="" disabled>Activité</option>{activities.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><input name="name" required placeholder="Nom" /><input name="category" required placeholder="Catégorie" /><input name="description" placeholder="Description" /><button className="button button-secondary" disabled={busy}>Créer</button></form></section>}
    <section className="department-grid">{departments.map((department) => { const departmentActivities = activities.filter((item) => item.department_id === department.id); return <article className="panel department-card" key={department.id}><div className="department-icon">{department.name.slice(0, 2).toUpperCase()}</div><div><h2>{department.name}</h2><p>{department.description || 'Sans description'}</p></div><span className="count-pill">{departmentActivities.length}</span>{departmentActivities.map((activity) => <div className="activity-detail" key={activity.id}><div><strong>{activity.name}</strong><small>{activity.description}</small></div><ul>{resources.filter((item) => item.activity_id === activity.id).map((resource) => <li key={resource.id}>{resource.name}<span>{resource.category}</span></li>)}</ul></div>)}</article>; })}</section>
    <section className="panel table-panel"><PanelTitle title="Inventaire des ressources" detail={`${resources.length} ressource(s) liée(s) aux activités`} /><div className="resource-grid">{resources.map((item) => <article key={item.id}><span>{item.category?.slice(0, 1) || 'R'}</span><div><strong>{item.name}</strong><small>{item.activity} · {item.department}</small><p>{item.description}</p></div></article>)}</div></section>
  </>;
}

