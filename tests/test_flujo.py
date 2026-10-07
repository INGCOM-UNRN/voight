"""Flujo de trabajo: format --check/--diff, pre-commit, configuración por repositorio."""

from click.testing import CliRunner

from voight.cli import cli

runner = CliRunner()


def test_format_check_y_diff_no_escriben(tmp_path):
    sucio = tmp_path / "a.gift"
    sucio.write_text("::A::Q {=a ~b}\n", encoding="utf-8")
    limpio = tmp_path / "b.gift"
    limpio.write_text("::B::\nQ\n{\n    =a\n    ~b\n}\n", encoding="utf-8")

    res = runner.invoke(cli, ["fix", "format", str(tmp_path), "--check"])
    assert res.exit_code == 1 and "[CAMBIARÍA]" in res.output and "a.gift" in res.output
    assert sucio.read_text(encoding="utf-8") == "::A::Q {=a ~b}\n"

    res = runner.invoke(cli, ["fix", "format", str(sucio), "--diff"])
    assert res.exit_code == 0
    assert f"--- a/{sucio}" in res.output and "+    =a" in res.output
    assert sucio.read_text(encoding="utf-8") == "::A::Q {=a ~b}\n"

    assert runner.invoke(cli, ["fix", "format", str(limpio), "--check"]).exit_code == 0
    runner.invoke(cli, ["fix", "format", str(tmp_path)])
    assert runner.invoke(cli, ["fix", "format", str(tmp_path), "--check"]).exit_code == 0


def test_hooks_de_pre_commit_ejecutan_comandos_reales(tmp_path):
    import re
    import shlex
    from pathlib import Path

    texto = (Path(__file__).resolve().parents[1] / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    hooks = dict(re.findall(r"^- id: (\S+)\n(?:  .*\n)*?  entry: (.+)$", texto, re.MULTILINE))
    nombres = {"format", "health", "health-estricto", "validate"}
    # voight-* y los ids anteriores questions-* (deprecados) corren lo mismo.
    assert set(hooks) == {f"voight-{n}" for n in nombres} | {f"questions-{n}" for n in nombres}
    assert all(hooks[f"questions-{n}"] == hooks[f"voight-{n}"] for n in nombres)
    sano = tmp_path / "sano.gift"
    sano.write_text("::P::\n¿Cuál?\n{\n    =a #bien\n    ~b #no\n    ~c #no\n    ####general\n}\n", encoding="utf-8")
    roto = tmp_path / "roto.gift"
    roto.write_text("::P:: ¿Cuál? {~a ~b ~c}\n", encoding="utf-8")  # sin correcta, sin formato
    for hook, entry in hooks.items():
        argumentos = shlex.split(entry)
        assert argumentos[0] == "voight"
        assert runner.invoke(cli, argumentos[1:] + [str(sano)]).exit_code == 0, hook
        assert runner.invoke(cli, argumentos[1:] + [str(roto)]).exit_code == 1, hook


def _banco_con_config(tmp_path, config: str):
    (tmp_path / ".questions.toml").write_text(config, encoding="utf-8")
    (tmp_path / "temas").mkdir()
    (tmp_path / "borradores").mkdir()
    (tmp_path / "temas" / "a.gift").write_text("::A:: ¿Cuál? {=a #bien ~b #no ~c #no ####g}\n", encoding="utf-8")
    (tmp_path / "borradores" / "b.gift").write_text("::B:: ¿Cuál? {~a ~b}\n", encoding="utf-8")
    return tmp_path


def test_configuracion_ignorar_y_valores_por_defecto(tmp_path):
    import json

    raiz = _banco_con_config(tmp_path, '[general]\nignorar = ["borradores/**"]\n\n[health]\nmin_opciones = 5\n')
    res = runner.invoke(cli, ["health", str(raiz), "-r", "--json"])
    datos = json.loads(res.output)
    assert datos["archivos"]["total"] == 1  # borradores/ ignorado
    assert datos["opciones"]["minimo"] == 5
    # La opción explícita gana sobre el archivo.
    datos = json.loads(runner.invoke(cli, ["health", str(raiz), "-r", "--json", "--min-opciones", "2"]).output)
    assert datos["opciones"]["minimo"] == 2


def test_configuracion_de_dedup_y_format(tmp_path):
    import json

    raiz = _banco_con_config(tmp_path, '[dedup]\numbral = 0.5\n\n[format]\nfullwidth = true\nmarcas = false\n')
    (raiz / "temas" / "codigo.gift").write_text("::C:: Ver\n```c\nint a = 1;\n```\n{=a ~b}\n", encoding="utf-8")
    assert json.loads(runner.invoke(cli, ["dedup", str(raiz), "-r", "--json"]).output)["umbral"] == 0.5
    runner.invoke(cli, ["fix", "format", str(raiz / "temas" / "codigo.gift")])
    texto = (raiz / "temas" / "codigo.gift").read_text(encoding="utf-8")
    assert "int a ＝ 1；\n```" in texto  # fullwidth del archivo, sin marcas
    runner.invoke(cli, ["fix", "format", str(raiz / "temas" / "codigo.gift"), "--normal"])
    assert "int a \\= 1;" in (raiz / "temas" / "codigo.gift").read_text(encoding="utf-8")
    assert runner.invoke(cli, ["fix", "format", str(raiz), "--fullwidth", "--normal"]).exit_code == 1


def test_configuracion_contexto_de_classify(tmp_path, monkeypatch):
    import voight.core.clasificacion as cl

    monkeypatch.setattr(cl, "resolver_clave", lambda: None)
    raiz = _banco_con_config(tmp_path, '[ai]\ncontexto = "Programación 1 (C)"\n')
    res = runner.invoke(cli, ["ai", str(raiz / "temas"), "--mode", "classify", "--dry-run"])
    assert '"contexto": "Programación 1 (C)"' in res.output


def _git(raiz, *args):
    import subprocess

    subprocess.run(["git", "-C", str(raiz), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"], "HOME": str(raiz)})


def test_desde_procesa_solo_lo_cambiado(tmp_path):
    import json
    import shutil

    import pytest

    if not shutil.which("git"):
        pytest.skip("requiere git")
    raiz = tmp_path / "banco"
    raiz.mkdir()
    # Mismo texto en ambos archivos (el título cuenta en la similitud).
    pregunta = "::Punteros:: ¿Qué guarda un puntero en lenguaje C cuando se declara?\n{{=Una dirección ~Un entero ~Nada}}\n// {n}\n"
    (raiz / "viejo.gift").write_text(pregunta.format(n=1), encoding="utf-8")
    (raiz / "tocado.gift").write_text("::T:: ¿Sí? {T}\n", encoding="utf-8")
    _git(raiz, "init", "-q")
    _git(raiz, "add", ".")
    _git(raiz, "commit", "-qm", "inicio")
    (raiz / "tocado.gift").write_text("::T:: ¿Sí o no? {T}\n", encoding="utf-8")
    (raiz / "nuevo.gift").write_text(pregunta.format(n=2), encoding="utf-8")

    datos = json.loads(runner.invoke(cli, ["health", str(raiz), "--desde", "HEAD", "--json"]).output)
    assert datos["archivos"]["total"] == 2
    res = runner.invoke(cli, ["fix", "format", str(raiz), "--check", "--desde", "HEAD"])
    assert "viejo.gift" not in res.output and "nuevo.gift" in res.output
    # dedup compara contra todo el banco: el nuevo duplica al viejo, que no cambió.
    grupos = json.loads(runner.invoke(cli, ["dedup", str(raiz), "-s", "0.9", "--desde", "HEAD", "--json"]).output)["grupos"]
    assert len(grupos) == 1
    archivos = {grupos[0]["conserva"]["archivo"]} | {d["archivo"] for d in grupos[0]["elimina"]}
    assert {p.rsplit("/", 1)[-1] for p in archivos} == {"viejo.gift", "nuevo.gift"}
    datos = json.loads(runner.invoke(cli, ["health", "validate", str(raiz), "--desde", "HEAD", "--json"]).output)
    assert sorted(f["filepath"].rsplit("/", 1)[-1] for f in datos["files"]) == ["nuevo.gift", "tocado.gift"]

    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "a.gift").write_text("::A:: q {T}\n", encoding="utf-8")
    res = runner.invoke(cli, ["health", str(fuera), "--desde", "HEAD"])
    assert res.exit_code == 1 and "git" in res.output


def test_accion_de_github_declara_sus_entradas_y_salidas():
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    accion = (raiz / "action.yml").read_text(encoding="utf-8")
    entradas = re.findall(r"^  (\w+):\n    description:", accion.split("\noutputs:")[0], re.M)
    assert entradas == ["rutas", "desde", "estricto", "comentar", "version", "token"]
    assert re.findall(r"^  (\w+):\n", accion.split("\noutputs:")[1].split("\nruns:")[0], re.M) == ["ok", "errores", "advertencias"]
    assert "using: composite" in accion and "voight health" in accion
    # Las entradas llegan al script por variables de entorno, nunca interpoladas en el código.
    script = accion.split("      run: |\n", 1)[1]
    assert "${{" not in script
    ejemplo = (raiz / "docs" / "ejemplos" / "salud-banco.yml").read_text(encoding="utf-8")
    assert "uses: INGCOM-UNRN/voight@main" in ejemplo and "fetch-depth: 0" in ejemplo


def test_dry_run_en_todos_los_comandos_que_escriben(tmp_path):
    import hashlib

    from voight.core.converter import gift_to_xml

    raiz = tmp_path / "banco"
    raiz.mkdir()
    (raiz / "Mi Pregunta.gift").write_text(
        "::Título Nuevo:: ¿Qué imprime?\n```\nint main(){\nreturn 0;}\n```\n{=0 ~1 ~2}\n\n::Otra:: ¿<b>Sí</b>? {T}\n",
        encoding="utf-8")
    (raiz / "Banco XML.xml").write_text(gift_to_xml("::X:: <p style='color:red'><font>¿Sí?</font></p> {T}\n"),
                                        encoding="utf-8")

    def foto():
        return {p.relative_to(raiz): hashlib.sha256(p.read_bytes()).hexdigest() for p in raiz.rglob("*")}

    antes = foto()
    comandos = [
        ["fix", "slugify"], ["fix", "name-from-title"], ["fix", "title-from-name"], ["fix", "extension"],
        ["fix", "code-indent"], ["fix", "code-chars"],
        ["fix", "xml", "cdata"], ["fix", "xml", "clean-tags"], ["fix", "xml", "rename"],
        ["split", "--remove"], ["convert", "html-to-md"], ["health", "--clean-html"],
    ]
    for comando in comandos:
        res = runner.invoke(cli, comando + [str(raiz), "-n"])
        assert res.exception is None or isinstance(res.exception, SystemExit), (comando, res.output)
        assert foto() == antes, comando
    # Al menos los que tienen algo que hacer lo anuncian.
    assert "[SIMULACIÓN]" in runner.invoke(cli, ["fix", "slugify", str(raiz), "-n"]).output
    assert "[SIMULACIÓN]" in runner.invoke(cli, ["split", str(raiz), "-n"]).output


def test_alias_en_ingles_de_las_opciones():
    import re
    from pathlib import Path

    for comando in (["health", "check"], ["dedup"], ["ai"], ["fix", "format"], ["verify"], ["synth"], ["fix", "code-chars"]):
        ayuda = runner.invoke(cli, comando + ["--help"], terminal_width=200).output
        assert ayuda, comando
    fuentes = "".join(p.read_text(encoding="utf-8") for p in Path("src/voight/commands").glob("*.py"))
    # Toda opción larga en castellano de esta lista lleva su alias inglés al lado.
    for es, en in [("aplicar", "apply"), ("conservar", "keep"), ("estricto", "strict"), ("contexto", "context"),
                   ("reclasificar", "reclassify"), ("desde", "since"), ("sin-cache", "no-cache")]:
        assert re.findall(rf'"--{es}"(?!, "--{en}")', fuentes) == [], es


def test_alias_en_ingles_funcionan(tmp_path):
    import json

    banco = tmp_path / "b"
    banco.mkdir()
    pregunta = "::P:: ¿Qué guarda un puntero en lenguaje C cuando se declara?\n{=Una dirección ~Un entero ~Nada}\n"
    (banco / "a.gift").write_text(pregunta, encoding="utf-8")
    (banco / "b.gift").write_text(pregunta, encoding="utf-8")
    res = runner.invoke(cli, ["health", str(banco), "--strict", "--json"])
    assert res.exit_code == 1 and json.loads(res.output)["resumen"]["total_advertencias"] > 0
    res = runner.invoke(cli, ["dedup", str(banco), "-s", "0.9", "--apply", "--keep", "primera", "--log", str(tmp_path / "l"),
                                 "--backup-dir", str(tmp_path / "r")])
    assert res.exit_code == 0 and (banco / "a.gift").exists() and not (banco / "b.gift").exists()


def test_barra_de_progreso_solo_en_terminal(monkeypatch):
    import io

    from voight.core import progreso

    with progreso.barra(10, "x") as avance:  # en los tests stderr no es una terminal
        avance()
    assert not avance.activa
    salida = io.StringIO()
    monkeypatch.setattr("sys.stderr", salida)
    with progreso.barra(3, "Auditando", activa=True) as avance:
        for _ in range(3):
            avance()
    assert avance.activa
    monkeypatch.setenv("QUESTIONS_SIN_PROGRESO", "1")
    assert progreso.mostrar_progreso() is False


def test_format_json(tmp_path):
    import json

    ok, mal = tmp_path / "ok.gift", tmp_path / "mal.gift"
    ok.write_text("::A:: ¿Sí?\n{T}\n", encoding="utf-8")
    runner.invoke(cli, ["fix", "format", str(ok)])
    mal.write_text("::B::¿Sí?{T}", encoding="utf-8")
    res = runner.invoke(cli, ["fix", "format", str(tmp_path), "--check", "--json"])
    datos = json.loads(res.output)
    assert res.exit_code == 1 and datos["modo"] == "check" and datos["archivos"] == 2
    assert [p.rsplit("/", 1)[-1] for p in datos["cambian"]] == ["mal.gift"] and datos["errores"] == []
    res = runner.invoke(cli, ["fix", "format", str(tmp_path), "--json"])
    assert json.loads(res.output)["modo"] == "escritura"
    datos = json.loads(runner.invoke(cli, ["fix", "format", str(tmp_path), "--check", "--json"]).output)
    assert datos["cambian"] == []
