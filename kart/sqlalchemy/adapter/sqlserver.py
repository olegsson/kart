from kart import crs_util
from kart.schema import Schema, ColumnSchema
from kart.sqlalchemy.sqlserver import Db_SqlServer
from kart.sqlalchemy.adapter.base import BaseKartAdapter


# Adds all CURVE subtypes to GEOMETRY's subtypes since CURVE is a subtype of GEOMETRY, and so on.
def _build_transitive_subtypes(direct_subtypes, type_, result=None):
    if result is None:
        result = {}

    subtypes = set()
    subtypes |= direct_subtypes.get(type_, set())
    sub_subtypes = set()
    for subtype in subtypes:
        sub_subtypes |= _build_transitive_subtypes(direct_subtypes, subtype, result)[
            subtype
        ]

    subtypes |= sub_subtypes
    # type_ is also considered to be a subtype of type_ for our purposes:
    subtypes.add(type_)
    result[type_] = subtypes

    # Also key this data by upper case name, so we can find it in a case-insensitive manner
    # (since V2 geometry types are uppercase).
    result[type_.upper()] = subtypes
    return result


class KartAdapter_SqlServer(BaseKartAdapter, Db_SqlServer):
    """
    Adapts a table in SQL Server (and the attached CRS, if there is one) to a V2 dataset.
    Or, does the reverse - adapts a V2 dataset to a SQL Server table.
    Note that writing custom CRS to a SQL Server instance is not possible.
    """

    V2_TYPE_TO_SQL_TYPE = {
        "boolean": "BIT",
        "blob": "VARBINARY",
        "date": "DATE",
        "float": {0: "REAL", 32: "REAL", 64: "FLOAT"},
        "geometry": "GEOMETRY",
        "integer": {
            0: "INT",
            8: "TINYINT",
            16: "SMALLINT",
            32: "INT",
            64: "BIGINT",
        },
        "interval": "TEXT",  # Approximated
        "numeric": "NUMERIC",
        "text": "NVARCHAR",
        "time": "TIME",
        "timestamp": "DATETIMEOFFSET",
    }

    SQL_TYPE_TO_V2_TYPE = {
        "BIT": "boolean",
        "TINYINT": ("integer", 8),
        "SMALLINT": ("integer", 16),
        "INT": ("integer", 32),
        "BIGINT": ("integer", 64),
        "REAL": ("float", 32),
        "FLOAT": ("float", 64),
        "BINARY": "blob",
        "CHAR": "text",
        "DATE": "date",
        "DATETIME": "timestamp",
        "DATETIME2": "timestamp",
        "DATETIMEOFFSET": "timestamp",
        "DECIMAL": "numeric",
        "GEOGRAPHY": "geometry",
        "GEOMETRY": "geometry",
        "NCHAR": "text",
        "NUMERIC": "numeric",
        "NVARCHAR": "text",
        "NTEXT": "text",
        "TEXT": "text",
        "TIME": "time",
        "VARCHAR": "text",
        "VARBINARY": "blob",
    }

    # Types that can't be roundtripped perfectly in SQL Server, and what they end up as.
    APPROXIMATED_TYPES = {"interval": "text"}
    # Note that although this means that all other V2 types above can be roundtripped, it
    # doesn't mean that extra type info is always preserved.
    # Specifically, the geometryType is not roundtripped.

    # Extra type info that might be missing/extra due to an approximated type.
    APPROXIMATED_TYPES_EXTRA_TYPE_INFO = ("length",)

    # Used for constraining a column to be of a certain type, including subtypes of that type.
    # The CHECK need to explicitly list all types and subtypes, eg for SURFACE:
    # >>> CHECK(geom.STGeometryType() IN ('SURFACE','POLYGON','CURVEPOLYGON'))
    _MS_GEOMETRY_DIRECT_SUBTYPES = {
        "Geometry": set(["Point", "Curve", "Surface", "GeometryCollection"]),
        "Curve": set(["LineString", "CircularString", "CompoundCurve"]),
        "Surface": set(["Polygon", "CurvePolygon"]),
        "GeometryCollection": set(["MultiPoint", "MultiCurve", "MultiSurface"]),
        "MultiCurve": set(["MultiLineString"]),
        "MultiSurface": set(["MultiPolygon"]),
    }

    _MS_GEOMETRY_SUBTYPES = _build_transitive_subtypes(
        _MS_GEOMETRY_DIRECT_SUBTYPES, "Geometry"
    )

    @classmethod
    def v2_schema_to_sql_spec(cls, schema, v2_obj):
        """
        Generate the SQL CREATE TABLE spec from a V2 object eg:
        'fid INTEGER, geom GEOMETRY(POINT,2136), desc VARCHAR(128), PRIMARY KEY(fid)'
        """
        result = [cls.v2_column_schema_to_sqlserver_spec(col, v2_obj) for col in schema]

        if schema.pk_columns:
            pk_col_names = ", ".join((cls.quote(col.name) for col in schema.pk_columns))
            result.append(f"PRIMARY KEY({pk_col_names})")

        return ", ".join(result)

    @classmethod
    def v2_column_schema_to_sqlserver_spec(cls, column_schema, v2_obj):
        name = column_schema.name
        ms_type = cls.v2_type_to_ms_type(column_schema)
        constraints = []

        if ms_type == "GEOMETRY":
            extra_type_info = column_schema.extra_type_info
            geometry_type = extra_type_info.get("geometryType")
            if geometry_type is not None:
                geometry_type = geometry_type.split(" ")[0].upper()
                if geometry_type != "GEOMETRY":
                    constraints.append(
                        cls._geometry_type_constraint(name, geometry_type)
                    )

            crs_name = extra_type_info.get("geometryCRS")
            crs_id = crs_util.get_identifier_int_from_dataset(v2_obj, crs_name)
            if crs_id is not None:
                constraints.append(cls._geometry_crs_constraint(name, crs_id))

        if constraints:
            constraint = f"CHECK({' AND '.join(constraints)})"
            return " ".join([cls.quote(column_schema.name), ms_type, constraint])

        return " ".join([cls.quote(name), ms_type])

    @classmethod
    def _geometry_type_constraint(cls, col_name, geometry_type):
        ms_geometry_types = cls._MS_GEOMETRY_SUBTYPES.get(geometry_type.upper())
        ms_geometry_types_sql = ",".join(f"'{g}'" for g in ms_geometry_types)

        result = f"({cls.quote(col_name)}).STGeometryType()"
        if len(ms_geometry_types) > 1:
            result += f" IN ({ms_geometry_types_sql})"
        else:
            result += f" = {ms_geometry_types_sql}"

        return result

    @classmethod
    def _geometry_crs_constraint(cls, col_name, crs_id):
        return f"({cls.quote(col_name)}).STSrid = {crs_id}"

    @classmethod
    def v2_type_to_ms_type(cls, column_schema):
        """Convert a v2 schema type to a SQL server type."""

        v2_type = column_schema.data_type
        extra_type_info = column_schema.extra_type_info

        ms_type_info = cls.V2_TYPE_TO_SQL_TYPE.get(v2_type)
        if ms_type_info is None:
            raise ValueError(f"Unrecognised data type: {v2_type}")

        if isinstance(ms_type_info, dict):
            return ms_type_info.get(extra_type_info.get("size", 0))

        ms_type = ms_type_info

        if ms_type in ("VARCHAR", "NVARCHAR", "VARBINARY"):
            length = extra_type_info.get("length", None)
            return f"{ms_type}({length})" if length is not None else f"{ms_type}(max)"

        if ms_type == "NUMERIC":
            precision = extra_type_info.get("precision", None)
            scale = extra_type_info.get("scale", None)
            if precision is not None and scale is not None:
                return f"NUMERIC({precision},{scale})"
            elif precision is not None:
                return f"NUMERIC({precision})"
            else:
                return "NUMERIC"

        return ms_type

    @classmethod
    def sqlserver_to_v2_schema(cls, ms_table_info, ms_crs_info, id_salt):
        """Generate a V2 schema from the given SQL server metadata."""
        return Schema(
            [
                cls._sqlserver_to_column_schema(col, ms_crs_info, id_salt)
                for col in ms_table_info
            ]
        )

    @classmethod
    def _sqlserver_to_column_schema(cls, ms_col_info, ms_crs_info, id_salt):
        """
        Given the MS column info for a particular column, converts it to a ColumnSchema.

        Parameters:
        ms_col_info - info about a single column from ms_table_info.
        id_salt - the UUIDs of the generated ColumnSchema are deterministic and depend on
                  the name and type of the column, and on this salt.
        """
        name = ms_col_info["column_name"]
        pk_index = ms_col_info["pk_ordinal_position"]
        if pk_index is not None:
            pk_index -= 1

        if ms_col_info["data_type"] in ("geometry", "geography"):
            data_type, extra_type_info = cls._ms_type_to_v2_geometry_type(
                ms_col_info, ms_crs_info
            )
        else:
            data_type, extra_type_info = cls._ms_type_to_v2_type(ms_col_info)

        col_id = ColumnSchema.deterministic_id(name, data_type, id_salt)
        return ColumnSchema(col_id, name, data_type, pk_index, **extra_type_info)

    @classmethod
    def _ms_type_to_v2_type(cls, ms_col_info):
        ms_type = ms_col_info["data_type"].upper()
        v2_type_info = cls.SQL_TYPE_TO_V2_TYPE.get(ms_type)

        if isinstance(v2_type_info, tuple):
            v2_type = v2_type_info[0]
            extra_type_info = {"size": v2_type_info[1]}
        else:
            v2_type = v2_type_info
            extra_type_info = {}

        if v2_type in ("text", "blob"):
            length = ms_col_info["character_maximum_length"] or None
            if length is not None and length > 0:
                extra_type_info["length"] = length

        if v2_type == "numeric":
            extra_type_info["precision"] = ms_col_info["numeric_precision"] or None
            extra_type_info["scale"] = ms_col_info["numeric_scale"] or None

        return v2_type, extra_type_info

    @classmethod
    def _ms_type_to_v2_geometry_type(cls, ms_col_info, ms_crs_info):
        extra_type_info = {"geometryType": "geometry"}

        crs_row = next(
            (r for r in ms_crs_info if r["column_name"] == ms_col_info["column_name"]),
            None,
        )
        if crs_row:
            auth_name = crs_row['authority_name']
            auth_code = crs_row['authorized_spatial_reference_id']
            if not auth_name and not auth_code:
                auth_name, auth_code = "CUSTOM", crs_row['srid']
            geometry_crs = f"{auth_name}:{auth_code}"
            extra_type_info["geometryCRS"] = geometry_crs

        return "geometry", extra_type_info
