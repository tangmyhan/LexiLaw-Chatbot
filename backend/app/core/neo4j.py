import os
import neo4j
from neo4j import AsyncGraphDatabase
from app.core.config import settings

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI, 
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
            trusted_certificates=neo4j.TrustAll  # Disable SSL cert verification for Aura
        )
    return _driver

async def close_driver():
    global _driver
    if _driver:
        await _driver.close()
        _driver = None

def get_db():
    # helper for session kwargs
    return {"database": settings.NEO4J_DATABASE} if settings.NEO4J_DATABASE else {}