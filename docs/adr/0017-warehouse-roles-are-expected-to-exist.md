# Warehouse roles are expected to exist

The generated SQL grants access to roles but never creates them. The roles of readers, PII readers and data products (the role naming template, ADR-0006) belong to whoever runs the warehouse, usually through their identity provider or an infrastructure repo. When a role is missing, the apply task fails and says which role. We chose this so that the connection used by the orchestrator needs no right to create roles, and so that `patchbay` does not become a second place where people and groups are managed.

## Considered options

- **Create missing roles with `CREATE ROLE`.** Rejected: the orchestrator's connection would need the `CREATEROLE` right, and a typo in a reader name would silently create a role nobody is a member of instead of failing.
- **Create only the roles that the role naming template produces for data products.** Rejected: two kinds of role behave differently, and a data product's login still has to become a member of its role somewhere else.

## Consequences

- Creating a data product's role, and making the data product's login a member of it, happens outside `patchbay`.
- The apply runs as one transaction, so a missing role leaves the previous views and grants as they were.
- Removing a reader revokes on the next apply: it revokes every privilege on the port's schema from every role that has one, and drops and creates the views again, which drops their privileges. Privileges given by hand to a port's schema or views are removed too.
- A view that depends on a port's view, such as a view in another schema, blocks the drop and fails the apply until it is removed.
