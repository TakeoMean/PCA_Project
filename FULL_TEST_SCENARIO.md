# Full application test scenario

Follow this walkthrough to test the risk register, treatment approval, action tracking, residual-risk reassessment, user roles, and report exports.

## What you need

- The application running:
  - Frontend: <http://localhost:5173>
  - API: <http://localhost:8000>
- Use the demo accounts only for this local test. Do not use these passwords for real accounts.

| Account | Username | Password | Used for |
|---|---|---|---|
| Administrator | `admin` | `admin123` | Create the test risk, approve the plan, complete reassessment, create an Auditor |
| Risk Manager | `riskmanager` | `admin123` | Propose the treatment and complete its assigned action |

This local setup uses the SQLite demo database. The test creates a new risk and an Auditor account; it does not require changing the seeded risks.

## Test story

An IT production service depends on a single server and power feed. A prolonged power failure could interrupt critical services. The organisation will reduce the risk by adding a tested backup power arrangement and recording the recovery procedure.

Expected ratings:

- Initial probability: **4**
- Initial impact: **5**
- Initial score: **4 × 5 = 20 / 25 — Critical**
- Residual probability after treatment: **2**
- Residual impact after treatment: **3**
- Residual score: **2 × 3 = 6 / 25 — Moderate**

## Part 1 — Sign in and record the risk

1. Open <http://localhost:5173>.
2. Sign in as **Administrator** (`admin` / `admin123`).
3. On **Overview**, confirm that the dashboard loads and shows the existing demo risks.
4. Open **Risk register**.
5. Expand **Register a new risk** and enter:

   | Field | Value |
   |---|---|
   | Risk ID | `TEST-BC-001` |
   | Risk name | `Production power failure` |
   | Category | `Technical` |
   | Department | `IT` |
   | Activity | `Application Hosting` |
   | Owner | System Administrator (or leave assigned to yourself) |
   | Threat | `Prolonged power outage` |
   | Vulnerability | `No tested backup power feed` |
   | Probability | `4` |
   | Impact | `5` |
   | Description | `A prolonged power outage may stop the production service and interrupt critical business applications.` |
   | Potential consequences | `Service unavailability, delayed business operations, and recovery costs.` |

6. Click **Save risk**.
7. Find `TEST-BC-001` in the risk table. It should show a score of **20/25** and severity **Critical**.

If the form says the risk ID already exists, use a different ID (for example `TEST-BC-002`) and use that new ID in the remaining steps.

## Part 2 — Propose a treatment as the Risk Manager

1. Sign out using the arrow beside your profile.
2. Sign in as **Risk Manager** (`riskmanager` / `admin123`).
3. Open **Treatment plans** and expand **Propose a treatment plan**.
4. Enter:

   | Field | Value |
   |---|---|
   | Risk | `TEST-BC-001 · Production power failure` |
   | Strategy | `Reduce` |
   | Start date | Today, or leave empty |
   | Target date | A future date about one week from now |
   | Treatment plan | `Install a backup power feed for the production environment, document the switchover procedure, and test the service recovery process.` |
   | Expected outcome | `Critical applications remain available or can be restored within the agreed recovery time during a power failure.` |
   | Resources required | `Facilities team, IT operations, backup power equipment, and a scheduled recovery test.` |

5. Click **Submit for review**.
6. Confirm the new plan appears with status **Proposed**. The app should show that it is waiting for review.

## Part 3 — Review and approve as the Administrator

1. Sign out and sign back in as **Administrator** (`admin` / `admin123`).
2. Open **Treatment plans** and find the `TEST-BC-001` plan.
3. Check that the strategy and treatment description are correct.
4. Click **Approve plan**.
5. Enter this review note when prompted: `Approved for implementation. Record the backup-power test result before completion.`
6. Confirm the plan status changes to **Approved** and the review note is displayed.
7. Click **Start plan**. The plan should change to **In progress**.

## Part 4 — Add and complete a delivery action

1. On the same plan, use **Add delivery action** and enter:

   | Field | Value |
   |---|---|
   | Action title | `Install and test backup power feed` |
   | Owner | `Risk Manager` |
   | Due date | A future date |
   | Expected result | `Backup feed supplies the production environment and the failover test passes.` |
   | Resources needed | `Facilities technician, IT operations, and a scheduled maintenance window.` |

2. Click **Add action**. The new action should appear as **Planned**.
3. Sign out and sign in as **Risk Manager**.
4. Open **Treatment plans**. Change the action from **Planned** to **In progress**.
5. Change it from **In progress** to **Completed**.
6. When prompted, enter the action result: `Backup feed installed; failover test passed and the production service remained available.`
7. Confirm the action now shows **Completed** and displays the result.

The action owner can update their own action. A user who is not the owner needs a treatment-management role.

## Part 5 — Reassess the residual risk

1. Sign out and sign back in as **Administrator**.
2. Open **Treatment plans** and find the `TEST-BC-001` plan.
3. Click **Complete & reassess**.
4. Enter:
   - Residual probability: `2`
   - Residual impact: `3`
5. Confirm the plan changes to **Completed** and displays residual score **6/25 — Moderate**.

The app requires at least one action, requires all actions to be completed, and records the result before allowing the plan to be completed.

## Part 6 — Verify the risk and audit history

1. Open **Risk register**.
2. Search for `TEST-BC-001`.
3. Confirm the risk now shows a residual score of **6/25** and severity **Moderate**. Its original inherent assessment remains available in the risk data; the residual assessment is recorded separately.
4. Open **Reports & audit**.
5. Check the activity list for entries relating to the risk, treatment proposal/review, action changes, and completed reassessment.

## Part 7 — Export reports

1. Stay signed in as Administrator and open **Reports & audit**.
2. Click **Export PDF**. Confirm that a PDF file downloads.
3. Click **Export Excel**. Confirm that an XLSX file downloads.
4. Open each file and check that `TEST-BC-001` and its latest risk score appear in the report.

## Part 8 — Check read-only Auditor access (optional)

1. While signed in as Administrator, open **People & access**.
2. Expand **Invite a user** and create:

   | Field | Value |
   |---|---|
   | Full name | `Test Auditor` |
   | Username | `auditor-test` |
   | Email | `auditor-test@example.test` |
   | Temporary password | `Audit-demo-2026` |
   | Role | `Auditor` |
   | Department | Leave as `No department` |

3. Click **Create account**.
4. Sign out and sign in as `auditor-test` with the password above.
5. Confirm that the Auditor can view the Risk register and Reports & audit, but does not see **People & access** or the controls for creating risks and treatment plans.

## If something does not work

- **Cannot sign in:** Confirm the backend is running at <http://localhost:8000/api/health> and use the exact demo username and password.
- **Treatment will not complete:** Confirm it is **In progress**, at least one action exists, every action is **Completed**, and each completed action has a result.
- **Approval is unavailable:** Sign in as Administrator or SMCA Manager, not the user who proposed the plan.
- **An action cannot be updated:** Sign in as the action owner or a role with treatment-management permission.
- **Could not open the app:** Restart the backend and frontend using the project README. This local run uses SQLite; PostgreSQL requires starting the Docker Compose setup.

## Resetting the test data

The scenario adds records to the local database. Use a new risk ID if repeating it. To reset the entire local demo database, stop the backend first and remove `backend/smca.db`; the demo roles, users, departments, activities, and sample risks will be recreated on the next backend start. Do not delete the database if you need to keep existing local data.
