# goofball-pipsqueak
A voice AI agent that lives goofily in your device

## CLI

```bash
uv run python -m src.main
```

## Web UI

Start the local server, then open http://127.0.0.1:8000 in your browser:

```bash
uv run pipsqueak-web
```

Or:

```bash
uv run uvicorn src.frontend.server:app --reload
```
