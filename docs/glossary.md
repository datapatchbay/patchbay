# Glossary

## General terms

These docs use a few terms of data engineering without explaining them each time.

**Schema**:
A named group of tables and views inside a warehouse. In datapatchbay, every port is one schema.

**View**:
A saved query that reads like a table. An output port holds views over the tables of the private schema.

**Role**:
A named set of permissions in the warehouse. People and programs log in as a member of a role.

**Grant**:
The permission that lets a role read a schema or a view.

**PII**:
Personally identifiable information: data about a person, such as a name or a customer number.

**DAG**:
A set of tasks with an order, which Airflow runs on a schedule. `dpb generate` writes one per data product.

**Cron expression**:
Five fields that state a schedule. `0 5 * * *` means every day at 05:00.

## Terms of datapatchbay

The terms used throughout these docs and in the files.

```{include} ../GLOSSARY.md
:start-after: "## Language"
```
