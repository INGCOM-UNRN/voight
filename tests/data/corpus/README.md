# Corpus sintético

Preguntas escritas para los tests, **no copiadas de ningún banco real**. Reproducen las
estructuras que aparecen en los bancos de las cátedras (árbol de categorías por carpetas,
código C y Java protegido con fullwidth y marcas `·`/`↵`, escapes de GIFT, comentarios
`// [tag:…]` y `// CAT: …::`, `$CATEGORY`, Moodle XML con comentarios, CDATA y metadatos,
preguntas rotas) para verificar invariantes en cada corrida del CI
(`tests/test_corpus.py`).

Para correr las mismas verificaciones sobre bancos reales, sin copiarlos al repositorio:

    VOIGHT_BANCOS=/ruta/al/banco1:/ruta/al/banco2 uv run pytest tests/test_corpus.py

Los bancos sólo se leen; lo que se escribe va a un directorio temporal.
