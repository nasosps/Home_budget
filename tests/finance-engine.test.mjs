import test from "node:test";
import assert from "node:assert/strict";
import {
    calculateMonth,
    carLoanSummary,
    installmentPosition,
    installmentSummary,
} from "../p3d_app/finance-engine.js";

test("car loan matches October 2026 baseline", () => {
    const summary = carLoanSummary({
        start_date: "2023-05-01",
        total_months: 65,
        monthly_payment: 250,
        down_payment: 1500,
        balloon: 0,
        is_active: 1,
    }, "2026-10");
    assert.equal(summary.ordinal, 42);
    assert.equal(summary.total, 65);
    assert.equal(summary.paid, 11750);
    assert.equal(summary.remaining, 6000);
    assert.equal(summary.remainingIncludingMonth, 24);
    assert.equal(summary.endMonth, "2028-09");
});

test("October 2026 card totals are Energy 226.24 and Alpha 21.96", () => {
    const plans = [
        ["SKROUTZ", 30.32, 6, "2026-05", "Energy"],
        ["TCL", 34.60, 24, "2024-12", "Energy"],
        ["Κινητό Νίκου", 16.12, 12, "2026-01", "Energy"],
        ["Air Condition Νάσου", 35.62, 12, "2026-02", "Energy"],
        ["Ακουστικό Μητέρας", 39.58, 24, "2025-03", "Energy", "Μητέρα"],
        ["Ασφάλεια KIA", 21.96, 12, "2026-05", "Alpha"],
        ["Κούνια Μωρού", 50, 12, "2026-09", "Energy"],
        ["Φούρνος Μητέρας", 20, 12, "2026-09", "Energy"],
    ].map(([title, amount, total, start, card, payer = "unassigned"]) => ({
        title,
        installment_amount: amount,
        total_installments: total,
        start_month: start,
        card_label: card,
        payer,
        status: "active",
        is_active: 1,
        reimbursement_status: title === "Ακουστικό Μητέρας" ? "pending" : "none",
        reimbursement_amount: title === "Ακουστικό Μητέρας" ? 39.58 : 0,
    }));
    const result = installmentSummary(plans, "2026-10");
    assert.equal(result.cardTotals.Energy, 226.24);
    assert.equal(result.cardTotals.Alpha, 21.96);
    assert.equal(result.cardTotal, 248.20);
    assert.equal(result.thirdParty, 39.58);
    assert.equal(result.reimbursementsPending, 39.58);
    assert.equal(result.rows.find((row) => row.title === "SKROUTZ").position.ordinal, 6);
    assert.equal(result.rows.find((row) => row.title === "TCL").position.ordinal, 23);
    assert.equal(result.rows.find((row) => row.title === "Κινητό Νίκου").position.ordinal, 10);
    assert.equal(result.rows.find((row) => row.title === "Air Condition Νάσου").position.ordinal, 9);
    assert.equal(result.rows.find((row) => row.title === "Air Condition Νάσου").position.endMonth, "2027-01");
});

test("third-party installment increases card total but not personal cost", () => {
    const result = installmentSummary([{
        title: "Ακουστικό Μητέρας",
        installment_amount: 39.58,
        total_installments: 24,
        start_month: "2025-03",
        card_label: "Energy",
        payer: "Μητέρα",
        reimbursement_status: "pending",
        reimbursement_amount: 39.58,
        status: "active",
        is_active: 1,
    }], "2026-10");
    assert.equal(result.cardTotal, 39.58);
    assert.equal(result.personal, 0);
    assert.equal(result.thirdParty, 39.58);
});

test("3D printing income is protected by the 100% savings rule", () => {
    const summary = calculateMonth({
        recurringItems: [{ id: "salary", kind: "income", amount: 1450, start_month: "2026-01", is_active: 1 }],
        installments: [],
        carLoans: [],
        scenarios: [],
        settings: { printing_savings_rate: 100 },
        monthEntries: [{ month: "2026-10", entry_type: "extra_income", category: "3d_printing", amount: 120 }],
    }, "2026-10");
    assert.equal(summary.baseIncome, 1450);
    assert.equal(summary.extraIncome, 120);
    assert.equal(summary.savings.planned, 120);
    assert.equal(summary.safeToSpend, 1450);
});

test("ordinary extra income is not forced into 3D printing savings", () => {
    const summary = calculateMonth({
        recurringItems: [{ id: "salary", kind: "income", amount: 1450, start_month: "2026-01", is_active: 1 }],
        installments: [], carLoans: [], scenarios: [], settings: { printing_savings_rate: 100 },
        monthEntries: [{ month: "2026-10", entry_type: "extra_income", category: "Άλλο", title: "Δώρο", amount: 100 }],
    }, "2026-10");
    assert.equal(summary.extraIncome, 100);
    assert.equal(summary.savings.planned, 0);
    assert.equal(summary.safeToSpend, 1550);
});

test("month-aware installment boundaries are inclusive", () => {
    const plan = { start_month: "2026-05", total_installments: 6, status: "active", is_active: 1 };
    assert.equal(installmentPosition(plan, "2026-04").due, false);
    assert.equal(installmentPosition(plan, "2026-10").due, true);
    assert.equal(installmentPosition(plan, "2026-11").due, false);
});
