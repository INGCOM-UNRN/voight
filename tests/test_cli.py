from click.testing import CliRunner
from voight.cli import cli

def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'ai' in result.output
    assert 'health' in result.output and 'grammar' in result.output


def test_cli_doctor():
    runner = CliRunner()
    result = runner.invoke(cli, ['doctor'])
    assert result.exit_code == 0
    assert 'Diagnóstico del Entorno VOIGHT' in result.output

    res_json = runner.invoke(cli, ['doctor', '--json'])
    assert res_json.exit_code == 0
    assert '"schema_version": "1.0.0"' in res_json.output
    assert '"herramienta": "voight"' in res_json.output
    assert '"ok": true' in res_json.output


def test_cli_validate_file(tmp_path):
    f = tmp_path / "test.gift"
    f.write_text("::Title:: Q{=A}")
    
    runner = CliRunner()
    result = runner.invoke(cli, ['health', 'validate', str(f)])
    assert result.exit_code == 0
    assert 'Archivo válido' in result.output

def test_cli_format(tmp_path):
    f = tmp_path / "test.gift"
    f.write_text("::T::Q{=A}")
    
    runner = CliRunner()
    result = runner.invoke(cli, ['fix', 'format', str(f)])
    assert result.exit_code == 0
    assert 'MODIFICADO' in result.output
    
    # Verify formatted content
    content = f.read_text()
    assert '    =A' in content

def test_cli_fix_slugify(tmp_path):
    f = tmp_path / "Test Name.gift"
    f.write_text("::T::Q{=A}")
    
    runner = CliRunner()
    result = runner.invoke(cli, ['fix', 'slugify', str(f)])
    assert result.exit_code == 0
    assert 'test_name.gift' in result.output
    assert not f.exists()
    assert (tmp_path / "test_name.gift").exists()

def test_cli_ai_prompt_file(tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Make it harder")
    gift_file = tmp_path / "test.gift"
    gift_file.write_text("::Q::Text{=A}")
    
    # We test the parsing and setup logic, but we stop before the API call 
    # (since we don't have a valid API key in tests environment usually)
    runner = CliRunner()
    # If GEMINI_API_KEY is missing, it will echo an error and return.
    result = runner.invoke(cli, ['ai', str(gift_file), '--prompt', str(prompt_file)])
    
    # It might fail due to missing API key, but we can verify it tried to load the prompt
    # or just check that it didn't crash on argument parsing.
    assert result.exit_code == 0 or "GEMINI_API_KEY" in result.output


def test_comandos_desduplicados_y_nombres_anteriores(tmp_path):
    """Una sola forma de hacer cada cosa; los nombres anteriores avisan y siguen funcionando."""
    from click.testing import CliRunner

    f = tmp_path / "ok.gift"
    f.write_text("::P:: ¿2+2? {=4 ~3 ~5}\n", encoding="utf-8")
    runner = CliRunner()
    ayuda = runner.invoke(cli, ["--help"], terminal_width=200).output
    for oculto in ("validate", "analyze", "spellcheck", "languagetool", "grammar", "format", "xml", "tree"):
        assert f"│ {oculto} " not in ayuda
    # health ES el diagnóstico: su ayuda muestra sus opciones y los subcomandos.
    ayuda = runner.invoke(cli, ["health", "--help"], terminal_width=200).output
    assert "--estricto" in ayuda and "stats" in ayuda and "similar" in ayuda
    assert " check " not in ayuda and " validate " not in ayuda
    ayuda = runner.invoke(cli, ["fix", "--help"], terminal_width=200).output
    assert "clean-html" in ayuda and "clean-tags" in ayuda and "│ xml " not in ayuda
    res = runner.invoke(cli, ["health", "check", str(f)])
    assert res.stdout == runner.invoke(cli, ["health", str(f)]).stdout
    for viejo, nuevo in ((["validate"], "health"), (["health", "validate"], "health"),
                         (["analyze", "stats"], "health stats"), (["format", "-n"], "fix format"),
                         (["xml", "cdata", "-n"], "fix format"), (["fix", "xml", "cdata", "-n"], "fix format"),
                         (["fix", "xml", "rename", "-n"], "fix name-from-title"),
                         (["fix", "xml", "clean-tags", "-n"], "fix clean-tags"),
                         (["grammar", "--help"], None)):
        if nuevo is None:  # la ayuda corta antes del aviso: alcanza con que siga existiendo
            assert runner.invoke(cli, viejo).exit_code == 0
            continue
        res = runner.invoke(cli, viejo + [str(f)])
        assert res.exit_code == 0, res.output
        assert f"ahora es `voight {nuevo}`" in res.stderr, viejo


def test_health_absorbe_los_chequeos_de_validate(tmp_path):
    import json
    from click.testing import CliRunner

    (tmp_path / "corta.xml").write_text(
        '<quiz><question type="shortanswer"><name><text>C</text></name>'
        '<questiontext format="html"><text>¿Capital de Francia?</text></questiontext></question></quiz>',
        encoding="utf-8")
    (tmp_path / "vacio.gift").write_text("// sólo un comentario\n$CATEGORY: $course$/X\n", encoding="utf-8")
    (tmp_path / "par.xml").write_text(
        '<quiz><question type="matching"><name><text>M</text></name>'
        '<questiontext format="html"><text>Uní</text></questiontext>'
        '<subquestion format="html"><text>a</text><answer><text>1</text></answer></subquestion>'
        '</question></quiz>', encoding="utf-8")
    res = CliRunner().invoke(cli, ["health", str(tmp_path), "--json"])
    assert res.exit_code == 1
    resumen = json.loads(res.stdout)["resumen"]
    errores = {e["clave"] for e in resumen["errores"]}
    advertencias = {a["clave"] for a in resumen["advertencias"]}
    assert {"pocos_pares", "sin_respuestas"} <= errores
    assert "archivos_sin_preguntas" in advertencias
    md = CliRunner().invoke(cli, ["health", str(tmp_path)]).stdout
    assert "Archivos sin preguntas" in md and "Emparejamiento con menos de 2 pares" in md


def test_fix_clean_html_y_el_aviso_de_health(tmp_path):
    from click.testing import CliRunner

    f = tmp_path / "a.gift"
    f.write_text('::P:: <font color="red">¿2+2?</font> {=4 ~3 ~5}\n', encoding="utf-8")
    runner = CliRunner()
    assert "1 archivos a modificar" in runner.invoke(cli, ["fix", "clean-html", str(f), "-n"]).output
    assert "<font" in f.read_text(encoding="utf-8")
    assert runner.invoke(cli, ["fix", "clean-html", str(f)]).exit_code == 0
    assert "<font" not in f.read_text(encoding="utf-8")
    f.write_text('::P:: <font color="red">¿2+2?</font> {=4 ~3 ~5}\n', encoding="utf-8")
    res = runner.invoke(cli, ["health", str(f), "--clean-html"])
    assert "ahora es `voight fix clean-html`" in res.stderr
    assert "<font" not in f.read_text(encoding="utf-8")
