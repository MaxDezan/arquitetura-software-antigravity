import os

import click
import uvicorn


@click.command("serve")
@click.option("--db", "db_path", default="data/comparador.db",
              help="SQLite database path")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--reload", is_flag=True, help="Auto-reload on code changes (dev)")
def serve(db_path, host, port, reload):
    """Start the dashboard web server."""
    os.environ["COMPARADOR_DB"] = str(db_path)
    uvicorn.run(
        "comparador.adapters.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )
