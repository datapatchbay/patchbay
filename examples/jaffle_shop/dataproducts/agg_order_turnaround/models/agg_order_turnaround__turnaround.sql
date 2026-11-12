-- The turnaround of completed orders. It reads the output port of sa_jaffle_orders through its generated source, never
-- that data product's private schema.
select
    order_id,
    extract(epoch from completed_at - ordered_at) / 3600 as turnaround_hours,
    ordered_at
from {{ source('sa_jaffle_orders', 'orders') }}
where completed_at is not null
