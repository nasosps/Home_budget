# Supabase Setup

This repo is moving toward a private single-user budget app on Supabase.

## Security model

- The web app can be public on the internet.
- The data is not public.
- Every table is protected with Row Level Security.
- Only the owner account can read or write records.
- Raw bank PDFs should stay local by default and be parsed from `bank_files/`.

## Dedicated project note

- This app should live in its own dedicated Supabase project.
- The setup now assumes the default `public` schema of that new project.
- You do not need custom schema exposure for this version.
- The storage bucket for this app is `home-budget-imports`.

## Recommended auth setup

1. Create a new Supabase project just for Home Budget.
2. Enable Email auth.
3. Prefer magic link for simplicity, or email/password with MFA later.
4. Disable open signups if possible, or keep the owner-only RLS policies from the migration so non-owner accounts cannot access data.
5. After your first login, run:

```sql
update public.profiles
set is_owner = true
where email = lower('nasosps@outlook.com');
```

## Storage convention

- Bucket: `home-budget-imports`
- Private bucket only
- Path convention: `<auth.uid()>/incoming/<filename>.pdf`

## Owner account

- Allowed owner email for this app: `nasosps@outlook.com`
- The SQL migration also expects the authenticated JWT email to match this address before any table access is allowed.

## Local importer

Fastest local flow:

```powershell
python scripts/process_bank_files.py
```

On Windows you can also run:

```powershell
run_bank_import.cmd
```

If you want the folder to auto-process new PDFs continuously, run:

```powershell
python scripts/watch_bank_files.py
```

Or on Windows:

```powershell
run_bank_watch.cmd
```

If you want the split steps instead, use the local parser first:

```powershell
python scripts/import_alpha_pdfs.py
```

Outputs are written under `.local/imports/` and are ignored by git.

## Local sync to Supabase

1. Copy `.env.example` to `.env`.
2. Fill `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
3. Make sure you have already logged into the app once with `nasosps@outlook.com`.
4. Run:

```powershell
python scripts/sync_to_supabase.py
```

The sync reads parsed JSON from `.local/imports/parsed/` and writes a local run log under `.local/sync/`.

## One-off Firebase migration

If you want to pull your existing manual data from the old Firebase app into Supabase without typing everything again:

```powershell
python scripts/migrate_firebase_to_supabase.py --email nasosps@outlook.com
```

The script will prompt for the old Firebase password locally and log the run under `.local/migrations/`.

## Local manual snapshot import

If you want to seed the manual budget state from a local-only JSON snapshot instead:

```powershell
python scripts/import_manual_snapshot.py --input .local/manual_snapshot.json
```

This is useful for one-off reconstruction from screenshots or exported notes without committing private values into git.

## Why this split is safer

- The public website never needs direct access to raw bank PDFs.
- Bank exports stay on your machine unless you explicitly choose to upload them.
- Supabase stores normalized transactions and app state behind RLS.
