"""Ola 14: `voight health --compilar` certifica el código C de las preguntas con daedalus."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from voight.cli import app
from voight.core.certificar import armar_fuente, certificar_banco

pytest.importorskip("daedalus.core.compiler")
pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="hace falta gcc")

BANCO = r"""::bien:: ¿Qué imprime este código?
```c
int x = 3;
printf("%d\\n", x * 2);
```
{=6 ~5 ~3}

::sin-inicializar:: ¿Qué imprime este código?
```c
int x;
printf("%d\\n", x + 1);
```
{=1 ~0 ~2}

::sintaxis:: ¿Qué imprime este código?
```c
int x = 3
printf("%d\\n", x);
```
{=3 ~0 ~4}

::a-proposito:: ¿Qué imprime este código?
```c
int x = 3
printf("%d\\n", x);
```
{=Error de compilación ~3 ~0}

::fragmento:: ¿Cuánto vale `y`?
```c
nodo_t *n = crear(3);
y = n->valor * 2;
```
{=6 ~3 ~0}

::funcion:: ¿Qué devuelve `doble(4)`?
```c
int doble(int n, int sin_usar)
{
    return n * 2;
}
```
{=8 ~4 ~16}

::conversion:: ¿Qué imprime?
```c
float f = 3.14;
printf("%.2f\\n", f);
```
{=3.14 ~3 ~0}
"""


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    ruta = tmp_path / "banco.gift"
    ruta.write_text(BANCO, encoding="utf-8")
    return ruta


def test_armar_fuente_completa_sin_chocar_con_el_snippet():
    fuente, antes, envuelto = armar_fuente('printf("%d", abs(-3));')
    assert envuelto and "#include <stdio.h>" in fuente and "#include <stdlib.h>" in fuente
    assert "#include <math.h>" not in fuente and antes == 4  # dos includes, `int main(void)` y `{`
    fuente, _, envuelto = armar_fuente("#define true 1\nint f(void)\n{\n    return true;\n}\n")
    assert not envuelto and "stdbool" not in fuente and fuente.rstrip().endswith("return 0;\n}")


def test_estados_de_cada_pregunta(banco):
    datos = certificar_banco([banco])
    titulos = {clave: {i["titulo"] for i in datos[clave]} for clave in ("rechazadas", "fragmentos", "intencionales")}
    assert titulos["rechazadas"] == {"sin-inicializar", "sintaxis", "conversion"}
    assert titulos["fragmentos"] == {"fragmento"}
    assert titulos["intencionales"] == {"a-proposito"}
    assert datos["certificadas"] == 2 and datos["con_codigo_c"] == 7  # bien y funcion (el parámetro sin usar no cuenta)
    motivos = {i["titulo"]: " ".join(i["motivos"]) for i in datos["rechazadas"]}
    assert "línea 2" in motivos["sin-inicializar"] and "-Wuninitialized" in motivos["sin-inicializar"]
    assert "-Wfloat-conversion" in motivos["conversion"]


def test_health_compilar_falla_y_lo_informa(banco):
    res = CliRunner().invoke(app, ["health", str(banco), "--compilar", "--json"])
    assert res.exit_code == 1
    datos = json.loads(res.output)
    claves = {e["clave"] for e in datos["resumen"]["errores"]}
    assert "codigo_c_rechazado" in claves
    assert {a["clave"] for a in datos["resumen"]["advertencias"]} >= {"codigo_c_fragmento"}


def test_permitir_un_warning(banco, tmp_path):
    solo = tmp_path / "conv.gift"
    solo.write_text(BANCO.split("::conversion::")[0].split("::bien::")[0] + "::conversion::" + BANCO.split("::conversion::")[1],
                    encoding="utf-8")
    assert CliRunner().invoke(app, ["health", str(solo), "--compilar"]).exit_code == 1
    res = CliRunner().invoke(app, ["health", str(solo), "--compilar", "--permitir-warning", "float-conversion"])
    assert "Código C certificado con daedalus (1 de 1)" in res.output


def test_validate_compilar(banco):
    res = CliRunner().invoke(app, ["validate", str(banco), "--compilar"])
    assert res.exit_code == 1 and "Rechazadas" in res.output
