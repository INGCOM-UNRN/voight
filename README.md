# voight — bancos de preguntas de Moodle

> 📖 **Manual de Usuario:** Para una guía exhaustiva de comandos, banderas, arquitectura y ejemplos, consultá el [Manual de Uso](MANUAL.md).

Conjunto de herramientas unificadas en Python para gestionar preguntas de Moodle en formatos XML y GIFT. Facilita la conversión, análisis, limpieza, mantenimiento y generación de preguntas mediante IA.

Todas las herramientas anteriores han sido consolidadas en un único comando raíz: `voight`.

---

## 🎯 Alcance

### Qué cubre
- Gestión integral, validación y mantenimiento de bancos de preguntas pedagógicas de Moodle.
- Conversión bidireccional fiel y sin pérdida entre formatos GIFT y Moodle XML.
- Normalización tipográfica de delimitadores de fórmulas matemáticas (LaTeX `\(...\)` y `\[...\]`) y bloques de código Markdown.
- Paridad entre GIFT y Moodle XML: formato, protección del código (fullwidth, `·` y `↵`), análisis de repositorios, duplicados y reportes de salud trabajan igual sobre ambos formatos (y sobre repositorios mixtos).
- Validación sintáctica y de completitud de metadatos de preguntas (retroalimentación, pesos porcentuales, categorías).
- Reorganización y sincronización de estructuras de directorios de categorías de preguntas.

### Qué no cubre (Límites y Delegación)
- Generación de preguntas de C con salida verificada por compilación: el comando `synth` **invoca** el motor de síntesis de `alucarD` (`generador_examenes.synthesizer`); la lógica de plantillas y su validación con GCC vive allí, no acá.
- Generación de exámenes en PDF con reconocimiento OMR (delegado a `alucard`).
- Creación de módulos de aprendizaje SCORM (delegado a `scorm-tools`).

---

## 📋 Requisitos

### Requisitos de Sistema y Entorno
- Multiplataforma. Python >= 3.10.

### Dependencias Externas y Binarios
- Para los comandos de gestión de bancos (conversión, validación, limpieza): ninguna.
- Diagramas mermaid al fusionar Moodle XML (`unify`, `tree collect`): mermaid-cli (`npm install -g @mermaid-js/mermaid-cli`).
- `synth`: `gcc` (compila y ejecuta los snippets para verificar su salida) y el paquete `alucarD`, que aporta el motor de síntesis.
- `ai`: un proveedor de IA. Con Gemini (el de siempre), el extra opcional `ai` (`uv tool install "voight[ai] @ git+https://github.com/INGCOM-UNRN/voight"`) y una `GEMINI_API_KEY` (se guarda con el comando `config`); con Claude, el mismo extra y `ANTHROPIC_API_KEY`; con un servidor local (Ollama, llama.cpp, LM Studio…) u OpenCode, nada más.
- LanguageTool (local o API remota) para la revisión ortográfica opcional.
- `voight doctor` informa cuáles de estos requisitos están presentes.

### Integración en el Ecosistema
- CLI `voight`. Subcomando `doctor`.

---

### Contrato de datos GIFT (consumidores por formato)

`scorm-tools from-gift` consume bancos GIFT producidos aquí. La frontera es el
formato, no el código, y su versión es `voight.core.gift_model.GIFT_CONTRACT_VERSION`
(hoy `1.1.0`). El contrato cubre los tipos `MC`, `TF`, `Short` y `Numerical`,
con retroalimentación por opción y global; está fijado por
`tests/test_contrato_gift.py`. Un cambio incompatible sube la versión mayor y
debe coordinarse con scorm-tools.

## 🚀 Instalación y Uso

Este proyecto utiliza [uv](https://docs.astral.sh/uv/) para la gestión de dependencias y ejecución.
Se instala siempre desde el repositorio, no por nombre desde PyPI.

```bash
# Instalación como herramienta (comando `voight`)
uv tool install git+https://github.com/INGCOM-UNRN/voight
# con el editor web opcional (`voight ui`)
uv tool install "voight[ui] @ git+https://github.com/INGCOM-UNRN/voight"
# con las interfaces de terminal (`dedup --tui`, `health --tui`, `ai --mode classify --revisar`)
uv tool install "voight[tui] @ git+https://github.com/INGCOM-UNRN/voight"
# con los SDK de Gemini y Claude para `voight ai` (un servidor local u OpenCode no los necesitan)
uv tool install "voight[ai,tui] @ git+https://github.com/INGCOM-UNRN/voight"
```

Para desarrollo:

```bash
# Clonar el repositorio
git clone https://github.com/INGCOM-UNRN/voight.git
cd voight

# Ejecutar la ayuda principal
uv run voight --help
```

## 📦 Comandos Disponibles

El CLI `voight` se organiza en subcomandos especializados:

`health` agrupa la salud del banco (`voight health RUTAS`, igual a `health check`), la validación y el análisis; y `fix`, las correcciones, el formato, la revisión ortográfica (`fix grammar`) y el mantenimiento de Moodle XML. Los nombres anteriores (`validate`, `analyze`, `spellcheck`, `languagetool`, `grammar`, `format`, `xml`) siguen funcionando con un aviso y se van a retirar.

### 1. Validación y Análisis (GIFT y XML)
- `voight health validate`: Valida archivos o directorios GIFT y Moodle XML, genera informes detallados y detecta duplicados.
- `voight health stats`: Genera estadísticas completas sobre un repositorio de preguntas (por formato, tipo, categoría y tags).
- `voight health similar`: Encuentra preguntas similares usando TF-IDF + Jaccard, también entre un `.gift` y un `.xml`; escala a miles de preguntas.
- `voight dedup`: Elimina preguntas duplicadas según un umbral de similitud configurable (`-s`, por defecto 0.95), en GIFT y XML. Sólo considera duplicadas las del mismo tipo, con la misma respuesta correcta y enunciados que también superan el umbral; conserva la más completa. Simula por defecto (`--aplicar` elimina) y registra cada eliminación con la ruta completa en `dedup.log`; guarda una copia de los originales y `--restaurar ultimo` lo deshace. `--confirmar-jev` confirma cada par con Jev y `--tui` abre una interfaz de terminal para revisar los grupos lado a lado y decidir cuáles eliminar (extra `tui`).
- `voight health`: Reporte de salud del banco (archivos o directorios, GIFT y XML): claves de corrección y porcentajes que Moodle acepta, feedback general y por opción, cantidad de opciones, longitud relativa de las respuestas, señales de redacción (posición de la correcta, «todas las anteriores», negaciones sin resaltar, distractores débiles), distribución de Bloom y dificultad con el blueprint por categoría, campos de Moodle inconsistentes, código sin proteger o sin lenguaje, enlaces y HTML obsoleto. Separa errores de advertencias y sale con código 1 si hay errores (`--estricto`: también con advertencias). `--csv` exporta una fila por pregunta y `--tui` recorre los hallazgos y aplica los arreglos automáticos.
- `voight verify`: Compila y ejecuta el código C y Java de las preguntas y avisa si la salida coincide con un distractor en lugar de la correcta, si no compila, falla o tiene comportamiento indefinido (`--sanitizar`); `--estilo` revisa el código C con las reglas de la cátedra.

### 2. Formateo y Corrección (GIFT y XML)
- `voight fix format`: Estandariza el formato visual de archivos GIFT y Moodle XML (`--correct-first` ordena las opciones por porcentaje). `--fullwidth` protege el código: símbolos fullwidth, `·` en la indentación y `↵` al final de cada línea; `--normal` lo deshace. `--gaff` formatea el código C de los bloques con gaff (estilo de la cátedra): restaura los caracteres normales, aplica `gaff fix` y lo vuelve a proteger como estaba. Ver [caracteres especiales](./docs/caracteres_especiales.md).
- `voight fix format --check` / `--diff`: Verifican el formato sin escribir (para CI y pre-commit).
- `voight fix code-lang`: Etiqueta el lenguaje (C o Java) de los bloques ``` que no lo tienen.
- `voight fix code-format`: Formatea el código C y Java con clang-format (`--estilo allman` u otro estilo de llaves aplica esas llaves sobre el estilo por defecto; un estilo que clang-format no acepta da error).
- `voight fix code-indent`: Marca la indentación del código con `·`.
- `voight fix code-chars`: Convierte los caracteres del código entre normal y fullwidth; conserva la indentación `·` y los `↵`, así que se combina con `code-indent`.
- `voight fix slugify`: Normaliza nombres de archivos (minúsculas, sin acentos).
- `voight fix name-from-title`: Renombra archivos según el título de la pregunta.
- `voight fix title-from-name`: Actualiza el título interno según el nombre del archivo.
- `voight fix extension`: Corrige la extensión según el contenido (`.xml` con GIFT adentro pasa a `.gift` y viceversa); no pisa archivos existentes.

### 3. Conversión
- `voight convert html-to-md`: Convierte etiquetas HTML a Markdown en archivos XML o GIFT.
- `voight convert xml-to-gift`: Convierte Moodle XML a GIFT (soporta categorías, selección múltiple con pesos, V/F, emparejamiento, numérica con tolerancia, ensayo y descripción).
- `voight convert gift-to-xml`: Convierte GIFT a Moodle XML con bloques CDATA correctos. Ambos conversores viajan sobre el modelo unificado de preguntas del parser PEG y son estables en round-trip.

### 4. Árboles de Directorios (absorbe moodle-reorganizer)
- `voight tree export banco.gift|xml -o dir/`: Exporta un banco monolítico a un árbol de carpetas por categoría (1 archivo por pregunta).
- `voight tree collect dir/ -o reconstruido.gift|xml`: Recolecta el árbol nuevamente a un archivo único, restaurando las categorías. En Moodle XML (también con `voight unify`), los bloques ```` ```mermaid ```` se renderizan con mermaid-cli (`mmdc`) y las imágenes con ruta relativa se incrustan en el archivo fusionado como `@@PLUGINFILE@@`; las preguntas fuente siguen siendo texto (`--no-incrustar` lo desactiva, `--diagramas svg` cambia el formato).

### 5. Editor Web (absorbe moodle-visor / mxviz)
- `voight ui [dir]`: Abre un editor web local para navegar y editar preguntas organizadas en directorios, con soporte nativo de **Moodle XML y GIFT**. Edita todos los tipos de Moodle (numérica con tolerancia, calculadas, emparejamiento, ordenamiento, huecos, arrastrar y soltar, cloze…) sin perder lo que no muestra. Filtra el árbol por cantidad de opciones (menos de / exactamente / más de N) para encontrar preguntas con pocas opciones. Requiere el extra opcional: `uv tool install "voight[ui] @ git+https://github.com/INGCOM-UNRN/voight"`.

### 6. Mantenimiento XML
- `voight fix xml cdata`: Asegura que los bloques `<text>` usen secciones CDATA.
- `voight fix xml clean-tags`: Elimina secciones de etiquetas (`<tags>`) redundantes.
- `voight fix xml rename`: Renombra archivos XML basándose en el nombre interno de la pregunta.

### 7. Inteligencia Artificial (Gemini, servidor local, OpenCode o Claude)
- `voight ai`: Mejora la calidad pedagógica (`improve`), crea variaciones (`multiply`), completa sólo la retroalimentación que falta (`feedback`) o agrega distractores donde faltan (`distractors`) en preguntas GIFT y Moodle XML, con Google Gemini, un servidor local con la API de OpenAI (Ollama, llama.cpp, LM Studio, vLLM), OpenCode o Claude (`--proveedor google|local|opencode|claude`, y `--model`). El proveedor se configura igual que en el resto del ecosistema (yutani.ia): `--proveedor`, `VOIGHT_PROVEEDOR`, `P1_IA_PROVEEDOR`, `P1_IA_MODELO`, `P1_IA_URL` o `~/.config/p1/ia.toml` (con `[herramientas.voight]` para lo propio); sin nada configurado sigue siendo Gemini, y `voight doctor` muestra cuál quedó y si está disponible. El modelo recibe GIFT compacto (sin metadatos ni marcas, código en ASCII) y la respuesta se aplica sobre el archivo original. Además, cada modo envía y recibe sólo lo que necesita: `--parte enunciado` manda y recibe sólo el enunciado, `--parte respuestas` el enunciado como contexto y las opciones sin retroalimentación (vuelven sólo las opciones), `feedback` sólo las opciones y qué retroalimentación falta (vuelve sólo esa) y `distractors` las opciones sin retroalimentación (vuelven sólo los distractores nuevos); lo devuelto se aplica sobre la pregunta original, que nunca viaja entera. Estima tokens y costo antes de llamar al modelo, guarda las respuestas en caché y `--dry-run` muestra lo que se enviaría.
- `voight ai --mode classify`: Clasifica cada pregunta con Jev (TypeSafe): nivel de Bloom (B1–B6) y dificultad (1–5) del enunciado y de las respuestas, escritos como comentario en GIFT y XML (y como tags de Moodle con `--tags`). `--calibrar` mide la concordancia con una clasificación docente y `--revisar` abre una interfaz de terminal para corregir las de poca confianza. Requiere `TYPESAFE_API_KEY`.

### 8. Moodle e integración
- `voight moodle subir`: Sube un banco a un curso de Moodle por servicio web (requiere el plugin `local_questions_importer_ws` en el sitio).
- `.voight.toml`: valores por defecto de cada comando para un banco (umbral de dedup, contexto de classify, fullwidth de format, rutas a ignorar…).
- `--desde <rev>` procesa sólo lo cambiado desde una revisión git; hooks de [pre-commit](./.pre-commit-hooks.yaml) y una acción de GitHub (`uses: INGCOM-UNRN/voight@main`, ejemplo en [docs/ejemplos/salud-banco.yml](./docs/ejemplos/salud-banco.yml)) para revisar la salud de cada PR.

## 📚 Documentación Detallada

Para más información sobre funcionalidades específicas, consulta la carpeta [docs/](./docs):

- **[Guía de Inicio Rápido](./docs/QUICK_START.md)**
- **[Validación y Análisis](./docs/README_validate_questions.md)**
- **[Mantenimiento XML](./docs/README_xml_maintenance.md)**
- **[Referencia de Caracteres Especiales](./docs/caracteres_especiales.md)**

## ✍️ Autor

[Especificar autor]

---

**Última actualización:** Octubre 2026 (calidad del banco, verificación del código e integración con los repositorios de preguntas)

<!-- p1:referencia:inicio — generado por p1-tools/scripts/readme_generado.py: no editar a mano -->

## Referencia rápida

### Requisitos

- Python ≥ 3.11 y [uv](https://docs.astral.sh/uv/getting-started/installation/).

### Opciones de `voight`

| Opción | Descripción |
|:--|:--|
| `--llm` | Muestra instrucciones generales para un LLM. |

### Comandos

| Comando | Descripción |
|:--|:--|
| `voight doctor` | Verifica el estado del entorno de VOIGHT (Python, LanguageTool, gcc y el motor de síntesis). |
| `voight ai` | Procesamiento de preguntas GIFT y Moodle XML usando IA (Gemini, un servidor local, OpenCode o Claude). |
| `voight dedup` | Elimina preguntas duplicadas según un umbral de similitud (GIFT y Moodle XML). |
| `voight verify` | Compila y ejecuta el código de las preguntas de salida y compara con las opciones (gcc, javac). |
| `voight split` | Divide archivos GIFT o Moodle XML con múltiples preguntas en archivos individuales. |
| `voight unify` | Unifica árboles o grupos de archivos de preguntas (GIFT o XML) en un único archivo. |
| `voight synth` | daedalus en belmont: sintetiza preguntas de C verificadas con GCC. |
| `voight ui` | Abre el editor web local (cerebro) sobre DIRECTORIO. |
| `voight health` | Salud del banco (`voight health RUTAS` es `health check`), validación, estadísticas y similares. |
| `voight config` | Configuración global de las herramientas. |
| `voight convert` | Comandos para convertir entre formatos. |
| `voight fix` | Comandos para corregir problemas comunes, el formato (format), la ortografía (grammar) y Moodle XML (xml). |
| `voight tree` | Organiza bancos en árboles de directorios por categoría. |
| `voight moodle` | Operaciones sobre un sitio Moodle (servicio web). |

Ayuda de cada comando: `voight <comando> -h`.

### Salida JSON

Con `--json`, estos comandos emiten el resultado como JSON por la salida estándar, para usarlo desde scripts, ripley o dredd: `voight doctor`, `voight dedup`, `voight verify`, `voight synth`. El de `doctor --json` lleva `schema_version` y `ok`.

### Códigos de salida

| Código | Significado |
|:--|:--|
| `0` | Terminó bien (en `doctor`: está todo lo requerido). |
| `1` | El comando encontró problemas (hallazgos, pruebas que fallan, un umbral que no se alcanza) o un dato no se pudo usar (un archivo ilegible, un formato inválido). |
| `2` | Error de uso: comando, opción o argumento inválido. |

<!-- p1:referencia:fin -->
