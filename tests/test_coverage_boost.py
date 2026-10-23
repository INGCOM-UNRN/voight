"""Tests adicionales para maximizar la cobertura en VOIGHT."""

from click.testing import CliRunner
from voight.cli import cli

runner = CliRunner()


def test_cli_convert_gift_to_xml(tmp_path):
    gift = tmp_path / "preguntas.gift"
    gift.write_text("::P1:: ¿2+2? {=4 ~3}\n")
    xml_out = tmp_path / "preguntas.xml"

    res = runner.invoke(cli, ["convert", "gift-to-xml", str(gift), "-o", str(xml_out)])
    assert res.exit_code == 0
    assert xml_out.exists()


def test_cli_convert_xml_to_gift(tmp_path):
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <quiz>
      <question type="multichoice">
        <name><text>P1</text></name>
        <questiontext format="html"><text>¿Cuánto es 2+2?</text></questiontext>
        <answer fraction="100"><text>4</text></answer>
        <answer fraction="0"><text>3</text></answer>
      </question>
    </quiz>
    """
    xml_f = tmp_path / "quiz.xml"
    xml_f.write_text(xml_content)
    gift_out = tmp_path / "quiz.gift"

    res = runner.invoke(cli, ["convert", "xml-to-gift", str(xml_f), "-o", str(gift_out)])
    assert res.exit_code == 0
    assert gift_out.exists()


def test_cli_split_gift(tmp_path):
    gift = tmp_path / "multi.gift"
    gift.write_text("::P1:: Texto 1 {=A}\n\n::P2:: Texto 2 {=B}\n")

    res = runner.invoke(cli, ["split", str(gift)])
    assert res.exit_code == 0


def test_cli_tree_export_and_collect(tmp_path):
    gift = tmp_path / "cat.gift"
    gift.write_text("$CATEGORY: Matematicas/Algebra\n::P1:: Texto {=A}\n")
    out_tree = tmp_path / "tree_dir"

    res_exp = runner.invoke(cli, ["tree", "export", str(gift), "-o", str(out_tree)])
    assert res_exp.exit_code == 0
    assert out_tree.is_dir()

    collected_gift = tmp_path / "rebuilt.gift"
    res_col = runner.invoke(cli, ["tree", "collect", str(out_tree), "-o", str(collected_gift)])
    assert res_col.exit_code == 0
    assert collected_gift.is_file()


def test_cli_config_commands():
    # El conftest apunta VOIGHT_CONFIG_DIR a un directorio temporal: nunca el del usuario.
    assert runner.invoke(cli, ["config", "show"]).exit_code == 0
    assert runner.invoke(cli, ["config", "unset", "gemini-key"]).exit_code == 0


def test_cli_xml_cdata(tmp_path):
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <quiz>
      <question type="multichoice">
        <name><text>P1</text></name>
        <questiontext format="html"><text>Texto simple</text></questiontext>
      </question>
    </quiz>
    """
    xml_f = tmp_path / "quiz.xml"
    xml_f.write_text(xml_content)

    res = runner.invoke(cli, ["fix", "xml", "cdata", str(xml_f)])
    assert res.exit_code == 0
