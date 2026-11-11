"""Decide whether a proposed SQL query is allowed to run. The model never makes this decision.

Checks the parsed structure of the query, not its text: one statement, read-only,
and only tables, columns and functions that the schema and this file approve.

By default it checks against this project's schema with a strict function allow-list. For an outside
database (the BIRD benchmark) pass that database's columns and allowed_functions=None, which switches
to a block-list: any ordinary SQL function is fine, but anything that touches the server is refused.
"""
from dataclasses import dataclass, field
from pathlib import Path

import sqlglot
from sqlglot import exp

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

# Functions the assistant may use. Anything else (pg_sleep, set_config, dblink, ...) is rejected.
ALLOWED_FUNCTIONS = {
    exp.Sum, exp.Count, exp.Avg, exp.Min, exp.Max, exp.Round, exp.Abs,
    exp.Coalesce, exp.Nullif, exp.Greatest, exp.Least,
    exp.Case, exp.If, exp.Cast, exp.TryCast, exp.Extract, exp.DateTrunc, exp.TimestampTrunc,
}

# Used when allowed_functions=None: function names (or name prefixes) that reach outside the query itself.
BLOCKED_FUNCTION_PREFIXES = (
    "pg_", "lo_", "dblink", "set_config", "current_setting", "query_to_xml", "table_to_xml",
    "cursor_to_xml", "database_to_xml", "schema_to_xml", "txid_", "inet_", "version",
)

# Statement types that change data or the database. Rejected anywhere in the query, including inside a CTE.
FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.TruncateTable, exp.Command, exp.Copy, exp.Into, exp.Set, exp.Grant, exp.Lock,
)


@dataclass
class ValidationResult:
    allowed: bool
    errors: list = field(default_factory=list)


def load_allowed_columns():
    """Read {table: {columns}} from db/schema.sql so the allow-list can't drift from the real schema."""
    allowed = {}
    for statement in sqlglot.parse(SCHEMA_FILE.read_text(), read="postgres"):
        if isinstance(statement, exp.Create) and statement.kind == "TABLE":
            table = statement.this.this.name
            allowed[table] = {col.name for col in statement.this.find_all(exp.ColumnDef)}
    return allowed


ALLOWED_COLUMNS = load_allowed_columns()


def validate_sql(sql, allowed_columns=None, allowed_functions=ALLOWED_FUNCTIONS):
    """Return a ValidationResult saying whether this SQL may be executed, and why not if it may not.

    allowed_columns: {table: {columns}}; defaults to this project's schema. Names compare case-insensitively.
    allowed_functions: set of SQLGlot function classes, or None for block-list mode (outside databases).
    """
    schema = {
        table.lower(): {col.lower() for col in cols}
        for table, cols in (allowed_columns if allowed_columns is not None else ALLOWED_COLUMNS).items()
    }
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as error:
        detail = error.errors[0].get("description", "syntax error") if error.errors else "syntax error"
        return ValidationResult(False, [f"SQL could not be parsed: {detail}."])

    if len(statements) != 1:
        return ValidationResult(False, [f"Expected exactly one statement, found {len(statements)}."])
    tree = statements[0]
    errors = []

    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        errors.append(f"Only SELECT queries are allowed, not {tree.key.upper()}.")
    for node in tree.find_all(*FORBIDDEN_NODES):
        errors.append(f"Forbidden operation inside the query: {node.key.upper()}.")

    cte_names = {cte.alias.lower() for cte in tree.find_all(exp.CTE)}
    alias_to_table = {}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names:
            alias_to_table[table.alias_or_name.lower()] = None  # a CTE: its columns are defined in the query itself
        elif name not in schema or table.db:
            errors.append(f"Table not allowed: {table.sql(dialect='postgres')}.")
        else:
            alias_to_table[table.alias_or_name.lower()] = name
    for subquery in tree.find_all(exp.Subquery):
        if subquery.alias:
            alias_to_table[subquery.alias.lower()] = None  # a derived table: its columns are checked inside it

    output_aliases = {a.alias.lower() for a in tree.find_all(exp.Alias)} | {
        col.lower() for cte in tree.find_all(exp.CTE) for col in getattr(cte.this, "named_selects", [])
    }
    used_tables = {t for t in alias_to_table.values() if t}
    for column in tree.find_all(exp.Column):
        name, qualifier = column.name.lower(), column.table.lower()
        if qualifier:
            if qualifier not in alias_to_table:
                errors.append(f"Unknown table or alias '{qualifier}' in column {qualifier}.{name}.")
            elif alias_to_table[qualifier] and name not in schema[alias_to_table[qualifier]]:
                errors.append(f"Column not in schema: {alias_to_table[qualifier]}.{name}.")
        elif name not in output_aliases and not any(name in schema[t] for t in used_tables):
            errors.append(f"Column not in schema: {name}.")

    for function in tree.find_all(exp.Func):
        if isinstance(function, exp.Connector):
            continue  # AND / OR are operators that SQLGlot happens to model as functions
        label = function.name if isinstance(function, exp.Anonymous) else function.key
        if allowed_functions is None:
            if label.lower().startswith(BLOCKED_FUNCTION_PREFIXES):
                errors.append(f"Function not allowed: {label}.")
        elif type(function) not in allowed_functions:
            errors.append(f"Function not allowed: {label}.")

    return ValidationResult(not errors, sorted(set(errors)))
