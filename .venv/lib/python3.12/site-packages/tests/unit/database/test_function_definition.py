"""
This file contains all unit tests of function definition in the database.
(Corresponding to the file: 'flask_monitoringdashboard/database/function_definition.py')
"""

from flask_monitoringdashboard.database import FunctionDefinition
from flask_monitoringdashboard.database.function_definition import (
    add_function_definition,
    get_function_definition_from_id,
)


def test_add_function_definition(session, function_definition):
    function_definition_id = add_function_definition(session, function_definition)
    f_def = (
        session.query(FunctionDefinition)
        .filter(FunctionDefinition.id == function_definition_id)
        .one()
    )
    assert f_def.code == function_definition.code
    assert f_def.code_hash == function_definition.code_hash


def test_add_existing_function_definition(session, function_definition):
    function_definition_id = add_function_definition(session, function_definition)
    function_definition_count = session.query(FunctionDefinition).count()
    function_definition_id_2 = add_function_definition(session, function_definition)
    assert function_definition_count == session.query(FunctionDefinition).count()
    assert function_definition_id == function_definition_id_2


def test_get_function_definition_from_id(session, function_definition):
    f_def = get_function_definition_from_id(session, function_definition.id)
    assert f_def.id == function_definition.id
    assert f_def.code == function_definition.code
    assert f_def.code_hash == function_definition.code_hash


def test_get_function_definition_from_invalid_id(session):
    f_def = get_function_definition_from_id(session, -1)
    assert f_def is None
