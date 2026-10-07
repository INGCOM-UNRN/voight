"""Contrato GIFT que consume scorm-tools (MOODLE-D0903): tipos y claves estables."""

from voight.core.gift_model import GIFT_CONTRACT_VERSION
from voight.core.parser import parse_gift

BANCO = """
::mc:: ¿2+2? {=4#bien ~3#mal ~5}

::tf:: El cielo es azul. {T}

::corta:: Capital de Francia {=París =Paris}

::num:: ¿Pi aprox? {#3.14:0.01}
"""


def test_version_del_contrato():
    assert GIFT_CONTRACT_VERSION.split(".")[0] == "1"


def test_los_cuatro_tipos_y_sus_claves():
    res = parse_gift(BANCO)
    assert res["success"] is True
    tipos = [q["type"] for q in res["questions"]]
    assert tipos == ["MC", "TF", "Short", "Numerical"]
    for q in res["questions"]:
        assert {"type", "title", "stem"} <= set(q)
