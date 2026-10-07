from voight.core.moodle_health import (
    verificar_porcentajes_opciones,
    auditar_retroalimentaciones,
    limpiar_html_y_estilos_obsoletos,
    auditar_enlaces_y_multimedia,
    convertir_windows1252_a_utf8,
    generar_reporte_salud_markdown,
)


def test_verificar_porcentajes_opciones():
    gift_valido = "::P1:: Enunciado { ~%50%Opt1 ~%50%Opt2 ~%-100%Opt3 }"
    res = verificar_porcentajes_opciones(gift_valido)
    assert res["ok"] is True

    gift_invalido = "::P2:: Enunciado { ~%60%Opt1 ~%30%Opt2 }"
    res2 = verificar_porcentajes_opciones(gift_invalido)
    assert res2["ok"] is False
    assert len(res2["preguntas_inconsistentes"]) == 1


def test_auditar_retroalimentaciones():
    gift_con_fb = "::P1:: Test { =Rta #Muy bien ~Mal #Error común }"
    assert auditar_retroalimentaciones(gift_con_fb)["sin_feedback_count"] == 0

    gift_sin_fb = "::P2:: Test { =Rta ~Mal }"
    res = auditar_retroalimentaciones(gift_sin_fb)
    assert res["sin_feedback_count"] == 1


def test_limpiar_html_y_estilos_obsoletos():
    sucio = '<center><font color="red" style="font-size:12px;">Texto</font></center>'
    limpio = limpiar_html_y_estilos_obsoletos(sucio)
    assert "<font" not in limpio
    assert "<center" not in limpio
    assert "style=" not in limpio
    assert "Texto" in limpio


def test_auditar_enlaces_y_multimedia():
    texto = "Ver https://ejemplo.com y http://inseguro.com o http://localhost:8080/img.png"
    res = auditar_enlaces_y_multimedia(texto)
    assert res["todas_validas"] is False
    assert len(res["urls_sospechosas"]) == 2


def test_convertir_windows1252_a_utf8():
    bytes_cp1252 = "Programación".encode("cp1252")
    res = convertir_windows1252_a_utf8(bytes_cp1252)
    assert res == "Programación"


def test_generar_reporte_salud_markdown(tmp_path):
    gift = "::P1:: Enunciado { =Ok #Bien ~Mal #Error }"
    arch = tmp_path / "banco.gift"
    arch.write_text(gift, encoding="utf-8")
    rep = generar_reporte_salud_markdown(arch, gift, es_xml=False)
    assert "Informe de Salud" in rep
    assert "Estadísticas Generales" in rep
