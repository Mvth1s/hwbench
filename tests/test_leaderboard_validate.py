import json
from dataclasses import replace

import pytest
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


def test_tampered_points_are_refused(tmp_path) -> None:
    data = good_payload()
    data["backend_scores"][0]["points"] *= 2
    assert any("points incohérents avec les résultats" in p for p in problems(tmp_path, data))


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
    assert "1 fichier(s) refusé(s) sur 2" in out.err


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
