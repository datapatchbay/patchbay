# A port is a folder with its own port file

A data product is one folder. Each port is a subfolder under `inputs/` or `outputs/` holding a `port.yaml` (kind, freshness, access, source, schedule) and one YAML per table. `dataproduct.yaml` also lists the port names, and `dpb validate` fails when the list and the folders disagree. We chose the folder per port because a port is the unit that carries a freshness promise and an access policy, and it mirrors one schema in the warehouse. We accepted the duplicate list so that one file shows the whole shape of a data product to someone who does not browse folders.

Input ports and output ports use the same shape, including ports of kind `table`, which have exactly one table file. One table format is used everywhere.

## Considered options

- **All port facts inside `dataproduct.yaml`.** Rejected: the file grows with every port, and a port cannot be reviewed on its own.
- **Folders only, no list in `dataproduct.yaml`.** Rejected: nothing to keep in sync, but the data product's shape is only visible in the folder tree.
- **A flat `tables/` folder with a port field per table.** Rejected: membership of a port is then spread over the table files.
