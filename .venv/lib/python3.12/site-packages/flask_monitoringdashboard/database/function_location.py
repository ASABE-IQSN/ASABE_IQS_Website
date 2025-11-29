from sqlalchemy.orm import Session
from flask_monitoringdashboard.database import FunctionLocation

def add_function_location(session: Session, file_path_id: int, function_definition_id: int, function_start_line_number: int) -> int:
    """
    Adds a FunctionLocation to the database if it does not already exist.
    :param session: Session for the database
    :param file_path_id: The ID of the FilePath of the function.
    :param function_definition_id: The ID of the FunctionDefinition of the function.
    :param function_start_line_number: The starting line number of the function in the source file.
    :return: The ID of the existing or newly added FunctionDefinition.
    """

    existing_function_location = (
        session.query(FunctionLocation)
        .filter(FunctionLocation.file_path_id == file_path_id)
        .filter(FunctionLocation.function_definition_id == function_definition_id)
        .filter(FunctionLocation.function_start_line_number == function_start_line_number)
        .first()
    )
    if existing_function_location is not None:
        return existing_function_location.id
    else:
        f_location = FunctionLocation(file_path_id=file_path_id, function_definition_id=function_definition_id, function_start_line_number=function_start_line_number)
        session.add(f_location)
        session.flush()
        return f_location.id
