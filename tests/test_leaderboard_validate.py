import json
from dataclasses import replace

import pytest
from conftest import make_result
from test_compare import export
from test_scoring import REFERENCE, machine, payload

from hwbench.export import to_dict
from hwbench.leaderboard import __main__ as cli
from hwbench.leaderboard.validate import MAX_BYTES, current_versions, validate_file
from hwbench.scoring import reference_from_dict


def submit(tmp_path, data, name: str = "mon-desktop.json"):
    path = tmp_path / "results" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data)
    return path


def good_payload() -> dict:
    return to_dict(export(machine(1.2), "ASRock B850 Riptide WiFi"))


def problems(tmp_path, data, name: str = "mon-desktop.json", reference=REFERENCE) -> list[str]:
    return validate_file(submit(tmp_path, data, name), reference)


def test_valid_export_is_accepted(tmp_path) -> None:
    assert problems(tmp_path, good_payload()) == []


def test_current_versions_come_from_the_registry() -> None:
    versions = current_versions()
    assert versions["glmark2"] == "2" and versions["native-cpu-single"] == "1"


@pytest.mark.parametrize("name", ["Mon-Desktop.json", "mon desktop.json", "x.txt", "-a.json"])
def test_file_name_rules(tmp_path, name: str) -> None:
    assert any("nom de fichier invalide" in p for p in problems(tmp_path, good_payload(), name))


def test_file_must_sit_directly_in_results(tmp_path) -> None:
    path = tmp_path / "results" / "sub" / "x.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(good_payload()))
    assert any("directement dans results/" in p for p in validate_file(path, REFERENCE))


def test_identifier_in_a_value_is_reported_with_its_path(tmp_path) -> None:
    data = good_payload()
    data["results"][4]["environment"]["renderer"] = "GPU aa:bb:cc:dd:ee:ff"
    found = problems(tmp_path, data)
    assert "results[4].environment.renderer : ressemble à un(e) adresse MAC" in found


def test_identifier_key_is_refused(tmp_path) -> None:
    data = good_payload()
    data["snapshot"]["board"]["serial"] = "ABC123"
    assert "snapshot.board.serial : champ d'identifiant interdit" in problems(tmp_path, data)


def test_unknown_schema(tmp_path) -> None:
    data = good_payload() | {"schema_version": 1}
    assert any("schéma d'export 1 non pris en charge" in p for p in problems(tmp_path, data))


def test_export_without_reference(tmp_path) -> None:
    data = to_dict(export(machine(1.0), reference=None))
    assert any("exporté sans référence" in p for p in problems(tmp_path, data))


def test_other_reference(tmp_path) -> None:
    other = reference_from_dict(payload(["power_unknown"]))
    found = problems(tmp_path, to_dict(export(machine(1.0), reference=other)))
    assert any("autre référence que celle du paquet" in p for p in found)


def test_forced_reference(tmp_path) -> None:
    forced = reference_from_dict(payload(["power_unknown"]))
    data = to_dict(export(machine(1.0), reference=forced))
    assert problems(tmp_path, data, reference=forced) == [
        "noté contre une référence forcée (--force)"
    ]


def test_outdated_or_unknown_bench(tmp_path) -> None:
    results = [replace(r, version="1") if r.name == "glmark2" else r for r in machine(1.0)]
    results.append(replace(results[0], name="geekbench-cpu"))
    found = problems(tmp_path, to_dict(export(results)))
    assert any(p.startswith("glmark2 : protocole v1, la version actuelle est v2") for p in found)
    assert "geekbench-cpu : bench inconnu" in found


def _tamper(mutate) -> dict:
    data = good_payload()
    mutate(data)
    return data


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda d: d["backend_scores"][0].update(points=d["backend_scores"][0]["points"] * 2),
            "backend native-cpu-single : points incohérents",
        ),
        # échapper au contrôle en supprimant ou en annulant des entrées ne marche pas
        (lambda d: d.update(backend_scores=[]), "backend native-cpu-single : points incohérents"),
        (
            lambda d: d["backend_scores"][0].update(points=None),
            "backend native-cpu-single : points incohérents avec les résultats "
            "(non comparable au lieu de",
        ),
        (lambda d: d["categories"][2].update(points=5000.0), "catégorie gpu : points incohérents"),
        (
            lambda d: d.update(categories=[]),
            "catégorie cpu_single : points incohérents avec les résultats (absent",
        ),
        (lambda d: d["combined"].update(points=9999.0), "score combiné : points incohérents"),
        (
            lambda d: d.update(combined=None),
            "score combiné : points incohérents avec les résultats (absent au lieu",
        ),
    ],
)
def test_tampered_points_are_refused(tmp_path, mutate, expected) -> None:
    found = problems(tmp_path, _tamper(mutate))
    assert any(p.startswith(expected) for p in found), found


def test_size_and_json_errors(tmp_path) -> None:
    assert any("fichier trop gros" in p for p in problems(tmp_path, "x" * (MAX_BYTES + 1)))
    assert any("JSON invalide" in p for p in problems(tmp_path, "{nope"))


def test_cli_reports_each_file_and_fails_on_any_problem(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    good = submit(tmp_path, good_payload(), "good.json")
    bad = submit(tmp_path, good_payload() | {"schema_version": 1}, "bad.json")
    assert cli.main(["validate", str(good)]) == 0
    assert cli.main(["validate", str(good), str(bad)]) == 1
    out = capsys.readouterr()
    assert f"✓ {good}" in out.out and f"✗ {bad}" in out.out
    assert "schéma d'export 1" in out.out
    assert "1 fichier refusé sur 2" in out.err


def test_cli_annotates_problems_under_github_actions(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    bad = submit(tmp_path, good_payload() | {"schema_version": 1}, "bad.json")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert cli.main(["validate", str(bad)]) == 1
    assert "::error" not in capsys.readouterr().out
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert cli.main(["validate", str(bad)]) == 1
    errors = [line for line in capsys.readouterr().out.splitlines() if line.startswith("::error")]
    assert errors and all(line.startswith("::error title=Soumission refusée::") for line in errors)
    assert any(f"{bad} : " in line and "schéma d'export 1" in line for line in errors)


def test_annotation_stays_on_one_line() -> None:
    # un retour à la ligne venu d'un fichier soumis ne doit pas ouvrir une autre commande
    assert cli._annotation("a\n::warning::b\r%") == "a%0A::warning::b%0D%25"


def test_symlink_is_refused_without_being_read(tmp_path) -> None:
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps(good_payload()))
    link = tmp_path / "results" / "lien.json"
    link.parent.mkdir()
    link.symlink_to(secret)
    assert validate_file(link, REFERENCE) == [
        "lien symbolique refusé : soumettre un fichier ordinaire"
    ]
    dev_zero = tmp_path / "results" / "zero.json"
    dev_zero.symlink_to("/dev/zero")
    assert validate_file(dev_zero, REFERENCE) == [
        "lien symbolique refusé : soumettre un fichier ordinaire"
    ]


def test_read_is_bounded(tmp_path) -> None:
    path = submit(tmp_path, " " * (MAX_BYTES * 4))
    assert any("fichier trop gros" in p for p in validate_file(path, REFERENCE))


def test_results_dir_replaced_by_a_symlink_is_refused(tmp_path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "x.json").write_text(json.dumps(good_payload()))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "results").symlink_to(elsewhere)
    assert validate_file(repo / "results" / "x.json", REFERENCE) == [
        "doit être placé directement dans results/, sans lien symbolique"
    ]


def test_path_traversal_is_refused(tmp_path) -> None:
    submit(tmp_path, good_payload())
    sneaky = tmp_path / "results" / ".." / "mon-desktop.json"
    assert validate_file(sneaky, REFERENCE) == [
        "doit être placé directement dans results/, sans lien symbolique"
    ]


def test_duplicate_keys_cannot_hide_an_identifier(tmp_path) -> None:
    text = json.dumps(good_payload())
    # Python garderait la seconde valeur : la première (une MAC) resterait dans le fichier publié
    sneaky = text.replace('"machine": ', '"machine": "aa:bb:cc:dd:ee:ff", "machine": ', 1)
    assert json.loads(sneaky)["machine"] != "aa:bb:cc:dd:ee:ff"
    found = problems(tmp_path, sneaky)
    assert found == ["JSON invalide : clé en double : machine"]


def test_non_standard_constants_are_refused(tmp_path) -> None:
    text = json.dumps(good_payload()).replace('"stdev": 0.0', '"stdev": NaN', 1)
    assert problems(tmp_path, text) == ["JSON invalide : valeur non standard en JSON : NaN"]


@pytest.mark.parametrize("created", ["garbage", "", "2026-13-45"])
def test_invalid_export_date_is_refused(tmp_path, created) -> None:
    data = good_payload() | {"created": created}
    assert "created : date d'export invalide (ISO 8601 attendu)" in problems(tmp_path, data)


def test_export_with_memory_and_disk_is_accepted(tmp_path) -> None:
    results = machine(1.2) + [
        make_result("native-memory-single", 12_000.0),
        make_result("native-memory-multi", 30_000.0),
        make_result("sysbench-memory-single", 13_000.0, tool_version="1.0.20"),
        make_result(
            "fio-disk",
            9_000.0,
            tool_version="3.40",
            presentation="1GiB",
            details={"seq_read": 3000.0, "rand_read_4k": 200_000.0},
            detail_units={"seq_read": "MiB/s", "rand_read_4k": "IOPS"},
        ),
    ]
    assert problems(tmp_path, to_dict(export(results, "Avec disque"))) == []
