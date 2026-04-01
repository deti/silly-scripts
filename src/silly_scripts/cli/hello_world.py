"""CLI command to print a Hello World greeting."""

import logging

import click


logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--name",
    "-n",
    default=None,
    type=str,
    help="Name to include in the greeting.",
)
def main(name: str | None) -> None:
    """Print a Hello World greeting.

    Outputs "Hello, World!" by default, or a personalized greeting
    when the --name option is provided.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    greeting = f"Hello, {name}!" if name else "Hello, World!"

    logger.debug(f"Greeting: {greeting}")
    click.echo(greeting)


if __name__ == "__main__":
    main()  # pragma: no cover
