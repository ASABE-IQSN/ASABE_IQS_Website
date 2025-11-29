from flask_monitoringdashboard.core.exceptions.text_hash import text_hash

import traceback
from types import TracebackType
from typing import Union

from flask_monitoringdashboard.core.exceptions.stack_frame_parsing import (
    get_function_definition_from_frame,
)


def hash_stack_trace(exc, tb):
    """
    Hashes the stack trace of an exception including the function definition
    of each frame in thehash_stack_trace python traceback-type.
    """

    # Using the triple argument version to be compatible with Python 3.9
    stack_trace_string = "".join(traceback.format_exception(type(exc), exc, tb))
    stack_trace_hash = text_hash(stack_trace_string)
    return _hash_traceback_type_object(stack_trace_hash, tb)


def _hash_traceback_type_object(h: str, tb: Union[TracebackType, None]):
    if tb is None:
        return h

    f_def = get_function_definition_from_frame(tb.tb_frame)
    new_hash = text_hash(h + f_def.code_hash)

    return _hash_traceback_type_object(new_hash, tb.tb_next)
