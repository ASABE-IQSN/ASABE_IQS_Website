from typing import Union
from sqlalchemy.orm import Session
from flask_monitoringdashboard.database import ExceptionStackLine, FilePath, StackTraceSnapshot, FunctionDefinition, FunctionLocation, ExceptionFrame
from sqlalchemy import desc


def get_stack_trace_by_hash(
    session: Session, stack_trace_snapshot_hash: str
) -> Union[StackTraceSnapshot, None]:
    """
    Get StackTraceSnapshot record by its hash.
    """
    result = (
        session.query(StackTraceSnapshot)
        .filter_by(hash=stack_trace_snapshot_hash)
        .first()
    )
    return result


def add_stack_trace_snapshot(session: Session, stack_trace_snapshot_hash: str) -> int:
    """
    Add a new StackTraceSnapshot record. Returns the id.
    """
    existing_trace = get_stack_trace_by_hash(session, stack_trace_snapshot_hash)
    if existing_trace is not None:
        return int(existing_trace.id)

    result = StackTraceSnapshot(hash=stack_trace_snapshot_hash)
    session.add(result)
    session.flush()

    return int(result.id)


def get_stacklines_from_stack_trace_snapshot_id(
    session: Session, stack_trace_snapshot_id: int
):
    """
    Gets all the stack lines referred to by a stack_trace.
    :param session: session for the database
    :param stack_trace_snapshot_id: Filter ExceptionStackLines on this stack trace id
    return: A list of dicts. Each dict contains:
             - position (int) in the stack trace
             - path (str) to the file
             - line_number (int) in the file
             - name (str) of the function
             - function_start_line_number (int)
             - function_definition_id (int) of the function
    """
    result = (
        session.query(
            ExceptionStackLine.position,
            FilePath.path,
            ExceptionFrame.line_number,
            FunctionDefinition.name,
            FunctionLocation.function_start_line_number,
            FunctionLocation.function_definition_id,
        )
        .join(ExceptionFrame, ExceptionStackLine.exception_frame)
        .join(FunctionLocation, ExceptionFrame.function_location)
        .join(FunctionDefinition, FunctionLocation.function_definition)
        .join(FilePath, FunctionLocation.file_path)
        .filter(ExceptionStackLine.stack_trace_snapshot_id == stack_trace_snapshot_id)
        .order_by(desc(ExceptionStackLine.position))
        .all()
    )
    return result
