"""
main.py — Urban Data Explorer API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from dependencies import limiter
from routers import mobilite, connectivite

app = FastAPI(
    title="Urban Data Explorer API",
    version="2.0.0",
    description="""
## Urban Data Explorer API

Scores composites par arrondissement parisien.

### Authentification
Tous les endpoints (sauf `/` et `/quota`) nécessitent un header `X-API-Key`.

### Rate limiting
- Endpoints scores : **60 requêtes/minute**
- Endpoints GeoJSON : **30 requêtes/minute**
""",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["X-API-Key"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(mobilite.router)
app.include_router(connectivite.router)

@app.get("/", tags=["Info"])
def root():
    return {"message": "Urban Data Explorer API", "version": "2.0.0"}

@app.get("/quota", tags=["Info"])
def get_quota():
    return {
        "auth": "Header X-API-Key requis sur tous les endpoints de données",
        "endpoints": {
            "/mobilite":                    "60 requêtes/minute",
            "/mobilite/points/geojson":     "30 requêtes/minute",
            "/connectivite":                "60 requêtes/minute",
            "/connectivite/points/geojson": "30 requêtes/minute",
        },
    }