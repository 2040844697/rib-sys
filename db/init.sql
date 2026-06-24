BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS groups (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  qq_group_number TEXT,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'enabled',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES groups(id),
  account TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  password_salt TEXT NOT NULL,
  password_iterations INTEGER NOT NULL,
  password_key_length INTEGER NOT NULL,
  password_digest TEXT NOT NULL,
  display_name TEXT NOT NULL,
  qq_number TEXT NOT NULL UNIQUE,
  group_nickname TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  last_login_at TIMESTAMPTZ,
  password_changed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_group_id ON users(group_id);

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS user_roles (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, role)
);

CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role);

CREATE TABLE IF NOT EXISTS user_aliases (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_aliases_user_id ON user_aliases(user_id);

CREATE TABLE IF NOT EXISTS auth_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  created_ip TEXT,
  user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);

CREATE TABLE IF NOT EXISTS file_objects (
  id TEXT PRIMARY KEY,
  bucket TEXT NOT NULL,
  object_key TEXT NOT NULL,
  url TEXT NOT NULL,
  content_type TEXT,
  size_bytes BIGINT,
  uploaded_by TEXT REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (bucket, object_key)
);

ALTER TABLE file_objects
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

ALTER TABLE file_objects
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS goods (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  series_name TEXT,
  aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
  character_names JSONB NOT NULL DEFAULT '[]'::jsonb,
  sku TEXT,
  description TEXT,
  main_image_id TEXT,
  length_mm INTEGER,
  width_mm INTEGER,
  weight_gram INTEGER,
  release_price_jpy INTEGER,
  suggested_price_jpy INTEGER,
  domestic_spot_suggested_price_cny INTEGER,
  status TEXT NOT NULL DEFAULT 'enabled',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_goods_name ON goods(name);
CREATE INDEX IF NOT EXISTS idx_goods_series_name ON goods(series_name);
CREATE INDEX IF NOT EXISTS idx_goods_sku ON goods(sku);
CREATE INDEX IF NOT EXISTS idx_goods_aliases_gin ON goods USING GIN (aliases);
CREATE INDEX IF NOT EXISTS idx_goods_character_names_gin ON goods USING GIN (character_names);

CREATE TABLE IF NOT EXISTS goods_images (
  id TEXT PRIMARY KEY,
  goods_id TEXT NOT NULL REFERENCES goods(id) ON DELETE CASCADE,
  file_object_id TEXT REFERENCES file_objects(id),
  image_url TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_primary BOOLEAN NOT NULL DEFAULT FALSE,
  uploaded_by TEXT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_goods_images_goods_id ON goods_images(goods_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_goods_main_image'
  ) THEN
    ALTER TABLE goods
      ADD CONSTRAINT fk_goods_main_image
      FOREIGN KEY (main_image_id) REFERENCES goods_images(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS payment_channels (
  id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES users(id),
  type TEXT NOT NULL,
  display_name TEXT NOT NULL,
  qr_file_object_id TEXT REFERENCES file_objects(id),
  qr_image_url TEXT,
  account_text TEXT,
  note TEXT,
  status TEXT NOT NULL DEFAULT 'enabled',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE payment_channels
  ALTER COLUMN status SET DEFAULT 'active';

UPDATE payment_channels
SET status = 'active'
WHERE status = 'enabled';

CREATE INDEX IF NOT EXISTS idx_payment_channels_owner_user_id ON payment_channels(owner_user_id);

CREATE TABLE IF NOT EXISTS group_buys (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES groups(id),
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL,
  owner_user_id TEXT REFERENCES users(id),
  close_at TIMESTAMPTZ,
  payment_channel_id TEXT REFERENCES payment_channels(id),
  warehouse_user_id TEXT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_group_buys_group_id ON group_buys(group_id);
CREATE INDEX IF NOT EXISTS idx_group_buys_status ON group_buys(status);

CREATE TABLE IF NOT EXISTS group_buy_items (
  id TEXT PRIMARY KEY,
  group_buy_id TEXT NOT NULL REFERENCES group_buys(id) ON DELETE CASCADE,
  goods_id TEXT REFERENCES goods(id),
  name_snapshot TEXT NOT NULL,
  alias_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
  character_names_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
  description_snapshot TEXT,
  image_url_snapshot TEXT,
  unit_price_cny INTEGER NOT NULL,
  release_price_jpy_snapshot INTEGER,
  suggested_price_jpy_snapshot INTEGER,
  domestic_spot_suggested_price_cny_snapshot INTEGER,
  length_mm_snapshot INTEGER,
  width_mm_snapshot INTEGER,
  weight_gram_snapshot INTEGER,
  total_quantity INTEGER NOT NULL DEFAULT 0,
  reserved_quantity INTEGER NOT NULL DEFAULT 0,
  claimed_quantity INTEGER NOT NULL DEFAULT 0,
  available_quantity INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'available',
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (total_quantity >= 0),
  CHECK (reserved_quantity >= 0),
  CHECK (claimed_quantity >= 0),
  CHECK (available_quantity >= 0)
);

CREATE INDEX IF NOT EXISTS idx_group_buy_items_group_buy_id ON group_buy_items(group_buy_id);
CREATE INDEX IF NOT EXISTS idx_group_buy_items_goods_id ON group_buy_items(goods_id);

CREATE TABLE IF NOT EXISTS charges (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  payer_user_id TEXT NOT NULL REFERENCES users(id),
  payee_user_id TEXT NOT NULL REFERENCES users(id),
  biz_type TEXT NOT NULL,
  biz_id TEXT NOT NULL,
  amount_cny INTEGER NOT NULL,
  status TEXT NOT NULL,
  payment_channel_id TEXT REFERENCES payment_channels(id),
  note TEXT,
  snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_charges_payer_user_id ON charges(payer_user_id);
CREATE INDEX IF NOT EXISTS idx_charges_payee_user_id ON charges(payee_user_id);
CREATE INDEX IF NOT EXISTS idx_charges_biz ON charges(biz_type, biz_id);

CREATE TABLE IF NOT EXISTS payment_proofs (
  id TEXT PRIMARY KEY,
  submitted_by TEXT NOT NULL REFERENCES users(id),
  from_user_id TEXT NOT NULL REFERENCES users(id),
  to_user_id TEXT NOT NULL REFERENCES users(id),
  amount_cny INTEGER NOT NULL,
  paid_at TIMESTAMPTZ,
  proof_file_object_id TEXT REFERENCES file_objects(id),
  proof_image_url TEXT,
  note TEXT,
  status TEXT NOT NULL,
  reviewed_by TEXT REFERENCES users(id),
  reviewed_at TIMESTAMPTZ,
  reject_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_proofs_submitted_by ON payment_proofs(submitted_by);

ALTER TABLE payment_proofs
  ADD COLUMN IF NOT EXISTS review_note TEXT;

ALTER TABLE charges
  ADD COLUMN IF NOT EXISTS submitted_proof_id TEXT REFERENCES payment_proofs(id);

ALTER TABLE charges
  ADD COLUMN IF NOT EXISTS confirmed_proof_id TEXT REFERENCES payment_proofs(id);

ALTER TABLE charges
  ADD COLUMN IF NOT EXISTS cancelled_reason TEXT;

CREATE TABLE IF NOT EXISTS payment_proof_allocations (
  id TEXT PRIMARY KEY,
  proof_id TEXT NOT NULL REFERENCES payment_proofs(id) ON DELETE CASCADE,
  charge_id TEXT NOT NULL REFERENCES charges(id) ON DELETE CASCADE,
  allocated_amount_cny INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (proof_id, charge_id)
);

CREATE INDEX IF NOT EXISTS idx_payment_proof_allocations_charge_id ON payment_proof_allocations(charge_id);

CREATE TABLE IF NOT EXISTS group_buy_records (
  id TEXT PRIMARY KEY,
  group_buy_id TEXT NOT NULL REFERENCES group_buys(id) ON DELETE CASCADE,
  group_buy_item_id TEXT NOT NULL REFERENCES group_buy_items(id) ON DELETE CASCADE,
  member_user_id TEXT NOT NULL REFERENCES users(id),
  status TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  goods_charge_id TEXT REFERENCES charges(id),
  goods_payment_record_id TEXT REFERENCES payment_proofs(id),
  international_charge_id TEXT REFERENCES charges(id),
  international_payment_record_id TEXT REFERENCES payment_proofs(id),
  domestic_shipping_charge_id TEXT REFERENCES charges(id),
  dispatch_request_id TEXT,
  transfer_id TEXT,
  is_exception BOOLEAN NOT NULL DEFAULT FALSE,
  exception_reason TEXT,
  status_priority INTEGER,
  note TEXT,
  source TEXT NOT NULL DEFAULT 'member_claim',
  source_record_id TEXT REFERENCES group_buy_records(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (group_buy_item_id, member_user_id),
  CHECK (quantity > 0)
);

ALTER TABLE group_buy_records
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'member_claim';

ALTER TABLE group_buy_records
  ADD COLUMN IF NOT EXISTS source_record_id TEXT REFERENCES group_buy_records(id);

CREATE INDEX IF NOT EXISTS idx_group_buy_records_group_buy_id ON group_buy_records(group_buy_id);
CREATE INDEX IF NOT EXISTS idx_group_buy_records_member_user_id ON group_buy_records(member_user_id);
CREATE INDEX IF NOT EXISTS idx_group_buy_records_status ON group_buy_records(status);

CREATE TABLE IF NOT EXISTS price_adjustments (
  id TEXT PRIMARY KEY,
  group_buy_id TEXT NOT NULL REFERENCES group_buys(id) ON DELETE CASCADE,
  group_buy_item_id TEXT NOT NULL REFERENCES group_buy_items(id) ON DELETE CASCADE,
  old_price_cny INTEGER NOT NULL,
  new_price_cny INTEGER NOT NULL,
  impact_scope TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL REFERENCES users(id),
  reviewed_by TEXT REFERENCES users(id),
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_price_adjustments_group_buy_item_id ON price_adjustments(group_buy_item_id);

CREATE TABLE IF NOT EXISTS order_screenshots (
  id TEXT PRIMARY KEY,
  group_buy_id TEXT NOT NULL REFERENCES group_buys(id) ON DELETE CASCADE,
  uploaded_by TEXT NOT NULL REFERENCES users(id),
  screenshot_file_object_id TEXT REFERENCES file_objects(id),
  screenshot_url TEXT NOT NULL,
  is_ordered BOOLEAN NOT NULL DEFAULT FALSE,
  ordered_at TIMESTAMPTZ,
  website TEXT,
  website_order_no TEXT,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS international_batches (
  id TEXT PRIMARY KEY,
  forwarder_name TEXT NOT NULL,
  batch_no TEXT,
  status TEXT NOT NULL,
  warehouse_user_id TEXT REFERENCES users(id),
  international_tracking_no TEXT,
  total_weight_gram INTEGER,
  shipping_fee_cny INTEGER,
  tax_fee_cny INTEGER,
  other_fee_cny INTEGER,
  shipped_at TIMESTAMPTZ,
  arrived_domestic_at TIMESTAMPTZ,
  stocked_at TIMESTAMPTZ,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS international_batch_records (
  id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES international_batches(id) ON DELETE CASCADE,
  group_buy_record_id TEXT NOT NULL REFERENCES group_buy_records(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (batch_id, group_buy_record_id)
);

CREATE TABLE IF NOT EXISTS international_fee_allocations (
  id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES international_batches(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id),
  weight_gram INTEGER,
  shipping_fee_cny INTEGER NOT NULL DEFAULT 0,
  tax_fee_cny INTEGER NOT NULL DEFAULT 0,
  other_fee_cny INTEGER NOT NULL DEFAULT 0,
  adjustment_cny INTEGER NOT NULL DEFAULT 0,
  total_cny INTEGER NOT NULL DEFAULT 0,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE international_fee_allocations
  ADD COLUMN IF NOT EXISTS charge_id TEXT REFERENCES charges(id);

CREATE TABLE IF NOT EXISTS stock_items (
  id TEXT PRIMARY KEY,
  warehouse_user_id TEXT NOT NULL REFERENCES users(id),
  group_buy_record_id TEXT NOT NULL REFERENCES group_buy_records(id),
  quantity INTEGER NOT NULL,
  status TEXT NOT NULL,
  stocked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (quantity >= 0)
);

CREATE TABLE IF NOT EXISTS dispatch_requests (
  id TEXT PRIMARY KEY,
  requester_user_id TEXT NOT NULL REFERENCES users(id),
  warehouse_user_id TEXT NOT NULL REFERENCES users(id),
  status TEXT NOT NULL,
  receiver_name TEXT NOT NULL,
  receiver_phone TEXT NOT NULL,
  receiver_address TEXT NOT NULL,
  note TEXT,
  submitted_at TIMESTAMPTZ,
  packed_at TIMESTAMPTZ,
  shipped_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dispatch_items (
  id TEXT PRIMARY KEY,
  dispatch_request_id TEXT NOT NULL REFERENCES dispatch_requests(id) ON DELETE CASCADE,
  stock_item_id TEXT NOT NULL REFERENCES stock_items(id),
  group_buy_record_id TEXT NOT NULL REFERENCES group_buy_records(id),
  quantity INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (dispatch_request_id, stock_item_id),
  CHECK (quantity > 0)
);

CREATE TABLE IF NOT EXISTS domestic_shipments (
  id TEXT PRIMARY KEY,
  dispatch_request_id TEXT NOT NULL REFERENCES dispatch_requests(id) ON DELETE CASCADE,
  carrier TEXT,
  tracking_no TEXT,
  shipping_fee_cny INTEGER,
  fee_mode TEXT NOT NULL,
  shipped_at TIMESTAMPTZ,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transfers (
  id TEXT PRIMARY KEY,
  from_user_id TEXT NOT NULL REFERENCES users(id),
  to_user_id TEXT NOT NULL REFERENCES users(id),
  status TEXT NOT NULL,
  reason TEXT,
  requested_by TEXT NOT NULL REFERENCES users(id),
  approved_by TEXT REFERENCES users(id),
  approved_at TIMESTAMPTZ,
  rejected_by TEXT REFERENCES users(id),
  rejected_at TIMESTAMPTZ,
  reject_reason TEXT,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE transfers
  ADD COLUMN IF NOT EXISTS rejected_by TEXT REFERENCES users(id);

ALTER TABLE transfers
  ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ;

ALTER TABLE transfers
  ADD COLUMN IF NOT EXISTS reject_reason TEXT;

ALTER TABLE transfers
  ADD COLUMN IF NOT EXISTS note TEXT;

CREATE TABLE IF NOT EXISTS transfer_items (
  id TEXT PRIMARY KEY,
  transfer_id TEXT NOT NULL REFERENCES transfers(id) ON DELETE CASCADE,
  group_buy_record_id TEXT NOT NULL REFERENCES group_buy_records(id),
  quantity INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (quantity > 0)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_group_buy_records_dispatch_request'
  ) THEN
    ALTER TABLE group_buy_records
      ADD CONSTRAINT fk_group_buy_records_dispatch_request
      FOREIGN KEY (dispatch_request_id) REFERENCES dispatch_requests(id);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_group_buy_records_transfer'
  ) THEN
    ALTER TABLE group_buy_records
      ADD CONSTRAINT fk_group_buy_records_transfer
      FOREIGN KEY (transfer_id) REFERENCES transfers(id);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS charge_adjustments (
  id TEXT PRIMARY KEY,
  charge_id TEXT NOT NULL REFERENCES charges(id) ON DELETE CASCADE,
  source_charge_id TEXT REFERENCES charges(id),
  delta_cny INTEGER NOT NULL,
  reason TEXT NOT NULL,
  source_type TEXT,
  source_id TEXT,
  approved_by TEXT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY,
  actor_user_id TEXT REFERENCES users(id),
  action TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  before_json JSONB,
  after_json JSONB,
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_object ON audit_logs(object_type, object_id);

COMMIT;
