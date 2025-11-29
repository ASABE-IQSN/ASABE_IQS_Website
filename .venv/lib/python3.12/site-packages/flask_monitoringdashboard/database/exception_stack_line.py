from flask_monitoringdashboard.database import ExceptionStackLine

def add_exception_stack_line(
    session,
    stack_trace_snapshot_id,
    exception_frame_id,
    position,
):
    """
    Adds a ExceptionStackLine to the database
    :param session: Session for the database
    :param stack_trace_snapshot_id: id of the stack trace snapshot
    :param exception_frame_id: id of the ExceptionFrame
    :param position: position of the ExceptionStackLine in the stack trace
    """
    session.add(
        ExceptionStackLine(
            stack_trace_snapshot_id=stack_trace_snapshot_id,
            exception_frame_id=exception_frame_id,
            position=position,
        )
    )
