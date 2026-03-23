create extension if not exists pgcrypto;

grant usage on schema public to authenticated, service_role;
grant all on all tables in schema public to authenticated, service_role;
grant all on all sequences in schema public to authenticated, service_role;
alter default privileges in schema public grant all on tables to authenticated, service_role;
alter default privileges in schema public grant all on sequences to authenticated, service_role;

do $$
begin
    if not exists (
        select 1
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where t.typname = 'cashflow_kind' and n.nspname = 'public'
    ) then
        create type public.cashflow_kind as enum ('income', 'expense');
    end if;

    if not exists (
        select 1
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where t.typname = 'import_file_kind' and n.nspname = 'public'
    ) then
        create type public.import_file_kind as enum ('bank_account_pdf', 'card_statement_pdf', 'manual_csv', 'other');
    end if;

    if not exists (
        select 1
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where t.typname = 'import_job_status' and n.nspname = 'public'
    ) then
        create type public.import_job_status as enum ('queued', 'processing', 'applied', 'failed');
    end if;

    if not exists (
        select 1
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where t.typname = 'installment_status' and n.nspname = 'public'
    ) then
        create type public.installment_status as enum ('active', 'completed', 'cancelled');
    end if;

    if not exists (
        select 1
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where t.typname = 'transaction_direction' and n.nspname = 'public'
    ) then
        create type public.transaction_direction as enum ('credit', 'debit');
    end if;
end $$;

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null unique,
    full_name text not null default '',
    is_owner boolean not null default false,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint profiles_email_lowercase check (email = lower(email))
);

create table if not exists public.bank_accounts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    bank_name text not null default 'Alpha Bank',
    label text not null,
    iban text,
    iban_masked text,
    is_active boolean not null default true,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    unique (user_id, label)
);

create table if not exists public.card_accounts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    issuer text not null default 'Alpha Bank',
    label text not null,
    last4 text,
    card_number_masked text,
    is_active boolean not null default true,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    unique (user_id, label, last4)
);

create table if not exists public.cashflow_items (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    kind public.cashflow_kind not null,
    title text not null,
    amount numeric(12, 2) not null check (amount >= 0),
    source text not null default 'manual',
    notes text not null default '',
    is_active boolean not null default true,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.car_loans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    label text not null default 'Car Loan',
    lender text not null default 'Unknown',
    start_date date not null,
    total_months integer not null check (total_months > 0),
    monthly_payment numeric(12, 2) not null check (monthly_payment > 0),
    down_payment numeric(12, 2) not null default 0 check (down_payment >= 0),
    balloon numeric(12, 2) not null default 0 check (balloon >= 0),
    is_active boolean not null default true,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.installment_plans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    card_account_id uuid references public.card_accounts(id) on delete set null,
    title text not null,
    total_amount numeric(12, 2) not null check (total_amount > 0),
    total_months integer not null check (total_months > 0),
    monthly_payment numeric(12, 2) not null check (monthly_payment > 0),
    start_date date not null,
    status public.installment_status not null default 'active',
    notes text not null default '',
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.import_files (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    original_name text not null,
    storage_path text,
    sha256 text not null,
    file_kind public.import_file_kind not null,
    parser_key text not null default 'local.alpha_pdf.v1',
    statement_from date,
    statement_to date,
    last_status public.import_job_status not null default 'queued',
    raw_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    unique (user_id, sha256)
);

create table if not exists public.import_jobs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    import_file_id uuid not null references public.import_files(id) on delete cascade,
    status public.import_job_status not null default 'queued',
    summary jsonb not null default '{}'::jsonb,
    error_text text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.bank_transactions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    bank_account_id uuid references public.bank_accounts(id) on delete set null,
    import_file_id uuid references public.import_files(id) on delete set null,
    entry_index integer,
    posted_on date not null,
    effective_on date,
    description text not null,
    amount numeric(12, 2) not null,
    direction public.transaction_direction not null,
    transaction_ref text,
    location_code text,
    fingerprint text not null,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default timezone('utc', now()),
    unique (user_id, fingerprint)
);

create table if not exists public.card_transactions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    card_account_id uuid references public.card_accounts(id) on delete set null,
    import_file_id uuid references public.import_files(id) on delete set null,
    entry_index integer,
    posted_on date not null,
    merchant text not null,
    posted_time text,
    amount numeric(12, 2) not null,
    direction public.transaction_direction not null,
    transaction_type text not null default '',
    status_text text not null default '',
    category text not null default '',
    fingerprint text not null,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default timezone('utc', now()),
    unique (user_id, fingerprint)
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, email, full_name, is_owner)
    values (
        new.id,
        lower(coalesce(new.email, '')),
        coalesce(new.raw_user_meta_data ->> 'full_name', ''),
        false
    )
    on conflict (id) do update
    set email = excluded.email,
        full_name = case
            when excluded.full_name = '' then public.profiles.full_name
            else excluded.full_name
        end,
        updated_at = timezone('utc', now());

    return new;
end;
$$;

create or replace function public.is_owner()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.profiles
        where id = auth.uid()
          and is_owner = true
          and email = lower('nasosps@outlook.com')
          and lower(coalesce(auth.jwt() ->> 'email', '')) = lower('nasosps@outlook.com')
    );
$$;

create trigger set_profiles_updated_at
before update on public.profiles
for each row
execute procedure public.set_updated_at();

create trigger set_bank_accounts_updated_at
before update on public.bank_accounts
for each row
execute procedure public.set_updated_at();

create trigger set_card_accounts_updated_at
before update on public.card_accounts
for each row
execute procedure public.set_updated_at();

create trigger set_cashflow_items_updated_at
before update on public.cashflow_items
for each row
execute procedure public.set_updated_at();

create trigger set_car_loans_updated_at
before update on public.car_loans
for each row
execute procedure public.set_updated_at();

create trigger set_installment_plans_updated_at
before update on public.installment_plans
for each row
execute procedure public.set_updated_at();

create trigger set_import_files_updated_at
before update on public.import_files
for each row
execute procedure public.set_updated_at();

drop trigger if exists on_auth_user_created_home_budget on auth.users;
drop trigger if exists on_auth_user_created_budget on auth.users;
create trigger on_auth_user_created_budget
after insert on auth.users
for each row
execute procedure public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.bank_accounts enable row level security;
alter table public.card_accounts enable row level security;
alter table public.cashflow_items enable row level security;
alter table public.car_loans enable row level security;
alter table public.installment_plans enable row level security;
alter table public.import_files enable row level security;
alter table public.import_jobs enable row level security;
alter table public.bank_transactions enable row level security;
alter table public.card_transactions enable row level security;

create policy "owner can view own profile"
on public.profiles
for select
to authenticated
using (public.is_owner() and id = auth.uid());

create policy "owner can update own profile"
on public.profiles
for update
to authenticated
using (public.is_owner() and id = auth.uid())
with check (public.is_owner() and id = auth.uid());

create policy "owner can manage own bank accounts"
on public.bank_accounts
for all
to authenticated
using (public.is_owner() and user_id = auth.uid())
with check (public.is_owner() and user_id = auth.uid());

create policy "owner can manage own card accounts"
on public.card_accounts
for all
to authenticated
using (public.is_owner() and user_id = auth.uid())
with check (public.is_owner() and user_id = auth.uid());

create policy "owner can manage own cashflow items"
on public.cashflow_items
for all
to authenticated
using (public.is_owner() and user_id = auth.uid())
with check (public.is_owner() and user_id = auth.uid());

create policy "owner can manage own car loans"
on public.car_loans
for all
to authenticated
using (public.is_owner() and user_id = auth.uid())
with check (public.is_owner() and user_id = auth.uid());

create policy "owner can manage own installment plans"
on public.installment_plans
for all
to authenticated
using (public.is_owner() and user_id = auth.uid())
with check (public.is_owner() and user_id = auth.uid());

create policy "owner can manage own import files"
on public.import_files
for all
to authenticated
using (public.is_owner() and user_id = auth.uid())
with check (public.is_owner() and user_id = auth.uid());

create policy "owner can manage own import jobs"
on public.import_jobs
for all
to authenticated
using (public.is_owner() and user_id = auth.uid())
with check (public.is_owner() and user_id = auth.uid());

create policy "owner can manage own bank transactions"
on public.bank_transactions
for all
to authenticated
using (public.is_owner() and user_id = auth.uid())
with check (public.is_owner() and user_id = auth.uid());

create policy "owner can manage own card transactions"
on public.card_transactions
for all
to authenticated
using (public.is_owner() and user_id = auth.uid())
with check (public.is_owner() and user_id = auth.uid());

insert into storage.buckets (id, name, public)
values ('home-budget-imports', 'home-budget-imports', false)
on conflict (id) do nothing;

create policy "owner can view own home budget import files"
on storage.objects
for select
to authenticated
using (
    bucket_id = 'home-budget-imports'
    and public.is_owner()
    and (storage.foldername(name))[1] = auth.uid()::text
);

create policy "owner can upload own home budget import files"
on storage.objects
for insert
to authenticated
with check (
    bucket_id = 'home-budget-imports'
    and public.is_owner()
    and (storage.foldername(name))[1] = auth.uid()::text
);

create policy "owner can update own home budget import files"
on storage.objects
for update
to authenticated
using (
    bucket_id = 'home-budget-imports'
    and public.is_owner()
    and (storage.foldername(name))[1] = auth.uid()::text
)
with check (
    bucket_id = 'home-budget-imports'
    and public.is_owner()
    and (storage.foldername(name))[1] = auth.uid()::text
);

create policy "owner can delete own home budget import files"
on storage.objects
for delete
to authenticated
using (
    bucket_id = 'home-budget-imports'
    and public.is_owner()
    and (storage.foldername(name))[1] = auth.uid()::text
);
