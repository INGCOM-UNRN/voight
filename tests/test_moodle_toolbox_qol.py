"""Tests para las mejoras QoL de MOODLE-TOOLBOX."""

from voight.core.duplicates import detectar_preguntas_duplicadas
from voight.core.accessibility import validar_accesibilidad_imagenes
from voight.core.catalog import exportar_catalogo_markdown
from voight.core.latex_fixer import corregir_delimitadores_latex
from voight.core.simulator import simular_examen_aleatorio


def test_duplicates_detector():
    p1 = {"name": "P1", "text": "Calcule la complejidad de un bucle for anidado de N elementos."}
    p2 = {"name": "P2", "text": "Calcule la complejidad de un bucle for anidado con N elementos."}
    p3 = {"name": "P3", "text": "Explique el funcionamiento de malloc y free en C."}

    dups = detectar_preguntas_duplicadas([p1, p2, p3], umbral_similitud=0.8)
    assert len(dups) == 1
    assert dups[0]["id1"] == "P1"
    assert dups[0]["id2"] == "P2"


def test_accessibility_validator():
    html_ok = '<p>Diagrama:</p><img src="foto.png" alt="Arbol binario de busqueda">'
    html_bad = '<p>Diagrama:</p><img src="foto.png">'

    res_ok = validar_accesibilidad_imagenes(html_ok)
    res_bad = validar_accesibilidad_imagenes(html_bad)

    assert res_ok["accesible"] is True
    assert res_bad["accesible"] is False
    assert res_bad["imagenes_sin_alt"] == 1


def test_catalog_exporter():
    preguntas = [
        {"name": "P1", "type": "multichoice", "text": "Que es C?", "options": [{"text": "Lenguaje", "fraction": 100}]}
    ]
    md = exportar_catalogo_markdown(preguntas)
    assert "Catálogo de Preguntas" in md
    assert "Que es C?" in md
    assert "[✓] Lenguaje" in md


def test_latex_fixer():
    txt = "La complejidad es $$O(N^2)$$ y la constante es $c = 4$."
    corregido = corregir_delimitadores_latex(txt)
    assert r"\[ O(N^2) \]" in corregido
    assert r"\( c = 4 \)" in corregido


def test_simulator():
    banco = [{"id": i, "text": f"Pregunta {i}"} for i in range(20)]
    muestra = simular_examen_aleatorio(banco, cantidad_preguntas=5, seed=99)
    assert len(muestra) == 5
