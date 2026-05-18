<?php

declare(strict_types=1);

require_once __DIR__ . '/_bootstrap.php';

$action = (string) ($_GET['action'] ?? '');
$method = strtoupper((string) ($_SERVER['REQUEST_METHOD'] ?? 'GET'));

if ($method === 'OPTIONS') {
    json_response(['ok' => true], 200);
}

set_exception_handler(static function (Throwable $throwable): void {
    json_response([
        'error' => $throwable->getMessage(),
    ], 500);
});

switch ($action) {
    case 'health':
        json_response(['ok' => true, 'time' => now_utc()]);
        break;

    case 'session':
        if ($method !== 'GET') {
            json_response(['error' => 'Method not allowed.'], 405);
        }
        json_response(['data' => ['session' => current_session()]]);
        break;

    case 'login':
        if ($method !== 'POST') {
            json_response(['error' => 'Method not allowed.'], 405);
        }
        $payload = json_input();
        $email = mb_strtolower(trim((string) ($payload['email'] ?? '')));
        $password = (string) ($payload['password'] ?? '');
        if ($email === '' || $password === '') {
            json_response(['error' => 'Missing credentials.'], 400);
        }

        $user = find_user_by_email($email);
        if (!$user || $user['status'] !== 'active' || !password_verify_app($password, (string) $user['password_hash'])) {
            json_response(['error' => 'Invalid credentials.'], 401);
        }
        if (empty($user['is_owner'])) {
            json_response(['error' => 'Unauthorized.'], 403);
        }

        destroy_current_session();
        $session = create_user_session($user);
        json_response(['data' => ['session' => $session]]);
        break;

    case 'logout':
        if ($method !== 'POST') {
            json_response(['error' => 'Method not allowed.'], 405);
        }
        destroy_current_session();
        json_response(['data' => ['session' => null]]);
        break;

    case 'db':
        if ($method !== 'POST') {
            json_response(['error' => 'Method not allowed.'], 405);
        }
        handle_db_request();
        break;

    default:
        json_response(['error' => 'Unknown action.'], 404);
}

function handle_db_request(): void
{
    $session = require_owner_session();
    $userId = (string) $session['user']['id'];
    $input = json_input();

    $table = (string) ($input['table'] ?? '');
    $operation = (string) ($input['operation'] ?? 'select');
    $tableDefinition = require_table_definition($table);

    if ($operation === 'select') {
        json_response(handle_select($table, $tableDefinition, $userId, $input));
    }
    if ($operation === 'insert') {
        if (empty($tableDefinition['allow_insert'])) {
            json_response(['error' => 'Insert not allowed.'], 403);
        }
        json_response(handle_insert($table, $tableDefinition, $userId, $input));
    }
    if ($operation === 'update') {
        if (empty($tableDefinition['allow_update'])) {
            json_response(['error' => 'Update not allowed.'], 403);
        }
        json_response(handle_update($table, $tableDefinition, $userId, $input));
    }

    json_response(['error' => 'Unsupported operation.'], 400);
}

function build_where_clause(array $filters, array $tableDefinition, string $userId, array &$params): string
{
    $parts = [];
    $index = 0;
    foreach ($filters as $filter) {
        $paramKey = ':f' . $index++;
        $parts[] = $filter['field'] . ' = ' . $paramKey;
        $params[$paramKey] = $filter['value'];
    }

    $ownerColumn = $tableDefinition['owner_column'];
    $parts[] = $ownerColumn . ' = :owner_id';
    $params[':owner_id'] = $userId;

    return implode(' AND ', $parts);
}

function handle_select(string $table, array $tableDefinition, string $userId, array $input): array
{
    $columns = normalize_columns((string) ($input['columns'] ?? '*'), $tableDefinition);
    $filters = normalize_filters((array) ($input['filters'] ?? []), $tableDefinition);
    $order = normalize_order(isset($input['order']) && is_array($input['order']) ? $input['order'] : null, $tableDefinition);
    $limit = isset($input['limit']) ? max(0, (int) $input['limit']) : 0;
    $options = is_array($input['options'] ?? null) ? $input['options'] : [];

    $params = [];
    $where = build_where_clause($filters, $tableDefinition, $userId, $params);

    if (!empty($options['head']) && ($options['count'] ?? '') === 'exact') {
        $statement = db()->prepare('SELECT COUNT(*) FROM ' . $table . ' WHERE ' . $where);
        $statement->execute($params);
        return [
            'data' => null,
            'count' => (int) $statement->fetchColumn(),
        ];
    }

    $sql = 'SELECT ' . $columns . ' FROM ' . $table . ' WHERE ' . $where;
    if ($order) {
        $sql .= ' ORDER BY ' . $order['field'] . ' ' . $order['direction'];
    }
    if ($limit > 0) {
        $sql .= ' LIMIT ' . $limit;
    }

    $statement = db()->prepare($sql);
    $statement->execute($params);
    return [
        'data' => $statement->fetchAll(),
        'count' => null,
    ];
}

function handle_insert(string $table, array $tableDefinition, string $userId, array $input): array
{
    $payload = $input['payload'] ?? null;
    if ($payload === null) {
        json_response(['error' => 'Missing payload.'], 400);
    }

    $rows = array_is_list($payload) ? $payload : [$payload];
    $insertedIds = [];
    $pdo = db();

    foreach ($rows as $row) {
        if (!is_array($row)) {
            json_response(['error' => 'Invalid insert payload.'], 400);
        }

        $clean = sanitize_payload_row($table, $row, $tableDefinition, $userId, true);
        $columns = array_keys($clean);
        $placeholders = array_map(static fn ($column) => ':' . $column, $columns);
        $sql = 'INSERT INTO ' . $table .
            ' (' . implode(', ', $columns) . ') VALUES (' . implode(', ', $placeholders) . ')';
        $statement = $pdo->prepare($sql);

        $params = [];
        foreach ($clean as $column => $value) {
            $params[':' . $column] = $value;
        }
        $statement->execute($params);
        $insertedIds[] = $clean['id'];
    }

    $returningColumns = trim((string) ($input['returningColumns'] ?? ''));
    if ($returningColumns === '') {
        return ['data' => null, 'count' => null];
    }

    $columns = normalize_columns($returningColumns, $tableDefinition);
    $placeholders = [];
    $params = [':owner_id' => $userId];
    foreach ($insertedIds as $index => $id) {
        $key = ':id' . $index;
        $placeholders[] = $key;
        $params[$key] = $id;
    }

    $ownerColumn = $tableDefinition['owner_column'];
    $sql = 'SELECT ' . $columns .
        ' FROM ' . $table .
        ' WHERE ' . $ownerColumn . ' = :owner_id AND id IN (' . implode(', ', $placeholders) . ')';
    $statement = $pdo->prepare($sql);
    $statement->execute($params);
    return ['data' => $statement->fetchAll(), 'count' => null];
}

function handle_update(string $table, array $tableDefinition, string $userId, array $input): array
{
    $payload = $input['payload'] ?? null;
    if (!is_array($payload)) {
        json_response(['error' => 'Missing update payload.'], 400);
    }

    $filters = normalize_filters((array) ($input['filters'] ?? []), $tableDefinition);
    $clean = sanitize_payload_row($table, $payload, $tableDefinition, $userId, false);
    unset($clean['id']);
    if (!$clean) {
        json_response(['error' => 'No writable fields supplied.'], 400);
    }

    $assignments = [];
    $params = [];
    foreach ($clean as $column => $value) {
        $key = ':set_' . $column;
        $assignments[] = $column . ' = ' . $key;
        $params[$key] = $value;
    }

    $whereParams = [];
    $where = build_where_clause($filters, $tableDefinition, $userId, $whereParams);
    $params = array_merge($params, $whereParams);

    $sql = 'UPDATE ' . $table . ' SET ' . implode(', ', $assignments) . ' WHERE ' . $where;
    $statement = db()->prepare($sql);
    $statement->execute($params);

    $returningColumns = trim((string) ($input['returningColumns'] ?? ''));
    if ($returningColumns === '') {
        return ['data' => null, 'count' => null];
    }

    $columns = normalize_columns($returningColumns, $tableDefinition);
    $select = db()->prepare('SELECT ' . $columns . ' FROM ' . $table . ' WHERE ' . $where);
    $select->execute($whereParams);
    return ['data' => $select->fetchAll(), 'count' => null];
}
