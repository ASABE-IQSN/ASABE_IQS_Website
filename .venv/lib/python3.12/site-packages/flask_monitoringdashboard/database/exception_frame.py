from typing import Union
from sqlalchemy.orm import Session
from flask_monitoringdashboard.database import ExceptionFrame, FunctionLocation


def add_exception_frame(
    session: Session,
    function_location_id: int,
    line_number: int,
):
    """
    Adds a ExceptionFrame to the database if it does not already exist.
    :param session: Session for the database
    :param function_location_id: The ID of the FunctionLocation of the frame.
    :param line_number: The line number of the frame.
    :return: The ID of the existing or newly added ExceptionFrame.
    """

    existing_exception_frame = (
        session.query(ExceptionFrame)
        .filter(ExceptionFrame.function_location_id == function_location_id)
        .filter(ExceptionFrame.line_number == line_number)
        .first()
    )
    if existing_exception_frame is not None:
        return existing_exception_frame.id
    else:
        frame = ExceptionFrame(
            function_location_id=function_location_id, line_number=line_number
        )
        session.add(frame)
        session.flush()
        return frame.id
