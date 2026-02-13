from rich.console import Console
from rich.table import Table

from flakyguard.core.models import FlakyTest


class RichReporter:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def report(self, flaky_tests: list[FlakyTest]) -> None:
        if not flaky_tests:
            self.console.print("[green]No flaky tests detected! 🎉[/green]")
            return

        self.console.print("\n[bold]FlakyGuard Report[/bold]")
        self.console.print(f"Found {len(flaky_tests)} flaky test(s)\n")

        table = Table(title="Flaky Tests", show_header=True, header_style="bold cyan")
        table.add_column("Test ID", style="dim", no_wrap=False)
        table.add_column("Flakiness Rate", justify="right")
        table.add_column("Failures", justify="right")
        table.add_column("Total Runs", justify="right")
        table.add_column("Last Seen", justify="right")
        table.add_column("Quarantine", justify="center")

        for flaky in flaky_tests:
            rate_percent = f"{flaky.flakiness_rate * 100:.1f}%"

            if flaky.flakiness_rate > 0.2:
                rate_color = "red"
            elif flaky.flakiness_rate > 0.1:
                rate_color = "yellow"
            else:
                rate_color = "green"

            table.add_row(
                flaky.test_id,
                f"[{rate_color}]{rate_percent}[/{rate_color}]",
                str(flaky.failures),
                str(flaky.total_runs),
                flaky.last_seen.strftime("%Y-%m-%d %H:%M"),
                flaky.quarantine_mode.value if flaky.quarantine_mode else "-",
            )

        self.console.print(table)

        self._print_summary(flaky_tests)

    def _print_summary(self, flaky_tests: list[FlakyTest]) -> None:
        self.console.print()

        high_flaky = sum(1 for f in flaky_tests if f.flakiness_rate > 0.2)
        medium_flaky = sum(1 for f in flaky_tests if 0.1 < f.flakiness_rate <= 0.2)
        low_flaky = sum(1 for f in flaky_tests if f.flakiness_rate <= 0.1)

        self.console.print("[bold]Summary:[/bold]")
        if high_flaky > 0:
            self.console.print(f"  [red]High flakiness (>20%)[/red]: {high_flaky}")
        if medium_flaky > 0:
            self.console.print(
                f"  [yellow]Medium flakiness (10-20%)[/yellow]: {medium_flaky}"
            )
        if low_flaky > 0:
            self.console.print(f"  [green]Low flakiness (<10%)[/green]: {low_flaky}")

        self.console.print()

        most_flaky = max(flaky_tests, key=lambda f: f.flakiness_rate)
        self.console.print(
            f"[bold]Most flaky:[/bold] {most_flaky.test_id} "
            f"({most_flaky.flakiness_rate * 100:.1f}%)"
        )
