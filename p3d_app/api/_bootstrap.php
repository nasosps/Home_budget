<?php

declare(strict_types=1);

date_default_timezone_set('UTC');

const APP_PASSWORD_SCHEME = 'pbkdf2_sha256';
const APP_PASSWORD_ITERATIONS = 600000;

function app_config(): array
{
    static $config = null;
    if ($config !== null) {
        return $config;
    }

    $configPath = __DIR__ . '/config.local.php';
    if (!is_file($configPath)) {
        json_response(['error' => 'Missing local API config.'], 500);
    }

    $config = require $configPath;
    if (!is_array($config)) {
        json_response(['error' => 'Invalid local API config.'], 500);
    }

    return $config;
}

function json_response(array $payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function json_input(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') {
        return [];
    }

    $decoded = json_decode($raw, true);
    if (!is_array($decoded)) {
        json_response(['error' => 'Invalid JSON body.'], 400);
    }

    return $decoded;
}

function app_cookie_path(): string
{
    $scriptDir = str_replace('\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '/'));
    $basePath = preg_replace('#/api/?$#', '', $scriptDir);
    $basePath = $basePath !== '' ? $basePath : '/';
    return rtrim($basePath, '/') . '/';
}

function db(): PDO
{
    static $pdo = null;
    if ($pdo instanceof PDO) {
        return $pdo;
    }

    $config = app_config();
    $dsn = sprintf(
        'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
        $config['db_host'],
        (int) $config['db_port'],
        $config['db_name']
    );

    $pdo = new PDO($dsn, $config['db_user'], $config['db_password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);

    return $pdo;
}

function now_utc(): string
{
    return gmdate('Y-m-d H:i:s');
}

function generate_uuid(): string
{
    $bytes = random_bytes(16);
    $bytes[6] = chr((ord($bytes[6]) & 0x0f) | 0x40);
    $bytes[8] = chr((ord($bytes[8]) & 0x3f) | 0x80);
    $hex = bin2hex($bytes);

    return sprintf(
        '%s-%s-%s-%s-%s',
        substr($hex, 0, 8),
        substr($hex, 8, 4),
        substr($hex, 12, 4),
        substr($hex, 16, 4),
        substr($hex, 20, 12)
    );
}

function password_hash_pbkdf2(string $password, ?string $salt = null, int $iterations = APP_PASSWORD_ITERATIONS): string
{
    $salt = $salt ?: bin2hex(random_bytes(16));
    $digest = hash_pbkdf2('sha256', $password, $salt, $iterations, 64, false);
    return APP_PASSWORD_SCHEME . '$' . $iterations . '$' . $salt . '$' . $digest;
}

function password_verify_app(string $password, string $storedHash): bool
{
    if (str_starts_with($storedHash, APP_PASSWORD_SCHEME . '$')) {
        $parts = explode('$', $storedHash, 4);
        if (count($parts) !== 4) {
            return false;
        }
        [, $iterations, $salt, $expected] = $parts;
        $actual = hash_pbkdf2('sha256', $password, $salt, (int) $iterations, 64, false);
        return hash_equals($expected, $actual);
    }

    if (str_starts_with($storedHash, '$2y$') || str_starts_with($storedHash, '$argon2')) {
        return password_verify($password, $storedHash);
    }

    return false;
}

function client_ip(): ?string
{
    $keys = ['HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR'];
    foreach ($keys as $key) {
        if (!empty($_SERVER[$key])) {
            $value = trim(explode(',', (string) $_SERVER[$key])[0]);
            if ($value !== '') {
                return $value;
            }
        }
    }
    return null;
}

function session_cookie_name(): string
{
    $config = app_config();
    return (string) ($config['cookie_name'] ?? 'home_budget_session');
}

function set_session_cookie(string $token, int $expiryTimestamp): void
{
    $isSecure = !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off';
    setcookie(session_cookie_name(), $token, [
        'expires' => $expiryTimestamp,
        'path' => app_cookie_path(),
        'secure' => $isSecure,
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
}

function clear_session_cookie(): void
{
    $isSecure = !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off';
    setcookie(session_cookie_name(), '', [
        'expires' => time() - 3600,
        'path' => app_cookie_path(),
        'secure' => $isSecure,
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
}

function build_session_payload(array $userRow): array
{
    return [
        'user' => [
            'id' => $userRow['id'],
            'email' => $userRow['email'],
            'full_name' => $userRow['full_name'],
            'is_owner' => (bool) $userRow['is_owner'],
        ],
    ];
}

function find_user_by_email(string $email): ?array
{
    $statement = db()->prepare(
        'SELECT id, email, password_hash, full_name, is_owner, status
         FROM users
         WHERE email = :email
         LIMIT 1'
    );
    $statement->execute(['email' => mb_strtolower(trim($email))]);
    $row = $statement->fetch();
    return $row ?: null;
}

function create_user_session(array $userRow): array
{
    $token = bin2hex(random_bytes(32));
    $tokenHash = hash('sha256', $token);
    $sessionId = generate_uuid();
    $days = max(1, (int) (app_config()['session_days'] ?? 30));
    $expiresAt = gmdate('Y-m-d H:i:s', time() + ($days * 86400));

    $statement = db()->prepare(
        'INSERT INTO app_sessions
            (id, user_id, token_hash, ip_address, user_agent, expires_at, last_seen_at, created_at)
         VALUES
            (:id, :user_id, :token_hash, :ip_address, :user_agent, :expires_at, :last_seen_at, :created_at)'
    );
    $statement->execute([
        'id' => $sessionId,
        'user_id' => $userRow['id'],
        'token_hash' => $tokenHash,
        'ip_address' => client_ip(),
        'user_agent' => substr((string) ($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 512),
        'expires_at' => $expiresAt,
        'last_seen_at' => now_utc(),
        'created_at' => now_utc(),
    ]);

    set_session_cookie($token, strtotime($expiresAt));

    return build_session_payload($userRow);
}

function destroy_current_session(): void
{
    $token = $_COOKIE[session_cookie_name()] ?? '';
    if ($token !== '') {
        $statement = db()->prepare('DELETE FROM app_sessions WHERE token_hash = :token_hash');
        $statement->execute(['token_hash' => hash('sha256', $token)]);
    }
    clear_session_cookie();
}

function current_session(): ?array
{
    $token = $_COOKIE[session_cookie_name()] ?? '';
    if ($token === '') {
        return null;
    }

    $statement = db()->prepare(
        'SELECT
            s.id AS session_id,
            s.user_id,
            s.expires_at,
            u.id,
            u.email,
            u.full_name,
            u.is_owner,
            u.status
         FROM app_sessions s
         INNER JOIN users u ON u.id = s.user_id
         WHERE s.token_hash = :token_hash
           AND s.expires_at > UTC_TIMESTAMP()
         LIMIT 1'
    );
    $statement->execute(['token_hash' => hash('sha256', $token)]);
    $row = $statement->fetch();
    if (!$row || $row['status'] !== 'active') {
        destroy_current_session();
        return null;
    }

    $touch = db()->prepare('UPDATE app_sessions SET last_seen_at = :last_seen_at WHERE id = :id');
    $touch->execute([
        'last_seen_at' => now_utc(),
        'id' => $row['session_id'],
    ]);

    return build_session_payload($row);
}

function require_owner_session(): array
{
    $session = current_session();
    if (!$session || empty($session['user']['is_owner'])) {
        json_response(['error' => 'Unauthorized'], 401);
    }
    return $session;
}

function app_table_definitions(): array
{
    return [
        'profiles' => [
            'owner_column' => 'id',
            'columns' => ['id', 'email', 'full_name', 'is_owner', 'created_at', 'updated_at'],
            'writable' => [],
            'allow_insert' => false,
            'allow_update' => false,
        ],
        'card_accounts' => [
            'owner_column' => 'user_id',
            'columns' => ['id', 'user_id', 'issuer', 'label', 'last4', 'card_number_masked', 'is_active', 'created_at', 'updated_at'],
            'writable' => ['issuer', 'label', 'last4', 'card_number_masked', 'is_active'],
            'allow_insert' => true,
            'allow_update' => true,
        ],
        'cashflow_items' => [
            'owner_column' => 'user_id',
            'columns' => ['id', 'user_id', 'kind', 'title', 'amount', 'source', 'notes', 'is_active', 'created_at', 'updated_at'],
            'writable' => ['kind', 'title', 'amount', 'source', 'notes', 'is_active'],
            'allow_insert' => true,
            'allow_update' => true,
        ],
        'car_loans' => [
            'owner_column' => 'user_id',
            'columns' => ['id', 'user_id', 'label', 'lender', 'start_date', 'total_months', 'monthly_payment', 'down_payment', 'balloon', 'is_active', 'created_at', 'updated_at'],
            'writable' => ['label', 'lender', 'start_date', 'total_months', 'monthly_payment', 'down_payment', 'balloon', 'is_active'],
            'allow_insert' => true,
            'allow_update' => true,
        ],
        'installment_plans' => [
            'owner_column' => 'user_id',
            'columns' => ['id', 'user_id', 'card_account_id', 'title', 'total_amount', 'total_months', 'monthly_payment', 'start_date', 'status', 'notes', 'created_at', 'updated_at'],
            'writable' => ['card_account_id', 'title', 'total_amount', 'total_months', 'monthly_payment', 'start_date', 'status', 'notes'],
            'allow_insert' => true,
            'allow_update' => true,
        ],
        'import_files' => [
            'owner_column' => 'user_id',
            'columns' => ['id', 'user_id', 'original_name', 'storage_path', 'sha256', 'file_kind', 'parser_key', 'statement_from', 'statement_to', 'last_status', 'raw_metadata', 'created_at', 'updated_at'],
            'writable' => [],
            'allow_insert' => false,
            'allow_update' => false,
        ],
    ];
}

function require_table_definition(string $table): array
{
    $definitions = app_table_definitions();
    if (!isset($definitions[$table])) {
        json_response(['error' => 'Unknown table.'], 400);
    }
    return $definitions[$table];
}

function normalize_columns(string $columnString, array $tableDefinition): string
{
    $allowed = $tableDefinition['columns'];
    $columnString = trim($columnString);
    if ($columnString === '' || $columnString === '*') {
        return implode(', ', $allowed);
    }

    $columns = array_map('trim', explode(',', $columnString));
    $valid = [];
    foreach ($columns as $column) {
        if (!in_array($column, $allowed, true)) {
            json_response(['error' => 'Invalid column selection.'], 400);
        }
        $valid[] = $column;
    }

    return implode(', ', $valid);
}

function normalize_filters(array $filters, array $tableDefinition): array
{
    $allowed = $tableDefinition['columns'];
    $normalized = [];
    foreach ($filters as $filter) {
        if (!is_array($filter)) {
            continue;
        }
        $field = (string) ($filter['field'] ?? '');
        $operator = (string) ($filter['op'] ?? 'eq');
        if (!in_array($field, $allowed, true) || $operator !== 'eq') {
            json_response(['error' => 'Invalid filter.'], 400);
        }
        $normalized[] = [
            'field' => $field,
            'value' => $filter['value'] ?? null,
        ];
    }
    return $normalized;
}

function normalize_order(?array $order, array $tableDefinition): ?array
{
    if (!$order) {
        return null;
    }
    $field = (string) ($order['field'] ?? '');
    if (!in_array($field, $tableDefinition['columns'], true)) {
        json_response(['error' => 'Invalid order field.'], 400);
    }
    return [
        'field' => $field,
        'direction' => !empty($order['ascending']) ? 'ASC' : 'DESC',
    ];
}

function encode_json_columns(string $table, array $row): array
{
    $jsonColumns = [
        'import_files' => ['raw_metadata'],
    ];
    foreach ($jsonColumns[$table] ?? [] as $column) {
        if (array_key_exists($column, $row) && !is_string($row[$column])) {
            $row[$column] = json_encode($row[$column], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        }
    }
    return $row;
}

function sanitize_payload_row(string $table, array $row, array $tableDefinition, string $userId, bool $isInsert): array
{
    $clean = [];
    foreach ($tableDefinition['writable'] as $column) {
        if (array_key_exists($column, $row)) {
            $clean[$column] = $row[$column];
        }
    }

    $ownerColumn = $tableDefinition['owner_column'];
    if ($ownerColumn !== 'id') {
        $clean[$ownerColumn] = $userId;
    }

    if ($isInsert) {
        $clean['id'] = array_key_exists('id', $row) && is_string($row['id']) && $row['id'] !== '' ? $row['id'] : generate_uuid();
    }

    return encode_json_columns($table, $clean);
}
