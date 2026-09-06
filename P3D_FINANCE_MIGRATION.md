# P3D Finance migration

Date: `2026-09-06`

## Safety model

- The legacy tables are retained unchanged.
- New budgeting data lives only in `finance_*` tables.
- Every migrated recurring item and installment retains its legacy ID and link.
- The migration is guarded by `p3d-finance-v1-20260906`; reruns are no-op.
- A full gzip JSON database backup and a source snapshot were created under ignored `.local/backups/` before the migration.

## Production audit and result

| Category | Found | Migrated | Active in P3D Finance | Preserved for review |
| --- | ---: | ---: | ---: | ---: |
| Cashflow items | 17 | 17 | Based on legacy activity and known current rules | 10 require metadata review |
| Installments | 34 | 34 | 8 canonical active installments | 26 inactive legacy/duplicate rows |
| Card accounts | 5 | Referenced, not copied | 5 | 0 |
| Car loans | 1 | Kept in `car_loans` | 1 | 0 |
| Savings goals | 0 | 1 new goal | 1 | Balance intentionally blank |
| Scenarios | 0 | 1 new scenario | 0 | Future housing scenario is inactive |

All eight required October 2026 installment records were matched. None were missing.

## New tables

- `finance_recurring_items`
- `finance_installments`
- `finance_month_entries`
- `finance_savings_goals`
- `finance_scenarios`
- `finance_settings`
- `finance_migration_log`

Historical bank/report tables remain in the database for preservation, but the P3D Finance UI does not read or expose them.

## Intentional review queue

Seven canonical installments have `payer = unassigned`. The in-app one-time wizard asks only who pays each installment. `Ακουστικό Μητέρας` is already marked as paid by `Μητέρα`, with a pending reimbursement of `39.58 €`, because this is explicit in the requirements.

## Commands

Read-only preview:

```powershell
python scripts/migrate_p3d_finance.py --dry-run
```

Idempotent migration:

```powershell
python scripts/migrate_p3d_finance.py
```

Tests:

```powershell
npm test
npm run check
```
