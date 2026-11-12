# Names are derived from naming templates

A data product states a bare `name` (`jaffle_orders`) and a kind with a prefix (`sa`). Every other name is produced by a naming template in `datapatchbay.yaml`: the folder name, the output port name, the private port name and the role name. `dpb validate` compares what is on disk with what the templates produce. We chose templates because a team's naming convention then lives in one place, can be changed there, and makes port names unique across the repo by construction.

## Considered options

- **The name includes the prefix (`sa_jaffle_orders`) and rules check it.** Rejected: the convention is repeated in every data product, and changing it means renaming each one by hand.
- **A regular expression per kind of name.** Rejected: it can check a name but cannot produce one, so `dpb new` could not scaffold from it.
- **Column naming rules by type.** Left out: column types are free text (see ADR-0012), so a rule such as "timestamps end in `_at`" cannot be checked reliably.
