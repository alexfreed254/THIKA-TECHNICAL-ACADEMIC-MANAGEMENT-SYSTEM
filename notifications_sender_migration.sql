-- Allow senders to recall notifications they sent with a notice.
-- Safe to re-run.

ALTER TABLE notifications
  ADD COLUMN IF NOT EXISTS sender_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS notice_id UUID;

CREATE INDEX IF NOT EXISTS idx_notifications_sender
  ON notifications (sender_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_notice
  ON notifications (notice_id)
  WHERE notice_id IS NOT NULL;
