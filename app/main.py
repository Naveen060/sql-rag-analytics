import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.auth import authorize
from app.generation import generate
from app.guardrails import UnsafeSQL, validate
from app.retrieval import SchemaRetriever
from app.warehouse import execute, seed

load_dotenv()
log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    app.state.schema = json.loads(Path(os.getenv('SCHEMA_PATH','schema.json')).read_text())
    app.state.retriever = SchemaRetriever(app.state.schema)
    if os.getenv('WAREHOUSE','sqlite') == 'sqlite':
        seed()
    yield

app = FastAPI(title='SQL RAG Analytics', version='1.0.0', lifespan=lifespan)

class Question(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    execute: bool = False

@app.get('/health')
def health():
    return {'status':'ok'}

@app.post('/query', dependencies=[Depends(authorize)])
def query(body: Question):
    dialect = 'snowflake' if os.getenv('WAREHOUSE') == 'snowflake' else 'sqlite'
    try:
        context = app.state.retriever.search(body.question)
        raw = generate(body.question, context, dialect)
        sql = validate(raw, app.state.schema, dialect)
        return {'sql':sql, 'retrieved_tables':list(context), 'executed':body.execute,
                'result':execute(sql) if body.execute else None}
    except (UnsafeSQL, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.exception('Query failed')
        raise HTTPException(502, 'Provider or warehouse failed; check server logs') from exc
