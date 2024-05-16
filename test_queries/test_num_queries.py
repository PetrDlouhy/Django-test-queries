import inspect
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict

from debug_toolbar.panels.sql.tracking import wrap_cursor
from django.db import DEFAULT_DB_ALIAS, connections
from django.test import TransactionTestCase
from django.test.testcases import _AssertNumQueriesContext


def strtobool(val):
    """Convert a string representation of truth to true (1) or false (0).
    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return True
    if val in ("n", "no", "f", "false", "off", "0"):
        return False
    raise ValueError(f"invalid truth value {val}")


def boolean_env_var(var: str, default=False) -> bool:
    return strtobool(os.environ.get(var, str(default)))


class Logger(object):
    def __init__(self, context):
        self.queries = []
        self.context = context

    def record(self, sql, raw_sql, stacktrace, *args, **kwargs):
        self.context["records"].append(
            {
                "sql": sql,
                "raw_sql": re.sub(r'SAVEPOINT ".*"', 'SAVEPOINT "%1"', raw_sql),
                "stacktrace": stacktrace,
                "args": args,
                **kwargs,
            }
        )

    def current_transaction_id(self, alias):
        pass

    def new_transaction_id(self, alias):
        pass


def write_full_record(records, file):
    for error_dict in records:
        file.write(f"Raw SQL: {error_dict['raw_sql']}\n\n")
        file.write("Stacktrace:\n")
        stacktrace_entries = [
            f'  File: "{s[0]}", Line: {s[1]}, in {s[2]}\n    {s[3]}' for s in error_dict["stacktrace"]
        ]
        file.write("\n".join(stacktrace_entries) + "\n")

        file.write("\n")
        for rk, rv in error_dict.items():
            if rk in ["sql", "params"]:
                file.write(f"{rk}: {rv}\n\n")
        file.write("\n")
        file.write("----------------------------------------------------------------------")
        file.write("\n")
        file.write("\n")


class _AssertQueriesContext(_AssertNumQueriesContext):
    def __init__(self, test_case, num, connection, context_dict):
        self.context_dict = context_dict
        super().__init__(test_case, num, connection)

    def __exit__(self, exc_type, exc_value, traceback):
        if boolean_env_var("TEST_QUERIES_DISABLE"):
            return
        try:
            super_result = super().__exit__(exc_type, exc_value, traceback)
        except AssertionError as e:
            custom_query_message = self.custom_format_queries()
            custom_message = "\n".join(e.args[0].split("\n")[0:1]) + "\n" + custom_query_message
            raise AssertionError(custom_message) from None
        return super_result

    def custom_format_queries(self):
        formatted_queries = []
        filename = self.context_dict["filename"]
        try:
            with open(filename, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = None
        raw_queries = [s["raw_sql"] for s in self.context_dict["records"]]
        if lines:
            lines = [line.strip() for line in lines]
            lines.sort()
            raw_queries.sort()
            s = SequenceMatcher(None, lines, raw_queries)
            for tag, i1, i2, j1, j2 in s.get_opcodes():
                if tag not in ["insert", "replace", "equal"]:
                    formatted_queries.append(
                        "{:7}   a[{}:{}] --> b[{}:{}] {!r:>8} --> {!r}".format(
                            tag,
                            i1,
                            i2,
                            j1,
                            j2,
                            [s[:50] + "..." for s in lines[i1:i2]],
                            [s[:50] + "..." for s in raw_queries[j1:j2]],
                        )
                    )
                if tag in ["insert", "replace"]:
                    for j in range(j1, j2):
                        if tag == "insert":
                            formatted_queries.append("New query was recorded:")
                        elif tag == "replace":
                            formatted_queries.append("Query was replaced:")
                        formatted_queries.append("\t" + self.context_dict["records"][j]["raw_sql"] + "\n")

        formatted_queries.append("See difference:")
        formatted_queries.append(f"  diff {filename} {filename}.new")
        os.makedirs(filename.rsplit("/", 1)[0], exist_ok=True)

        fr_filename = filename + ".full_record"
        with open(fr_filename, "w") as f:
            write_full_record(self.context_dict["records"], f)
            formatted_queries.append(f"  full record: {fr_filename}")

        if not boolean_env_var("TEST_QUERIES_REWRITE_SQLLOGS"):
            filename += ".new"
        with open(filename, "w") as f:
            f.write("\n".join(raw_queries) + "\n")

        return "\n".join(formatted_queries)


class NumQueriesMixin(TransactionTestCase):
    executed_times = 0
    context: Dict[str, Any] = {}

    def assertNumQueries(self, num, func=None, *args, using=DEFAULT_DB_ALIAS, **kwargs):  # noqa: N802
        conn = connections[using]
        path, file_prefix = inspect.getmodule(self).__file__[:-3].rsplit("/", 1)
        filename = (
            f"{path}/sqllog/{file_prefix}."
            f"{self.__class__.__name__}."
            f"{self._testMethodName}.{self.executed_times}.sqllog"
        )
        self.executed_times += 1
        self.context["filename"] = filename
        self.context["records"] = []
        logger = Logger(context=self.context)

        if not boolean_env_var("TEST_QUERIES_DISABLE"):
            conn._djdt_logger = logger

            try:  # DDT >= 4.2.0
                wrap_cursor(conn)
            except TypeError:
                wrap_cursor(conn, logger)

        context = _AssertQueriesContext(self, num, conn, self.context)

        if func is None:
            return context

        with context:
            func(*args, **kwargs)
