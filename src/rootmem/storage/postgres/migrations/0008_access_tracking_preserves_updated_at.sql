-- yoyo-migrations: 0008_access_tracking_preserves_updated_at
-- depends: 0007_ranking_decay_trust_audit

-- Found live during Phase 4's manual check: recording a read (recall/search
-- access tracking, ADR 0023) fired set_updated_at() and bumped `updated_at`,
-- so a memory that was only READ looked as if it had been modified.
-- `updated_at` must keep meaning "last changed", so the access-tracking
-- UPDATE opts out per transaction via a transaction-local setting. Every
-- other UPDATE behaves exactly as before.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    IF current_setting('rootmem.skip_updated_at', true) = 'on' THEN
        NEW.updated_at = OLD.updated_at;
    ELSE
        NEW.updated_at = now();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
