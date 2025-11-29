from sqlalchemy.orm import Session
from flask_monitoringdashboard.database import FilePath


def add_file_path(session: Session, path: str) -> int:
    """
    Adds an FilePath to the database if it does not already exist. Returns the id.
    """
    path = path[:256]  # To avoid error if larger than allowed in db
    file_path = session.query(FilePath).filter_by(path=path).first()

    if file_path is None:
        file_path = FilePath(path=path)
        session.add(file_path)
        session.flush()

    return file_path.id
