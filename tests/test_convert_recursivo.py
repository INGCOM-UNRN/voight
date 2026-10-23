"""convert html-to-md, xml-to-gift y gift-to-xml recorren directorios recursivamente."""

from pathlib import Path

from click.testing import CliRunner

from voight.cli import cli
from voight.core.parser import parse_gift

runner = CliRunner()


def _banco_gift(raiz: Path) -> Path:
    (raiz / "t1" / "sub").mkdir(parents=True)
    (raiz / "t2").mkdir()
    (raiz / ".oculto").mkdir()
    (raiz / "t1" / "a.gift").write_text("::A:: ¿2+2? {=4 ~3}\n", encoding="utf-8")
    (raiz / "t1" / "sub" / "b.gift").write_text("::B:: <b>x</b> {T}\n", encoding="utf-8")
    (raiz / "t2" / "c.gift").write_text("::C:: c {=s ~n}\n", encoding="utf-8")
    (raiz / ".oculto" / "d.gift").write_text("::D:: d {T}\n", encoding="utf-8")
    return raiz


def test_gift_to_xml_replica_el_arbol_y_vuelve(tmp_path):
    banco = _banco_gift(tmp_path / "banco")
    salida = tmp_path / "xml"

    res = runner.invoke(cli, ["convert", "gift-to-xml", str(banco), "-o", str(salida)])
    assert res.exit_code == 0, res.output
    assert sorted(p.relative_to(salida).as_posix() for p in salida.rglob("*.xml")) == [
        "t1/a.xml", "t1/sub/b.xml", "t2/c.xml"]

    # Sin -o, al lado de cada original.
    res = runner.invoke(cli, ["convert", "xml-to-gift", str(salida)])
    assert res.exit_code == 0, res.output
    vuelta = (salida / "t1" / "sub" / "b.gift").read_text(encoding="utf-8")
    assert parse_gift(vuelta)["questions"][0]["title"] == "B"


def test_no_pisa_salvo_forzar_y_no_recursive(tmp_path):
    banco = _banco_gift(tmp_path / "banco")
    assert runner.invoke(cli, ["convert", "gift-to-xml", str(banco)]).exit_code == 0
    res = runner.invoke(cli, ["convert", "gift-to-xml", str(banco)])
    assert res.exit_code == 1 and "ya existe" in res.output
    assert runner.invoke(cli, ["convert", "gift-to-xml", str(banco), "--forzar"]).exit_code == 0

    res = runner.invoke(cli, ["convert", "xml-to-gift", str(banco / "t1"), "--no-recursive",
                              "-o", str(tmp_path / "plano"), "-n"])
    assert res.exit_code == 0, res.output
    assert "1 archivos a convertir de 1" in res.output
    assert not (tmp_path / "plano").exists()


def test_un_archivo_sigue_yendo_a_stdout(tmp_path):
    banco = _banco_gift(tmp_path / "banco")
    res = runner.invoke(cli, ["convert", "gift-to-xml", str(banco / "t1" / "a.gift")])
    assert res.exit_code == 0 and "<quiz>" in res.output
    assert not (banco / "t1" / "a.xml").exists()


def test_html_to_md_es_recursivo_y_no_toca_lo_que_no_tiene_html(tmp_path):
    banco = _banco_gift(tmp_path / "banco")
    res = runner.invoke(cli, ["convert", "html-to-md", str(banco)])
    assert res.exit_code == 0, res.output
    assert "1 archivos modificados" in res.output
    assert (banco / "t1" / "sub" / "b.gift").read_text(encoding="utf-8") == "::B:: **x** {T}\n"
    assert (banco / "t1" / "a.gift").read_text(encoding="utf-8") == "::A:: ¿2+2? {=4 ~3}\n"
