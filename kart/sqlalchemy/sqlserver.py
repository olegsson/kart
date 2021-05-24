import logging
import re
from urllib.parse import urlsplit, urlunsplit

import sqlalchemy
from sqlalchemy.dialects.mssql.base import MSIdentifierPreparer, MSDialect


from kart.exceptions import NotFound, NO_DRIVER
from .base import BaseDb


L = logging.getLogger("kart.sqlalchemy.sqlserver")


class Db_SqlServer(BaseDb):
    """Functionality for using sqlalchemy to connect to a SQL Server database."""

    CANONICAL_SCHEME = "mssql"
    INTERNAL_SCHEME = "mssql+pyodbc"
    INSTALL_DOC_URL = "https://docs.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server"

    preparer = MSIdentifierPreparer(MSDialect())

    @classmethod
    def create_engine(cls, msurl):
        url = urlsplit(msurl)
        if url.scheme != cls.CANONICAL_SCHEME:
            raise ValueError("Expecting mssql://")

        url_query = cls._append_to_query(
            url.query,
            {"driver": cls.get_sqlserver_driver(), "Application Name": "kart"},
        )

        # SQL Server driver prefers 127.0.0.1 or similar to localhost.
        url_netloc = cls._replace_localhost_with_ip(url.netloc)

        msurl = urlunsplit([cls.INTERNAL_SCHEME, url_netloc, url.path, url_query, ""])

        engine = sqlalchemy.create_engine(msurl, poolclass=cls._pool_class())
        return engine

    @classmethod
    def get_odbc_drivers(cls):
        """Returns a list of names of all ODBC drivers."""
        try:
            import pyodbc
        except ImportError as e:
            # this likely means unixODBC isn't installed. But since the MSSQL
            # drivers on macOS/Linux depend on it then it'll be installed with them.
            L.debug("pyodbc import error: %s", e)
            raise NotFound(
                f"ODBC support for SQL Server is required but was not found.\nSee {cls.INSTALL_DOC_URL}",
                exit_code=NO_DRIVER,
            )

        return pyodbc.drivers()

    @classmethod
    def get_sqlserver_driver(cls):
        """Return the name of the SQL Server driver."""
        drivers = cls.get_odbc_drivers()
        mssql_drivers = [
            d for d in drivers if re.search("SQL Server", d, flags=re.IGNORECASE)
        ]
        if not mssql_drivers:
            raise NotFound(
                f"ODBC Driver for SQL Server is required but was not found.\nSee {cls.INSTALL_DOC_URL}",
                exit_code=NO_DRIVER,
            )
        return sorted(mssql_drivers)[-1]  # Latest driver
