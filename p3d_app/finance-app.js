import { createLocalClient } from "./api-client.js";
import {
    addMonths,
    calculateMonth,
    carLoanSummary,
    forecast,
    installmentPosition,
    money,
    simulatePurchase,
    upcomingFreedCash,
} from "./finance-engine.js";

const api = createLocalClient();
const $ = (id) => document.getElementById(id);
const today = new Date();
const currentMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
const state = {
    selectedMonth: localStorage.getItem("p3d-finance-month") || currentMonth,
    recurringItems: [], installments: [], carLoans: [], monthEntries: [], savingsGoals: [], scenarios: [], settings: {},
    wizardIndex: 0,
};

const entryTitles = {
    extra_income: "Νέο έσοδο", expense: "Νέο έξοδο", installment: "Νέα δόση",
    subscription: "Νέα συνδρομή", actual_saving: "Πραγματική αποταμίευση",
    reimbursement: "Επιστροφή χρημάτων", recurring: "Νέο πάγιο", recurring_override: "Πραγματικό ποσό μήνα",
    edit_recurring: "Επεξεργασία επαναλαμβανόμενης εγγραφής", edit_installment: "Επεξεργασία δόσης",
};

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function euros(value, sign = false) {
    const amount = money(value);
    const prefix = sign && amount > 0 ? "+" : "";
    return `${prefix}${new Intl.NumberFormat("el-GR", { minimumFractionDigits: amount % 1 ? 2 : 0, maximumFractionDigits: 2 }).format(amount)} €`;
}

function monthLabel(value, style = "long") {
    const [year, month] = value.slice(0, 7).split("-").map(Number);
    return new Intl.DateTimeFormat("el-GR", { month: style, year: "numeric" }).format(new Date(year, month - 1, 1));
}

function bool(value) { return value === true || value === 1 || value === "1"; }
function show(id) { $(id)?.classList.remove("hidden"); }
function hide(id) { $(id)?.classList.add("hidden"); }
function empty(message) { return `<p class="empty">${escapeHtml(message)}</p>`; }

let toastTimer;
function toast(message) {
    clearTimeout(toastTimer);
    $("toast").textContent = message;
    show("toast");
    toastTimer = setTimeout(() => hide("toast"), 2800);
}

function setLoading(active) { $("loading").classList.toggle("hidden", !active); }

async function table(name, columns = "*") {
    const { data, error } = await api.from(name).select(columns);
    if (error) throw new Error(error.message);
    return data || [];
}

async function refreshData() {
    setLoading(true);
    try {
        const [recurringItems, installments, carLoans, monthEntries, savingsGoals, scenarios, settings] = await Promise.all([
            table("finance_recurring_items"), table("finance_installments"), table("car_loans"),
            table("finance_month_entries"), table("finance_savings_goals"), table("finance_scenarios"), table("finance_settings"),
        ]);
        Object.assign(state, { recurringItems, installments, carLoans, monthEntries, savingsGoals, scenarios, settings: settings[0] || {} });
        render();
    } finally { setLoading(false); }
}

function calculation(options = {}) {
    const now = new Date();
    const daysRemaining = state.selectedMonth === currentMonth
        ? new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() - now.getDate() + 1
        : undefined;
    return calculateMonth(state, state.selectedMonth, { daysRemaining, ...options });
}

function setText(id, value) { if ($(id)) $(id).textContent = value; }

function renderHome(summary) {
    setText("heroMonth", monthLabel(state.selectedMonth));
    setText("safeToSpend", euros(summary.safeToSpend));
    setText("safePerDay", `${euros(summary.safePerDay)} / ημέρα`);
    setText("baseIncome", euros(summary.baseIncome));
    setText("extraIncome", euros(summary.extraIncome, true));
    setText("ownObligations", euros(summary.obligations));
    setText("salaryRemaining", euros(summary.remainingFromSalary));
    setText("plannedSavings", euros(summary.savings.planned));
    setText("actualSavings", euros(summary.savings.actual));
    setText("cardsTotal", euros(summary.installments.cardTotal));
    setText("cardsMine", euros(summary.installments.personal));
    setText("cardsOthers", euros(summary.installments.thirdParty));
    setText("refundsPending", euros(summary.installments.reimbursementsPending));
    setText("cardsUnassigned", euros(summary.installments.unassigned));

    const unassigned = state.installments.filter((item) => bool(item.is_active) && item.status === "active" && item.payer === "unassigned");
    $("reviewNotice").classList.toggle("hidden", unassigned.length === 0);
    setText("reviewNoticeText", `${unassigned.length} υπάρχουσες δόσεις περιμένουν μόνο τον πληρωτή τους.`);

    const upcoming = upcomingFreedCash(state, state.selectedMonth, 60).slice(0, 6);
    $("upcomingList").innerHTML = upcoming.length ? upcoming.map((item) => `<div class="timeline-item"><span>${escapeHtml(monthLabel(item.month, "short"))}</span><strong>${escapeHtml(item.title)}</strong><b>+${euros(item.amount)}/μήνα</b></div>`).join("") : empty("Δεν υπάρχουν προσωπικές δόσεις που λήγουν στο διάστημα.");
}

function recurringRow(item, allowOverride = false) {
    const override = state.monthEntries.find((entry) => entry.entry_type === "recurring_override" && entry.recurring_item_id === item.id && String(entry.month).slice(0, 7) === state.selectedMonth);
    const amount = override ? override.amount : item.amount;
    return `<div class="data-row"><div><p>${escapeHtml(item.title)}</p><small>${escapeHtml(item.category)}${override ? " • πραγματικό ποσό" : ""}</small></div><div><strong>${euros(amount)}</strong><button data-edit-recurring="${escapeHtml(item.id)}">Επεξεργασία</button>${allowOverride ? `<button data-override="${escapeHtml(item.id)}">Αλλαγή μήνα</button>` : ""}</div></div>`;
}

function renderMonth(summary) {
    setText("monthTitle", monthLabel(state.selectedMonth));
    setText("monthIncomeTotal", euros(summary.baseIncome + summary.extraIncome));
    setText("monthExpenseTotal", euros(summary.recurring.expenses + summary.oneOffExpenses));
    setText("subscriptionTotal", euros(summary.recurring.subscriptions));
    setText("subscriptionAnnual", `Ετήσιο ισοδύναμο: ${euros(summary.recurring.subscriptions * 12)}`);

    const incomes = summary.recurring.rows.filter((item) => item.kind === "income");
    const expenses = summary.recurring.rows.filter((item) => item.kind === "expense");
    const subscriptions = summary.recurring.rows.filter((item) => item.kind === "subscription");
    $("incomeList").innerHTML = incomes.length ? incomes.map((item) => recurringRow(item)).join("") : empty("Δεν υπάρχουν ενεργά επαναλαμβανόμενα έσοδα.");
    $("expenseList").innerHTML = expenses.length ? expenses.map((item) => recurringRow(item, item.amount_type === "variable")).join("") : empty("Δεν υπάρχουν ενεργά πάγια.");
    $("subscriptionList").innerHTML = subscriptions.length ? subscriptions.map((item) => recurringRow(item)).join("") : empty("Δεν έχει καταχωρηθεί συνδρομή.");

    const entries = state.monthEntries.filter((entry) => String(entry.month).slice(0, 7) === state.selectedMonth && entry.entry_type !== "recurring_override");
    $("monthEntriesList").innerHTML = entries.length ? entries.map((entry) => `<div class="data-row"><div><p>${escapeHtml(entry.title)}</p><small>${escapeHtml(entry.category)} • ${escapeHtml(entryTitles[entry.entry_type] || entry.entry_type)}</small></div><strong>${euros(entry.amount, entry.entry_type.includes("income"))}</strong></div>`).join("") : empty("Δεν υπάρχουν νέες χειροκίνητες εγγραφές.");
}

function renderInstallments(summary) {
    setText("installmentGrandTotal", euros(summary.installments.cardTotal));
    const cards = Object.entries(summary.installments.cardTotals);
    $("cardBreakdown").innerHTML = cards.length ? cards.map(([label, amount]) => `<div class="mini-card"><span>${escapeHtml(label)}</span><strong>${euros(amount)}</strong></div>`).join("") : empty("Καμία δόση αυτόν τον μήνα.");

    const loan = state.carLoans[0];
    if (loan) {
        const car = carLoanSummary(loan, state.selectedMonth);
        const progress = car.total ? Math.min(100, car.paidBeforeMonth / car.total * 100) : 0;
        $("carCard").innerHTML = `<div class="car-top"><div><span>Αυτοκίνητο</span><h3>${car.ordinal} / ${car.total}</h3></div><strong>${euros(car.payment)}/μήνα</strong></div><div class="progress"><i style="width:${progress}%"></i></div><div class="car-stats"><div><span>Πληρωμένα</span><strong>${euros(car.paid)}</strong></div><div><span>Υπόλοιπο</span><strong>${euros(car.remaining)}</strong></div><div><span>Λήξη</span><strong>${escapeHtml(monthLabel(car.endMonth, "short"))}</strong></div></div>`;
        $("carCard").classList.remove("hidden");
    } else { $("carCard").classList.add("hidden"); }

    const rows = summary.installments.rows;
    $("installmentList").innerHTML = rows.length ? rows.map((row) => {
        const payerChip = row.payer_kind === "unassigned" ? `<span class="chip pending">Πληρωτής: εκκρεμεί</span>` : `<span class="chip ${row.payer_kind === "third_party" ? "third" : ""}">${escapeHtml(row.payer)}</span>`;
        return `<article class="installment"><div class="installment-top"><div><h4>${escapeHtml(row.title)}</h4><small>${escapeHtml(row.card_label)}</small></div><span class="amount">${euros(row.amount)}</span></div><div class="installment-meta"><span class="chip">${row.position.ordinal} / ${row.position.total}</span><span class="chip">Λήξη ${escapeHtml(monthLabel(row.position.endMonth, "short"))}</span>${payerChip}${row.reimbursement_status === "pending" ? `<button class="chip pending" data-mark-reimbursed="${row.id}">Επιστροφή ${euros(row.reimbursement_amount)} • πληρώθηκε;</button>` : ""}<button class="chip" data-edit-installment="${row.id}">Επεξεργασία</button></div></article>`;
    }).join("") : empty("Δεν υπάρχουν ενεργές δόσεις για αυτόν τον μήνα.");
}

function renderSavings() {
    $("savingsGoals").innerHTML = state.savingsGoals.length ? state.savingsGoals.map((goal) => {
        const hasBalance = goal.current_balance !== null && goal.current_balance !== "";
        const balance = hasBalance ? money(goal.current_balance) : 0;
        const progress = hasBalance ? Math.min(100, balance / Math.max(1, money(goal.target_amount)) * 100) : 0;
        return `<article class="goal-card"><p class="eyebrow">Ενεργός στόχος</p><h3>${escapeHtml(goal.title)}</h3><div class="goal-amounts"><div><span>Τώρα</span><strong>${hasBalance ? euros(balance) : "Δεν καταχωρήθηκε"}</strong></div><div><span>Στόχος</span><strong>${euros(goal.target_amount)}</strong></div></div><div class="progress"><i style="width:${progress}%"></i></div><form data-goal-form="${escapeHtml(goal.id)}"><input name="balance" type="number" min="0" step="0.01" placeholder="Τρέχον υπόλοιπο" value="${hasBalance ? escapeHtml(goal.current_balance) : ""}"><button class="secondary" type="submit">Ενημέρωση</button></form></article>`;
    }).join("") : empty("Δεν υπάρχει στόχος αποταμίευσης.");
}

function renderMore(summary, includeInactiveScenario = false) {
    const range = Number($("forecastRange").value || 12);
    const projections = forecast(state, state.selectedMonth, range, { includeInactiveScenarios: includeInactiveScenario });
    $("forecastList").innerHTML = projections.map((item) => `<div class="forecast-row"><span>${escapeHtml(monthLabel(item.selectedMonth, "short"))}</span><small>Υποχρεώσεις ${euros(item.obligations)}</small><strong class="${item.freeMoney < 0 ? "negative" : ""}">${euros(item.freeMoney)}</strong></div>`).join("");
    const housing = state.scenarios[0];
    if (housing) {
        $("housingToggle").checked = bool(housing.is_active);
        $("housingStart").value = housing.start_month ? String(housing.start_month).slice(0, 7) : "";
        setText("housingDescription", `${housing.title} • ${euros(housing.monthly_amount)}/μήνα. ${bool(housing.is_active) ? "Ενεργό" : "Ανενεργό"}.`);
    }
    $("savingRate").value = state.settings.printing_savings_rate ?? 100;
    renderPurchase(summary);
}

function renderPurchase(summary) {
    const result = simulatePurchase(summary, $("purchaseAmount").value || 0);
    $("purchaseResult").innerHTML = `<div><span>Διαθέσιμο πριν</span><strong>${euros(result.before)}</strong></div><div><span>Διαθέσιμο μετά</span><strong>${euros(result.after)}</strong></div><div><span>Αποταμίευση επηρεάζεται</span><strong>${result.savingsAffected ? "Ναι" : "Όχι"}</strong></div><div><span>Επόμενος μήνας</span><strong>${euros(calculateMonth(state, addMonths(state.selectedMonth, 1)).safeToSpend)}</strong></div>`;
}

function render() {
    $("monthPicker").value = state.selectedMonth;
    const summary = calculation();
    renderHome(summary); renderMonth(summary); renderInstallments(summary); renderSavings(); renderMore(summary);
}

function switchView(view) {
    document.querySelectorAll(".view").forEach((item) => item.classList.toggle("active", item.id === `view-${view}`));
    document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function shiftMonth(amount) {
    state.selectedMonth = addMonths(state.selectedMonth, amount);
    localStorage.setItem("p3d-finance-month", state.selectedMonth);
    render();
}

function openEntry(type, preset = {}) {
    hide("quickSheet"); show("entryModal");
    $("entryForm").reset(); $("entryType").value = type; $("entryRecurringId").value = preset.recurringId || "";
    setText("entryTitle", entryTitles[type] || "Νέα καταχώρηση");
    $("entryName").value = preset.title || ""; $("entryAmount").value = preset.amount ?? ""; $("entryMonth").value = preset.month ? String(preset.month).slice(0, 7) : state.selectedMonth;
    $("entryCategory").value = preset.category || "Άλλο";
    $("entryPayer").value = preset.payer || "Νάσος"; $("entryNotes").value = preset.notes || "";
    $("entryAmountType").value = preset.amountType || "fixed"; $("entryCard").value = preset.card || "Energy"; $("entryTotalInstallments").value = preset.totalInstallments || "";
    const installmentMode = ["installment", "edit_installment"].includes(type);
    $("totalInstallmentsField").classList.toggle("hidden", !installmentMode);
    $("cardField").classList.toggle("hidden", !installmentMode);
    $("amountTypeField").classList.toggle("hidden", !["recurring", "subscription", "edit_recurring"].includes(type));
    $("entryTotalInstallments").required = installmentMode;
}

async function insertRow(tableName, payload) {
    const { error } = await api.from(tableName).insert(payload);
    if (error) throw new Error(error.message);
}

async function updateRow(tableName, id, payload) {
    const { error } = await api.from(tableName).update(payload).eq("id", id);
    if (error) throw new Error(error.message);
}

function payerMetadata(payer, amount) {
    const personal = ["Νάσος", "Κοινό"].includes(payer);
    const assigned = payer !== "unassigned";
    return { affects_my_budget: personal ? 1 : 0, reimbursement_expected: assigned && !personal ? 1 : 0, reimbursement_amount: assigned && !personal ? amount : 0, reimbursement_status: assigned && !personal ? "pending" : "none", needs_review: assigned ? 0 : 1 };
}

async function saveEntry(event) {
    event.preventDefault();
    const type = $("entryType").value;
    const amount = money($("entryAmount").value);
    const month = `${$("entryMonth").value}-01`;
    const common = { title: $("entryName").value.trim(), amount, category: $("entryCategory").value.trim() || "Άλλο", payer: $("entryPayer").value, notes: $("entryNotes").value.trim() };
    setLoading(true);
    try {
        if (["installment", "edit_installment"].includes(type)) {
            const total = Number($("entryTotalInstallments").value);
            const card = $("entryCard").value;
            const payload = { ...common, card_label: card, charged_to: card, total_installments: total, installment_amount: amount, total_amount: money(amount * total), start_month: month, end_month: `${addMonths(month, total - 1)}-01`, status: "active", is_active: 1, ...payerMetadata(common.payer, amount) };
            if (type === "edit_installment") {
                const existing = state.installments.find((item) => item.id === $("entryRecurringId").value);
                if (existing?.reimbursement_status === "paid" && payload.reimbursement_expected) payload.reimbursement_status = "paid";
                await updateRow("finance_installments", $("entryRecurringId").value, payload);
            } else await insertRow("finance_installments", payload);
        } else if (["recurring", "subscription", "edit_recurring"].includes(type)) {
            const affectsBudget = ["Νάσος", "Κοινό", "unassigned"].includes(common.payer) ? 1 : 0;
            const existing = state.recurringItems.find((item) => item.id === $("entryRecurringId").value);
            const payload = { ...common, kind: type === "edit_recurring" ? existing?.kind || "expense" : type === "subscription" ? "subscription" : "expense", recurrence: "monthly", start_month: month, end_month: existing?.end_month || null, payment_method: existing?.payment_method || "", amount_type: $("entryAmountType").value, affects_my_budget: affectsBudget, is_active: 1, needs_review: common.payer === "unassigned" ? 1 : 0, source: existing?.source || "manual" };
            if (type === "edit_recurring") await updateRow("finance_recurring_items", $("entryRecurringId").value, payload);
            else await insertRow("finance_recurring_items", payload);
        } else {
            const affectsBudget = type === "reimbursement" ? 0 : type === "expense" ? (["Νάσος", "Κοινό", "unassigned"].includes(common.payer) ? 1 : 0) : 1;
            await insertRow("finance_month_entries", { ...common, month, entry_type: type, recurring_item_id: $("entryRecurringId").value || null, savings_goal_id: type === "actual_saving" ? state.savingsGoals[0]?.id || null : null, affects_my_budget: affectsBudget });
        }
        hide("entryModal"); await refreshData(); toast("Η καταχώρηση αποθηκεύτηκε.");
    } catch (error) { toast(`Δεν αποθηκεύτηκε: ${error.message}`); setLoading(false); }
}

function unassignedPlans() { return state.installments.filter((item) => bool(item.is_active) && item.status === "active" && item.payer === "unassigned"); }

function renderPayerWizard() {
    const plans = unassignedPlans();
    if (!plans.length) { hide("payerWizard"); toast("Όλες οι υπάρχουσες δόσεις έχουν πληρωτή."); return; }
    state.wizardIndex = Math.min(state.wizardIndex, plans.length - 1);
    const plan = plans[state.wizardIndex];
    $("payerWizardBody").innerHTML = `<div class="payer-focus"><p class="eyebrow">${state.wizardIndex + 1} από ${plans.length}</p><h3>${escapeHtml(plan.title)}</h3><p class="big">${euros(plan.installment_amount)}</p><p class="muted compact">${escapeHtml(plan.card_label)} • ${plan.total_installments} δόσεις</p><div class="payer-buttons">${["Νάσος", "Μητέρα", "Νίκος", "Κοινό", "Άλλος"].map((payer) => `<button data-set-payer="${payer}" data-plan-id="${plan.id}">${payer}</button>`).join("")}</div></div>`;
}

async function setPayer(planId, payer) {
    const plan = state.installments.find((item) => item.id === planId);
    if (!plan) return;
    setLoading(true);
    try {
        await updateRow("finance_installments", planId, { payer, ...payerMetadata(payer, money(plan.installment_amount)) });
        await refreshData(); renderPayerWizard(); toast("Ο πληρωτής αποθηκεύτηκε.");
    } catch (error) { toast(error.message); setLoading(false); }
}

async function markReimbursed(planId) {
    setLoading(true);
    try { await updateRow("finance_installments", planId, { reimbursement_status: "paid" }); await refreshData(); toast("Η επιστροφή σημειώθηκε ως πληρωμένη."); }
    catch (error) { toast(error.message); setLoading(false); }
}

async function updateGoal(form) {
    const goal = state.savingsGoals.find((item) => item.id === form.dataset.goalForm);
    const value = form.elements.balance.value;
    if (!goal || value === "") return;
    setLoading(true);
    try { await updateRow("finance_savings_goals", goal.id, { current_balance: money(value) }); await refreshData(); toast("Το υπόλοιπο ενημερώθηκε."); }
    catch (error) { toast(error.message); setLoading(false); }
}

async function updateScenario() {
    const scenario = state.scenarios[0]; if (!scenario) return;
    setLoading(true);
    try { await updateRow("finance_scenarios", scenario.id, { is_active: $("housingToggle").checked ? 1 : 0, start_month: $("housingStart").value ? `${$("housingStart").value}-01` : null }); await refreshData(); toast("Το σενάριο ενημερώθηκε."); }
    catch (error) { toast(error.message); setLoading(false); }
}

async function saveSettings(event) {
    event.preventDefault(); setLoading(true);
    const { error } = await api.from("finance_settings").update({ printing_savings_rate: Math.max(0, Math.min(100, Number($("savingRate").value))) });
    if (error) { toast(error.message); setLoading(false); return; }
    await refreshData(); toast("Ο κανόνας αποταμίευσης ενημερώθηκε.");
}

async function handleLogin(event) {
    event.preventDefault(); setText("loginError", ""); setLoading(true);
    const { data, error } = await api.auth.signInWithPassword({ email: $("emailInput").value.trim(), password: $("passwordInput").value });
    if (error || !data.session) { setText("loginError", error?.message || "Η σύνδεση απέτυχε."); setLoading(false); return; }
    localStorage.setItem("p3d-finance-email", $("emailInput").value.trim());
    hide("loginView"); show("app");
    try { await refreshData(); } catch (loadError) { toast(loadError.message); setLoading(false); }
}

function bindEvents() {
    $("loginForm").addEventListener("submit", handleLogin);
    $("logoutBtn").addEventListener("click", async () => { await api.auth.signOut(); location.reload(); });
    $("previousMonth").addEventListener("click", () => shiftMonth(-1)); $("nextMonth").addEventListener("click", () => shiftMonth(1));
    $("monthPicker").addEventListener("change", (event) => { state.selectedMonth = event.target.value || currentMonth; localStorage.setItem("p3d-finance-month", state.selectedMonth); render(); });
    $("quickAddBtn").addEventListener("click", () => show("quickSheet")); $("entryForm").addEventListener("submit", saveEntry);
    $("forecastRange").addEventListener("change", render); $("purchaseForm").addEventListener("submit", (event) => { event.preventDefault(); renderPurchase(calculation()); });
    $("settingsForm").addEventListener("submit", saveSettings); $("housingToggle").addEventListener("change", updateScenario); $("housingStart").addEventListener("change", updateScenario);
    $("previewHousing").addEventListener("click", () => { renderMore(calculation({ includeInactiveScenarios: true }), true); toast("Η πρόβλεψη περιλαμβάνει προσωρινά το σενάριο των 300 €."); });
    document.addEventListener("submit", (event) => { if (event.target.matches("[data-goal-form]")) { event.preventDefault(); updateGoal(event.target); } });
    document.addEventListener("click", (event) => {
        const view = event.target.closest("[data-view]")?.dataset.view; if (view) switchView(view);
        const add = event.target.closest("[data-add]")?.dataset.add; if (add) openEntry(add);
        const action = event.target.closest("[data-action]")?.dataset.action;
        if (action === "close-sheet") hide("quickSheet"); if (action === "close-entry") hide("entryModal");
        if (action === "open-payer-wizard") { state.wizardIndex = 0; renderPayerWizard(); show("payerWizard"); }
        if (action === "close-payer-wizard") hide("payerWizard");
        const payerButton = event.target.closest("[data-set-payer]"); if (payerButton) setPayer(payerButton.dataset.planId, payerButton.dataset.setPayer);
        const overrideId = event.target.closest("[data-override]")?.dataset.override;
        if (overrideId) { const item = state.recurringItems.find((row) => row.id === overrideId); if (item) openEntry("recurring_override", { recurringId: item.id, title: item.title, amount: item.amount, category: item.category, payer: item.payer }); }
        const recurringId = event.target.closest("[data-edit-recurring]")?.dataset.editRecurring;
        if (recurringId) { const item = state.recurringItems.find((row) => row.id === recurringId); if (item) openEntry("edit_recurring", { recurringId: item.id, title: item.title, amount: item.amount, category: item.category, payer: item.payer, month: item.start_month, amountType: item.amount_type, notes: item.notes }); }
        const installmentId = event.target.closest("[data-edit-installment]")?.dataset.editInstallment;
        if (installmentId) { const item = state.installments.find((row) => row.id === installmentId); if (item) openEntry("edit_installment", { recurringId: item.id, title: item.title, amount: item.installment_amount, category: item.category || "Δόση", payer: item.payer, month: item.start_month, card: item.card_label, totalInstallments: item.total_installments, notes: item.notes }); }
        const reimbursedId = event.target.closest("[data-mark-reimbursed]")?.dataset.markReimbursed; if (reimbursedId) markReimbursed(reimbursedId);
        const printProfit = event.target.closest("[data-print-profit]")?.dataset.printProfit;
        if (printProfit) openEntry("extra_income", { title: "3D Printing", amount: printProfit, category: "3d_printing", payer: "Νάσος", notes: "Καθαρό κέρδος μήνα" });
    });
}

async function bootstrap() {
    bindEvents(); $("emailInput").value = localStorage.getItem("p3d-finance-email") || "";
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("./service-worker.js").catch(() => {});
    const { data } = await api.auth.getSession();
    if (data.session) { show("app"); hide("loginView"); try { await refreshData(); } catch (error) { toast(error.message); setLoading(false); } }
    else { hide("app"); show("loginView"); setLoading(false); }
}

bootstrap();
