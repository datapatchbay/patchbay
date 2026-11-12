# Import an existing dbt project

`dpb new --from-dbt` turns the models of a dbt project that you already have into a data product. It copies the models, writes a table file for each from its dbt properties, and turns the dbt data tests into quality rules. Use it to adopt datapatchbay one data product at a time.

This guide imports the models in `legacy_dbt/models/marts/` into a data product `agg_shop_orders`.

## 1. Choose the models of one data product

A data product is a group of tables with one owner. Choose a folder of the dbt project that holds such a group: `dpb` reads the folder recursively.

Two things decide what is imported:

- **A model needs properties with at least one column.** A model that has only a `.sql` file is skipped, because there are no columns for a table file. Describe its columns in the dbt properties first.
- **Every imported model becomes a table of the default output port,** so readers will see it. A model that readers should not see is better left out of the import. See step 3.

## 2. Run the import

Run it from the datapatchbay repo, with the folder of the models:

```console
$ dpb new --from-dbt legacy_dbt/models/marts --name shop_orders --kind aggregate --owner "Jane Doe" --no-input
created dataproducts/agg_shop_orders/dataproduct.yaml
created dataproducts/agg_shop_orders/outputs/agg_shop_orders/port.yaml
created dataproducts/agg_shop_orders/outputs/agg_shop_orders/orders.yaml
created dataproducts/agg_shop_orders/models/agg_shop_orders__orders.sql
not imported: orders.customer_id relationships: no matching quality rule
skipped stg_orders: it has no properties, so there are no columns for a table file
no data_type: orders.status is written as 'text'; set the real type
ref not renamed: orders ref('stg_orders'): it names a model that is not imported, so it is not renamed; edit it by hand
```

The data product gets `executor: dbt`. Each model is copied to `models/<data product>__<model>.sql`, and `ref()` calls between imported models are renamed to the new names. The table file holds the description, the columns with their types, `pii` from `meta: {pii: true}`, and the `not_null`, `unique` and `accepted_values` tests as quality rules.

The SQL is copied, not moved. The old project keeps working until you switch over.

## 3. Work through the report

The lines after the `created` lines say what `dpb` could not carry over. Nothing is dropped in silence. With `--json` the same lists are in the output.

`not imported: <model>.<column> <test>`
: The data test has no matching quality rule: `relationships`, a package test, a test on a whole model, or a test with an option such as `where`. Write it as a `sql` rule in the table file, or keep it as a singular dbt test that you write by hand in the `tests/` folder of the data product.

`skipped <model>`
: The model has no properties, no columns or no `.sql` file, so it is not in the data product. To publish it, describe its columns in the old project and import again. To keep it as an internal step, copy its `.sql` file into the `models/` folder of the data product by hand. A model without a table file is plain dbt: `dpb` writes no properties for it and checks nothing about it, and dbt builds it in the schema of your profile.

`no data_type: <model>.<column> is written as 'text'`
: The dbt properties had no `data_type` for the column. Set the real type in the table file, because the generated dbt model contract is checked against it.

`ref not renamed: <model> ref(...)`
: The model reads a model that was not imported, or uses a `ref` with a package or a version. The call is copied as written. If it points at a model of another data product, replace it in step 6. If it points at a skipped model, see above.

The [dbt reference](../dbt.md#what-dpb-new---from-dbt-imports) lists everything that is and is not imported.

## 4. Give the repo a dbt project

`dpb` expects one dbt project for the whole repo, with its `dbt_project.yml` at the repo root. If the repo has none, create it:

```yaml
name: shop
version: "1.0"
profile: shop
```

Add the `generate_schema_name` macro as well, so that models land in the private schema of their data product. See [Build a table with dbt](dbt.md#4-add-a-dbt-project).

Once a table is built by dbt, `dpb generate` owns the `model-paths` and `test-paths` of this file, and sets them to the folders of the data products. So this dbt project builds only models that are in a data product. Keep the old project as it is, with its own `dbt_project.yml`, until every model that you need has moved.

## 5. Generate, parse and validate

```console
$ dpb generate
$ dbt parse
$ dpb validate
ok: 1 data product(s) valid
```

`dpb generate` writes the dbt properties of each model from its table file, and the paths in `dbt_project.yml`. Commit them. The order matters: dbt cannot parse the project before the generated files are there, and `dpb validate` reads the manifest that `dbt parse` writes.

Do not copy the old properties files into the data product. `dpb validate` fails on a model that is declared twice, and names both files.

## 6. Replace reads of other data products

Inside one data product, models read each other with `ref()`. A model that reads a model of another data product must go through an output port:

1. Declare an input port on the output port, and ask its owner to list your data product as a reader. See [Give a reader access to an output port](access.md#give-another-data-product-access).
2. Run `dpb generate`, which writes the dbt source of that port.
3. Replace `ref('<model>')` with `source('<port>', '<table>')` in the model.

`dpb validate` fails on a `ref()` into another data product, because that reads its private schema.

## 7. Switch over

Run the data product next to the old models until its output is right. Then:

1. Point the readers at the views of the output port.
2. Delete the original models and their properties from the old project. The copies in the data product are now the only ones.

## Next

- [Build a table with dbt](dbt.md) explains the files that `dpb generate` writes.
- [Validate in CI](ci.md#repos-with-dbt) shows the CI steps for a repo with dbt.
