"""Regresión de MOODLE-D0601: --json versionado en analyze, health, tree y synth."""

import json
import shutil
import importlib.util

import pytest

from click.testing import CliRunner

from voight.cli import cli

runner = CliRunner()
GIFT = "$CATEGORY: Mate/Algebra\n::P1:: ¿2+2? {=4 ~3 ~5}\n"


def _json(res):
    assert res.exit_code == 0, res.output
    datos = json.loads(res.output)
    assert datos["schema_version"] == "1.0.0"
    assert datos["herramienta"] == "voight"
    return datos


def test_analyze_stats_json(tmp_path):
    (tmp_path / "a.gift").write_text(GIFT, encoding="utf-8")
    datos = _json(runner.invoke(cli, ["health", "stats", str(tmp_path), "--json"]))
    assert datos["comando"] == "analyze stats"
    assert datos["stats"]["totalQuestions"] == 1


def test_analyze_similar_json(tmp_path):
    (tmp_path / "a.gift").write_text(GIFT, encoding="utf-8")
    datos = _json(runner.invoke(cli, ["health", "similar", str(tmp_path), "--json"]))
    assert datos["pares"] == []


def test_health_json(tmp_path):
    f = tmp_path / "a.gift"
    f.write_text(GIFT, encoding="utf-8")
    datos = _json(runner.invoke(cli, ["health", str(f), "--json"]))
    assert datos["formato"] == "gift"
    assert "porcentajes" in datos and "enlaces" in datos


def test_split_y_unify_json(tmp_path):
    f = tmp_path / "cat.gift"
    f.write_text(GIFT, encoding="utf-8")
    out = tmp_path / "arbol"
    datos = _json(runner.invoke(cli, ["split", str(f), "-o", str(out), "--json"]))
    assert datos["preguntas"] == 1 and datos["comando"] == "split" and datos["simulacion"] is False
    assert (out / "Mate" / "Algebra").is_dir()
    salida = tmp_path / "rebuilt.gift"
    datos = _json(runner.invoke(cli, ["unify", str(out), "-o", str(salida), "--json"]))
    assert datos["comando"] == "unify" and datos["preguntas"] == 1


def test_split_en_lugar_json_y_dry_run(tmp_path):
    f = tmp_path / "varias.gift"
    f.write_text("::Q1:: ¿2+2? {=4 ~3}\n\n::Q2:: ¿3+3? {=6 ~5}\n", encoding="utf-8")

    res_dry = runner.invoke(cli, ["split", str(f), "--dry-run", "--json"])
    assert res_dry.exit_code == 0, res_dry.output
    assert res_dry.stderr == ""
    datos_dry = json.loads(res_dry.stdout)
    assert datos_dry["schema_version"] == "1.0.0"
    assert datos_dry["herramienta"] == "voight"
    assert datos_dry["comando"] == "split"
    assert datos_dry["archivos"] == 1
    assert datos_dry["preguntas"] == 2
    assert datos_dry["simulacion"] is True
    assert list(tmp_path.glob("*.gift")) == [f]

    res = runner.invoke(cli, ["split", str(f), "--json"])
    assert res.exit_code == 0, res.output
    assert res.stderr == ""
    datos = json.loads(res.stdout)
    assert datos["comando"] == "split"
    assert datos["archivos"] == 1
    assert datos["preguntas"] == 2
    assert datos["simulacion"] is False
    assert (tmp_path / "q1.gift").exists() and (tmp_path / "q2.gift").exists()


def test_split_exportar_dry_run_json_y_normal(tmp_path):
    f = tmp_path / "banco.gift"
    f.write_text(GIFT + "\n::P2:: ¿3+3? {=6 ~5}\n", encoding="utf-8")
    out = tmp_path / "arbol_dry"

    res_dry_json = runner.invoke(cli, ["split", str(f), "-o", str(out), "--dry-run", "--json"])
    assert res_dry_json.exit_code == 0, res_dry_json.output
    assert res_dry_json.stderr == ""
    datos = json.loads(res_dry_json.stdout)
    assert datos["schema_version"] == "1.0.0"
    assert datos["herramienta"] == "voight"
    assert datos["comando"] == "split"
    assert datos["simulacion"] is True
    assert datos["bancos"] == 1
    assert datos["directorio"] == str(out)
    assert not out.exists()

    res_dry_txt = runner.invoke(cli, ["split", str(f), "-o", str(out), "--dry-run"])
    assert res_dry_txt.exit_code == 0, res_dry_txt.output
    assert f"[SIMULACIÓN] 1 bancos se exportarían a {out}" in res_dry_txt.stdout
    assert not out.exists()


def test_split_modo_normal_y_directorio_vacio(tmp_path):
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    res_vacio = runner.invoke(cli, ["split", str(vacio), "--json"])
    assert res_vacio.exit_code == 0, res_vacio.output
    datos_vacio = json.loads(res_vacio.stdout)
    assert datos_vacio["archivos"] == 0 and datos_vacio["preguntas"] == 0 and datos_vacio["simulacion"] is False

    f = tmp_path / "normal.gift"
    f.write_text("::A1:: ¿1+1? {=2 ~3}\n\n::A2:: ¿4+4? {=8 ~7}\n", encoding="utf-8")
    res_dry = runner.invoke(cli, ["split", str(f), "--dry-run"])
    assert res_dry.exit_code == 0, res_dry.output
    assert "[SIMULACIÓN] " in res_dry.stdout
    assert "Resumen: 1 archivos divididos, 2 nuevos archivos creados." in res_dry.stdout

    res_normal = runner.invoke(cli, ["split", str(f)])
    assert res_normal.exit_code == 0, res_normal.output
    assert "✓ " in res_normal.stdout and "dividido en 2 archivos" in res_normal.stdout
    assert "Resumen: 1 archivos divididos, 2 nuevos archivos creados." in res_normal.stdout


def test_tree_export_y_collect_json_nombres_anteriores(tmp_path):
    f = tmp_path / "cat.gift"
    f.write_text(GIFT, encoding="utf-8")
    out = tmp_path / "arbol"
    res = runner.invoke(cli, ["tree", "export", str(f), "-o", str(out), "--json"])
    assert "ahora es `voight split -o DIR`" in res.stderr
    assert json.loads(res.stdout)["preguntas"] == 1
    res = runner.invoke(cli, ["tree", "collect", str(out), "-o", str(tmp_path / "rebuilt.gift"), "--json"])
    assert "ahora es `voight unify`" in res.stderr
    assert json.loads(res.stdout)["comando"] == "tree collect"


def test_synth_listar_json():
    datos = _json(runner.invoke(cli, ["synth", "--listar", "--json"]))
    assert "precedencia" in datos["plantillas"]


@pytest.mark.skipif(
    shutil.which("gcc") is None or importlib.util.find_spec("generador_examenes") is None,
    reason="Requiere gcc y generador_examenes (alucarD)"
)
def test_synth_generar_json(tmp_path):
    salida = tmp_path / "b.gift"
    datos = _json(runner.invoke(cli, ["synth", "precedencia", "-n", "1", "-o", str(salida), "--json"]))
    assert datos["cantidad"] == 1 and salida.exists()


def _init_git_repo(repo_dir):
    import os
    import subprocess

    if not shutil.which("git"):
        pytest.skip("requiere git")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ["PATH"],
        "HOME": str(repo_dir),
    }
    subprocess.run(["git", "-C", str(repo_dir), "init", "-q"], check=True, capture_output=True, env=env)
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True, capture_output=True, env=env)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-qm", "init"], check=True, capture_output=True, env=env)


def test_verify_desde_sin_ruta_posicional(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "q.gift").write_text("::Q1:: ¿2+2? {=4 ~3}\n", encoding="utf-8")
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    res_json = runner.invoke(cli, ["verify", "--desde", "HEAD", "--json"])
    assert res_json.exit_code == 0, res_json.output
    assert res_json.stderr == ""
    datos = json.loads(res_json.stdout)
    assert datos["schema_version"] == "1.0.0"
    assert datos["herramienta"] == "voight"
    assert datos["comando"] == "verify"
    assert datos["verificadas"] == 0
    assert datos["resultados"] == []

    res_txt = runner.invoke(cli, ["verify", "--desde", "HEAD"])
    assert res_txt.exit_code == 0, res_txt.output
    assert res_txt.stderr == ""
    assert "No hay archivos de preguntas cambiados desde HEAD." in res_txt.stdout

    # Con un archivo nuevo sin seguimiento, --desde HEAD sin ruta posicional debe procesarlo.
    (repo / "nuevo.gift").write_text(
        r"""::Q2:: ¿Qué imprime este código?
```c
printf("%d\\n", 6);
```
{=6 ~5}
""",
        encoding="utf-8",
    )
    res_nuevo = runner.invoke(cli, ["verify", "--desde", "HEAD", "--json"])
    assert res_nuevo.exit_code == 0, res_nuevo.output
    assert res_nuevo.stderr == ""
    datos_nuevo = json.loads(res_nuevo.stdout)
    assert datos_nuevo["comando"] == "verify"
    assert datos_nuevo["verificadas"] == 1
    assert datos_nuevo["resultados"][0]["titulo"] == "Q2"
    if shutil.which("gcc"):
        assert datos_nuevo["resultados"][0]["estado"] == "coincide"


def test_dedup_desde_sin_ruta_posicional(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    pregunta = "::Punteros:: ¿Qué guarda un puntero en lenguaje C cuando se declara?\n{=Una dirección ~Un entero ~Nada}\n"
    (repo / "a.gift").write_text(pregunta, encoding="utf-8")
    (repo / "b.gift").write_text(pregunta, encoding="utf-8")
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    # 0 archivos cambiados respecto de HEAD: no debe crashear ni reportar grupos.
    res_json = runner.invoke(cli, ["dedup", "--desde", "HEAD", "--json"])
    assert res_json.exit_code == 0, res_json.output
    assert res_json.stderr == ""
    datos = json.loads(res_json.stdout)
    assert datos["schema_version"] == "1.0.0"
    assert datos["comando"] == "dedup"
    assert datos["grupos"] == []
    assert datos["eliminadas"] == 0

    res_txt = runner.invoke(cli, ["dedup", "--desde", "HEAD"])
    assert res_txt.exit_code == 0, res_txt.output
    assert res_txt.stderr == ""
    assert "No hay duplicados" in res_txt.stdout

    # Un archivo nuevo duplicado dispara el grupo al usar dedup --desde HEAD sin ruta posicional.
    (repo / "c.gift").write_text(pregunta, encoding="utf-8")
    res_dup = runner.invoke(cli, ["dedup", "--desde", "HEAD", "--json"])
    assert res_dup.exit_code == 0, res_dup.output
    assert res_dup.stderr == ""
    datos_dup = json.loads(res_dup.stdout)
    assert len(datos_dup["grupos"]) == 1
    assert datos_dup["eliminadas"] >= 1

    res_tui_json = runner.invoke(cli, ["dedup", "--tui", "--json"])
    assert res_tui_json.exit_code == 1
    assert res_tui_json.stdout == ""
    assert "--tui y --json son excluyentes" in res_tui_json.stderr


def test_health_desde_sin_cambios_json(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "q.gift").write_text("::Q1:: ¿2+2? {=4 ~3 ~5}\n", encoding="utf-8")
    _init_git_repo(repo)
    monkeypatch.chdir(repo)

    for args in (["health", ".", "--desde", "HEAD", "--json"], ["health", "--desde", "HEAD", "--json"]):
        res = runner.invoke(cli, args)
        assert res.exit_code == 0, (args, res.output)
        assert res.stderr == ""
        datos = json.loads(res.stdout)
        assert datos["schema_version"] == "1.0.0"
        assert datos["herramienta"] == "voight"
        assert datos["comando"] == "health"
        assert datos["ok"] is True
        assert datos["archivos"]["total"] == 0
        assert datos["resumen"]["ok"] is True
        assert datos["resumen"]["total_errores"] == 0

    md_path = tmp_path / "salud.md"
    res_md = runner.invoke(cli, ["health", ".", "--desde", "HEAD", "--md", str(md_path), "--json"])
    assert res_md.exit_code == 0, res_md.output
    assert res_md.stderr == ""
    assert json.loads(res_md.stdout)["ok"] is True
    assert md_path.is_file()

    res_txt = runner.invoke(cli, ["health", "--desde", "HEAD"])
    assert res_txt.exit_code == 0, res_txt.output
    assert res_txt.stderr == ""
    assert "No hay archivos de preguntas cambiados desde HEAD." in res_txt.stdout

    res_tui_json = runner.invoke(cli, ["health", ".", "--tui", "--json"])
    assert res_tui_json.exit_code == 1
    assert res_tui_json.stdout == ""
    assert "--tui y --json son excluyentes" in res_tui_json.stderr


def test_moodle_subir_dry_run_json(tmp_path):
    f = tmp_path / "q.gift"
    f.write_text(GIFT, encoding="utf-8")
    res = runner.invoke(
        cli,
        ["moodle", "subir", str(f), "--url", "https://moodle.ejemplo.edu", "--curso", "42", "--dry-run", "--json"],
    )
    assert res.exit_code == 0, res.output
    assert res.stderr == ""
    datos = json.loads(res.stdout)
    assert datos["schema_version"] == "1.0.0"
    assert datos["herramienta"] == "voight"
    assert datos["comando"] == "moodle subir"
    assert datos["curso"] == 42
    assert datos["url"] == "https://moodle.ejemplo.edu"
    assert datos["preguntas"] == 1
    assert datos["archivos"] == 1
    assert datos["bytes"] > 0
    assert datos["simulacion"] is True


@pytest.mark.skipif(
    importlib.util.find_spec("myst_tools") is None,
    reason="Requiere extra languagetool (myst-tools)",
)
def test_spellcheck_vacio_y_md_json(tmp_path, monkeypatch):
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    res_vacio = runner.invoke(cli, ["fix", "grammar", str(vacio), "--json"])
    assert res_vacio.exit_code == 0, res_vacio.output
    assert res_vacio.stderr == ""
    datos_vacio = json.loads(res_vacio.stdout)
    assert datos_vacio["schema_version"] == "1.0.0"
    assert datos_vacio["comando"] == "fix grammar"
    assert datos_vacio["total_archivos"] == 0
    assert datos_vacio["total_issues"] == 0
    assert datos_vacio["issues"] == []

    # Con archivo real y --md + --json, escribe el Markdown y emite JSON válido en stdout.
    import urllib.request

    class _Resp:
        status = 200

        def read(self):
            return b'{"matches": []}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10.0: _Resp())
    banco = tmp_path / "ok.gift"
    banco.write_text("::P1:: Texto correcto. {=A ~B}\n", encoding="utf-8")
    md_out = tmp_path / "grammar.md"
    res_md = runner.invoke(cli, ["fix", "grammar", str(banco), "--md", str(md_out), "--json"])
    assert res_md.exit_code == 0, res_md.output
    assert res_md.stderr == ""
    assert md_out.is_file()
    datos_md = json.loads(res_md.stdout)
    assert datos_md["comando"] == "fix grammar"
    assert datos_md["total_archivos"] == 1
    assert datos_md["total_issues"] == 0


@pytest.mark.skipif(
    shutil.which("gcc") is None or importlib.util.find_spec("daedalus.core.compiler") is None,
    reason="Requiere gcc y daedalus",
)
def test_validate_compilar_json_unico_objeto(tmp_path):
    banco = tmp_path / "c.gift"
    banco.write_text(
        r"""::bien:: ¿Qué imprime?
```c
int x = 3;
printf("%d\\n", x);
```
{=3 ~0}
""",
        encoding="utf-8",
    )
    res = runner.invoke(cli, ["health", "validate", str(banco), "--compilar", "--json"])
    assert res.exit_code == 0, res.output
    assert "ahora es `voight health`" in res.stderr
    datos = json.loads(res.stdout)
    assert "files" in datos and "compilacion" in datos
    assert datos["compilacion"]["con_codigo_c"] == 1
    assert datos["compilacion"]["certificadas"] == 1


