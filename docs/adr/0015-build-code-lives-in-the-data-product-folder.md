# Build code lives in the data product's folder

The code that builds a data product's tables lives in that data product's folder, whatever the executor: Python modules in `src/`, dbt models in `models/`. A team with an existing dbt project or Python pipeline moves that code into data product folders when it adopts datapatchbay. We chose this because moving to data products means deciding which data product owns each table anyway, and the folder is where that decision becomes visible. A file sits in one folder, so every model has exactly one owner by construction.

## Considered options

- **Build code stays where it is, and table files point into it.** Rejected: it spares a team the move but not the work, since every model still needs an owner. Ownership would have to be worked out from lineage, and a model used by two data products would have no clear owner.
- **One `src/` folder for Python and dbt alike.** Rejected: dbt reads every `.py` file in its model paths as a dbt Python model.

## Consequences

- The data product that owns a dbt model or a Python module is the one whose folder holds it. No ownership key is needed in the code.
- The boundary check of ADR-0014 can tell private reads from port reads by location alone.
- Code that builds no table, such as dbt macros or a shared Python library, may live outside the data product folders.
- One dbt project spans the folders of several data products. Its `dbt_project.yml` sits at the repo root, and `dpb generate` keeps its `model-paths` in step with the data product folders, changing only that key.
- dbt model names must be unique across a dbt project, while table names are unique only within a data product. The model name therefore comes from a naming template (ADR-0006), by default `{dataproduct}__{table}`, and the generated alias keeps the table's own name in the warehouse.
