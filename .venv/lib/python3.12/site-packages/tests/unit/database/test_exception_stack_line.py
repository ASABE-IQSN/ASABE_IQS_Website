"""
This file contains all unit tests of exception stack line in the database.
(Corresponding to the file: 'flask_monitoringdashboard/database/exception_stack_line.py')
"""

from flask_monitoringdashboard.database import ExceptionStackLine
from flask_monitoringdashboard.database.exception_stack_line import (
    add_exception_stack_line,
)


def test_add_exception_stack_line(
    session, stack_trace_snapshot, exception_frame
):
    assert (
        session.query(ExceptionStackLine)
        .filter(ExceptionStackLine.stack_trace_snapshot_id == stack_trace_snapshot.id)
        .one_or_none()
        is None
    )
    add_exception_stack_line(
        session,
        stack_trace_snapshot_id=stack_trace_snapshot.id,
        exception_frame_id=exception_frame.id,
        position=0,
    )
    session.commit()
    assert (
        session.query(ExceptionStackLine)
        .filter(ExceptionStackLine.stack_trace_snapshot_id == stack_trace_snapshot.id)
        .one()
    )
