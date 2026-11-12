-- Output port sa_ilab_orders
CREATE SCHEMA IF NOT EXISTS "sa_ilab_orders";
DO $body$
DECLARE granted record;
BEGIN
    FOR granted IN
        SELECT acl.grantee FROM pg_namespace AS namespace, aclexplode(namespace.nspacl) AS acl
        WHERE namespace.nspname = 'sa_ilab_orders' AND acl.grantee <> namespace.nspowner
    LOOP
        EXECUTE 'REVOKE ALL ON SCHEMA ' || quote_ident('sa_ilab_orders') || ' FROM '
            || CASE WHEN granted.grantee = 0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(granted.grantee)) END;
    END LOOP;
END
$body$;
DROP VIEW IF EXISTS "sa_ilab_orders"."orders";
CREATE VIEW "sa_ilab_orders"."orders" AS SELECT "order_id", CASE WHEN pg_has_role(current_user, 'grp-lab-doctors', 'member') THEN "patient_id" ELSE NULL END AS "patient_id", "status" FROM "sa_ilab_orders_private"."orders";
GRANT USAGE ON SCHEMA "sa_ilab_orders" TO "dp_agg_lab_turnaround", "grp-lab-doctors", "grp-lab-reporting";
GRANT SELECT ON "sa_ilab_orders"."orders" TO "dp_agg_lab_turnaround", "grp-lab-doctors", "grp-lab-reporting";