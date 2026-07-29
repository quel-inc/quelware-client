"""quel3-unit-config: inspect or change QuEL-3 unit configuration controls.

``show`` prints each control's current and allowed values; ``set`` applies one
or more ``KEY=VALUE`` controls. Setting needs an admin PAT, an idle unit (no
deployed instruments), and locks on every port of the unit, so it is a
maintenance-window operation. Keys are opaque -- discover them with ``show``.
"""

import asyncio
import json
from collections.abc import Coroutine
from typing import Annotated, Any

import typer
from quelware_client.client import create_quelware_client
from quelware_client.core import QuelwareClient
from quelware_core.entities.resource import ResourceCategory, ResourceId
from quelware_core.entities.unit import UnitLabel

app = typer.Typer(add_completion=False, help="Show or set QuEL-3 unit configuration.")


@app.command()
def show(
    host: Annotated[str, typer.Argument(help="manager host")],
    unit: Annotated[str, typer.Option(help="unit label")],
    port: Annotated[int, typer.Option(help="manager port")] = 50051,
    pat: Annotated[
        str | None, typer.Option(help="PAT; defaults to the configured PAT")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="emit JSON")] = False,
) -> None:
    """Show a unit's configuration controls."""

    async def _main() -> None:
        qc = create_quelware_client(host, port, pat=pat)
        async with qc:
            cfg = await qc.get_unit_configuration(UnitLabel(unit))
        if as_json:
            doc = {
                s.key: {"current": s.current_value, "allowed": list(s.allowed_values)}
                for s in cfg.supported
            }
            print(json.dumps(doc, indent=2))
        else:
            for s in cfg.supported:
                allowed = ", ".join(s.allowed_values)
                print(f"{s.key}: {s.current_value}  (allowed: {allowed})")

    _run(_main())


@app.command("set")
def set_(
    host: Annotated[str, typer.Argument(help="manager host")],
    controls: Annotated[
        list[str], typer.Argument(help="controls to apply as KEY=VALUE")
    ],
    unit: Annotated[str, typer.Option(help="unit label")],
    port: Annotated[int, typer.Option(help="manager port")] = 50051,
    pat: Annotated[
        str | None, typer.Option(help="admin PAT; defaults to the configured PAT")
    ] = None,
    discard_instruments: Annotated[
        bool,
        typer.Option(
            "--discard-instruments",
            help="discard all instruments on the unit before configuring",
        ),
    ] = False,
) -> None:
    """Set KEY=VALUE controls on a unit (admin PAT, idle unit)."""
    parsed = _parse_controls(controls)

    async def _main() -> None:
        qc = create_quelware_client(host, port, pat=pat)
        async with qc:
            port_ids = await _unit_port_ids(qc, UnitLabel(unit))
            if not port_ids:
                raise RuntimeError(f"no ports found for unit '{unit}'")
            async with qc.create_session(port_ids) as session:
                if discard_instruments:
                    for port_id in port_ids:
                        await session.discard_instruments(port_id)
                result = await session.configure_unit(UnitLabel(unit), parsed)
        for key, value in result.items():
            print(f"{key}: {value}")

    _run(_main())


def _parse_controls(pairs: list[str]) -> dict[str, str]:
    controls: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise typer.BadParameter(f"expected KEY=VALUE, got {pair!r}")
        controls[key] = value
    return controls


async def _unit_port_ids(
    client: QuelwareClient, unit_label: UnitLabel
) -> list[ResourceId]:
    prefix = f"{unit_label}:"
    return [
        r.id
        for r in await client.list_resource_infos()
        if r.category == ResourceCategory.PORT and str(r.id).startswith(prefix)
    ]


def _run(coro: Coroutine[Any, Any, None]) -> None:
    try:
        asyncio.run(coro)
    except typer.Exit:
        raise
    except Exception as exc:
        # gRPC errors carry a human message; fall back to the repr otherwise
        message = getattr(exc, "message", None) or str(exc)
        typer.echo(f"error: {message}", err=True)
        raise typer.Exit(code=1) from exc


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
