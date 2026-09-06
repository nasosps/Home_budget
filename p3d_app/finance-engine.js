const EPSILON = 0.005;

export function money(value) {
    const parsed = Number(value ?? 0);
    return Number.isFinite(parsed) ? Math.round((parsed + Number.EPSILON) * 100) / 100 : 0;
}

export function monthIndex(value) {
    const match = String(value ?? "").match(/^(\d{4})-(\d{2})/);
    if (!match) return Number.NaN;
    return Number(match[1]) * 12 + Number(match[2]) - 1;
}

export function monthKey(index) {
    const year = Math.floor(index / 12);
    const month = (index % 12) + 1;
    return `${year}-${String(month).padStart(2, "0")}`;
}

export function addMonths(value, count) {
    return monthKey(monthIndex(value) + Number(count || 0));
}

export function daysInMonth(value) {
    const index = monthIndex(value);
    const year = Math.floor(index / 12);
    const month = (index % 12) + 1;
    return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export function isActiveInMonth(item, selectedMonth) {
    if (item.is_active === false || Number(item.is_active) === 0 || item.status === "cancelled") return false;
    const selected = monthIndex(selectedMonth);
    const start = item.start_month || item.start_date;
    const end = item.end_month || item.end_date;
    if (start && selected < monthIndex(start)) return false;
    if (end && selected > monthIndex(end)) return false;
    return true;
}

export function installmentPosition(plan, selectedMonth) {
    const start = monthIndex(plan.start_month || plan.start_date);
    const selected = monthIndex(selectedMonth);
    const total = Number(plan.total_installments ?? plan.total_months ?? 0);
    const ordinal = selected - start + 1;
    const due = total > 0 && ordinal >= 1 && ordinal <= total && plan.status !== "cancelled" && Number(plan.is_active ?? 1) !== 0;
    const paidBeforeMonth = Math.max(0, Math.min(total, ordinal - 1));
    return {
        due,
        ordinal: Math.max(0, ordinal),
        total,
        paidBeforeMonth,
        remainingIncludingMonth: Math.max(0, total - paidBeforeMonth),
        endMonth: total > 0 ? addMonths(plan.start_month || plan.start_date, total - 1) : null,
    };
}

export function carLoanSummary(loan, selectedMonth) {
    const position = installmentPosition({
        start_date: loan.start_date,
        total_months: loan.total_months,
        status: loan.is_active === false || Number(loan.is_active) === 0 ? "cancelled" : "active",
    }, selectedMonth);
    const payment = money(loan.monthly_payment);
    const downPayment = money(loan.down_payment);
    const balloon = money(loan.balloon);
    const paid = money(downPayment + position.paidBeforeMonth * payment);
    const remaining = money(position.remainingIncludingMonth * payment + balloon);
    return {
        ...position,
        payment,
        paid,
        remaining,
        totalCost: money(downPayment + Number(loan.total_months || 0) * payment + balloon),
    };
}

function payerKind(plan) {
    const payer = String(plan.payer || "unassigned").trim().toLowerCase();
    if (["νάσος", "nasos", "κοινό", "shared", "common"].includes(payer)) return "personal";
    if (["unassigned", "", "μη ανατεθειμένο"].includes(payer)) return "unassigned";
    return "third_party";
}

export function installmentSummary(plans, selectedMonth) {
    const due = (plans || []).filter((plan) => installmentPosition(plan, selectedMonth).due);
    const rows = due.map((plan) => ({
        ...plan,
        position: installmentPosition(plan, selectedMonth),
        amount: money(plan.installment_amount ?? plan.monthly_payment),
        payer_kind: payerKind(plan),
    }));
    const cardTotals = {};
    for (const row of rows) {
        const card = row.card_label || row.charged_to || "Χωρίς κάρτα";
        cardTotals[card] = money((cardTotals[card] || 0) + row.amount);
    }
    return {
        rows,
        cardTotals,
        cardTotal: money(rows.reduce((sum, row) => sum + row.amount, 0)),
        personal: money(rows.filter((row) => row.payer_kind === "personal").reduce((sum, row) => sum + row.amount, 0)),
        thirdParty: money(rows.filter((row) => row.payer_kind === "third_party").reduce((sum, row) => sum + row.amount, 0)),
        unassigned: money(rows.filter((row) => row.payer_kind === "unassigned").reduce((sum, row) => sum + row.amount, 0)),
        budgetCost: money(rows.filter((row) => Number(row.affects_my_budget ?? 1) !== 0).reduce((sum, row) => sum + row.amount, 0)),
        reimbursementsPending: money(rows
            .filter((row) => row.reimbursement_status === "pending")
            .reduce((sum, row) => sum + money(row.reimbursement_amount || row.amount), 0)),
    };
}

function overrideMap(entries, selectedMonth) {
    return new Map((entries || [])
        .filter((entry) => entry.entry_type === "recurring_override" && String(entry.month).slice(0, 7) === selectedMonth)
        .map((entry) => [entry.recurring_item_id, money(entry.amount)]));
}

export function recurringSummary(items, entries, selectedMonth) {
    const overrides = overrideMap(entries, selectedMonth);
    const rows = (items || [])
        .filter((item) => isActiveInMonth(item, selectedMonth))
        .map((item) => ({ ...item, effective_amount: overrides.has(item.id) ? overrides.get(item.id) : money(item.amount) }));
    const sumKind = (kind) => money(rows
        .filter((row) => row.kind === kind && (!["expense", "subscription"].includes(kind) || Number(row.affects_my_budget ?? 1) !== 0))
        .reduce((sum, row) => sum + row.effective_amount, 0));
    return {
        rows,
        income: sumKind("income"),
        expenses: sumKind("expense"),
        subscriptions: sumKind("subscription"),
        reimbursements: sumKind("reimbursement"),
    };
}

export function savingsSummary(entries, selectedMonth, extraIncome, savingRate = 100) {
    const monthEntries = (entries || []).filter((entry) => String(entry.month).slice(0, 7) === selectedMonth);
    const explicitPlanned = money(monthEntries
        .filter((entry) => entry.entry_type === "planned_saving")
        .reduce((sum, entry) => sum + money(entry.amount), 0));
    const actual = money(monthEntries
        .filter((entry) => entry.entry_type === "actual_saving")
        .reduce((sum, entry) => sum + money(entry.amount), 0));
    const protectedExtra = money(extraIncome * Math.max(0, Math.min(100, Number(savingRate ?? 100))) / 100);
    return { planned: money(explicitPlanned + protectedExtra), actual, protectedExtra };
}

export function scenarioCost(scenarios, selectedMonth, includeInactive = false) {
    return money((scenarios || [])
        .filter((scenario) => {
            if (!includeInactive && Number(scenario.is_active ?? 0) === 0) return false;
            if (scenario.start_month && monthIndex(selectedMonth) < monthIndex(scenario.start_month)) return false;
            return !scenario.end_month || monthIndex(selectedMonth) <= monthIndex(scenario.end_month);
        })
        .reduce((sum, scenario) => sum + money(scenario.monthly_amount), 0));
}

export function calculateMonth(data, selectedMonth, options = {}) {
    const recurring = recurringSummary(data.recurringItems, data.monthEntries, selectedMonth);
    const installments = installmentSummary(data.installments, selectedMonth);
    const selectedEntries = (data.monthEntries || []).filter((entry) => String(entry.month).slice(0, 7) === selectedMonth);
    const extraRows = selectedEntries
        .filter((entry) => ["extra_income", "income"].includes(entry.entry_type))
    const extraIncome = money(extraRows.reduce((sum, entry) => sum + money(entry.amount), 0));
    const printingIncome = money(extraRows
        .filter((entry) => entry.category === "3d_printing" || /3d\s*print/i.test(entry.title || ""))
        .reduce((sum, entry) => sum + money(entry.amount), 0));
    const oneOffExpenses = money(selectedEntries
        .filter((entry) => entry.entry_type === "expense" && Number(entry.affects_my_budget ?? 1) !== 0)
        .reduce((sum, entry) => sum + money(entry.amount), 0));
    const car = (data.carLoans || []).filter((loan) => carLoanSummary(loan, selectedMonth).due);
    const carTotal = money(car.reduce((sum, loan) => sum + money(loan.monthly_payment), 0));
    const scenarios = scenarioCost(data.scenarios, selectedMonth, Boolean(options.includeInactiveScenarios));
    const savings = savingsSummary(data.monthEntries, selectedMonth, printingIncome, data.settings?.printing_savings_rate ?? 100);
    const obligations = money(recurring.expenses + recurring.subscriptions + installments.budgetCost + carTotal + oneOffExpenses + scenarios);
    const baseIncome = recurring.income;
    const totalIncome = money(baseIncome + extraIncome);
    const remainingFromSalary = money(baseIncome - obligations);
    const freeMoney = money(totalIncome - obligations - savings.planned);
    const safeToSpend = Math.max(0, freeMoney);
    return {
        selectedMonth,
        baseIncome,
        extraIncome,
        printingIncome,
        totalIncome,
        recurring,
        installments,
        car,
        carTotal,
        oneOffExpenses,
        scenarios,
        obligations,
        remainingFromSalary,
        savings,
        freeMoney,
        safeToSpend,
        safePerDay: money(safeToSpend / Math.max(1, options.daysRemaining || daysInMonth(selectedMonth))),
    };
}

export function upcomingFreedCash(data, selectedMonth, months = 60) {
    const start = monthIndex(selectedMonth);
    const items = [];
    for (const plan of data.installments || []) {
        const position = installmentPosition(plan, selectedMonth);
        if (payerKind(plan) !== "personal" || !position.endMonth) continue;
        const end = monthIndex(position.endMonth);
        if (end >= start && end <= start + months) {
            items.push({ title: plan.title, month: position.endMonth, amount: money(plan.installment_amount ?? plan.monthly_payment), type: "installment" });
        }
    }
    for (const loan of data.carLoans || []) {
        const summary = carLoanSummary(loan, selectedMonth);
        if (summary.endMonth && monthIndex(summary.endMonth) >= start && monthIndex(summary.endMonth) <= start + months) {
            items.push({ title: loan.label || "Αυτοκίνητο", month: summary.endMonth, amount: money(loan.monthly_payment), type: "car" });
        }
    }
    return items.sort((left, right) => monthIndex(left.month) - monthIndex(right.month));
}

export function forecast(data, selectedMonth, months = 12, options = {}) {
    return Array.from({ length: months }, (_, offset) => calculateMonth(data, addMonths(selectedMonth, offset), options));
}

export function simulatePurchase(summary, amount) {
    const purchase = Math.max(0, money(amount));
    const after = money(summary.safeToSpend - purchase);
    return {
        before: summary.safeToSpend,
        after,
        savingsAffected: after < -EPSILON,
        shortfall: Math.max(0, money(-after)),
    };
}
