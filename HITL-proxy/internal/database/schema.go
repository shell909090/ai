package database

const schemaSQL = `
CREATE TABLE IF NOT EXISTS specs (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	name TEXT NOT NULL,
	version TEXT NOT NULL DEFAULT '',
	raw_json TEXT NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operations (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	spec_id INTEGER NOT NULL REFERENCES specs(id),
	operation_id TEXT NOT NULL,
	method TEXT NOT NULL,
	path TEXT NOT NULL,
	summary TEXT NOT NULL DEFAULT '',
	description TEXT NOT NULL DEFAULT '',
	parameters_json TEXT NOT NULL DEFAULT '[]',
	request_body_json TEXT NOT NULL DEFAULT '{}',
	tags TEXT NOT NULL DEFAULT '',
	UNIQUE(spec_id, operation_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS operations_fts USING fts5(
	operation_id,
	summary,
	description,
	tags,
	content='operations',
	content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS operations_ai AFTER INSERT ON operations BEGIN
	INSERT INTO operations_fts(rowid, operation_id, summary, description, tags)
	VALUES (new.id, new.operation_id, new.summary, new.description, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS operations_ad AFTER DELETE ON operations BEGIN
	INSERT INTO operations_fts(operations_fts, rowid, operation_id, summary, description, tags)
	VALUES ('delete', old.id, old.operation_id, old.summary, old.description, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS operations_au AFTER UPDATE ON operations BEGIN
	INSERT INTO operations_fts(operations_fts, rowid, operation_id, summary, description, tags)
	VALUES ('delete', old.id, old.operation_id, old.summary, old.description, old.tags);
	INSERT INTO operations_fts(rowid, operation_id, summary, description, tags)
	VALUES (new.id, new.operation_id, new.summary, new.description, new.tags);
END;

CREATE TABLE IF NOT EXISTS operation_deps (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	operation_id TEXT NOT NULL,
	depends_on_id TEXT NOT NULL,
	reason TEXT NOT NULL DEFAULT '',
	spec_id INTEGER NOT NULL REFERENCES specs(id),
	UNIQUE(spec_id, operation_id, depends_on_id)
);

CREATE TABLE IF NOT EXISTS api_keys (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	key_hash TEXT NOT NULL UNIQUE,
	agent_name TEXT NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS authz_rules (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	agent_name TEXT NOT NULL,
	operation_id TEXT NOT NULL,
	allowed BOOLEAN NOT NULL DEFAULT 1,
	UNIQUE(agent_name, operation_id)
);

CREATE TABLE IF NOT EXISTS approval_rules (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	operation_id TEXT NOT NULL UNIQUE,
	required BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS approval_requests (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	operation_id TEXT NOT NULL,
	agent_name TEXT NOT NULL,
	params_json TEXT NOT NULL DEFAULT '{}',
	reason TEXT NOT NULL DEFAULT '',
	status TEXT NOT NULL DEFAULT 'pending',
	decided_at DATETIME,
	decided_by TEXT NOT NULL DEFAULT '',
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
	agent_name TEXT NOT NULL DEFAULT '',
	operation_id TEXT NOT NULL,
	params_json TEXT NOT NULL DEFAULT '{}',
	reason TEXT NOT NULL DEFAULT '',
	response_status INTEGER NOT NULL DEFAULT 0,
	response_body TEXT NOT NULL DEFAULT '',
	approval_status TEXT NOT NULL DEFAULT '',
	error_message TEXT NOT NULL DEFAULT ''
);
`
