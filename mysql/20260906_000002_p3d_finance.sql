-- P3D Finance normalized budgeting layer.
-- Non-destructive: legacy tables remain intact and are linked through legacy_*_id columns.

SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS finance_recurring_items (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    legacy_cashflow_id CHAR(36) DEFAULT NULL,
    kind ENUM('income', 'expense', 'subscription', 'reimbursement') NOT NULL,
    title VARCHAR(255) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    category VARCHAR(128) NOT NULL DEFAULT 'Άλλο',
    payer VARCHAR(64) NOT NULL DEFAULT 'unassigned',
    recurrence ENUM('monthly', 'yearly', 'weekly') NOT NULL DEFAULT 'monthly',
    start_month DATE DEFAULT NULL,
    end_month DATE DEFAULT NULL,
    payment_method VARCHAR(128) NOT NULL DEFAULT '',
    amount_type ENUM('fixed', 'variable') NOT NULL DEFAULT 'fixed',
    affects_my_budget TINYINT(1) NOT NULL DEFAULT 1,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    needs_review TINYINT(1) NOT NULL DEFAULT 0,
    source VARCHAR(64) NOT NULL DEFAULT 'manual',
    notes TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_finance_recurring_legacy (legacy_cashflow_id),
    KEY idx_finance_recurring_user (user_id),
    KEY idx_finance_recurring_active (user_id, is_active),
    CONSTRAINT fk_finance_recurring_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_finance_recurring_legacy FOREIGN KEY (legacy_cashflow_id) REFERENCES cashflow_items(id) ON DELETE SET NULL,
    CONSTRAINT chk_finance_recurring_amount CHECK (amount >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_installments (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    legacy_installment_id CHAR(36) DEFAULT NULL,
    card_account_id CHAR(36) DEFAULT NULL,
    card_label VARCHAR(128) NOT NULL DEFAULT 'Χωρίς κάρτα',
    title VARCHAR(255) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    total_installments INT NOT NULL,
    installment_amount DECIMAL(12, 2) NOT NULL,
    start_month DATE NOT NULL,
    end_month DATE NOT NULL,
    payer VARCHAR(64) NOT NULL DEFAULT 'unassigned',
    charged_to VARCHAR(128) NOT NULL DEFAULT '',
    affects_my_budget TINYINT(1) NOT NULL DEFAULT 1,
    reimbursement_expected TINYINT(1) NOT NULL DEFAULT 0,
    reimbursement_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    reimbursement_status ENUM('none', 'pending', 'paid') NOT NULL DEFAULT 'none',
    status ENUM('active', 'completed', 'cancelled') NOT NULL DEFAULT 'active',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    needs_review TINYINT(1) NOT NULL DEFAULT 0,
    notes TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_finance_installments_legacy (legacy_installment_id),
    KEY idx_finance_installments_user (user_id),
    KEY idx_finance_installments_months (user_id, start_month, end_month),
    KEY idx_finance_installments_card (card_account_id),
    CONSTRAINT fk_finance_installments_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_finance_installments_legacy FOREIGN KEY (legacy_installment_id) REFERENCES installment_plans(id) ON DELETE SET NULL,
    CONSTRAINT fk_finance_installments_card FOREIGN KEY (card_account_id) REFERENCES card_accounts(id) ON DELETE SET NULL,
    CONSTRAINT chk_finance_installments_total CHECK (total_installments > 0),
    CONSTRAINT chk_finance_installments_amount CHECK (installment_amount > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_savings_goals (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    title VARCHAR(255) NOT NULL,
    target_amount DECIMAL(12, 2) NOT NULL,
    current_balance DECIMAL(12, 2) DEFAULT NULL,
    target_date DATE DEFAULT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    notes TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_finance_savings_user (user_id),
    CONSTRAINT fk_finance_savings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_finance_savings_target CHECK (target_amount > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_month_entries (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    month DATE NOT NULL,
    entry_type ENUM('income', 'extra_income', 'expense', 'recurring_override', 'planned_saving', 'actual_saving', 'reimbursement') NOT NULL,
    recurring_item_id CHAR(36) DEFAULT NULL,
    savings_goal_id CHAR(36) DEFAULT NULL,
    title VARCHAR(255) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    category VARCHAR(128) NOT NULL DEFAULT 'Άλλο',
    payer VARCHAR(64) NOT NULL DEFAULT 'Νάσος',
    affects_my_budget TINYINT(1) NOT NULL DEFAULT 1,
    notes TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_finance_month_entries_user_month (user_id, month),
    KEY idx_finance_month_entries_recurring (recurring_item_id),
    KEY idx_finance_month_entries_goal (savings_goal_id),
    CONSTRAINT fk_finance_month_entries_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_finance_month_entries_recurring FOREIGN KEY (recurring_item_id) REFERENCES finance_recurring_items(id) ON DELETE SET NULL,
    CONSTRAINT fk_finance_month_entries_goal FOREIGN KEY (savings_goal_id) REFERENCES finance_savings_goals(id) ON DELETE SET NULL,
    CONSTRAINT chk_finance_month_entries_amount CHECK (amount >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_scenarios (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    title VARCHAR(255) NOT NULL,
    monthly_amount DECIMAL(12, 2) NOT NULL,
    start_month DATE DEFAULT NULL,
    end_month DATE DEFAULT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 0,
    notes TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_finance_scenarios_user (user_id),
    CONSTRAINT fk_finance_scenarios_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_finance_scenarios_amount CHECK (monthly_amount >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_settings (
    user_id CHAR(36) NOT NULL,
    printing_forecast_low DECIMAL(12, 2) NOT NULL DEFAULT 80,
    printing_forecast_typical DECIMAL(12, 2) NOT NULL DEFAULT 120,
    printing_forecast_good DECIMAL(12, 2) NOT NULL DEFAULT 160,
    printing_savings_rate DECIMAL(5, 2) NOT NULL DEFAULT 100,
    safe_spend_basis ENUM('month_end', 'next_salary') NOT NULL DEFAULT 'month_end',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    CONSTRAINT fk_finance_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT chk_finance_savings_rate CHECK (printing_savings_rate >= 0 AND printing_savings_rate <= 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS finance_migration_log (
    id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    migration_key VARCHAR(128) NOT NULL,
    summary LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_finance_migration_user_key (user_id, migration_key),
    CONSTRAINT fk_finance_migration_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
