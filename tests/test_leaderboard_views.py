from dataclasses import replace

from test_compare import export
from test_scoring import machine, snapshot

from hwbench.display.fmt import grouped
from hwbench.leaderboard.views import cpu_brand, cv_max, gpu_brand, iso_day, kind, ranked
from hwbench.models import Battery, GpuData, PciGpu, PowerData


def test_grouped_matches_intl_fr() -> None:
    # même sortie que Intl.NumberFormat("fr-FR") : espace fine insécable, virgule décimale
    assert grouped(1117.1, 1) == "1 117,1"
    assert grouped(261099) == "261 099"
    assert grouped(976.04) == "976"


def test_kind_follows_system_battery() -> None:
    assert kind(export(machine(1.0))) == "desktop"
    battery = Battery("BAT0", 80, "Charging", 50.0, 45.0, 10)
    laptop = replace(
        export(machine(1.0)), snapshot=replace(snapshot(), power=PowerData(batteries=[battery]))
    )
    assert kind(laptop) == "laptop"


def test_brands() -> None:
    assert cpu_brand("AuthenticAMD") == "AMD" and cpu_brand("GenuineIntel") == "Intel"
    assert cpu_brand(None) == "other" and cpu_brand("Apple") == "other"
    ex = export(machine(1.0))
    nvidia = replace(ex.snapshot, gpu=GpuData(pci_devices=[PciGpu("NVIDIA Corporation", "AD104")]))
    assert gpu_brand(replace(ex, snapshot=nvidia)) == "NVIDIA"
    ati = replace(
        ex.snapshot,
        gpu=GpuData(pci_devices=[PciGpu("Advanced Micro Devices, Inc. [AMD/ATI]", "Navi 48")]),
    )
    assert gpu_brand(replace(ex, snapshot=ati)) == "AMD"
    assert gpu_brand(replace(ex, snapshot=replace(ex.snapshot, gpu=GpuData()))) is None


def test_cv_max_ignores_zero_values() -> None:
    results = [replace(r, stdev=r.value * 0.02) for r in machine(1.0)]
    results[0] = replace(results[0], stdev=results[0].value * 0.07)
    assert round(cv_max(results), 2) == 7.0
    assert cv_max([replace(results[0], value=0.0)]) is None


def test_iso_day_keeps_unreadable_dates() -> None:
    assert iso_day("2026-10-09T19:35:02+00:00") == "2026-10-09"
    assert iso_day("jamais") == "jamais"


def test_ranked_puts_unranked_last(tmp_path) -> None:
    from hwbench.leaderboard.views import MachineView

    def view(slug: str, points: float | None) -> MachineView:
        return MachineView(
            slug,
            slug.upper(),
            "desktop",
            None,
            "other",
            None,
            None,
            {"combined": points},
            None,
            None,
            None,
            None,
            True,
            False,
            None,
        )

    order = ranked(
        [view("b", None), view("c", 500.0), view("a", None), view("d", 900.0)], "combined"
    )
    assert [(rank, v.slug) for rank, v in order] == [(1, "d"), (2, "c"), (None, "a"), (None, "b")]


def test_charts_stay_bounded_with_huge_points() -> None:
    """Un export retouché aux points démesurés (mais finis) ne fait pas exploser la génération."""
    from hwbench.leaderboard import charts

    assert charts.ticks(1312.5) == [0, 500, 1000]
    assert len(charts.ticks(1e300)) <= 6 and charts.ticks(float("inf")) == [0.0]
    assert len(charts.histogram([500.0, 1e300], 700.0, "c", "m").bands) <= charts.HIST_MAX_BINS
    points = [charts.Point(1e300, 1e300, "desktop", "x"), charts.Point(900, 800, "laptop", "y")]
    assert charts.scatter(points, "c", "x", "y", "r").count("<line") <= 14
