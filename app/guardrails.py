import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

class UnsafeSQL(ValueError):
    pass

# Deliberately narrow: unknown/UDF functions are rejected, even inside SELECT.
ALLOWED_FUNCTIONS = {
    'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COALESCE', 'CAST', 'ROUND',
    'ABS', 'LOWER', 'UPPER', 'LENGTH', 'DATE_TRUNC', 'EXTRACT',
    'CURRENT_DATE', 'NULLIF', 'IF', 'CASE', 'ROW_NUMBER',
}

def validate(sql: str, schema: dict, dialect='sqlite', max_rows=200) -> str:
    try:
        statements = sqlglot.parse(sql, read=dialect)
        if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
            raise UnsafeSQL('Only one SELECT query is allowed')
        query = statements[0]
        forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
                     exp.Command, exp.Into, exp.Lock, exp.Merge)
        if any(isinstance(node, forbidden) for node in query.walk()):
            raise UnsafeSQL('Mutation or locking is not allowed')
        if any(cte.args.get('recursive') for cte in query.find_all(exp.With)):
            raise UnsafeSQL('Recursive queries are disabled')
        for function in query.find_all(exp.Func):
            name = function.name if isinstance(function, exp.Anonymous) else function.sql_name()
            if name.upper() not in ALLOWED_FUNCTIONS:
                raise UnsafeSQL(f'Function {name} is not approved')
        allowed = {name.lower() for name in schema}
        for scope in traverse_scope(query):
            for source in scope.sources.values():
                if isinstance(source, exp.Table):
                    if source.db or source.catalog or source.name.lower() not in allowed:
                        raise UnsafeSQL(f'Table {source.sql()} is not approved')
        query = qualify(query, dialect=dialect,
                        schema={k:v['columns'] for k,v in schema.items()},
                        validate_qualify_columns=True, identify=False)
        # Reject nonconstant limits and offsets; clamp oversized limits.
        for node in query.find_all(exp.Offset):
            if not isinstance(node.expression, exp.Literal) or not node.expression.is_int:
                raise UnsafeSQL('OFFSET must be a constant integer')
            if int(node.expression.this) > 10000 or int(node.expression.this) < 0:
                raise UnsafeSQL('OFFSET out of bounds')
        current = query.args.get('limit')
        count = max_rows
        if current:
            if not isinstance(current.expression, exp.Literal) or not current.expression.is_int:
                raise UnsafeSQL('LIMIT must be a constant integer')
            count = int(current.expression.this)
            if count < 0:
                raise UnsafeSQL('Negative LIMIT is not allowed')
        return query.limit(min(count, max_rows)).sql(dialect=dialect)
    except UnsafeSQL:
        raise
    except Exception as exc:
        raise UnsafeSQL(f'SQL validation failed: {exc}') from exc
