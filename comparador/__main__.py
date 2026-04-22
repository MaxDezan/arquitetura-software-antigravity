import click

from comparador.adapters.cli.serve_cmd import serve
from comparador.adapters.cli.track_cmd import track


@click.group()
def cli() -> None:
    """Comparador de preços — crawler + storage + dashboard."""


cli.add_command(track)
cli.add_command(serve)


if __name__ == "__main__":
    cli()
