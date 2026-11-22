-- Mini App customers use the standard order and finance pipeline.
CREATE TABLE IF NOT EXISTS private.telegram_miniapp_orders (
  order_id uuid PRIMARY KEY REFERENCES public.orders(id) ON DELETE CASCADE,
  telegram_user_id bigint NOT NULL CHECK (telegram_user_id > 0)
);

CREATE INDEX IF NOT EXISTS telegram_miniapp_orders_customer_idx
  ON private.telegram_miniapp_orders (telegram_user_id, order_id);

CREATE OR REPLACE FUNCTION private.telegram_miniapp_order_view(p_order public.orders)
RETURNS jsonb LANGUAGE sql STABLE SET search_path TO ''
AS $sql$
  SELECT jsonb_build_object(
    'id', p_order.id,
    'number', p_order.display_order_number,
    'status', p_order.status,
    'prepared', p_order.prepared_at IS NOT NULL,
    'created_at', p_order.created_at,
    'total', p_order.total,
    'delivery_fee', p_order.delivery_fee,
    'tracking_number', p_order.tracking_number,
    'carrier', p_order.carrier,
    'items', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'title', x->>'title',
        'quantity', x->'quantity',
        'price', x->'unit_price'
      ) ORDER BY item_no)
      FROM jsonb_array_elements(p_order.items) WITH ORDINALITY item(x, item_no)
    ), '[]'::jsonb)
  );
$sql$;

CREATE OR REPLACE FUNCTION private.telegram_miniapp_action(
  p_user bigint, p_action text, p_data jsonb
)
RETURNS jsonb LANGUAGE plpgsql SET search_path TO ''
AS $sql$
DECLARE
  v_order public.orders%ROWTYPE;
  v_id uuid;
  v_owner bigint;
  v_rows jsonb;
  v_order_data jsonb;
  v_search text := left(btrim(coalesce(p_data->>'search','')),80);
  v_offset integer;
BEGIN
  IF p_user IS NULL OR p_user < 1 OR p_user > 4503599627370495 THEN
    RAISE EXCEPTION USING MESSAGE = 'Telegram foydalanuvchisi tasdiqlanmadi';
  END IF;

  IF p_action = 'catalog' THEN
    v_offset := greatest(0,least(10000,coalesce((p_data->>'offset')::integer,0)));
    SELECT coalesce(jsonb_agg(to_jsonb(b)
      ORDER BY b.pinned DESC, b.created_at DESC, b.id), '[]'::jsonb) INTO v_rows
    FROM (
      SELECT id,title,author,category,left(description,900) AS description,stock,
        coalesce(nullif(thumbnail_url,''),image_url) AS cover,
        coalesce(catalog_pin_rank,0)>0 AS pinned, created_at,
        round(price*(100-(CASE WHEN discount_percent>0 AND
          (discount_ends_at IS NULL OR discount_ends_at>now())
          THEN greatest(0,least(99,discount_percent)) ELSE 0 END))/100.0)::integer AS price
      FROM public.books
      WHERE is_active AND catalog_archived_at IS NULL AND NOT coalesce(planned,false)
        AND price>0 AND stock>0
        AND (v_search='' OR strpos(lower(title),lower(v_search))>0
          OR strpos(lower(coalesce(author,'')),lower(v_search))>0
          OR strpos(lower(coalesce(category,'')),lower(v_search))>0)
      ORDER BY pinned DESC,created_at DESC,id
      LIMIT 25 OFFSET v_offset
    ) b;
    RETURN jsonb_build_object('books', v_rows, 'more', jsonb_array_length(v_rows)>24);
  END IF;

  IF p_action = 'orders' THEN
    v_offset := greatest(0,least(10000,coalesce((p_data->>'offset')::integer,0)));
    SELECT coalesce(jsonb_agg(private.telegram_miniapp_order_view(o)
      ORDER BY o.created_at DESC,o.id), '[]'::jsonb) INTO v_rows
    FROM (
      SELECT o.*
      FROM private.telegram_miniapp_orders own
      JOIN public.orders o ON o.id=own.order_id
      WHERE own.telegram_user_id=p_user
      ORDER BY o.created_at DESC,o.id LIMIT 21 OFFSET v_offset
    ) o;
    RETURN jsonb_build_object('orders', v_rows, 'more', jsonb_array_length(v_rows)>20);
  END IF;

  IF p_action IN ('lookup','order') THEN
    v_id := (p_data->>'id')::uuid;
    IF v_id IS NULL THEN
      RAISE EXCEPTION USING MESSAGE = 'Buyurtma raqami noto‘g‘ri';
    END IF;
    IF p_action = 'order' THEN
      PERFORM pg_advisory_xact_lock(hashtextextended('telegram-miniapp:'||v_id::text,0));
    END IF;
    SELECT telegram_user_id INTO v_owner FROM private.telegram_miniapp_orders WHERE order_id=v_id;
    IF v_owner = p_user THEN
      SELECT * INTO v_order FROM public.orders WHERE id=v_id;
      RETURN private.telegram_miniapp_order_view(v_order);
    END IF;
    IF p_action = 'lookup' THEN
      RETURN 'null'::jsonb;
    END IF;
    IF v_owner IS NOT NULL OR EXISTS (SELECT 1 FROM public.orders WHERE id=v_id) THEN
      RAISE EXCEPTION USING MESSAGE = 'Buyurtma raqami noto‘g‘ri';
    END IF;
  END IF;

  IF p_action NOT IN ('quote','order') OR p_action IS NULL THEN
    RAISE EXCEPTION USING MESSAGE = 'Noma’lum amal';
  END IF;

  v_order_data := jsonb_build_object(
    'customer_name',p_data->>'name',
    'phone',p_data->>'phone',
    'address',p_data->>'address',
    'delivery_type',p_data->>'delivery',
    'items',p_data->'items',
    'source','app'
  );
  IF p_action = 'quote' THEN
    v_order := private.release_prepare_order(
      jsonb_populate_record(NULL::public.orders,v_order_data)
    );
    RETURN jsonb_build_object(
      'subtotal',v_order.subtotal,'delivery_fee',v_order.delivery_fee,'total',v_order.total
    );
  END IF;

  PERFORM public.customer_order_submit(v_order_data || jsonb_build_object(
    'id',v_id,'payment_proof_path',p_data->>'receipt'
  ));
  SELECT * INTO STRICT v_order FROM public.orders WHERE id=v_id;
  -- A quote is for the amount the customer sees before sending the receipt.
  -- An amount change rolls back stock, print jobs and the order together.
  IF v_order.total IS DISTINCT FROM (p_data->>'total')::integer THEN
    RAISE EXCEPTION USING MESSAGE = 'Buyurtma summasi o‘zgardi. Jami summani qayta tekshiring.';
  END IF;
  INSERT INTO private.telegram_miniapp_orders (order_id,telegram_user_id)
    VALUES (v_id,p_user);
  RETURN private.telegram_miniapp_order_view(v_order);
END
$sql$;

CREATE OR REPLACE FUNCTION public.telegram_miniapp(
  p_secret text, p_user bigint, p_action text, p_data jsonb
)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO ''
AS $sql$
BEGIN
  -- Same credential check as the installed bot's cloud functions.
  IF NOT coalesce(public._secret_ok(p_secret,
    'ff2c7a6de8f32fb3153d1f01a7e9b171005789f249f364bd5bc6bf2210c6adfd'),false) THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Ruxsat yo‘q';
  END IF;
  RETURN private.telegram_miniapp_action(p_user,p_action,p_data);
END
$sql$;

REVOKE ALL ON private.telegram_miniapp_orders FROM PUBLIC;
REVOKE ALL ON FUNCTION private.telegram_miniapp_order_view(public.orders) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.telegram_miniapp_action(bigint,text,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.telegram_miniapp(text,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.telegram_miniapp(text,bigint,text,jsonb) TO mb_api_anon_v1, mb_api_service_v1;
NOTIFY pgrst, 'reload schema';
