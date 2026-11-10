# Deploy ContinuityOS on Red Hat Enterprise Linux 9.5

This guide transfers the current project to a RHEL 9.5 server and runs its PostgreSQL, FastAPI, and React services with Docker Compose.

> **Deployment scope:** the current Compose setup is suitable for a class/demo or a restricted test server. The frontend container runs Vite's development server, and the backend creates demo accounts. Do not expose this version directly to the public internet or treat it as production-ready. The production hardening checklist at the end must be completed before public use.

## 1. Check the target server

Log in to the RHEL server using an account with `sudo`, then check the OS, CPU architecture, storage, and SELinux:

```bash
cat /etc/redhat-release
uname -m
df -h /
getenforce
```

Expect a RHEL 9.5 release and a Docker-supported architecture such as `x86_64` or `aarch64`. For a small demo, plan for at least 2 CPU cores and 4 GB RAM, plus enough disk space for container images and the PostgreSQL data volume.

Apply approved operating-system updates and reboot first if the kernel was updated:

```bash
sudo dnf update -y
sudo reboot
```

Reconnect after the reboot. Do not disable SELinux or the system firewall to make containers work.

## 2. Install Docker Engine and Compose

This guide uses Docker CE from Docker's repository. These are Docker-provided packages, not Red Hat-supported container packages. If your organisation requires only Red Hat-supported software, ask its administrator to approve a Podman deployment instead; Compose compatibility should be validated before using this project's Compose file.

Install Docker using Docker's RHEL instructions:

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

If DNF reports a package conflict, stop and have the system administrator review it. Do not blindly remove Podman or other container software from a shared server.

For this walkthrough, keep using `sudo docker`. Membership in the `docker` group effectively grants root-level control over the host, so don't add an account to that group unless your administrator explicitly approves it.

## 3. Transfer the project from Windows

### Option A — use Git

If you have pushed the project to a private Git repository that the server is allowed to access, clone it into `/opt/smca`:

```bash
sudo mkdir -p /opt/smca
sudo chown "$USER":"$USER" /opt/smca
git clone <YOUR_PRIVATE_REPOSITORY_URL> /opt/smca
cd /opt/smca
```

Keep the repository private. Do not commit `.env`, passwords, signing keys, database dumps, or other secrets.

### Option B — transfer an archive with Windows OpenSSH

On the Windows development computer, open PowerShell and create a clean archive from the project directory. This excludes local dependencies, generated files, the SQLite demo database, reports, and environment secrets:

```powershell
Set-Location 'C:\Users\mejri\Desktop'
tar.exe -czf smca-project.tar.gz `
  --exclude='Project PCA\frontend\node_modules' `
  --exclude='Project PCA\frontend\dist' `
  --exclude='Project PCA\backend\.venv' `
  --exclude='Project PCA\backend\__pycache__' `
  --exclude='Project PCA\backend\smca.db' `
  --exclude='Project PCA\backend\reports' `
  --exclude='Project PCA\.env' `
  'Project PCA'
scp.exe .\smca-project.tar.gz aymen@192.168.61.148:/tmp/smca-project.tar.gz
```

Replace `<RHEL_USER>` and `<RHEL_HOST>` with your server login and hostname/IP. You will be prompted to authenticate. If Windows `tar.exe` does not accept the exclusion paths, create a clean copy containing the source folders and project configuration only, then archive and transfer that copy.

On RHEL, extract the archive to a path without spaces:

```bash
sudo mkdir -p /opt/smca
sudo tar -xzf /tmp/smca-project.tar.gz -C /opt/smca --strip-components=1
sudo chown -R "$USER":"$USER" /opt/smca
cd /opt/smca
```

Check that the files arrived:

```bash
ls -la
test -f docker-compose.yml && test -f .env.example && echo "Project files found"
```

The SQLite database is intentionally excluded. The deployment starts a new PostgreSQL database and seeds sample records. If you have user-created data that must be kept, stop here and plan and test a separate data migration first.

## 4. Set deployment secrets

Create a private local `.env` file:

```bash
cd /opt/smca
cp .env.example .env
chmod 600 .env
openssl rand -hex 32
openssl rand -hex 24
```

Edit it:

```bash
vi .env
```

Set unique values for:

```dotenv
POSTGRES_DB=smca
POSTGRES_USER=smca
POSTGRES_PASSWORD=<paste-the-24-byte-random-hex-value>
SECRET_KEY=<paste-the-32-byte-random-hex-value>
DEMO_ADMIN_PASSWORD=<unique-demo-password-at-least-10-characters>
DEMO_RISK_MANAGER_PASSWORD=<different-unique-demo-password>
DEMO_SMCA_MANAGER_PASSWORD=<different-unique-demo-password>


openssl rand -hex 32
openssl rand -hex 24
351bd002d8d506b708171171347b244ef1c68ae7e78a2aaa0a18da5181848e15
3464d9d1427c7d0a1fe876c04c2b9db39958c3648f81a9b4
```

Use the full random hex values for `POSTGRES_PASSWORD` and `SECRET_KEY`. Use a separate, strong password for each demo account. These account passwords are only used when those seed accounts are first created. Changing `.env` later does **not** change passwords already stored in the database.

Check the file permissions and make sure Git ignores it:

```bash
stat -c '%a %n' .env
git status --short 2>/dev/null || true
```

The mode for `.env` should be `600`.

## 5. Bind demo services to localhost

The supplied Compose file publishes all three ports on all host interfaces by default. For the safest initial demo, change the host port mappings so the services listen on the server's loopback interface only. Open the file:

```bash
vi docker-compose.yml
```

Change **only** the `ports` entries to:

```yaml
  db:
    ports:
      - '127.0.0.1:5432:5432'

  backend:
    ports:
      - '127.0.0.1:8000:8000'

  frontend:
    ports:
      - '127.0.0.1:5173:5173'
```

Keep the existing services, health checks, and named `postgres_data` volume. The containers can still reach one another using their Compose service names. Binding these ports to loopback means users on other machines cannot browse directly to them.

Validate the Compose configuration before starting services:

```bash
sudo docker compose config --quiet
```

If this reports missing environment variables, check `.env` and run the command again. Do not paste the contents of `.env` into tickets or public chat.

## 6. Build and start the application

From `/opt/smca`, build and start all services:

```bash
sudo docker compose up -d --build
sudo docker compose ps
```

Wait until `db` and `backend` report healthy and `frontend` is running. If a service exits or remains unhealthy, inspect its logs:

```bash
sudo docker compose logs --tail=100 db
sudo docker compose logs --tail=100 backend
sudo docker compose logs --tail=100 frontend
```

Check the API and frontend from the server:

```bash
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:5173/
```

The API health response should include `"status":"ok"` and `"database":"connected"`. The frontend response should contain the HTML page.

## 7. Open the app securely from your Windows computer

With the loopback port mappings above, create an SSH tunnel from a **second** PowerShell window on Windows:

```powershell
ssh.exe -N -L 5173:127.0.0.1:5173 <RHEL_USER>@<RHEL_HOST>
```

Leave that PowerShell window open while you use the app. In your browser, visit:

[http://localhost:5173](http://localhost:5173)

The frontend's `/api` requests are proxied to the backend within the Compose network; the browser does not need direct access to PostgreSQL or port 8000.

## 8. Test the deployment

1. Sign in with the Administrator username `admin` and the `DEMO_ADMIN_PASSWORD` set before the database's first start.
2. Confirm the dashboard loads its seeded risks.
3. Follow [FULL_TEST_SCENARIO.md](./FULL_TEST_SCENARIO.md) to test a complete risk, treatment approval, action, residual assessment, audit, and report-export workflow.
4. Confirm the expected test risk score is **20/25 Critical** before treatment and **6/25 Moderate** after the sample reassessment.
5. Test PDF and Excel downloads.
6. Sign out after testing.

## 9. Operate the application

Run these commands from `/opt/smca`:

```bash
# See service status
sudo docker compose ps

# Follow logs
sudo docker compose logs -f --tail=100

# Restart services after an approved configuration change
sudo docker compose up -d --build

# Stop services without deleting database data
sudo docker compose down

# Start them again
sudo docker compose up -d
```

`docker compose down` preserves the named PostgreSQL volume. **Do not run `docker compose down -v`** unless you intentionally want to permanently delete the database volume.

## 10. Back up the PostgreSQL database

Create a backup directory readable only by the current administrator:

```bash
mkdir -p "$HOME/smca-backups"
chmod 700 "$HOME/smca-backups"
```

Create a timestamped PostgreSQL dump without printing the database password:

```bash
set -a
. ./.env
set +a
umask 077
sudo docker compose exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$HOME/smca-backups/smca-$(date +%Y%m%d-%H%M%S).sql"
unset POSTGRES_PASSWORD SECRET_KEY DEMO_ADMIN_PASSWORD DEMO_RISK_MANAGER_PASSWORD DEMO_SMCA_MANAGER_PASSWORD
```

Check that the dump exists and has content:

```bash
ls -lh "$HOME"/smca-backups/
```

Store backups on a separate protected system and test restoring them to a separate test database. A backup that has never been restore-tested is not a verified recovery plan.

## 11. Troubleshooting

### Docker commands fail

```bash
sudo systemctl status docker --no-pager
sudo systemctl restart docker
sudo docker compose ps
```

### Backend is unhealthy or PostgreSQL will not start

```bash
sudo docker compose logs --tail=150 db backend
sudo docker compose ps
```

Check that the `.env` values are set and that enough free disk space is available. If this is an existing database volume, do not delete it to “fix” startup; preserve it and investigate the logs/backups first.

### Frontend loads but API requests fail

```bash
sudo docker compose logs --tail=100 frontend backend
curl --fail http://127.0.0.1:8000/api/health
```

Check that the frontend uses the supplied `VITE_BACKEND_PROXY: http://backend:8000` and that the backend is healthy.

### Browser cannot connect through the SSH tunnel

- Keep the SSH tunnel terminal open.
- Confirm `curl http://127.0.0.1:5173/` succeeds on the RHEL server.
- Confirm Windows is opening `http://localhost:5173`, not the RHEL host's address.
- Ensure another local program is not already using Windows port 5173; if necessary, use `-L 15173:127.0.0.1:5173` and browse to `http://localhost:15173`.

## 12. Before any real or public deployment

The steps above are for a restricted demo. Before using real organisational or personal data, have the system owner and security administrator review the design and at least:

- Replace the Vite development server container with a production frontend build served by a production web server.
- Put a maintained TLS reverse proxy in front of the app; do not send passwords or bearer tokens over public plain HTTP.
- Keep PostgreSQL and the backend unreachable from user networks; allow only the frontend/reverse proxy and administrators to reach their required endpoints.
- Remove automatic demo accounts and seed passwords from the production deployment path; create the initial administrator through a controlled one-time setup.
- Require unique, strong passwords and a protected signing secret; document rotation and recovery procedures.
- Review role permissions, department-level data access, audit retention, backup retention, and recovery objectives with the organisation.
- Patch RHEL, container images, Python and npm dependencies; pin and scan deployable image versions.
- Test upgrades and database restoration on staging before applying them to the live database.
- Review Docker's firewall behaviour and RHEL SELinux policy with the server administrator. Do not assume firewalld rules alone restrict every published container port.

## References

- [Docker Engine installation on RHEL](https://docs.docker.com/engine/install/rhel/) — Docker repository setup, packages, service startup, and verification.
- [Red Hat Enterprise Linux 9 container documentation](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/building_running_and_managing_containers/) — Red Hat's container tooling guidance. Docker CE is a separate vendor distribution.
- [Project quick start and application overview](./README.md)
- [Full application test scenario](./FULL_TEST_SCENARIO.md)
