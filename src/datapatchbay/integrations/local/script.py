"""The code that the `local` orchestrator copies into every script it generates.

The script may not import datapatchbay (ADR-0001), so this code is plain strings. The quality-rule code is shared with
the `airflow` orchestrator (`RUN_AUDIT_HELPER`).
"""

ANNOUNCE_HELPER = '''\
def _announce(step):
    """Log the step that is about to run, as 'data product: step'."""
    LOG.info("%s: %s", DATAPRODUCT, step)'''

CONNECT_HELPER = '''\
def _connect():
    """Open a connection to the warehouse. The environment variable named by CONNECTION_VARIABLE holds its URL."""
    url = os.environ.get(CONNECTION_VARIABLE)
    supported = (
        "duckdb:<path>, duckdb:///<absolute path>, postgresql://<user>:<password>@<host>/<database> "
        "or postgres://<user>:<password>@<host>/<database>"
    )
    if not url:
        raise RuntimeError(f"environment variable {CONNECTION_VARIABLE} is not set; set it to a URL: {supported}")
    if url.startswith("duckdb:"):
        path = url.removeprefix("duckdb:").removeprefix("//")
        if not path:
            raise RuntimeError(f"environment variable {CONNECTION_VARIABLE} names no DuckDB file; use {supported}")
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError(f"{CONNECTION_VARIABLE} is a duckdb: URL, but duckdb is not installed") from exc
        return duckdb.connect(path)
    if url.startswith(("postgresql://", "postgres://")):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(f"{CONNECTION_VARIABLE} is a postgres URL, but psycopg is not installed") from exc
        return psycopg.connect(url, autocommit=True)
    scheme = url.split(":", 1)[0]
    raise RuntimeError(
        f"environment variable {CONNECTION_VARIABLE} has an unsupported value (scheme '{scheme}'); use {supported}"
    )


def _audit_step(task_id, checks):
    """Run the quality rules of a table on a connection that lives as long as the step."""
    _announce(task_id)
    connection = _connect()
    try:
        _run_audit(checks, lambda sql: connection.execute(sql).fetchone()[0])
    finally:
        connection.close()


def _sql_step(task_id, sql):
    """Run SQL on a connection that lives as long as the step. The SQL manages its own transaction."""
    _announce(task_id)
    connection = _connect()
    try:
        connection.execute(sql)
    finally:
        connection.close()'''

UPSTREAM_HELPER = '''\
def _local_products():
    """Read the constants of the sibling scripts that are local data products, without importing them."""
    products = {}
    for path in sorted(Path(__file__).resolve().parent.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        constants = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try:
                    constants[node.targets[0].id] = ast.literal_eval(node.value)
                except ValueError:
                    continue
        if constants.get("ORCHESTRATOR") == "local":
            products[path.stem] = {
                "path": path,
                "reads": tuple(constants.get("READS", ())),
                "outputs": tuple(constants.get("OUTPUTS", ())),
            }
    return products


def _upstream(name, products):
    """Return the local data products that `name` reads, directly or indirectly, in the order to run them."""
    order = []
    visiting = []

    def visit(current):
        if current in order:
            return
        if current in visiting:
            raise RuntimeError("data products read each other in a cycle: " + " -> ".join([*visiting, current]))
        visiting.append(current)
        for port in products[current]["reads"]:
            producers = sorted(other for other, product in products.items() if port in product["outputs"])
            if not producers:
                LOG.warning("%s reads port '%s', which no local data product here produces", current, port)
            for producer in producers:
                visit(producer)
        visiting.pop()
        order.append(current)

    visit(name)
    return order[:-1]'''

MAIN_HELPER = '''\
def main(argv=None):
    """Run the data product; with --upstream, first run the local data products it reads."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", action="store_true", help="first run the local data products this one reads")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if arguments.upstream:
        products = _local_products()
        products.setdefault(DATAPRODUCT, {"path": Path(__file__).resolve(), "reads": READS, "outputs": OUTPUTS})
        for name in _upstream(DATAPRODUCT, products):
            LOG.info("%s: running upstream data product %s", DATAPRODUCT, name)
            subprocess.run([sys.executable, str(products[name]["path"])], check=True)
    run()'''
