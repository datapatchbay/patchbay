# datapatchbay

Data products as code: a data platform described as a set of owned data products, each declaring what it reads, what it publishes and what it promises.

## Language

### Data products

**Data product**:
A named, owned unit of data on the platform that reads through input ports and publishes through output ports.
_Avoid_: Product, dataset, project

**Owner**:
The person accountable for a data product and the one to call when a number is wrong.
_Avoid_: Business owner, steward

**Technical owner**:
The person who builds and maintains a data product.
_Avoid_: Maintainer, developer

**Data product kind**:
A label on a data product taken from a list the platform defines, by default source-aligned, aggregate or consumer-aligned. Each kind has a short prefix used in derived names.
_Avoid_: Product type, layer, tier

**Naming template**:
A platform-wide pattern that produces a derived name, such as a port name or a role name, from a data product's kind and name.
_Avoid_: Naming rule, pattern

**Domain**:
The business area a data product belongs to, such as finance, sales or operations.
_Avoid_: Department, area

### Ports

**Port**:
A named interface of a data product through which data enters or leaves. Its name comes from a naming template and is unique across the platform.
_Avoid_: Interface, endpoint, dataset

**Private schema**:
The place where a data product lands its ingested tables and builds its output tables. Nobody outside the data product reads it.
_Avoid_: Staging schema, internal schema

**Input port**:
A port through which a data product receives data, either from a source or from another data product's output port.
_Avoid_: Dependency, upstream

**Output port**:
A port through which a data product publishes data, with its own freshness promise and access policy. It exposes views only, never the tables themselves.
_Avoid_: Public schema, export

**Default output port**:
The output port that carries the same name as its data product.

**Port kind**:
The form a port takes: a schema holding several tables, or a single table. Other forms may follow.
_Avoid_: Port type

**Table**:
One table in a port, with the columns and quality rules expected of it.
_Avoid_: Model, dataset

**Quality rule**:
A condition the data in a column or a table must meet, such as not null, unique or a row count bound.
_Avoid_: Test, check, expectation

**Severity**:
What happens when a quality rule is broken: error fails the run, warning reports and continues, none ignores the rule.
_Avoid_: Level, priority

**Source**:
A system outside the platform that delivers data into an input port.
_Avoid_: Source system, upstream system

### Promises on an output port

**Reader**:
A group, role, user or data product that is allowed to read an output port.
_Avoid_: Consumer, subscriber

**PII reader**:
A reader that may also see the columns marked as personal data.

**Freshness**:
The promise of how old the newest data in an output port may be, stated as a duration.
_Avoid_: SLA, latency

### Building tables

**Contract**:
The part of a table's definition that states what to expect from it and names no technology.
_Avoid_: Spec, schema definition

**Build**:
The part of a table's definition that states how the table is made: its executor, its code and the parameters passed to it.
_Avoid_: Runner, pipeline config

**Executor**:
The technology that builds a table, such as Python or dbt.
_Avoid_: Runner, engine

**Orchestrator**:
The system that triggers builds on a schedule, such as Airflow. The platform usually has one.
_Avoid_: Scheduler

**Runtime**:
The place where an executor's code runs, such as an Airflow worker or a container.
_Avoid_: Environment, compute

**Integration**:
The support for one technology (an orchestrator, executor, runtime or warehouse) in one folder, found through an entry point.
_Avoid_: Provider, connector, adapter
