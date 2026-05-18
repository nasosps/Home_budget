const API_BASE = "./api/index.php";

async function apiRequest(action, { method = "GET", body = null } = {}) {
    const options = {
        method,
        credentials: "same-origin",
        headers: {
            Accept: "application/json",
        },
    };

    if (body !== null) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE}?action=${encodeURIComponent(action)}`, options);
    let payload = null;
    try {
        payload = await response.json();
    } catch {
        payload = null;
    }

    if (!response.ok) {
        throw new Error(payload?.error || payload?.message || `HTTP ${response.status}`);
    }

    return payload || {};
}

function normalizeFailure(error) {
    return {
        message: error instanceof Error ? error.message : String(error),
    };
}

class LocalQueryBuilder {
    constructor(table) {
        this.table = table;
        this.operation = "select";
        this.columns = "*";
        this.returningColumns = "";
        this.filters = [];
        this.orderBy = null;
        this.limitValue = 0;
        this.payload = null;
        this.options = {};
        this.wantsSingle = false;
        this.wantsMaybeSingle = false;
    }

    select(columns = "*", options = {}) {
        if (this.operation === "insert" || this.operation === "update") {
            this.returningColumns = columns;
        } else {
            this.columns = columns;
            this.options = options || {};
        }
        return this;
    }

    insert(payload) {
        this.operation = "insert";
        this.payload = payload;
        return this;
    }

    update(payload) {
        this.operation = "update";
        this.payload = payload;
        return this;
    }

    eq(field, value) {
        this.filters.push({ field, op: "eq", value });
        return this;
    }

    order(field, options = {}) {
        this.orderBy = {
            field,
            ascending: options.ascending !== false,
        };
        return this;
    }

    limit(value) {
        this.limitValue = Number.parseInt(value, 10) || 0;
        return this;
    }

    single() {
        this.wantsSingle = true;
        return this;
    }

    maybeSingle() {
        this.wantsMaybeSingle = true;
        return this;
    }

    async execute() {
        try {
            const payload = {
                table: this.table,
                operation: this.operation,
                columns: this.columns,
                returningColumns: this.returningColumns,
                filters: this.filters,
                order: this.orderBy,
                limit: this.limitValue,
                payload: this.payload,
                options: this.options,
            };
            const response = await apiRequest("db", { method: "POST", body: payload });
            let data = response.data ?? null;
            if (this.wantsSingle || this.wantsMaybeSingle) {
                if (Array.isArray(data)) {
                    data = data.length ? data[0] : null;
                }
                if (this.wantsSingle && data === null) {
                    return { data: null, error: { message: "Expected a single row." }, count: response.count ?? null };
                }
            }
            return { data, error: null, count: response.count ?? null };
        } catch (error) {
            return { data: null, error: normalizeFailure(error), count: null };
        }
    }

    then(resolve, reject) {
        return this.execute().then(resolve, reject);
    }
}

export function createLocalClient() {
    let cachedSession = null;
    const listeners = new Set();

    function notify(event, session) {
        cachedSession = session;
        listeners.forEach((listener) => {
            try {
                listener(event, session);
            } catch (error) {
                console.error("auth listener failed:", error);
            }
        });
    }

    return {
        auth: {
            async signInWithPassword({ email, password }) {
                try {
                    const response = await apiRequest("login", {
                        method: "POST",
                        body: { email, password },
                    });
                    const session = response.data?.session ?? null;
                    notify("SIGNED_IN", session);
                    return { data: { session }, error: null };
                } catch (error) {
                    return { data: { session: null }, error: normalizeFailure(error) };
                }
            },

            async signOut() {
                try {
                    await apiRequest("logout", { method: "POST" });
                    notify("SIGNED_OUT", null);
                    return { error: null };
                } catch (error) {
                    return { error: normalizeFailure(error) };
                }
            },

            async getSession() {
                try {
                    const response = await apiRequest("session");
                    const session = response.data?.session ?? null;
                    cachedSession = session;
                    return { data: { session }, error: null };
                } catch (error) {
                    return { data: { session: cachedSession }, error: normalizeFailure(error) };
                }
            },

            onAuthStateChange(callback) {
                listeners.add(callback);
                return {
                    data: {
                        subscription: {
                            unsubscribe() {
                                listeners.delete(callback);
                            },
                        },
                    },
                };
            },
        },

        from(table) {
            return new LocalQueryBuilder(table);
        },
    };
}
