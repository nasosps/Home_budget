import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.101.1/+esm";

const SUPABASE_URL = "https://vfegqdxpvdltwesggdwd.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_xLG3cL_kr9UqA61czA5m6w_Gwn9oBLJ";

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
    },
});

const DEFAULT_CASHFLOW_ROWS = [
    { kind: "income", title: "Μισθός Νάσου", amount: 1400 },
    { kind: "income", title: "Μισθός Ελπίδας", amount: 410 },
    { kind: "expense", title: "Δάνειο Αυτοκινήτου", amount: 250 },
    { kind: "expense", title: "Super Market", amount: 400 },
    { kind: "expense", title: "Ρεύμα", amount: 170 },
    { kind: "expense", title: "Καύσιμα", amount: 150 },
    { kind: "expense", title: "Ψυχοθεραπείες", amount: 180 },
];

const DEFAULT_CAR_LOAN = {
    label: "Αυτοκίνητο",
    lender: "Manual",
    startDate: "2023-05-01",
    totalMonths: 65,
    monthlyPayment: 250,
    downPayment: 1500,
    balloon: 0,
};

const LEGACY_CARD_PRESETS = {
    energy: { label: "Energy Mastercard", issuer: "Alpha Bank", last4: "1001" },
    alpha: { label: "Alpha Bank MasterCard", issuer: "Alpha Bank", last4: "1004" },
    pancreta: { label: "Pancreta", issuer: "Pancreta Bank", last4: null },
};

const CARD_STYLE_MAP = {
    energy: {
        border: "border-orange-500",
        badgeBg: "bg-orange-100",
        badgeText: "text-orange-800",
        label: "Energy",
    },
    alpha: {
        border: "border-red-500",
        badgeBg: "bg-red-100",
        badgeText: "text-red-800",
        label: "Alpha",
    },
    pancreta: {
        border: "border-blue-500",
        badgeBg: "bg-blue-100",
        badgeText: "text-blue-800",
        label: "PAGKR",
    },
};

const MONTH_STORAGE_KEY = "homeBudget.selectedMonth";

const state = {
    currentUser: null,
    activeTab: "cards",
    selectedMonth: "",
    cashFlow: { income: [], expenses: [] },
    carLoan: { ...DEFAULT_CAR_LOAN },
    carLoanRowId: null,
    installments: [],
    cardAccounts: [],
    legacyCardMap: {},
    globalMonthlyInstallments: 0,
};

let authSubscription = null;
let lastSessionUserId = "";

function $(id) {
    return document.getElementById(id);
}

function showLoading() {
    $("loadingOverlay").classList.remove("hidden");
}

function hideLoading() {
    $("loadingOverlay").classList.add("hidden");
}

function toNumber(value) {
    const parsed = Number.parseFloat(String(value));
    return Number.isFinite(parsed) ? parsed : 0;
}

function parseDateOnly(value) {
    return new Date(`${value}T00:00:00`);
}

function formatMoney(amount, digits = 2) {
    return `${toNumber(amount).toLocaleString("el-GR", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    })}€`;
}

function formatPlainAmount(amount, digits = 2) {
    return toNumber(amount).toLocaleString("el-GR", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    });
}

function formatShortDate(value) {
    if (!value) {
        return "--";
    }
    return parseDateOnly(value).toLocaleDateString("el-GR");
}

function formatMonthValue(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function currentMonthValue() {
    return formatMonthValue(new Date());
}

function parseMonthValue(value) {
    if (!/^\d{4}-\d{2}$/.test(value || "")) {
        return parseMonthValue(currentMonthValue());
    }
    const [year, month] = value.split("-").map((item) => Number.parseInt(item, 10));
    return new Date(year, month - 1, 1);
}

function referenceMonthDate(offset = 0) {
    const date = parseMonthValue(state.selectedMonth || currentMonthValue());
    date.setMonth(date.getMonth() + offset);
    return date;
}

function monthLabel(offset = 0) {
    return new Intl.DateTimeFormat("el-GR", { month: "short" }).format(referenceMonthDate(offset)).toUpperCase();
}

function monthLongLabel(offset = 0) {
    return new Intl.DateTimeFormat("el-GR", { month: "long", year: "numeric" }).format(referenceMonthDate(offset));
}

function updateMonthControls() {
    if (!$("monthPicker")) {
        return;
    }
    const selectedMonth = state.selectedMonth || currentMonthValue();
    $("monthPicker").value = selectedMonth;
    $("monthDisplayLabel").innerText = `Προβολή: ${monthLongLabel(0)}`;
    $("sumEnergyLabel").innerText = monthLabel(0);
    $("sumAlphaLabel").innerText = monthLabel(0);
    $("sumPancretaLabel").innerText = monthLabel(0);
    $("nextSumEnergyLabel").innerText = monthLabel(1);
    $("nextSumAlphaLabel").innerText = monthLabel(1);
    $("nextSumPancretaLabel").innerText = monthLabel(1);
}

function setSelectedMonth(value, persist = true) {
    state.selectedMonth = /^\d{4}-\d{2}$/.test(value || "") ? value : currentMonthValue();
    if (persist) {
        window.localStorage.setItem(MONTH_STORAGE_KEY, state.selectedMonth);
    }
    updateMonthControls();
    if (state.currentUser) {
        renderCarLoan();
        renderInstallments();
        updateSummaryView();
    }
}

function shiftSelectedMonth(offset) {
    const date = referenceMonthDate(0);
    date.setMonth(date.getMonth() + offset);
    setSelectedMonth(formatMonthValue(date));
}

function resetState() {
    state.cashFlow = { income: [], expenses: [] };
    state.carLoan = { ...DEFAULT_CAR_LOAN };
    state.carLoanRowId = null;
    state.installments = [];
    state.cardAccounts = [];
    state.legacyCardMap = {};
    state.globalMonthlyInstallments = 0;
}

function showLoggedOut(message = "") {
    resetState();
    $("loginView").classList.remove("hidden");
    $("navTabs").classList.add("hidden");
    $("monthControls").classList.add("hidden");
    $("logoutBtn").classList.add("hidden");
    $("fabBtn").classList.add("hidden");
    document.querySelectorAll(".tab-content").forEach((element) => element.classList.add("hidden"));
    $("loginMsg").innerText = message;
}

function showAppShell() {
    $("loginView").classList.add("hidden");
    $("navTabs").classList.remove("hidden");
    $("monthControls").classList.remove("hidden");
    $("logoutBtn").classList.remove("hidden");
    updateMonthControls();
    switchTab(state.activeTab);
}

function setSummaryTitle() {
    $("summaryTitle").innerText = `Τελικό Διαθέσιμο (${monthLongLabel(0).toUpperCase()})`;
}

function switchTab(tabName) {
    state.activeTab = tabName;
    document.querySelectorAll(".tab-content").forEach((element) => element.classList.add("hidden"));
    document.querySelectorAll(".nav-btn").forEach((element) => element.classList.remove("active"));
    $(`tab-${tabName}`).classList.remove("hidden");
    $(`tabBtn-${tabName}`).classList.add("active");
    $("fabBtn").classList.toggle("hidden", tabName !== "cards");
    if (tabName === "summary") {
        updateSummaryView();
    }
}

function cashFlowTotals() {
    return {
        income: state.cashFlow.income.reduce((sum, item) => sum + toNumber(item.amount), 0),
        expenses: state.cashFlow.expenses.reduce((sum, item) => sum + toNumber(item.amount), 0),
    };
}

function updateCashFlowTotals() {
    const totals = cashFlowTotals();
    $("totalIncomeDisplay").innerText = formatMoney(totals.income, 0);
    $("totalFixedDisplay").innerText = formatMoney(totals.expenses, 0);
}

function updateSummaryView() {
    setSummaryTitle();
    const totals = cashFlowTotals();
    $("sumInc").innerText = formatMoney(totals.income, 0);
    $("sumFix").innerText = formatPlainAmount(totals.expenses, 0);
    $("sumCards").innerText = formatPlainAmount(state.globalMonthlyInstallments, 0);
    const grandTotal = totals.income - totals.expenses - state.globalMonthlyInstallments;
    $("grandTotalSummary").innerText = toNumber(grandTotal).toLocaleString("el-GR", {
        maximumFractionDigits: 0,
    });
    $("grandTotalSummary").className = `text-6xl font-black tracking-tighter ${grandTotal < 0 ? "text-red-500" : "text-slate-800"}`;
}

function inferCardKeyFromAccount(account) {
    const haystack = `${account?.label || ""} ${account?.issuer || ""} ${account?.last4 || ""}`.toLowerCase();
    if (haystack.includes("energy") || haystack.includes("1001")) {
        return "energy";
    }
    if (haystack.includes("pancreta") || haystack.includes("pagkr") || haystack.includes("παγκρ")) {
        return "pancreta";
    }
    return "alpha";
}

function inferCardKeyFromPlan(plan) {
    if (typeof plan.notes === "string" && plan.notes.startsWith("legacy_bank:")) {
        return plan.notes.replace("legacy_bank:", "");
    }
    const account = state.cardAccounts.find((item) => item.id === plan.card_account_id);
    return inferCardKeyFromAccount(account);
}

function createCashFlowRow(item, type) {
    const row = document.createElement("div");
    row.className = "flex gap-2 items-center";

    const titleInput = document.createElement("input");
    titleInput.type = "text";
    titleInput.value = item.title || "";
    titleInput.className = `flex-grow p-3 rounded-xl border text-sm font-bold text-slate-700 focus:outline-none ${type === "income" ? "border-green-200 focus:border-green-500" : "border-red-200 focus:border-red-500"}`;
    titleInput.addEventListener("change", () => {
        void updateCashFlowItem(type, item.id, "title", titleInput.value);
    });

    const amountInput = document.createElement("input");
    amountInput.type = "number";
    amountInput.step = "0.01";
    amountInput.value = toNumber(item.amount);
    amountInput.className = `w-24 p-3 rounded-xl border text-sm font-bold text-slate-700 text-right focus:outline-none ${type === "income" ? "border-green-200 focus:border-green-500" : "border-red-200 focus:border-red-500"}`;
    amountInput.addEventListener("change", () => {
        void updateCashFlowItem(type, item.id, "amount", amountInput.value);
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "w-8 h-8 text-red-300 hover:text-red-500 flex items-center justify-center";
    deleteButton.innerHTML = '<i class="fas fa-trash"></i>';
    deleteButton.addEventListener("click", () => {
        void deleteCashFlowItem(type, item.id);
    });

    row.append(titleInput, amountInput, deleteButton);
    return row;
}

function renderCashFlow() {
    const incomeList = $("incomeList");
    const expensesList = $("expensesList");
    incomeList.replaceChildren();
    expensesList.replaceChildren();

    state.cashFlow.income.forEach((item) => incomeList.appendChild(createCashFlowRow(item, "income")));
    state.cashFlow.expenses.forEach((item) => expensesList.appendChild(createCashFlowRow(item, "expenses")));
    updateCashFlowTotals();
    updateSummaryView();
}

function createActionButton(iconClass, colorClass, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `w-8 h-8 rounded-full bg-slate-100 ${colorClass} flex items-center justify-center`;
    button.innerHTML = `<i class="${iconClass} text-xs"></i>`;
    button.addEventListener("click", onClick);
    return button;
}

function buildInstallmentView(plan) {
    const startDate = parseDateOnly(plan.start_date);
    const selectedMonth = referenceMonthDate(0);
    let currentInst = ((selectedMonth.getFullYear() - startDate.getFullYear()) * 12) + (selectedMonth.getMonth() - startDate.getMonth()) + 1;
    if (currentInst < 1) {
        currentInst = 0;
    }

    const endDate = new Date(startDate);
    endDate.setMonth(startDate.getMonth() + plan.total_months - 1);

    return {
        ...plan,
        bankKey: inferCardKeyFromPlan(plan),
        currentInst,
        nextInst: currentInst + 1,
        endDate,
        isActiveThisMonth: currentInst >= 1 && currentInst <= plan.total_months,
        isActiveNextMonth: currentInst + 1 >= 1 && currentInst + 1 <= plan.total_months,
        isCompleted: currentInst > plan.total_months,
    };
}

function renderInstallments() {
    const list = $("installmentsList");
    list.replaceChildren();

    const currentMonth = monthLabel(0);
    const nextMonth = monthLabel(1);
    const installmentViews = state.installments
        .map(buildInstallmentView)
        .sort((left, right) => left.endDate - right.endDate);
    const visibleItems = installmentViews.filter((item) => item.isActiveThisMonth);

    let sumEnergy = 0;
    let sumAlpha = 0;
    let sumPancreta = 0;
    let nextEnergy = 0;
    let nextAlpha = 0;
    let nextPancreta = 0;

    installmentViews.forEach((plan) => {
        const monthlyPayment = toNumber(plan.monthly_payment);
        if (plan.bankKey === "energy") {
            if (plan.isActiveThisMonth) {
                sumEnergy += monthlyPayment;
            }
            if (plan.isActiveNextMonth) {
                nextEnergy += monthlyPayment;
            }
        } else if (plan.bankKey === "pancreta") {
            if (plan.isActiveThisMonth) {
                sumPancreta += monthlyPayment;
            }
            if (plan.isActiveNextMonth) {
                nextPancreta += monthlyPayment;
            }
        } else {
            if (plan.isActiveThisMonth) {
                sumAlpha += monthlyPayment;
            }
            if (plan.isActiveNextMonth) {
                nextAlpha += monthlyPayment;
            }
        }
    });

    visibleItems.forEach((plan) => {
        const style = CARD_STYLE_MAP[plan.bankKey] || CARD_STYLE_MAP.alpha;
        const monthlyPayment = toNumber(plan.monthly_payment);
        const nextText = plan.nextInst > plan.total_months
            ? "ΤΕΛΟΣ"
            : `Δόση ${plan.nextInst} / ${plan.total_months}`;

        const card = document.createElement("div");
        card.className = `bg-white p-5 rounded-3xl shadow-sm border-l-8 ${style.border} relative overflow-hidden`;

        const header = document.createElement("div");
        header.className = "flex justify-between items-start mb-2";

        const left = document.createElement("div");
        const title = document.createElement("h4");
        title.className = "font-bold text-slate-800 text-lg";
        title.innerText = plan.title;
        const badge = document.createElement("span");
        badge.className = `${style.badgeBg} ${style.badgeText} text-[10px] px-2 py-1 rounded font-bold uppercase`;
        badge.innerText = style.label;
        left.append(title, badge);

        const payment = document.createElement("span");
        payment.className = "font-bold text-xl text-slate-900";
        payment.innerText = formatMoney(monthlyPayment);
        header.append(left, payment);

        const detailBox = document.createElement("div");
        detailBox.className = "mt-4 space-y-2 bg-slate-50 p-3 rounded-xl border border-slate-100";

        const currentRow = document.createElement("div");
        currentRow.className = "flex justify-between items-center text-sm";
        const currentLabel = document.createElement("span");
        currentLabel.className = "text-slate-500 font-medium";
        currentLabel.innerText = `Τώρα (${currentMonth}):`;
        const currentValue = document.createElement("span");
        currentValue.className = "font-bold text-slate-800 bg-white px-2 py-0.5 rounded shadow-sm border border-slate-200";
        currentValue.innerText = `Δόση ${plan.currentInst} / ${plan.total_months}`;
        currentRow.append(currentLabel, currentValue);

        const nextRow = document.createElement("div");
        nextRow.className = "flex justify-between items-center text-sm opacity-60";
        const nextLabel = document.createElement("span");
        nextLabel.className = "text-slate-500 font-medium";
        nextLabel.innerText = `Μετά (${nextMonth}):`;
        const nextValue = document.createElement("span");
        nextValue.className = "font-bold text-slate-800";
        nextValue.innerText = nextText;
        nextRow.append(nextLabel, nextValue);
        detailBox.append(currentRow, nextRow);

        const footer = document.createElement("div");
        footer.className = "flex justify-between items-end mt-3";

        const endText = document.createElement("p");
        endText.className = "text-[10px] text-slate-400 font-bold uppercase tracking-wide";
        endText.innerText = `Λήξη: ${plan.endDate.toLocaleDateString("el-GR", { month: "long", year: "numeric" })}`;

        const buttons = document.createElement("div");
        buttons.className = "flex gap-2";
        buttons.append(
            createActionButton("fas fa-pencil-alt", "text-slate-400 hover:text-blue-600", () => editInstallment(plan.id)),
            createActionButton("fas fa-trash", "text-slate-400 hover:text-red-500", () => {
                void deleteInstallment(plan.id);
            }),
        );

        footer.append(endText, buttons);
        card.append(header, detailBox, footer);
        list.appendChild(card);
    });

    if (!visibleItems.length) {
        const emptyState = document.createElement("div");
        emptyState.className = "bg-slate-50 border border-dashed border-slate-200 rounded-3xl p-5 text-sm text-slate-500";
        emptyState.innerText = "Δεν υπάρχουν ενεργές δόσεις ακόμα.";
        list.appendChild(emptyState);
    }

    $("sumEnergy").innerText = formatPlainAmount(sumEnergy);
    $("nextSumEnergy").innerText = formatPlainAmount(nextEnergy);
    $("sumAlpha").innerText = formatPlainAmount(sumAlpha);
    $("nextSumAlpha").innerText = formatPlainAmount(nextAlpha);
    $("sumPancreta").innerText = formatPlainAmount(sumPancreta);
    $("nextSumPancreta").innerText = formatPlainAmount(nextPancreta);
    state.globalMonthlyInstallments = sumEnergy + sumAlpha + sumPancreta;
    updateSummaryView();
}

function renderCarLoan() {
    const startDate = parseDateOnly(state.carLoan.startDate);
    const selectedMonth = referenceMonthDate(0);
    let currentInst = ((selectedMonth.getFullYear() - startDate.getFullYear()) * 12) + (selectedMonth.getMonth() - startDate.getMonth()) + 1;
    if (currentInst < 1) {
        currentInst = 0;
    }
    if (currentInst > state.carLoan.totalMonths) {
        currentInst = state.carLoan.totalMonths;
    }

    const installmentsPaid = currentInst > 0 ? currentInst - 1 : 0;
    const installmentsLeft = Math.max(state.carLoan.totalMonths - installmentsPaid, 0);
    const paidSoFar = (installmentsPaid * state.carLoan.monthlyPayment) + toNumber(state.carLoan.downPayment);
    const remainingAmount = (installmentsLeft * state.carLoan.monthlyPayment) + toNumber(state.carLoan.balloon);
    const totalPrincipal = (state.carLoan.totalMonths * state.carLoan.monthlyPayment) + toNumber(state.carLoan.downPayment) + toNumber(state.carLoan.balloon);
    const endDate = new Date(startDate);
    endDate.setMonth(startDate.getMonth() + state.carLoan.totalMonths - 1);

    $("carDoseis").innerText = `${currentInst} / ${state.carLoan.totalMonths}`;
    $("carPaid").innerText = formatMoney(paidSoFar);
    $("carRemaining").innerText = formatMoney(remainingAmount);
    $("carTotalCost").innerText = formatMoney(totalPrincipal);
    $("carEnds").innerText = endDate.toLocaleDateString("el-GR", { month: "short", year: "numeric" });
    $("carInstLeft").innerText = String(installmentsLeft);
    $("carProgress").style.width = `${state.carLoan.totalMonths > 0 ? (currentInst / state.carLoan.totalMonths) * 100 : 0}%`;
}

async function assertOwnerAccess() {
    const { data, error } = await supabase
        .from("profiles")
        .select("id,email,is_owner")
        .eq("id", state.currentUser.id)
        .maybeSingle();

    if (error || !data?.is_owner) {
        await supabase.auth.signOut();
        showLoggedOut("Ο λογαριασμός δεν έχει πρόσβαση σε αυτά τα δεδομένα.");
        return false;
    }
    return true;
}

async function ensureLegacyCardAccounts() {
    const { data, error } = await supabase
        .from("card_accounts")
        .select("id,label,last4,issuer,created_at,is_active")
        .eq("user_id", state.currentUser.id)
        .eq("is_active", true)
        .order("created_at", { ascending: true });

    if (error) {
        throw error;
    }

    const accounts = data || [];
    const legacyMap = {};
    accounts.forEach((account) => {
        const key = inferCardKeyFromAccount(account);
        if (!legacyMap[key]) {
            legacyMap[key] = account.id;
        }
    });

    const missingRows = Object.entries(LEGACY_CARD_PRESETS)
        .filter(([key]) => !legacyMap[key])
        .map(([, preset]) => ({
            user_id: state.currentUser.id,
            issuer: preset.issuer,
            label: preset.label,
            last4: preset.last4,
            is_active: true,
        }));

    let mergedAccounts = accounts;
    if (missingRows.length) {
        const { data: created, error: insertError } = await supabase
            .from("card_accounts")
            .insert(missingRows)
            .select("id,label,last4,issuer,created_at,is_active");

        if (insertError) {
            throw insertError;
        }
        mergedAccounts = [...accounts, ...(created || [])];
    }

    state.cardAccounts = mergedAccounts;
    state.legacyCardMap = {};
    mergedAccounts.forEach((account) => {
        const key = inferCardKeyFromAccount(account);
        if (!state.legacyCardMap[key]) {
            state.legacyCardMap[key] = account.id;
        }
    });
}

async function seedDefaultCashFlow() {
    const rows = DEFAULT_CASHFLOW_ROWS.map((item) => ({
        user_id: state.currentUser.id,
        kind: item.kind,
        title: item.title,
        amount: item.amount,
        source: "seed_v1",
        notes: "",
        is_active: true,
    }));

    const { error } = await supabase.from("cashflow_items").insert(rows);
    if (error) {
        throw error;
    }
}

async function loadCashFlow() {
    const { data, error } = await supabase
        .from("cashflow_items")
        .select("id,kind,title,amount,created_at")
        .eq("user_id", state.currentUser.id)
        .eq("is_active", true)
        .order("created_at", { ascending: true });

    if (error) {
        throw error;
    }

    if (!data || !data.length) {
        await seedDefaultCashFlow();
        return loadCashFlow();
    }

    state.cashFlow = {
        income: data.filter((item) => item.kind === "income"),
        expenses: data.filter((item) => item.kind === "expense"),
    };
    renderCashFlow();
}

async function seedDefaultCarLoan() {
    const { data, error } = await supabase
        .from("car_loans")
        .insert({
            user_id: state.currentUser.id,
            label: DEFAULT_CAR_LOAN.label,
            lender: DEFAULT_CAR_LOAN.lender,
            start_date: DEFAULT_CAR_LOAN.startDate,
            total_months: DEFAULT_CAR_LOAN.totalMonths,
            monthly_payment: DEFAULT_CAR_LOAN.monthlyPayment,
            down_payment: DEFAULT_CAR_LOAN.downPayment,
            balloon: DEFAULT_CAR_LOAN.balloon,
            is_active: true,
        })
        .select("id")
        .single();

    if (error) {
        throw error;
    }
    state.carLoanRowId = data.id;
}

async function loadCarLoan() {
    const { data, error } = await supabase
        .from("car_loans")
        .select("id,label,lender,start_date,total_months,monthly_payment,down_payment,balloon")
        .eq("user_id", state.currentUser.id)
        .eq("is_active", true)
        .order("created_at", { ascending: false })
        .limit(1);

    if (error) {
        throw error;
    }

    if (!data || !data.length) {
        await seedDefaultCarLoan();
        return loadCarLoan();
    }

    const row = data[0];
    state.carLoanRowId = row.id;
    state.carLoan = {
        label: row.label || DEFAULT_CAR_LOAN.label,
        lender: row.lender || DEFAULT_CAR_LOAN.lender,
        startDate: row.start_date,
        totalMonths: row.total_months,
        monthlyPayment: toNumber(row.monthly_payment),
        downPayment: toNumber(row.down_payment),
        balloon: toNumber(row.balloon),
    };
    renderCarLoan();
}

async function loadInstallments() {
    const { data, error } = await supabase
        .from("installment_plans")
        .select("id,card_account_id,title,total_amount,total_months,monthly_payment,start_date,notes,status,created_at")
        .eq("user_id", state.currentUser.id)
        .eq("status", "active")
        .order("start_date", { ascending: true });

    if (error) {
        throw error;
    }

    state.installments = data || [];
    renderInstallments();
}

async function loadImportOverview() {
    const card = $("importOverviewCard");
    const [{ data: latestFiles, error: latestError }, { count, error: countError }] = await Promise.all([
        supabase
            .from("import_files")
            .select("original_name,statement_from,statement_to,last_status,created_at")
            .eq("user_id", state.currentUser.id)
            .order("created_at", { ascending: false })
            .limit(1),
        supabase
            .from("import_files")
            .select("id", { head: true, count: "exact" })
            .eq("user_id", state.currentUser.id),
    ]);

    if (latestError || countError || !latestFiles || !latestFiles.length) {
        card.classList.add("hidden");
        return;
    }

    const latest = latestFiles[0];
    const fileCount = count || latestFiles.length;
    const range = latest.statement_from && latest.statement_to
        ? `${formatShortDate(latest.statement_from)} - ${formatShortDate(latest.statement_to)}`
        : "χωρίς περίοδο";

    $("importOverviewPrimary").innerText = `Τελευταίο PDF: ${latest.original_name}`;
    $("importOverviewSecondary").innerText = `${fileCount} αρχεία synced • ${range}`;
    card.classList.remove("hidden");
}

async function refreshAppData() {
    await ensureLegacyCardAccounts();
    await Promise.all([
        loadCashFlow(),
        loadCarLoan(),
        loadInstallments(),
        loadImportOverview(),
    ]);
    showAppShell();
    hideLoading();
}

async function updateCashFlowItem(type, id, field, value) {
    const payload = field === "amount" ? { amount: toNumber(value) } : { title: value.trim() };
    const { error } = await supabase
        .from("cashflow_items")
        .update(payload)
        .eq("id", id)
        .eq("user_id", state.currentUser.id);

    if (error) {
        alert("Δεν μπόρεσα να αποθηκεύσω την αλλαγή.");
        return;
    }
    await loadCashFlow();
}

async function addCashFlowItem(type) {
    const { error } = await supabase.from("cashflow_items").insert({
        user_id: state.currentUser.id,
        kind: type === "income" ? "income" : "expense",
        title: "",
        amount: 0,
        source: "manual",
        notes: "",
        is_active: true,
    });

    if (error) {
        alert("Δεν μπόρεσα να προσθέσω νέα γραμμή.");
        return;
    }
    await loadCashFlow();
}

async function deleteCashFlowItem(type, id) {
    if (!window.confirm("Διαγραφή;")) {
        return;
    }

    const { error } = await supabase
        .from("cashflow_items")
        .update({ is_active: false })
        .eq("id", id)
        .eq("user_id", state.currentUser.id);

    if (error) {
        alert("Δεν μπόρεσα να διαγράψω τη γραμμή.");
        return;
    }
    await loadCashFlow();
}

async function saveCarLoanData(payload) {
    if (state.carLoanRowId) {
        const { error } = await supabase
            .from("car_loans")
            .update(payload)
            .eq("id", state.carLoanRowId)
            .eq("user_id", state.currentUser.id);
        if (error) {
            throw error;
        }
        return;
    }

    const { data, error } = await supabase
        .from("car_loans")
        .insert(payload)
        .select("id")
        .single();

    if (error) {
        throw error;
    }
    state.carLoanRowId = data.id;
}

function openCarModal() {
    $("carModal").classList.remove("hidden");
    window.setTimeout(() => $("carModal").classList.add("active"), 10);
    $("inpCarStart").value = state.carLoan.startDate;
    $("inpCarMonths").value = state.carLoan.totalMonths;
    $("inpCarAmount").value = state.carLoan.monthlyPayment;
    $("inpCarDown").value = state.carLoan.downPayment || 0;
}

function closeCarModal() {
    $("carModal").classList.remove("active");
    window.setTimeout(() => $("carModal").classList.add("hidden"), 200);
}

async function saveCarLoanFromModal() {
    const startDate = $("inpCarStart").value;
    const totalMonths = Number.parseInt($("inpCarMonths").value, 10);
    const monthlyPayment = toNumber($("inpCarAmount").value);
    const downPayment = toNumber($("inpCarDown").value);

    if (!startDate || !totalMonths || !monthlyPayment) {
        alert("Λείπουν στοιχεία");
        return;
    }

    try {
        await saveCarLoanData({
            user_id: state.currentUser.id,
            label: state.carLoan.label || DEFAULT_CAR_LOAN.label,
            lender: state.carLoan.lender || DEFAULT_CAR_LOAN.lender,
            start_date: startDate,
            total_months: totalMonths,
            monthly_payment: monthlyPayment,
            down_payment: downPayment,
            balloon: 0,
            is_active: true,
        });
        await loadCarLoan();
        closeCarModal();
    } catch (error) {
        console.error("saveCarLoanFromModal failed:", error);
        alert("Δεν μπόρεσα να αποθηκεύσω το δάνειο.");
    }
}

function openModal() {
    $("addModal").classList.remove("hidden");
    window.setTimeout(() => $("addModal").classList.add("active"), 10);
    if (!$("inpDate").value) {
        $("inpDate").value = `${state.selectedMonth || currentMonthValue()}-01`;
    }
}

function closeModal() {
    $("addModal").classList.remove("active");
    window.setTimeout(() => {
        $("addModal").classList.add("hidden");
        $("editId").value = "";
        $("modalTitle").innerText = "Νέα Δόση";
        $("inpTitle").value = "";
        $("inpAmount").value = "";
        $("inpMonths").value = "";
        $("inpDate").value = "";
    }, 200);
}

function editInstallment(id) {
    const plan = state.installments.find((item) => item.id === id);
    if (!plan) {
        return;
    }

    $("editId").value = plan.id;
    $("modalTitle").innerText = "Επεξεργασία";
    $("inpTitle").value = plan.title;
    $("inpAmount").value = toNumber(plan.total_amount);
    $("inpMonths").value = plan.total_months;
    $("inpDate").value = plan.start_date;

    const bankKey = inferCardKeyFromPlan(plan);
    const radio = document.querySelector(`input[name="bankType"][value="${bankKey}"]`);
    if (radio) {
        radio.checked = true;
    }
    openModal();
}

async function saveInstallment() {
    const id = $("editId").value;
    const title = $("inpTitle").value.trim();
    const totalAmount = toNumber($("inpAmount").value);
    const totalMonths = Number.parseInt($("inpMonths").value, 10);
    const startDate = $("inpDate").value;
    const bankKey = document.querySelector('input[name="bankType"]:checked')?.value || "alpha";

    if (!title || !totalAmount || !totalMonths || !startDate) {
        alert("Λείπουν στοιχεία");
        return;
    }

    try {
        await ensureLegacyCardAccounts();
        const cardAccountId = state.legacyCardMap[bankKey] || null;
        const payload = {
            user_id: state.currentUser.id,
            card_account_id: cardAccountId,
            title,
            total_amount: totalAmount,
            total_months: totalMonths,
            monthly_payment: Number((totalAmount / totalMonths).toFixed(2)),
            start_date: startDate,
            status: "active",
            notes: `legacy_bank:${bankKey}`,
        };

        if (id) {
            const { error } = await supabase
                .from("installment_plans")
                .update(payload)
                .eq("id", id)
                .eq("user_id", state.currentUser.id);
            if (error) {
                throw error;
            }
        } else {
            const { error } = await supabase.from("installment_plans").insert(payload);
            if (error) {
                throw error;
            }
        }

        closeModal();
        await loadInstallments();
    } catch (error) {
        console.error("saveInstallment failed:", error);
        alert("Δεν μπόρεσα να αποθηκεύσω τη δόση.");
    }
}

async function deleteInstallment(id) {
    if (!window.confirm("Διαγραφή;")) {
        return;
    }

    const { error } = await supabase
        .from("installment_plans")
        .update({ status: "cancelled" })
        .eq("id", id)
        .eq("user_id", state.currentUser.id);

    if (error) {
        alert("Δεν μπόρεσα να διαγράψω τη δόση.");
        return;
    }
    await loadInstallments();
}

async function handleLogin() {
    const email = $("emailInput").value.trim();
    const password = $("passInput").value;

    if (!email || !password) {
        $("loginMsg").innerText = "Συμπλήρωσε email και κωδικό.";
        return;
    }

    $("loginMsg").innerText = "";
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
        $("loginMsg").innerText = "Λάθος στοιχεία ή μη εξουσιοδοτημένη πρόσβαση.";
    }
}

async function handleLogout() {
    await supabase.auth.signOut();
    showLoggedOut("");
}

async function handleSession(session) {
    const nextUserId = session?.user?.id || "";
    if (!nextUserId) {
        lastSessionUserId = "";
        state.currentUser = null;
        showLoggedOut("");
        return;
    }

    if (lastSessionUserId === nextUserId) {
        return;
    }

    lastSessionUserId = nextUserId;
    state.currentUser = session.user;
    showLoading();

    try {
        const allowed = await assertOwnerAccess();
        if (!allowed) {
            hideLoading();
            return;
        }
        await refreshAppData();
    } catch (error) {
        console.error("handleSession/refreshAppData failed:", error);
        hideLoading();
        showLoggedOut("Σφάλμα σύνδεσης με το Supabase.");
    }
}

async function bootstrap() {
    window.switchTab = switchTab;
    window.handleLogin = () => { void handleLogin(); };
    window.addCashFlowItem = (type) => { void addCashFlowItem(type); };
    window.updateCashFlowItem = (type, id, field, value) => { void updateCashFlowItem(type, id, field, value); };
    window.deleteCashFlowItem = (type, id) => { void deleteCashFlowItem(type, id); };
    window.openCarModal = openCarModal;
    window.closeCarModal = closeCarModal;
    window.saveCarLoanFromModal = () => { void saveCarLoanFromModal(); };
    window.openModal = openModal;
    window.closeModal = closeModal;
    window.editInstallment = editInstallment;
    window.saveInstallment = () => { void saveInstallment(); };

    $("logoutBtn").addEventListener("click", () => {
        void handleLogout();
    });

    ["emailInput", "passInput"].forEach((id) => {
        $(id).addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                void handleLogin();
            }
        });
    });

    state.selectedMonth = window.localStorage.getItem(MONTH_STORAGE_KEY) || currentMonthValue();
    $("monthPrevBtn").addEventListener("click", () => {
        shiftSelectedMonth(-1);
    });
    $("monthNextBtn").addEventListener("click", () => {
        shiftSelectedMonth(1);
    });
    $("monthTodayBtn").addEventListener("click", () => {
        setSelectedMonth(currentMonthValue());
    });
    $("monthPicker").addEventListener("change", (event) => {
        setSelectedMonth(event.target.value || currentMonthValue());
    });

    updateMonthControls();
    setSummaryTitle();
    try {
        const { data } = await supabase.auth.getSession();
        await handleSession(data?.session ?? null);
    } catch (error) {
        console.error("bootstrap getSession failed:", error);
        showLoggedOut("Σφάλμα σύνδεσης με το Supabase.");
    }

    authSubscription = supabase.auth.onAuthStateChange((_event, session) => {
        void handleSession(session);
    });
}

void bootstrap();

window.addEventListener("beforeunload", () => {
    authSubscription?.data?.subscription?.unsubscribe?.();
});
