# Backend

This package contains the Movie Language Helper HTTP API. The provider-free API
is complete through analysis. Optional OpenAI Responses and SubDL v2 adapters
are disabled unless explicitly enabled in `.env.example`; an offline lexicon
analyzer is available for demos (`MLH_LEXICON_ANALYZER_ENABLED=true`).

Run it from this directory with:

```bash
uv run --locked uvicorn movie_language_helper.adapters.inbound.http.app:create_app --factory --reload
```

The API is then available at `http://127.0.0.1:8000`, with interactive API
documentation at `/docs`.
