-- Home Budget MariaDB bootstrap schema for Polar55
-- Derived from supabase/migrations/20260323_000001_init.sql
-- This replaces Supabase Auth/RLS with local users + sessions and API-side ownership checks.

SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS users (
    id CHAR(36) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL DEFAULT '',
    is_owner TINYINT(1) NOT NULL DEFAULT 0,
    status ENUM('active', 'disabled') NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS app_sessions (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    ip_address VARCHAR(64) DEFAULT NULL,
    user_agent VARCHAR(512) DEFAULT NULL,
    expires_at DATETIME NOT NULL,
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_app_sessions_token_hash (token_hash),
    KEY idx_app_sessions_user_id (user_id),
    KEY idx_app_sessions_expires_at (expires_at),
    CONSTRAINT fk_app_sessions_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS profiles (
    id CHAR(36) NOT NULL,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL DEFAULT '',
    is_owner TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_profiles_email (email),
    CONSTRAINT fk_profiles_user
        FOREIGN KEY (id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bank_accounts (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    bank_name VARCHAR(255) NOT NULL DEFAULT 'Alpha Bank',
    label VARCHAR(255) NOT NULL,
    iban VARCHAR(64) DEFAULT NULL,
    iban_masked VARCHAR(64) DEFAULT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_bank_accounts_user_label (user_id, label),
    KEY idx_bank_accounts_user_id (user_id),
    CONSTRAINT fk_bank_accounts_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS card_accounts (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    issuer VARCHAR(255) NOT NULL DEFAULT 'Alpha Bank',
    label VARCHAR(255) NOT NULL,
    last4 VARCHAR(16) DEFAULT NULL,
    card_number_masked VARCHAR(64) DEFAULT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_card_accounts_user_label_last4 (user_id, label, last4),
    KEY idx_card_accounts_user_id (user_id),
    CONSTRAINT fk_card_accounts_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cashflow_items (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    kind ENUM('income', 'expense') NOT NULL,
    title VARCHAR(255) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'manual',
    notes TEXT NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_cashflow_items_user_id (user_id),
    KEY idx_cashflow_items_kind (kind),
    CONSTRAINT chk_cashflow_items_amount CHECK (amount >= 0),
    CONSTRAINT fk_cashflow_items_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS car_loans (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    label VARCHAR(255) NOT NULL DEFAULT 'Car Loan',
    lender VARCHAR(255) NOT NULL DEFAULT 'Unknown',
    start_date DATE NOT NULL,
    total_months INT NOT NULL,
    monthly_payment DECIMAL(12, 2) NOT NULL,
    down_payment DECIMAL(12, 2) NOT NULL DEFAULT 0,
    balloon DECIMAL(12, 2) NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_car_loans_user_id (user_id),
    CONSTRAINT chk_car_loans_total_months CHECK (total_months > 0),
    CONSTRAINT chk_car_loans_monthly_payment CHECK (monthly_payment > 0),
    CONSTRAINT chk_car_loans_down_payment CHECK (down_payment >= 0),
    CONSTRAINT chk_car_loans_balloon CHECK (balloon >= 0),
    CONSTRAINT fk_car_loans_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS installment_plans (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    card_account_id CHAR(36) DEFAULT NULL,
    title VARCHAR(255) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    total_months INT NOT NULL,
    monthly_payment DECIMAL(12, 2) NOT NULL,
    start_date DATE NOT NULL,
    status ENUM('active', 'completed', 'cancelled') NOT NULL DEFAULT 'active',
    notes TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_installment_plans_user_id (user_id),
    KEY idx_installment_plans_card_account_id (card_account_id),
    CONSTRAINT chk_installment_plans_total_amount CHECK (total_amount > 0),
    CONSTRAINT chk_installment_plans_total_months CHECK (total_months > 0),
    CONSTRAINT chk_installment_plans_monthly_payment CHECK (monthly_payment > 0),
    CONSTRAINT fk_installment_plans_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_installment_plans_card_account
        FOREIGN KEY (card_account_id) REFERENCES card_accounts(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_files (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    storage_path VARCHAR(1024) DEFAULT NULL,
    sha256 CHAR(64) NOT NULL,
    file_kind ENUM('bank_account_pdf', 'card_statement_pdf', 'manual_csv', 'other') NOT NULL,
    parser_key VARCHAR(128) NOT NULL DEFAULT 'local.alpha_pdf.v1',
    statement_from DATE DEFAULT NULL,
    statement_to DATE DEFAULT NULL,
    last_status ENUM('queued', 'processing', 'applied', 'failed') NOT NULL DEFAULT 'queued',
    raw_metadata LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_import_files_user_sha256 (user_id, sha256),
    KEY idx_import_files_user_id (user_id),
    KEY idx_import_files_status (last_status),
    CONSTRAINT fk_import_files_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_jobs (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    import_file_id CHAR(36) NOT NULL,
    status ENUM('queued', 'processing', 'applied', 'failed') NOT NULL DEFAULT 'queued',
    summary LONGTEXT NOT NULL,
    error_text TEXT DEFAULT NULL,
    started_at DATETIME DEFAULT NULL,
    finished_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_import_jobs_user_id (user_id),
    KEY idx_import_jobs_file_id (import_file_id),
    KEY idx_import_jobs_status (status),
    CONSTRAINT fk_import_jobs_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_import_jobs_import_file
        FOREIGN KEY (import_file_id) REFERENCES import_files(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bank_transactions (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    bank_account_id CHAR(36) DEFAULT NULL,
    import_file_id CHAR(36) DEFAULT NULL,
    entry_index INT DEFAULT NULL,
    posted_on DATE NOT NULL,
    effective_on DATE DEFAULT NULL,
    description TEXT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    direction ENUM('credit', 'debit') NOT NULL,
    transaction_ref VARCHAR(255) DEFAULT NULL,
    location_code VARCHAR(128) DEFAULT NULL,
    fingerprint VARCHAR(255) NOT NULL,
    raw_payload LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_bank_transactions_user_fingerprint (user_id, fingerprint),
    KEY idx_bank_transactions_user_id (user_id),
    KEY idx_bank_transactions_bank_account_id (bank_account_id),
    KEY idx_bank_transactions_import_file_id (import_file_id),
    KEY idx_bank_transactions_posted_on (posted_on),
    CONSTRAINT fk_bank_transactions_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_bank_transactions_bank_account
        FOREIGN KEY (bank_account_id) REFERENCES bank_accounts(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_bank_transactions_import_file
        FOREIGN KEY (import_file_id) REFERENCES import_files(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS card_transactions (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    card_account_id CHAR(36) DEFAULT NULL,
    import_file_id CHAR(36) DEFAULT NULL,
    entry_index INT DEFAULT NULL,
    posted_on DATE NOT NULL,
    merchant VARCHAR(255) NOT NULL,
    posted_time VARCHAR(32) DEFAULT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    direction ENUM('credit', 'debit') NOT NULL,
    transaction_type VARCHAR(128) NOT NULL DEFAULT '',
    status_text VARCHAR(128) NOT NULL DEFAULT '',
    category VARCHAR(128) NOT NULL DEFAULT '',
    fingerprint VARCHAR(255) NOT NULL,
    raw_payload LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_card_transactions_user_fingerprint (user_id, fingerprint),
    KEY idx_card_transactions_user_id (user_id),
    KEY idx_card_transactions_card_account_id (card_account_id),
    KEY idx_card_transactions_import_file_id (import_file_id),
    KEY idx_card_transactions_posted_on (posted_on),
    CONSTRAINT fk_card_transactions_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_card_transactions_card_account
        FOREIGN KEY (card_account_id) REFERENCES card_accounts(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_card_transactions_import_file
        FOREIGN KEY (import_file_id) REFERENCES import_files(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
