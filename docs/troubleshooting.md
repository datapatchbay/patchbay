# Troubleshooting

Find the message you see, then read the cause and the fix. Messages from `dpb validate` and `dpb generate` have the form `file:line: message`, so start at that line.

## Exit codes

Every command uses the same three exit codes:

| Exit code | Meaning |
| --- | --- |
| 0 | The command did what it was asked |
| 1 | The files have problems. `dpb` lists all of them and writes nothing |
| 2 | The command could not run: a wrong option, no `datapatchbay.yaml`, an unknown data product, or a failure while generating |

## Starting a command

`error: no datapatchbay.yaml found in <folder> or any parent directory; is this a datapatchbay repo?`
: `dpb` looks for `datapatchbay.yaml` in the working directory and its parents. Run the command inside the repo. In a new repo, create the file with one line, `schema_version: 1`.

`error: missing values: --kind, --owner; give them as flags or run without --no-input`
: `dpb new --no-input` never asks. Give the named flags, or leave out `--no-input` to answer the questions in the terminal.

`error: dataproducts/<folder> already exists; dpb new never overwrites a data product`
: A data product with that name and kind exists. Choose another name, or edit the existing folder.

`error: no data product named '<name>'; the data products are: ...`
: `dpb describe` takes the folder name, such as `sa_ilab_orders`, or the bare `name`, such as `ilab_orders`.

`dpb list` leaves out a data product
: A file of that data product fails validation. `dpb list` prints a warning on stderr. Run `dpb validate` to see why.

## Files and keys

`unknown key '<key>'; if it is not a typo, it may come from a newer datapatchbay`
: Unknown keys fail, so a typo never passes in silence. Correct the key. The [file reference](files.md) lists the keys of each kind of file. For your own extras, use the free-form `meta` map.

`` missing schema_version; add `schema_version: 1` ``
: Every file starts with `schema_version`. Add the line.

`schema_version 2 is newer than this datapatchbay understands (newest known: 1); upgrade datapatchbay`
: The file was written for a newer `dpb` than the one installed. [Upgrade](installation.md#upgrade) `dpb`.

`invalid YAML: ...`
: The file is not valid YAML. The line number points at where the parser stopped, which can be after the real mistake. Look for an open bracket or quote, or wrong indentation, on the lines before it.

`` folder inputs/<port> is not listed in `inputs` ``
: The port lists in `dataproduct.yaml` and the folders under `inputs/` and `outputs/` must match in both directions. Add the port to the list, or remove the folder.

`entrypoint file src/<file>.py does not exist in the data product folder`
: The `build.entrypoint` of a table points at a file that is not there, often after a rename. The path is relative to the data product folder.

## Names

`` data product folder '<folder>' must be named '<name>', which the naming template produces from `name` and `kind` ``
: Folder and port names are derived from `name` and `kind`. After you change either one, rename the folder and the ports to what the message says. To change the convention itself, change the templates under `conventions.names` in `datapatchbay.yaml`.

`kind '<kind>' is not one of the kinds in the conventions; declared kinds: ...`
: Use one of the declared kinds, or declare the new kind with its prefix under `conventions.kinds` in `datapatchbay.yaml`.

## Readers and freshness

`` data product '<reader>' reads '<port>' but is not listed in the readers of that port; add `- product: <reader>` under access.readers in <file> ``
: Declaring an input port does not give access. Add the line the message shows to the `port.yaml` of the output port. See [Give a reader access to an output port](howto/access.md).

`output port '<port>' promises freshness 12h, but source input port '<port>' delivers with a longest gap of 24h (schedule "0 5 * * *")`
: The port promises fresher data than its source delivers. Promise less, with a longer `freshness`, or make the `schedule` of the source input port more frequent.

`output port '<port>' promises freshness 1h, but the output port '<port>' that it reads (input port '<port>') promises only 24h`
: The same, for a data product that reads another one. A port cannot be fresher than the port it reads.

`freshness: Value error, '<value>' is not a duration; write a positive whole number and a unit, such as 30m, 24h or 7d`
: Write the duration as a number and one unit.

## Settings and plugins

`` runtime 'docker' needs an image, but none is set (data product '<folder>', table '<table>'); set `image` at the root, data product, port or table ``
: A container runtime runs an image. Set `image` at the level where you set `runtime`. See [Run build code in a container](howto/containers.md).

`orchestrator '<name>' has no plugin (data product '<folder>'); available orchestrator plugins: airflow`
: The name in the settings is not the name of an installed plugin. Correct the name, or install the package that provides the plugin in the same environment as `dpb`. The same message exists for executors, runtimes and warehouses.

A setting does not have the value you expect
: `dpb config` prints the root settings and where each comes from. `dpb describe <data product>` prints the resolved settings of every port and table, with the level that set each one. The nearest level wins: table, then port, then data product, then root.

## dbt

`` dbt properties file does not match its table file; run `dpb generate` to refresh it ``
: The table file changed after the properties were generated, or someone edited the properties by hand. Run `dpb generate` and commit the result. The same fix applies to `dbt properties file is missing`.

`model file models/<model>.sql does not exist in the folder of data product '<folder>'; table '<table>' is built by dbt`
: A dbt table needs its model, named by the `dbt_model` naming template. Create the file, or check the spelling of its name.

`tables are built by dbt, so a dbt_project.yml is expected at the repo root`
: Create `dbt_project.yml` at the repo root with at least `name`, `version` and `profile`.

`table rule 'row_count' is not supported for dbt yet; table '<table>' is built by dbt`
: Table rules (`primary_key`, `row_count` and `sql`) are not mapped to dbt yet. Remove the rule, or build the table with Python.

`` runtime 'docker' cannot run dbt (data product '<folder>', table '<table>'); set `runtime: worker` for the tables built by dbt ``
: dbt runs on the Airflow worker only.

The models land in a schema such as `<target schema>_<private port name>`
: The dbt project does not override the `generate_schema_name` macro. The views and grants then do not find the tables. See the [table file reference](files.md#table-file) for the macro.

## When the DAG runs

A build task fails with `NotImplementedError: write the build code of the table '<table>'`
: The build function is still the stub that `dpb new` wrote. Replace it with code that writes the table to the data product's private schema.

A build task cannot load the entrypoint file
: On the `worker` runtime, the DAG file finds the build code from its own location. Deploy the output folder and the data product folders in the same relative places as in the repo. See [Deploy the generated DAGs](howto/deploy.md).

`apply_access` fails because a role does not exist
: The generated SQL grants to roles and never creates them. Create the role in the warehouse. Until then, the views and grants of the previous run stay in place.

`apply_access` fails because another object depends on a view
: The views of an output port are dropped and created again on every run. A view in another schema that selects from them blocks the drop. Remove that view.

An audit task fails with `quality rule '<rule>' is broken on table '<table>', column '<column>': <n> violation(s)`
: The data breaks a quality rule with severity `error`. Correct the data or the build code. If the rule should only report, give it `severity: warning`.

A change to the readers has no effect
: Access is applied by the `apply_access` task. The change takes effect on the next run of the data product's DAG, after the new DAG file is deployed.

## Still stuck

Search the [GitHub issues](https://github.com/datapatchbay/patchbay/issues), or open a new one. Include the command, its output and the `dpb` files it names.
