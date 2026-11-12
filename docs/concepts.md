# Concepts

Each data product is one folder, made of three kinds of file:

```text
conventions.yaml          # naming rules for the whole platform
products/
└── lab_orders/
    ├── product.yaml      # owner, inputs, output ports
    └── tables/
        └── orders.yaml   # columns, tests, measures, dimensions
```

## The product file

`product.yaml` says who owns the product, what it reads and what it publishes.

```yaml
# products/lab_orders/product.yaml
name: lab_orders
domain: laboratory
owner: jane.doe@example.org
type: source-aligned

inputs:
  - source: lab_system

outputs:
  - name: public
    kind: schema
    freshness: 24h
    access:
      readers: [grp-lab-reporting]
      pii: [patient_id, doctor_name]
    consumers: [bi-app-general]
```

The contract never names a technology. You won't find Python paths, dbt selectors or connection strings in product or table files. Executors read the contract. How a product runs lives in a separate runner section that you can swap out.

## Output ports

An output port is what a product publishes. Each schema is one port, and the tables inside it are the contract.

A port has a `kind`. The default is `schema`, with `file`, `api` and `export` (for scheduled mails) planned. A different way of delivering the data is a different port on the same product.

## Freshness

Freshness belongs to the port and is a promise. A promise of "fresh within 24 hours" is checked against the latest timestamp. A weekly mail export and a daily schema can sit on the same product, each with its own promise.

## Access

The access policy sits on the output port. The port names the reader groups and the PII columns. `dpb deploy` generates roles, grants and masked views from it. Row filters are access control too, so they also sit on the output port.

BI apps are listed as consumers at the app level, since individual reports change weekly.

## Input ports

Inputs are declared at three levels:

Product level
: Declared by hand in `product.yaml`.

Table level
: Inferred from the code.

Column level
: Opt-in, for consumers who want protection against a dropped column.

## Tables

Each table in a port gets its own file, with columns, tests and a thin semantic layer.

```yaml
# products/lab_orders/tables/orders.yaml
name: orders
description: One row per lab order
columns:
  - name: order_id
    type: text
    tests: [not_null, unique]
  - name: ordered_at
    type: timestamp
    tests: [not_null]
measures:
  - name: order_count
    type: count
dimensions: [ordered_at]
```

The semantic layer covers measures, dimensions and joins for each table. It exports to Cube or to dbt metrics. Owning a small format and exporting from it is cheaper than following another project's roadmap.

## Conventions

`conventions.yaml` at the repo root holds the naming rules for the whole platform:

- language
- casing
- prefixes per product type
- suffixes for dates and keys

`dpb new` scaffolds products that already follow these rules, and `dpb check` validates every product against them.
