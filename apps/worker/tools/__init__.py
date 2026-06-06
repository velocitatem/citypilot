from context import RunContext
from tools.datasets import dataset_tools
from tools.db import db_tools
from tools.reports import report_tools


def build_tools(ctx: RunContext) -> list:
    return [*db_tools(ctx), *report_tools(ctx), *dataset_tools(ctx)]
