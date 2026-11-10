# Deploy ContinuityOS on AWS

This guide is a hands-on AWS Learner Lab proof of concept (PoC) for the ContinuityOS React/FastAPI/PostgreSQL application in this repository. It also describes a separate production target architecture. Follow the PoC steps first; do not treat the PoC as production-ready.

> **Important security boundary:** the current Compose setup runs Vite's development server and automatically creates demo accounts. The PoC below is for synthetic data and a restricted class demonstration only. It keeps the app reachable through an SSH tunnel, not through a public web port. Do not store real personal, financial, health, or business-confidential data in it.

## 1. What will be deployed

### Learner Lab PoC

```text
Student browser
    | http://localhost:5173 (local end of SSH tunnel)
    v
SSH, permitted only from your current public IP
    |
    v
One encrypted Amazon EC2 instance
    |-- Docker Compose: Vite dev server (127.0.0.1:5173)
    |-- FastAPI backend (127.0.0.1:8000)
    `-- PostgreSQL (127.0.0.1:5432, persistent Docker volume)

CloudTrail Event History / trail --> S3 audit bucket (if permitted)
CloudWatch metric filter + alarm --> SNS email (if permitted)
Encrypted S3 bucket <-- encrypted PostgreSQL dumps (if permitted)
```

The database, API, and frontend ports are not opened in the EC2 Security Group. The browser reaches the frontend through an SSH tunnel; the Vite container proxies `/api` requests to FastAPI on the private Compose network.

### Production target (not deployed by the PoC)

```text
Users -- HTTPS --> Route 53 / CloudFront + AWS WAF
                         |-- private S3 origin (production-built React files)
                         `-- /api/* --> Application Load Balancer
                                          --> private ECS/Fargate API tasks
                                          --> private Amazon RDS for PostgreSQL

Secrets Manager + KMS --> application secrets and encryption
CloudTrail --> protected log archive; CloudWatch alarms --> SNS
AWS Backup / RDS backups --> tested recovery process
```

The production target requires replacing the Vite development server, changing the demo account seeding approach, and deploying the app behind HTTPS. Services that are unavailable or restricted in Learner Lab must be marked **target architecture only** in the project report.

## 2. Prerequisites and safety checks

- An active AWS Learner Lab account and its permitted AWS Console session.
- A Windows computer with Windows OpenSSH (`ssh.exe`, `scp.exe`) and `tar.exe`.
- The project source locally, or access to its **private** Git repository.
- A region selected in the Learner Lab. Use that same region for EC2, S3, CloudTrail and CloudWatch where possible.
- A small amount of lab budget. A `t3.medium` with an encrypted 20–30 GiB gp3 EBS volume is a reasonable starting point for this multi-container demo, subject to lab availability and quota. Stop or terminate resources when finished.

Use only synthetic demo data. Do not make the repository public to transfer it, do not put `.env` or private keys in the repository/archive, and do not paste secret values into screenshots or reports.

## 3. Start the Learner Lab and record its limits

1. Start the Learner Lab session, open its AWS Console, and select the lab region.
2. In **EC2 → Instances**, confirm you can launch an instance and create a Security Group.
3. Keep the lab-provided AWS identity and credentials. Do not create IAM users, access keys, or broader policies to work around a permission error.
4. If a later step is denied, record the missing permission and document the feature as a target-architecture item instead.
5. Record the account ID and region for your report. Do not include temporary credentials.

## 4. Create a restricted EC2 instance

1. In **EC2 → Launch instance**, choose **Amazon Linux 2023**, a permitted x86_64 instance type (for example `t3.medium`), and an encrypted gp3 root volume of 20–30 GiB.
2. Create or select a key pair. Download the private key once and keep it outside the project folder. Never share it with teammates; each operator should have an individually controlled access path.
3. Create a Security Group such as `smca-poc-ec2` with these inbound rules:

   | Type | Port | Source | Purpose |
   |---|---:|---|---|
   | SSH | 22 | My IP (`/32`) only | Administrator access and SSH tunnel |

   Do **not** add inbound rules for 5173, 8000, 5432, or `0.0.0.0/0`. Keep the default outbound rule for this short demo unless your lab/network policy requires otherwise.
4. Launch the instance. Wait for status checks to pass and note its public IPv4 address. Confirm the instance's EBS volume is encrypted in **EC2 → Volumes**.
5. If your public IP changes, edit the SSH rule to the new **My IP** value. Do not temporarily open SSH to the whole internet.

## 5. Connect and install Docker

In Windows PowerShell, replace the key path and address:

```powershell
ssh.exe -i 'C:\path\to\smca-lab.pem' ec2-user@<EC2_PUBLIC_IP>
```

If Windows rejects the key because of file permissions, restrict access to your Windows account using the file's Properties → Security settings; do not upload the key to EC2.

On the EC2 instance:

```bash
sudo dnf update -y
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo docker --version
sudo docker compose version
```

The project requires Docker Compose v2 (`docker compose`). If the last command is unavailable, use Docker's current official Amazon Linux installation instructions to install the Compose plugin. Do not install the obsolete Python Compose v1 as a workaround.

## 6. Transfer the application

Choose **one** method.

### Option A — clone a private repository

On EC2, clone from a repository the team has already made private and authorized for this host:

```bash
sudo mkdir -p /opt/smca
sudo chown ec2-user:ec2-user /opt/smca
git clone <PRIVATE_REPOSITORY_URL> /opt/smca
cd /opt/smca
```

Use an approved private-repository authentication method. Do not put a personal access token in the clone URL or shell history. If the lab instance cannot access the private repository, use Option B.

### Option B — transfer a clean archive from Windows

From PowerShell on the development computer, create the archive from the directory above the project. Exclude local dependencies, generated files, databases, Git metadata, and secrets:

```powershell
Set-Location 'C:\Users\mejri\Desktop'
tar.exe -czf smca-project.tar.gz `
  --exclude='Project PCA\.git' `
  --exclude='Project PCA\frontend\node_modules' `
  --exclude='Project PCA\frontend\dist' `
  --exclude='Project PCA\backend\.venv' `
  --exclude='Project PCA\backend\__pycache__' `
  --exclude='Project PCA\backend\smca.db' `
  --exclude='Project PCA\.env' `
  'Project PCA'
scp.exe -i 'C:\path\to\smca-lab.pem' .\smca-project.tar.gz ec2-user@<EC2_PUBLIC_IP>:/tmp/
```

On EC2:

```bash
sudo mkdir -p /opt/smca
sudo tar -xzf /tmp/smca-project.tar.gz -C /opt/smca --strip-components=1
sudo chown -R ec2-user:ec2-user /opt/smca
rm -f /tmp/smca-project.tar.gz
cd /opt/smca
test -f docker-compose.yml && test -f backend/Dockerfile && test -f frontend/Dockerfile
```

If Windows `tar.exe` does not accept an exclude pattern, create a clean copy containing only source and required project configuration, then archive that copy. Verify it contains neither `.env` nor the local SQLite database before transfer.

## 7. Configure the app for the restricted demo

### Bind container ports to EC2 loopback

Edit `/opt/smca/docker-compose.yml`. Change **only** the three `ports` mappings as shown; retain the service names, environment variables, health checks, and `postgres_data` volume:

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

The backend and database remain reachable by the other containers using Compose service names. Binding these ports to loopback prevents external network clients from connecting directly to them. The EC2 Security Group remains a separate network control.

### Set unique demo secrets

On EC2, create the environment file with restricted permissions:

```bash
cd /opt/smca
umask 077
cp .env.example .env
chmod 600 .env
openssl rand -hex 32
openssl rand -hex 24
```

Edit `.env` with `nano .env` and replace **every** example value:

```dotenv
POSTGRES_DB=smca
POSTGRES_USER=smca
POSTGRES_PASSWORD=<unique-24-byte-random-hex-value>
SECRET_KEY=<unique-32-byte-random-hex-value>
DEMO_ADMIN_PASSWORD=<unique-strong-password>
DEMO_RISK_MANAGER_PASSWORD=<different-unique-strong-password>
DEMO_SMCA_MANAGER_PASSWORD=<different-unique-strong-password>
```

Paste the generated random values into the matching fields; use three different passwords for the demo accounts. Do not use the example `admin123` password. Keep the `.env` file private and out of Git. These seed passwords are used only when the accounts are first created; changing `.env` later does **not** change existing account passwords in PostgreSQL.

Validate the Compose configuration without displaying the resolved secrets:

```bash
sudo docker compose config --quiet
```

## 8. Build, start, and check the application

From `/opt/smca`:

```bash
sudo docker compose up -d --build
sudo docker compose ps
```

Wait for PostgreSQL and the backend to report healthy. Check from EC2:

```bash
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:5173/
```

The API health response should report an `ok` status and a connected database. The second command should return the frontend HTML.

If a service does not become healthy, inspect logs without printing `.env`:

```bash
sudo docker compose logs --tail=100 db
sudo docker compose logs --tail=100 backend
sudo docker compose logs --tail=100 frontend
```

### Open the app through an SSH tunnel

Keep the EC2 SSH session open, or open a second PowerShell window on Windows and run:

```powershell
ssh.exe -i 'C:\path\to\smca-lab.pem' -N -L 5173:127.0.0.1:5173 ec2-user@<EC2_PUBLIC_IP>
```

Keep the tunnel window open. On the same Windows computer, browse to [http://localhost:5173](http://localhost:5173). Do not browse to the EC2 address on port 5173; that port is intentionally not public.

Sign in using `admin` and the `DEMO_ADMIN_PASSWORD` set before the first database start. Confirm the dashboard, risk list, role-restricted views, treatment workflow, audit view, and PDF/XLSX exports. Use [FULL_TEST_SCENARIO.md](./FULL_TEST_SCENARIO.md) for the project workflow and its expected test values. Sign out after testing.

## 9. Apply the class-project security controls

### IAM and Zero Trust

Use the Learner Lab-provided identity for AWS console operations. Do not create long-lived access keys or store AWS credentials on the instance. If the lab permits an EC2 instance profile, assign only the permissions needed for the specific integration in use (for example, CloudWatch Agent delivery or writing backup objects to one bucket prefix). Do not attach broad administrator policies.

| Actor | Application access | AWS access |
|---|---|---|
| Administrator | App administration and user management | No AWS console access by default |
| SMCA Manager | Organization-wide governance, treatment approval, reports/audit | No AWS console access by default |
| Risk Manager | Organization-wide risk analysis and treatment proposals | No AWS console access by default |
| Department Manager | Department-scoped risk work | No AWS console access by default |
| Auditor | Read-only app access | No AWS console access by default |
| Lab operator | No extra app permissions | Lab-provided, time-limited AWS permissions; SSH only from an approved source IP |

The app's API enforces its own role and department checks; hiding a button in React is not an authorization control. The SSH tunnel and source-restricted Security Group limit network reachability, but do not replace app authentication. For a real company, use individually assigned AWS roles with MFA, time-limited access, separation of duties, and audited changes. Application MFA is not part of this PoC.

For the production target, a narrowly scoped backup policy can be proposed as follows. Replace all placeholders; attach it only to a dedicated EC2 role if the lab/administrator permits. This example allows access only to the backup bucket prefix and is not required for the SSH-tunnel PoC:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyBackupPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::<BUCKET_NAME>",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["smca-backups/*"]
        }
      }
    },
    {
      "Sid": "ManageBackupObjectsOnly",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::<BUCKET_NAME>/smca-backups/*"
    }
  ]
}
```

If the organization uses a customer-managed KMS key for S3, the role also needs explicitly scoped KMS permissions for that key. Do not add them unless that encryption design is actually used.

### Protect data and backups

- Treat risk registers, treatment plans, audit records, and exported reports as confidential business data. Store synthetic data only in the PoC.
- EBS root-volume encryption protects the EC2 volume at rest. For the production target, encrypt RDS, S3, snapshots, and backups; use KMS where available and document who controls/rotates keys.
- Keep backups in a separate, private S3 bucket in the same approved region when permitted. Enable **Block all public access**, default encryption, and versioning. Restrict access to the lab operator or a narrowly scoped role; set a lifecycle/retention period approved by the project owner.
- Do not assume a Docker volume is a backup. Test restoring a database dump into a separate test database before claiming the recovery process works.

If S3 is permitted, create a uniquely named **backup** bucket in the EC2 region using **S3 → Buckets → Create bucket**. Keep all four **Block Public Access** settings enabled, enable bucket versioning, and enable default encryption (SSE-S3 is sufficient for this PoC). Use a separate bucket for CloudTrail logs. On EC2, create a timestamped PostgreSQL dump:

```bash
cd /opt/smca
mkdir -p "$HOME/smca-backups"
chmod 700 "$HOME/smca-backups"
umask 077
BACKUP="$HOME/smca-backups/smca-$(date +%Y%m%d-%H%M%S).dump"
sudo docker compose exec -T db sh -lc 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$BACKUP"
ls -lh "$BACKUP"
aws s3 cp "$BACKUP" "s3://<BUCKET_NAME>/smca-backups/$(basename "$BACKUP")" --sse AES256
```

Replace `<BUCKET_NAME>` with the bucket you created. `--sse AES256` uses S3-managed encryption; use the approved KMS key instead if the project explicitly configured one and the role permits it. Do not upload if the lab has not granted the required S3 access. A successful upload is not proof of recovery: arrange and document a restore test separately.

The `aws s3 cp` command requires an EC2 instance profile that grants the narrow S3 permissions above. Check with `aws sts get-caller-identity`; do **not** copy Learner Lab credentials or access keys onto EC2. If the lab does not allow an instance profile, copy the dump to Windows with `scp.exe` (replace the filename and address), then upload it from the AWS Console's S3 upload page using your authorized lab session:

```powershell
scp.exe -i 'C:\path\to\smca-lab.pem' ec2-user@<EC2_PUBLIC_IP>:/home/ec2-user/smca-backups/<DUMP_FILE> .\
```

### CloudTrail, CloudWatch, and an alert

1. In **CloudTrail → Event history**, filter for EC2 management events such as `AuthorizeSecurityGroupIngress`. Review the event time, actor, source address, and request parameters.
2. If permitted, create a separate, uniquely named CloudTrail bucket using **S3 → Buckets → Create bucket**. Keep all public-access blocks enabled, use default encryption, and do not enable public website hosting.
3. In **CloudTrail → Trails → Create trail**, give the trail a name, select the dedicated S3 bucket, enable log-file validation if available, and log **Management events** for both read and write activity. Do not enable data events unless the assignment specifically requires them; they can create additional charges.
4. If permitted, select delivery to **CloudWatch Logs** while creating/editing the trail. Use a dedicated log group and allow the console to create the service role only if the Learner Lab permits it. Do not log application data as CloudTrail events.
5. In **CloudWatch → Logs → Log groups**, open the trail's log group and create a metric filter for Security Group changes using:

   ```text
   { ($.eventSource = "ec2.amazonaws.com") && (($.eventName = "AuthorizeSecurityGroupIngress") || ($.eventName = "RevokeSecurityGroupIngress")) }
   ```

   Publish a metric such as `SMCA/SecurityGroupChange` with value `1`. Create a CloudWatch alarm for a value greater than or equal to `1` in one period. Optionally create an SNS topic, subscribe your email, confirm the subscription, and select the topic as the alarm action.
6. Demonstrate detection by adding and then removing a harmless temporary inbound rule on **your own PoC Security Group**, restricted to your IP and a non-application port. Confirm the CloudTrail event and, if configured, alarm/notification. Do not open SSH or any app/database port to the internet for this test.
7. If CloudTrail-to-CloudWatch or SNS is blocked by Learner Lab permissions, capture the Event History evidence and document the metric filter/notification as target architecture. Do not broaden permissions to force the integration.

Capture screenshots with account IDs, public IPs, email addresses, and sensitive values redacted. Keep the event JSON needed for the report, but do not publish secrets or user data.

## 10. Risk register starter

Use a 1–5 scale for likelihood (`L`) and impact (`I`); initial score = `L × I`. These are **discussion estimates**, not measured results. Adjust them for the selected SME, evidence, and data classification, then record an owner and residual rating in the project report.

| Risk | Example initial rating | PoC treatment | Residual risk to discuss |
|---|---:|---|---|
| Accidental exposure of SSH, API, frontend, or database ports | L3 × I5 = 15 | SSH from My IP only; no app/database Security Group rules; bind Compose ports to loopback; verify externally | Medium: mistaken rule changes remain possible |
| Weak or leaked database/JWT/demo credentials | L3 × I5 = 15 | Unique generated secrets; `.env` mode 600; exclude from Git; use synthetic accounts | Medium: demo account seeding remains; rotate/reset before reuse |
| Compromised or over-privileged AWS identity | L2 × I5 = 10 | Use lab role only; no static keys; avoid policy escalation; audit via CloudTrail | Medium: lab role may be broader than the workload needs |
| Unauthorized access to risks or reports | L3 × I4 = 12 | App API role/department checks; restrict tunnel access; test with each role | Medium: PoC has no app MFA and is not production hardened |
| PostgreSQL data loss or EC2 failure | L3 × I4 = 12 | Persistent Docker volume; encrypted EBS; encrypted off-instance dump if allowed; document restore test | Medium/high until restores and recovery objectives are proven |
| Backup deletion, public exposure, or lost encryption key | L2 × I5 = 10 | S3 Block Public Access, versioning, encryption, narrow access, retention, restore test | Medium: Learner Lab account/resource lifecycle may limit retention |
| Undetected security-group change or compromised account | L3 × I4 = 12 | CloudTrail Event History/trail; CloudWatch metric filter/alarm; SNS if available | Medium: delivery/alert permissions and retention may be constrained |
| Vulnerable or tampered container/dependency image | L3 × I4 = 12 | Use reviewed source and pinned project dependencies; update images; keep PoC private | Medium: image scanning/signing and release controls are not included |
| Regional/service outage or accidental resource termination | L2 × I4 = 8 | Document dependencies and cleanup; retain a separate backup when allowed | Medium/high: PoC is single-instance and has no high availability |

For on-premises-to-cloud migration risks, add the source environment's existing risks (for example, incomplete inventory, insecure transfer, compatibility failure, or an unverified legacy backup) and record the migration control and residual risk. Do not present this starter table as a completed assessment.

## 11. Incident-response exercise

Use a controlled Security Group misconfiguration/detection scenario on your own EC2 instance:

1. **Preparation:** record the EC2 ID, Security Group ID, approved SSH source IP, account/region, CloudTrail location, and the person authorized to respond. Keep a known-good Security Group rule set.
2. **Detection and analysis:** use the CloudWatch alarm (if available) or CloudTrail Event History to identify `AuthorizeSecurityGroupIngress`. Record event time, principal, source IP, affected group, and exact changed rule. Do not include credentials in evidence.
3. **Containment:** if an unauthorized rule exists, remove only that rule, restore SSH to the approved `/32`, and verify no app/database inbound rule was added. If identity compromise is suspected, notify the lab instructor/account owner and follow their credential/session revocation instructions.
4. **Eradication and recovery:** review related CloudTrail events, verify the Security Group and instance state, check application health and logs, and restore from a known-good backup only if data integrity is affected.
5. **Lessons learned:** document the timeline, evidence locations, impact, root cause, residual risk, notification decision, and preventive action (for example, tighter change access, an alarm, or a tested recovery runbook).

Keep the test within resources assigned to your group and the Learner Lab rules. Preserve CloudTrail evidence and relevant timestamps; do not run tests against other accounts or public systems.

## 12. Operate, stop, and clean up

Useful commands from `/opt/smca`:

```bash
sudo docker compose ps
sudo docker compose logs --tail=100
sudo docker compose restart
sudo docker compose down
```

`docker compose down` preserves the named `postgres_data` volume. **Do not run `docker compose down -v`** unless permanent database deletion is intended and approved.

Before ending the lab:

1. Create and verify any required backup; note the bucket/key and encryption setting without recording credentials.
2. Stop the EC2 instance when temporarily finished. Stopping does not remove EBS storage charges and may change its public IP on restart.
3. Terminate the EC2 instance and remove unneeded resources only when the PoC is complete and data retention has been addressed. Check for volumes, snapshots, S3 buckets/objects, CloudTrail trails, CloudWatch log groups/alarms, SNS subscriptions, and Elastic IPs that may continue to incur cost.
4. Do not delete the only copy of required evidence or backups. Confirm with the project owner before deleting shared resources.

## 13. Troubleshooting

| Symptom | Checks |
|---|---|
| SSH times out | Instance running; correct public IP and key; Security Group SSH source matches your current IP; lab session active |
| `docker compose` not found | Install the current Compose v2 plugin using Docker's official Amazon Linux instructions |
| `docker compose config --quiet` fails | Check `.env` exists and each required variable is set; never paste secret values into logs/chat |
| Backend unhealthy | `sudo docker compose logs --tail=100 db backend`; verify DB health and `.env`; do not delete the data volume to troubleshoot |
| Frontend works but API fails | Check backend health, frontend logs, and `VITE_BACKEND_PROXY: http://backend:8000` in Compose |
| Browser cannot open app | Keep SSH tunnel running; use `http://localhost:5173`; verify the EC2 loopback curl succeeds |
| CloudTrail, CloudWatch, SNS, or S3 action denied | Record the permission limitation and use the permitted evidence path; do not create broader credentials or policies |

## 14. Production readiness: changes required before real data or public access

Do not expose the current Compose deployment directly to the internet. Before production, at minimum:

- Replace Vite's dev server with `npm run build` artifacts served by a maintained production web server; route `/api` through a protected reverse proxy or CloudFront/API origin.
- Require HTTPS with managed certificates; restrict API/database network paths to only required security groups and private subnets.
- Move PostgreSQL to private Amazon RDS with encryption, automated backups, monitoring, tested point-in-time recovery, and a defined RPO/RTO.
- Move app secrets to Secrets Manager/Parameter Store; use scoped IAM roles, MFA, individual operator identities, and key rotation.
- Remove production demo-account seeding and unsafe code defaults; establish the first administrator through a controlled process. The current backend creates seeded users on startup, so changing only the deployment configuration is not sufficient to make it production-safe.
- Review app authorization, password policy, MFA requirements, audit-log integrity/retention, dependency/image scanning, patch cadence, incident contacts, and applicable privacy/regulatory obligations.
- Deploy across multiple Availability Zones where required; add CloudWatch dashboards/alarms, SNS routing, S3 log retention, backup restore tests, and an approved change/release process.

## 15. Project evidence and report checklist

Keep the PoC and target architecture clearly separated. Gather:

- SME scenario, users, business processes, data inventory/classification, and application data flows.
- A minimum eight-item risk assessment with likelihood, impact, treatment, owner, and residual rating.
- An architecture diagram identifying deployed PoC components, target-only services, allowed network flows, and trust boundaries.
- IAM/app-role matrix, least-privilege example policy, MFA/separation-of-duties approach, and Zero Trust explanation.
- Encryption, secret-handling, backup/versioning/retention, and recovery objectives; include restore-test evidence or clearly mark it as not tested.
- CloudTrail event evidence, CloudWatch dashboard/alarm/metric-filter configuration, and SNS notification evidence if available.
- Incident-response timeline, evidence retained, containment/recovery actions, lessons learned, PoC limitations, and recommendations.
- A short demo that proves one preventive control (for example, database ports not reachable from outside) and one detection/audit control (for example, a CloudTrail Security Group change).

The lab brief asks for an approximately 12-page technical report and a 20-minute presentation/demo. This deployment guide is a runbook, not a substitute for the report's analysis, references, screenshots, and justifications.

## References

- [Project quick start and application overview](./README.md)
- [Full application test scenario](./FULL_TEST_SCENARIO.md)
- [AWS EC2 User Guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html)
- [AWS Security Groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html)
- [AWS CloudTrail Event history](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html)
- [CloudWatch metric filters](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/MonitoringLogData.html)
- [Amazon S3 Block Public Access](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)
- [Docker Engine on Amazon Linux](https://docs.docker.com/engine/install/)
