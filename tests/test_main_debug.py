"""Regresión de MOODLE-D0203: main() no debe esconder el traceback sin salida de escape."""

import pytest

import voight.cli as mod


def _romper(monkeypatch, error=None):
    def boom(*a, **k):
        raise error or ValueError("falla interna")
    monkeypatch.setattr(mod, "cli", boom)


def test_main_resume_el_error_y_sale_con_1(monkeypatch, capsys):
    _romper(monkeypatch)
    monkeypatch.delenv("QUESTIONS_DEBUG", raising=False)
    monkeypatch.delenv("P1_DEPURAR", raising=False)
    with pytest.raises(SystemExit) as e:
        mod.main()
    assert e.value.code == 1
    assert "falla interna" in capsys.readouterr().err


@pytest.mark.parametrize("variable", ["QUESTIONS_DEBUG", "P1_DEPURAR"])
def test_main_con_la_variable_de_depuracion_propaga_el_traceback(monkeypatch, variable):
    _romper(monkeypatch)
    monkeypatch.delenv("QUESTIONS_DEBUG", raising=False)
    monkeypatch.delenv("P1_DEPURAR", raising=False)
    monkeypatch.setenv(variable, "1")
    with pytest.raises(ValueError):
        mod.main()


def test_main_explica_en_espanol_los_errores_de_datos(monkeypatch, capsys):
    _romper(monkeypatch, FileNotFoundError(2, "No such file or directory", "banco.xml"))
    monkeypatch.delenv("QUESTIONS_DEBUG", raising=False)
    monkeypatch.delenv("P1_DEPURAR", raising=False)
    with pytest.raises(SystemExit) as e:
        mod.main()
    assert e.value.code == 1
    assert "no existe banco.xml." in capsys.readouterr().err
