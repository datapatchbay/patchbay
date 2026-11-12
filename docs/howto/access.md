# Give a reader access to an output port

Access to an output port is declared in its `port.yaml`, under `access`. Nobody runs a `GRANT` by hand: the `apply_access` task of the data product's DAG applies what the file says.

All examples below edit `dataproducts/sa_ilab_orders/outputs/sa_ilab_orders/port.yaml`.

## Give a role access

Add the name of the warehouse role to `readers`, as the warehouse spells it:

```yaml
access:
  readers:
    - grp-lab-reporting
```

The role can then read every view of the port. It sees NULL in the columns marked as personal data.

## Give another data product access

Two files change, usually in one pull request that the owner of the port approves.

1. In the port that is read, add the reading data product by its folder name:

   ```yaml
   access:
     readers:
       - grp-lab-reporting
       - product: agg_lab_turnaround
   ```

2. In the reading data product, declare the input port. Create `inputs/sa_ilab_orders/port.yaml`, in a folder named after the output port:

   ```yaml
   schema_version: 1
   from: sa_ilab_orders
   ```

   Then add `sa_ilab_orders` to `inputs` in its `dataproduct.yaml`.

`product: agg_lab_turnaround` maps to that data product's role, `dp_agg_lab_turnaround` with the default naming template. `dpb validate` fails when a data product declares the input port but is not in the readers.

## Let a role see personal data

Mark the column in the table file:

```yaml
columns:
  - name: patient_id
    type: text
    pii: true
```

Then add the role to `pii_readers`:

```yaml
access:
  readers: [grp-lab-reporting]
  pii_readers: [grp-lab-doctors]
```

A PII reader can read the port and sees the values of the PII columns. Readers and PII readers query the same view. A PII reader does not have to be in `readers` as well.

## Take access away

Remove the line. The next run of the DAG revokes the access.

## Check the result

```console
$ dpb validate
$ dpb describe sa_ilab_orders
```

`dpb describe` shows `readers`, `pii readers` and `read by` for each output port.

## What to know

- **The roles must exist.** The generated SQL grants to roles and never creates them. When a role is missing, `apply_access` fails and names it, and the views and grants of the previous run stay as they were.
- **A change takes effect on the next run** of the data product's DAG, not when the pull request is merged.
- **The file is the only source of access.** Every run revokes all privileges on the port's schema and grants them again from the file. A privilege that someone gave by hand is removed.
- **A view that depends on a port's view blocks the run.** The views are dropped and created again on every run. A view in another schema that selects from a port's view makes `apply_access` fail until it is removed.

[How it works](../concepts.md#readers-and-personal-data) explains the model behind this.
