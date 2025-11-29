from typing import Union
from sqlalchemy.orm import Session
from flask_monitoringdashboard.database import (
    CodeLine,
    ExceptionStackLine,
    FunctionDefinition,
)


def add_function_definition(session: Session, f_def: FunctionDefinition) -> int:
    """
    Adds a FunctionDefinition to the database if it does not already exist.
    :param session: Session for the database
    :param f_def: The FunctionDefinition object to be added
    :return: The ID of the existing or newly added FunctionDefinition.
    """
    result: Union[FunctionDefinition, None] = (
        session.query(FunctionDefinition)
        .filter(FunctionDefinition.code_hash == f_def.code_hash)
        .first()
    )
    if result is not None:
        return result.id
    else:
        session.add(f_def)
        session.flush()
        return f_def.id


def get_function_definition_from_id(
    session: Session, function_id: int
) -> Union[FunctionDefinition, None]:
    return (
        session.query(FunctionDefinition)
        .filter(FunctionDefinition.id == function_id)
        .first()
    )

def get_function_definition_code_from_id(session: Session, function_id: int) -> Union[str, None]:
    """
    Retrieves the code of a function definition from the database using its ID.
    :param session: Session for the database
    :param function_id: ID of the FunctionDefinition
    :return: The code of the function definition if found, otherwise None.
    """
    result: Union[FunctionDefinition, None] = get_function_definition_from_id(session, function_id)
    if result is not None:
        return result.code
    else:
        return None
