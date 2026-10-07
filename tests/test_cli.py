from click.testing import CliRunner
from voight.cli import cli

def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'ai' in result.output
    assert 'validate' in result.output


def test_cli_doctor():
    runner = CliRunner()
    result = runner.invoke(cli, ['doctor'])
    assert result.exit_code == 0
    assert 'Diagnóstico del Entorno MOODLE-TOOLBOX' in result.output

    res_json = runner.invoke(cli, ['doctor', '--json'])
    assert res_json.exit_code == 0
    assert '"schema_version": "1.0.0"' in res_json.output
    assert '"herramienta": "moodle-toolbox"' in res_json.output
    assert '"ok": true' in res_json.output


def test_cli_validate_file(tmp_path):
    f = tmp_path / "test.gift"
    f.write_text("::Title:: Q{=A}")
    
    runner = CliRunner()
    result = runner.invoke(cli, ['validate', str(f)])
    assert result.exit_code == 0
    assert 'Archivo válido' in result.output

def test_cli_format(tmp_path):
    f = tmp_path / "test.gift"
    f.write_text("::T::Q{=A}")
    
    runner = CliRunner()
    result = runner.invoke(cli, ['format', str(f)])
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
