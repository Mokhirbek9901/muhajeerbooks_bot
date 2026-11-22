-- Queue Mini App messages in the same transaction as the admin status update.
CREATE TABLE IF NOT EXISTS private.telegram_miniapp_notices (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id uuid NOT NULL REFERENCES private.telegram_miniapp_orders(order_id) ON DELETE CASCADE,
  status text NOT NULL CHECK(status IN ('accepted','shipping')),
  created_at timestamptz NOT NULL DEFAULT now(),
  available_at timestamptz NOT NULL DEFAULT now(),
  lease_until timestamptz,
  lease_token uuid,
  attempts smallint NOT NULL DEFAULT 0,
  finished_at timestamptz,
  result text CHECK(result IN ('sent','unavailable','failed','uncertain')),
  UNIQUE(order_id,status)
);

CREATE INDEX IF NOT EXISTS telegram_miniapp_notices_pending
  ON private.telegram_miniapp_notices(available_at,id) WHERE finished_at IS NULL;

CREATE OR REPLACE FUNCTION private.queue_telegram_miniapp_notice()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path TO ''
AS $sql$
BEGIN
  INSERT INTO private.telegram_miniapp_notices(order_id,status)
  SELECT order_id,NEW.status FROM private.telegram_miniapp_orders WHERE order_id=NEW.id
  ON CONFLICT (order_id,status) DO NOTHING;
  RETURN NEW;
END
$sql$;

CREATE OR REPLACE TRIGGER orders_queue_telegram_miniapp_notice
  AFTER UPDATE OF status ON public.orders
  FOR EACH ROW WHEN (NEW.status IN ('accepted','shipping') AND OLD.status IS DISTINCT FROM NEW.status)
  EXECUTE FUNCTION private.queue_telegram_miniapp_notice();

CREATE OR REPLACE FUNCTION private.telegram_miniapp_notice_job(p_action text,p_data jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path TO ''
AS $sql$
DECLARE
  batch jsonb;
  outcome text := p_data->>'result';
BEGIN
  IF p_action = 'notice_claim' THEN
    WITH ready AS (
      SELECT n.id
      FROM private.telegram_miniapp_notices n
      JOIN public.orders o ON o.id=n.order_id
      WHERE n.finished_at IS NULL AND n.available_at <= now()
        AND (n.lease_until IS NULL OR n.lease_until <= now())
        AND o.status <> 'cancelled'
      ORDER BY n.available_at,n.id
      LIMIT 5
      FOR UPDATE OF n SKIP LOCKED
    ), claimed AS (
      UPDATE private.telegram_miniapp_notices n
        SET lease_until=now()+interval '6 minutes', lease_token=gen_random_uuid(),
            attempts=n.attempts+1
      FROM ready WHERE n.id=ready.id RETURNING n.*
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object(
      'id',c.id,'lease',c.lease_token,'status',c.status,
      'number',coalesce(o.display_order_number,o.order_number),
      'recipient',m.telegram_user_id,
      'tracking',CASE WHEN c.status='shipping' THEN o.tracking_number END
    ) ORDER BY c.available_at,c.id),'[]'::jsonb) INTO batch
    FROM claimed c
    JOIN private.telegram_miniapp_orders m ON m.order_id=c.order_id
    JOIN public.orders o ON o.id=c.order_id;
    RETURN batch;
  END IF;

  IF p_action IS DISTINCT FROM 'notice_finish' OR outcome IS NULL OR
      outcome NOT IN ('sent','unavailable','failed','uncertain','retry') THEN
    RAISE EXCEPTION USING MESSAGE='Xabar holati noto‘g‘ri';
  END IF;
  UPDATE private.telegram_miniapp_notices
    SET lease_until=NULL, lease_token=NULL,
        available_at=CASE WHEN outcome='retry' AND attempts<5 THEN
          now()+make_interval(secs=>greatest(5,least(3600,coalesce((p_data->>'retry_after')::int,60))))
          ELSE available_at END,
        finished_at=CASE WHEN outcome='retry' AND attempts<5 THEN NULL ELSE now() END,
        result=CASE WHEN outcome='retry' AND attempts<5 THEN NULL
          WHEN outcome='retry' THEN 'failed' ELSE outcome END
    WHERE id=(p_data->>'id')::bigint AND lease_token=(p_data->>'lease')::uuid
      AND finished_at IS NULL;
  RETURN to_jsonb(FOUND);
END
$sql$;

CREATE OR REPLACE FUNCTION public.telegram_miniapp(p_secret text, p_user bigint, p_action text, p_data jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
BEGIN
  -- Same credential check as the installed bot's cloud functions.
  IF NOT coalesce(public._secret_ok(p_secret,
    'ff2c7a6de8f32fb3153d1f01a7e9b171005789f249f364bd5bc6bf2210c6adfd'),false) THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Ruxsat yo‘q';
  END IF;
  IF p_action IN ('notice_claim','notice_finish') AND p_user = 0 THEN
    RETURN private.telegram_miniapp_notice_job(p_action,p_data);
  END IF;
  RETURN private.telegram_miniapp_action(p_user,p_action,p_data);
END
$function$;

REVOKE ALL ON private.telegram_miniapp_notices FROM PUBLIC;
REVOKE ALL ON FUNCTION private.queue_telegram_miniapp_notice() FROM PUBLIC;
REVOKE ALL ON FUNCTION private.telegram_miniapp_notice_job(text,jsonb) FROM PUBLIC;
