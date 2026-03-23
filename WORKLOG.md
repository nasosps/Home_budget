# Work Log

## 2026-03-23

### Goal
Harden the app so budget data is private, prepare a safer import flow for bank files, and keep a local progress trail inside the repo.

### Completed
- Reviewed the current app structure and identified that the app is a single-page static site backed by Firebase Auth and Firestore.
- Confirmed the repo did not include `firebase.json` or Firestore security rules, which means the most important access control was not versioned here.
- Verified there is now a local `bank_files/` folder with sample PDF exports from the bank.
- Added `.gitignore` rules so raw bank files stay local and are not committed accidentally.
- Started this persistent work log.
- Added a Supabase scaffold with migration SQL, owner-only RLS model, and storage policy groundwork.
- Locked the new Supabase design to the owner email `nasosps@outlook.com`.
- Built a local Alpha Bank PDF parser at `scripts/import_alpha_pdfs.py`.
- Parsed the current sample PDFs successfully into `.local/imports/parsed/`.
- Created a local import manifest log at `.local/imports/import-manifest.jsonl`.
- Pivoted again to a dedicated Supabase project so Home Budget has its own isolated backend.
- Added a local `scripts/sync_to_supabase.py` tool for idempotent sync into Supabase.
- Verified the sync tool with a local dry run across all parsed sample files.
- Created a local sync run log at `.local/sync/sync-log.jsonl`.
- Configured the new dedicated Supabase project URL and secret API key in local `.env`.
- Ran the first real sync successfully into Supabase.
- Confirmed 3 import files were applied, with 45 card transactions and 30 bank transactions stored.
- Added a new frontend module layer in `app.js` to replace the old Firebase client logic with Supabase Auth and Supabase data access.
- Added a `PDF Sync` overview block in the UI so imported bank files are visible from the app.
- Added a one-command local pipeline with `scripts/process_bank_files.py` and `run_bank_import.cmd` so new bank PDFs can be dropped into `bank_files/` and processed with one run.
- Added `scripts/migrate_firebase_to_supabase.py` so old manual Firebase data can be copied into Supabase instead of being retyped by hand.
- Extended import metadata written into Supabase so imported files keep more banking context.
- Ran the new PDF processing pipeline successfully against the current sample files.
- Used temporary local HTTP servers for browser smoke tests during the migration work, then shut them down after testing.
- Restored the existing `created by NAEL` footer while keeping the frontend migration on `app.js`.
- Added watcher mode with `scripts/watch_bank_files.py` and `run_bank_watch.cmd` so dropped bank PDFs can trigger the local pipeline automatically.
- Extended the parser to recognize the older card account summary PDFs via OCR and synced all 9 local PDFs into Supabase.
- Imported a local manual snapshot derived from the old app screenshots into Supabase.
- Verified the imported manual totals match the old screenshots:
  income `2042.63`
  fixed expenses `1230.00`
  Energy installments `234.42`
  Alpha installments `161.16`
  Pancreta installments `0.00`
  total card installments `395.58`
- Confirmed the active Supabase state now includes 11 cashflow rows, 1 active car loan, 9 active installment plans, 45 card transactions, 30 bank transactions and 9 import files.
- Added a persistent global month selector in the migrated UI so the cards view, car loan widget and summary can be projected for any chosen month instead of only the current month.
- Wired the month selector into `localStorage` so the last selected month is remembered between reloads.
- Smoke-tested the logged-out app locally after the month selector wiring; no runtime JavaScript errors were reported.
- Prepared the repository for git push while keeping raw bank PDFs, local screenshots, `.env`, `.local/` outputs and Playwright artifacts out of version control.

### Current Focus
- Final signed-in UI validation of the new month selector against the Supabase-backed app.
- Prepare the repo for a clean git push after the last authenticated check.

### Risks / Notes
- The public Firebase config in the client is not the real problem by itself; the critical issue is whether Firebase Auth providers and Firestore rules are properly locked down.
- If Email/Password sign-up is enabled in Firebase, someone could potentially create an account unless we disable sign-up or enforce strict Firestore rules for a single allowed user.
- Existing `index.html` has a staged user change unrelated to this work; do not overwrite it.
- Owner account selected for the Supabase rebuild: `nasosps@outlook.com`.
- The local import manifest currently records each parser run, so reruns append new entries instead of replacing old ones.
- The initial real Supabase sync used a secret API key stored locally in `.env`; rotate the key later if you want to invalidate the one shared during setup.
- Raw bank PDFs must remain local only and are intentionally excluded from git.
- Temporary local `http.server` windows during testing are only local browser test servers on `127.0.0.1` and are not public internet exposure.
- The three local screenshots from the old app are now treated as local-only inputs and are excluded from git with `old_*.png`.
- One older OCR summary PDF still has a slightly noisy `minimum payment` field, but the due balance and dates are being parsed correctly.

### Next Steps
- Sign into the migrated app and verify the authenticated screens render the imported Supabase data as expected for multiple selected months.
- Decide whether to pull extra historical data from Firebase or keep the screenshot-based manual snapshot as the authoritative starting point.
- Prepare the repo for git push without raw PDFs, screenshots or local secrets.
