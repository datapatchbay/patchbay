-- Output port sa_jaffle_orders
CREATE SCHEMA IF NOT EXISTS "sa_jaffle_orders";
DO $body$
DECLARE granted record;
BEGIN
    FOR granted IN
        SELECT acl.grantee FROM pg_namespace AS namespace, aclexplode(namespace.nspacl) AS acl
        WHERE namespace.nspname = 'sa_jaffle_orders' AND acl.grantee <> namespace.nspowner
    LOOP
        EXECUTE 'REVOKE ALL ON SCHEMA ' || quote_ident('sa_jaffle_orders') || ' FROM '
            || CASE WHEN granted.grantee = 0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(granted.grantee)) END;
    END LOOP;
END
$body$;
DROP VIEW IF EXISTS "sa_jaffle_orders"."orders";
CREATE VIEW "sa_jaffle_orders"."orders" AS SELECT "order_id", CASE WHEN pg_has_role(current_user, 'grp-shop-support', 'member') THEN "customer_id" ELSE NULL END AS "customer_id", "status" FROM "sa_jaffle_orders_private"."orders";
GRANT USAGE ON SCHEMA "sa_jaffle_orders" TO "dp_agg_order_turnaround", "grp-shop-reporting", "grp-shop-support";
GRANT SELECT ON "sa_jaffle_orders"."orders" TO "dp_agg_order_turnaround", "grp-shop-reporting", "grp-shop-support";