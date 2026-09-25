CREATE TABLE tickets (
    ticket_id text PRIMARY KEY,
    customer_id text NOT NULL,
    subject text NOT NULL CHECK (char_length(subject) BETWEEN 5 AND 200),
    category text NOT NULL CHECK (category IN ('support', 'billing', 'technical')),
    status text NOT NULL CHECK (status IN ('open', 'in_progress', 'resolved')),
    priority text NOT NULL CHECK (priority IN ('critical', 'high', 'normal', 'low')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0)
);

CREATE INDEX tickets_customer_updated_idx
    ON tickets (customer_id, updated_at DESC, ticket_id);

CREATE TABLE ticket_actions (
    action_id text PRIMARY KEY CHECK (action_id ~ '^act_[0-9a-f]{32}$'),
    customer_id text NOT NULL,
    route text NOT NULL CHECK (route IN ('support', 'billing', 'technical')),
    action_type text NOT NULL CHECK (
        action_type IN ('create_ticket', 'update_ticket_status', 'update_ticket_priority')
    ),
    payload jsonb NOT NULL,
    status text NOT NULL CHECK (
        status IN ('pending', 'approved', 'executing', 'succeeded', 'failed', 'rejected', 'expired')
    ),
    approval_required boolean NOT NULL DEFAULT true CHECK (approval_required),
    proposed_by_request_id text NOT NULL,
    proposal_key char(64) NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    approved_at timestamptz,
    rejected_at timestamptz,
    execution_started_at timestamptz,
    completed_at timestamptz,
    result jsonb,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ticket_actions_customer_created_idx
    ON ticket_actions (customer_id, created_at DESC);
CREATE INDEX ticket_actions_pending_expiry_idx
    ON ticket_actions (expires_at)
    WHERE status = 'pending';

CREATE TABLE ticket_action_receipts (
    action_id text PRIMARY KEY REFERENCES ticket_actions (action_id) ON DELETE RESTRICT,
    action_type text NOT NULL CHECK (
        action_type IN ('create_ticket', 'update_ticket_status', 'update_ticket_priority')
    ),
    result jsonb NOT NULL,
    executed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ticket_action_audit_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action_id text NOT NULL REFERENCES ticket_actions (action_id) ON DELETE RESTRICT,
    event_type text NOT NULL,
    actor_type text NOT NULL CHECK (actor_type IN ('model', 'human', 'system', 'mcp')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ticket_action_audit_action_idx
    ON ticket_action_audit_events (action_id, event_id);
