# Plugins through entry points, built-ins included

datapatchbay has four extension points: orchestrator, executor, runtime and warehouse. Plugins are found through Python entry points, which are part of the standard library and add no dependency. The built-in Airflow, Python and Postgres support is written against the same interfaces and registered the same way. We chose this so that the core stays small, and so that the interfaces are exercised from the first release instead of being designed later around code that never needed them.

The interface is not stable in milestone 1. It is declared stable once the dbt executor, the first second implementation of an extension point, has proven it.

## Considered options

- **Hard-code Airflow, Python and Postgres, add plugins later.** Rejected: the first generator would grow without boundaries and have to be taken apart.
- **A stable plugin interface in milestone 1.** Rejected: an interface with one implementation is a guess.
- **More extension points (validation rules, quality rule types, export formats).** Left out until someone needs one.
