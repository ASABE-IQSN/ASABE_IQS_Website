import inspect
from types import FrameType

from flask_monitoringdashboard.core.exceptions.text_hash import text_hash
from flask_monitoringdashboard.database import FunctionDefinition


def get_function_definition_from_frame(frame: FrameType) -> FunctionDefinition:

    f_def = FunctionDefinition()
    f_def.code = inspect.getsource(frame.f_code)
    f_def.code_hash = text_hash(f_def.code)
    f_def.name = frame.f_code.co_name[:256]
    return f_def
