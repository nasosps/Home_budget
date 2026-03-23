# Supabase Rebuild Plan

## Objective

Rebuild the current Firebase-based budget app as a private Supabase app with:

- single-user private access
- Row Level Security on all data
- local-first bank PDF imports
- repeatable work logging in this repo

## Recommended architecture

### Public web app

- Hosted anywhere
- Uses Supabase Auth for login
- Uses Supabase client with publishable key
- Reads only data allowed by RLS

### Supabase backend

- Postgres for normalized budget data
- dedicated Supabase project for Home Budget
- default schema: `public`
- RLS locked to the owner account
- private storage bucket for optional uploaded import files
- future Edge Functions for automation around already-normalized files

### Local import runner

- Reads raw bank PDFs from `bank_files/`
- Parses statements locally with Python
- Writes normalized JSON into `.local/imports/`
- Later can upsert into Supabase using local secrets from `.env`

## Why local-first imports are important

- Raw PDF exports contain more sensitive details than the app actually needs.
- PDF parsing is easier and more reliable locally with Python tools like `pdfplumber`.
- It avoids pushing bank exports to the internet unless you explicitly decide to.

## Migration phases

1. Create a new Supabase project for Home Budget and run the SQL migration.
2. Mark your email profile as `is_owner = true`.
3. Disable open signup if desired.
4. Create the first importer run from local PDFs.
5. Sync parsed JSON into Supabase.
6. Build the new UI against Supabase tables.
7. Retire Firebase after data is verified.

## Immediate next implementation targets

- add local `sync_to_supabase.py`
- rebuild UI with Supabase Auth
- create import review screen before applying parsed data

## Locked owner identity

- Primary owner email: `nasosps@outlook.com`
- App access should remain owner-only even if the site itself is publicly reachable
