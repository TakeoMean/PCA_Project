import { useState } from 'react';
import { FormField, Modal, PanelTitle, StatusChip } from '../components/Common';
import { formObject, numberOrNull } from '../riskUtils';

export default function UsersView({ users, roles, departments, currentUserId, busy, apiFetch, run }) {
  const [resetUser, setResetUser] = useState(null);
  const submit = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formObject(form);
    payload.department_id = numberOrNull(payload.department_id);
    return run(async () => { await apiFetch('/api/users', { method: 'POST', body: payload }); form.reset(); }, 'Compte créé avec changement de mot de passe obligatoire.');
  };
  const resetPassword = (event) => {
    event.preventDefault();
    const password = new FormData(event.currentTarget).get('new_password');
    return run(async () => { await apiFetch(`/api/users/${resetUser.id}/reset-password`, { method: 'POST', body: { new_password: password } }); setResetUser(null); }, 'Mot de passe temporaire défini.');
  };
  return <>
    <div className="page-heading"><div><p className="eyebrow">IDENTITÉS ET HABILITATIONS</p><h1>Utilisateurs et accès</h1><p className="subtle">Rôles métiers, périmètres départementaux et séparation des responsabilités.</p></div></div>
    <details className="panel form-panel"><summary className="form-summary"><span><strong>Créer un compte</strong><small>L’utilisateur devra remplacer le mot de passe temporaire.</small></span><span className="summary-plus">＋</span></summary><form className="form-grid" onSubmit={submit}><FormField label="Nom complet"><input name="full_name" required /></FormField><FormField label="Nom d’utilisateur"><input name="username" required minLength="3" /></FormField><FormField label="E-mail"><input name="email" type="email" required /></FormField><FormField label="Mot de passe temporaire"><input name="password" type="password" required minLength="10" /></FormField><FormField label="Rôle"><select name="role">{roles.map((item) => <option value={item.name} key={item.id}>{item.name}</option>)}</select></FormField><FormField label="Département"><select name="department_id"><option value="">Aucun</option>{departments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></FormField><div className="form-actions"><button className="button button-primary" disabled={busy}>Créer le compte</button></div></form></details>
    <section className="panel table-panel"><PanelTitle title="Membres de l’espace" detail={`${users.length} compte(s)`} /><div className="data-table-wrap"><table className="data-table"><thead><tr><th>Utilisateur</th><th>Rôle</th><th>Département</th><th>État</th><th>Sécurité</th><th>Actions</th></tr></thead><tbody>{users.map((member) => <tr key={member.id}><td><strong>{member.full_name}</strong><small className="table-subline">{member.username} · {member.email}</small></td><td><select value={member.role} disabled={member.id === currentUserId || busy} onChange={(event) => run(() => apiFetch(`/api/users/${member.id}`, { method: 'PATCH', body: { role: event.target.value } }), 'Rôle mis à jour.')}>{roles.map((item) => <option value={item.name} key={item.id}>{item.name}</option>)}</select></td><td>{member.department}</td><td><StatusChip status={member.is_active ? 'Active' : 'Inactive'} /></td><td>{member.must_change_password ? <span className="security-warning">Changement requis</span> : <span className="security-ok">À jour</span>}</td><td><div className="inline-actions"><button className="text-button" disabled={member.id === currentUserId || busy} onClick={() => run(() => apiFetch(`/api/users/${member.id}`, { method: 'PATCH', body: { is_active: !member.is_active } }), member.is_active ? 'Compte désactivé.' : 'Compte réactivé.')}>{member.is_active ? 'Désactiver' : 'Réactiver'}</button><button className="text-button" onClick={() => setResetUser(member)}>Réinitialiser</button></div></td></tr>)}</tbody></table></div></section>
    {resetUser && <Modal title="Réinitialiser le mot de passe" subtitle={resetUser.full_name} onClose={() => setResetUser(null)}><form className="modal-form single-column" onSubmit={resetPassword}><FormField label="Nouveau mot de passe temporaire"><input name="new_password" type="password" required minLength="10" autoFocus /></FormField><p className="subtle">Un changement sera exigé lors de la prochaine connexion.</p><div className="form-actions"><button type="button" className="button button-secondary" onClick={() => setResetUser(null)}>Annuler</button><button className="button button-primary" disabled={busy}>Réinitialiser</button></div></form></Modal>}
  </>;
}

