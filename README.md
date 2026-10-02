# Moodle Toolbox (Questions CLI)

> 📖 **Manual de Usuario:** Para una guía exhaustiva de comandos, banderas, arquitectura y ejemplos, consultá el [Manual de Uso](MANUAL.md).

Conjunto de herramientas unificadas en Python para gestionar preguntas de Moodle en formatos XML y GIFT. Facilita la conversión, análisis, limpieza, mantenimiento y generación de preguntas mediante IA.

Todas las herramientas anteriores han sido consolidadas en un único comando raíz: `questions`.

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
- `synth`: `gcc` (compila y ejecuta los snippets para verificar su salida) y el paquete `alucarD`, que aporta el motor de síntesis.
- `ai`: el extra opcional `ai` (`uv tool install "questions[ai] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox"`) y una `GEMINI_API_KEY` (se guarda con el comando `config`).
- LanguageTool (local o API remota) para la revisión ortográfica opcional.
- `moodle-toolbox doctor` informa cuáles de estos requisitos están presentes.

### Integración en el Ecosistema
- CLI `moodle-toolbox` (y alias `questions`). Subcomando `doctor`.

---

### Contrato de datos GIFT (consumidores por formato)

`scorm-tools from-gift` consume bancos GIFT producidos aquí. La frontera es el
formato, no el código, y su versión es `questions.core.gift_model.GIFT_CONTRACT_VERSION`
(hoy `1.1.0`). El contrato cubre los tipos `MC`, `TF`, `Short` y `Numerical`,
con retroalimentación por opción y global; está fijado por
`tests/test_contrato_gift.py`. Un cambio incompatible sube la versión mayor y
debe coordinarse con scorm-tools.

## 🚀 Instalación y Uso

Este proyecto utiliza [uv](https://docs.astral.sh/uv/) para la gestión de dependencias y ejecución.
Se instala siempre desde el repositorio: el nombre `questions` en PyPI pertenece a
otro proyecto, así que instalarlo por nombre traería un paquete ajeno.

```bash
# Instalación como herramienta (comandos `questions` y `moodle-toolbox`)
uv tool install git+https://github.com/INGCOM-UNRN/moodle-toolbox
# con el editor web opcional (`questions ui`)
uv tool install "questions[ui] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox"
# con las interfaces de terminal (`dedup --tui`, `health --tui`, `ai --mode classify --revisar`)
uv tool install "questions[tui] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox"
# con los proveedores de IA (Gemini y Claude) para `questions ai`
uv tool install "questions[ai,tui] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox"
```

Para desarrollo:

```bash
# Clonar el repositorio
git clone https://github.com/INGCOM-UNRN/moodle-toolbox.git
cd moodle-toolbox

# Ejecutar la ayuda principal
uv run questions --help
```

## 📦 Comandos Disponibles

El CLI `questions` se organiza en subcomandos especializados:

### 1. Validación y Análisis (GIFT y XML)
- `questions validate`: Valida archivos o directorios GIFT y Moodle XML, genera informes detallados y detecta duplicados.
- `questions analyze stats`: Genera estadísticas completas sobre un repositorio de preguntas (por formato, tipo, categoría y tags).
- `questions analyze similar`: Encuentra preguntas similares usando TF-IDF + Jaccard, también entre un `.gift` y un `.xml`; escala a miles de preguntas.
- `questions dedup`: Elimina preguntas duplicadas según un umbral de similitud configurable (`-s`, por defecto 0.95), en GIFT y XML. Sólo considera duplicadas las del mismo tipo, con la misma respuesta correcta y enunciados que también superan el umbral; conserva la más completa. Simula por defecto (`--aplicar` elimina) y registra cada eliminación con la ruta completa en `dedup.log`; guarda una copia de los originales y `--restaurar ultimo` lo deshace. `--confirmar-jev` confirma cada par con Jev y `--tui` abre una interfaz de terminal para revisar los grupos lado a lado y decidir cuáles eliminar (extra `tui`).
- `questions health`: Reporte de salud del banco (archivos o directorios, GIFT y XML): claves de corrección y porcentajes que Moodle acepta, feedback general y por opción, cantidad de opciones, longitud relativa de las respuestas, señales de redacción (posición de la correcta, «todas las anteriores», negaciones sin resaltar, distractores débiles), distribución de Bloom y dificultad con el blueprint por categoría, campos de Moodle inconsistentes, código sin proteger o sin lenguaje, enlaces y HTML obsoleto. Separa errores de advertencias y sale con código 1 si hay errores (`--estricto`: también con advertencias). `--csv` exporta una fila por pregunta y `--tui` recorre los hallazgos y aplica los arreglos automáticos.
- `questions verify`: Compila y ejecuta el código C y Java de las preguntas y avisa si la salida coincide con un distractor en lugar de la correcta, si no compila, falla o tiene comportamiento indefinido (`--sanitizar`); `--estilo` revisa el código C con las reglas de la cátedra.

### 2. Formateo y Corrección (GIFT y XML)
- `questions format`: Estandariza el formato visual de archivos GIFT y Moodle XML (`--correct-first` ordena las opciones por porcentaje). `--fullwidth` protege el código: símbolos fullwidth, `·` en la indentación y `↵` al final de cada línea; `--normal` lo deshace. Ver [caracteres especiales](./docs/caracteres_especiales.md).
- `questions format --check` / `--diff`: Verifican el formato sin escribir (para CI y pre-commit).
- `questions fix code-lang`: Etiqueta el lenguaje (C o Java) de los bloques ``` que no lo tienen.
- `questions fix code-format`: Formatea el código C y Java con clang-format.
- `questions fix code-indent`: Marca la indentación del código con `·`.
- `questions fix code-chars`: Convierte los caracteres del código entre normal y fullwidth.
- `questions fix slugify`: Normaliza nombres de archivos (minúsculas, sin acentos).
- `questions fix name-from-title`: Renombra archivos según el título de la pregunta.
- `questions fix title-from-name`: Actualiza el título interno según el nombre del archivo.
- `questions fix extension`: Corrige la extensión según el contenido (`.xml` con GIFT adentro pasa a `.gift` y viceversa); no pisa archivos existentes.

### 3. Conversión
- `questions convert html-to-md`: Convierte etiquetas HTML a Markdown en archivos XML o GIFT.
- `questions convert xml-to-gift`: Convierte Moodle XML a GIFT (soporta categorías, selección múltiple con pesos, V/F, emparejamiento, numérica con tolerancia, ensayo y descripción).
- `questions convert gift-to-xml`: Convierte GIFT a Moodle XML con bloques CDATA correctos. Ambos conversores viajan sobre el modelo unificado de preguntas del parser PEG y son estables en round-trip.

### 4. Árboles de Directorios (absorbe moodle-reorganizer)
- `questions tree export banco.gift|xml -o dir/`: Exporta un banco monolítico a un árbol de carpetas por categoría (1 archivo por pregunta).
- `questions tree collect dir/ -o reconstruido.gift|xml`: Recolecta el árbol nuevamente a un archivo único, restaurando las categorías.

### 5. Editor Web (absorbe moodle-visor / mxviz)
- `questions ui [dir]`: Abre un editor web local para navegar y editar preguntas organizadas en directorios, con soporte nativo de **Moodle XML y GIFT**. Edita todos los tipos de Moodle (numérica con tolerancia, calculadas, emparejamiento, ordenamiento, huecos, arrastrar y soltar, cloze…) sin perder lo que no muestra. Filtra el árbol por cantidad de opciones (menos de / exactamente / más de N) para encontrar preguntas con pocas opciones. Requiere el extra opcional: `uv tool install "questions[ui] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox"`.

### 6. Mantenimiento XML
- `questions xml cdata`: Asegura que los bloques `<text>` usen secciones CDATA.
- `questions xml clean-tags`: Elimina secciones de etiquetas (`<tags>`) redundantes.
- `questions xml rename`: Renombra archivos XML basándose en el nombre interno de la pregunta.

### 7. Inteligencia Artificial (Gemini o Claude)
- `questions ai`: Mejora la calidad pedagógica (`improve`), crea variaciones (`multiply`), completa sólo la retroalimentación que falta (`feedback`) o agrega distractores donde faltan (`distractors`) en preguntas GIFT y Moodle XML, con Google Gemini o Claude (`--proveedor`). El modelo recibe GIFT compacto (sin metadatos ni marcas, código en ASCII) y la respuesta se aplica sobre el archivo original. Estima tokens y costo antes de llamar al modelo, guarda las respuestas en caché y `--dry-run` muestra lo que se enviaría.
- `questions ai --mode classify`: Clasifica cada pregunta con Jev (TypeSafe): nivel de Bloom (B1–B6) y dificultad (1–5) del enunciado y de las respuestas, escritos como comentario en GIFT y XML (y como tags de Moodle con `--tags`). `--calibrar` mide la concordancia con una clasificación docente y `--revisar` abre una interfaz de terminal para corregir las de poca confianza. Requiere `TYPESAFE_API_KEY`.

### 8. Moodle e integración
- `questions moodle subir`: Sube un banco a un curso de Moodle por servicio web (requiere el plugin `local_questions_importer_ws` en el sitio).
- `.questions.toml`: valores por defecto de cada comando para un banco (umbral de dedup, contexto de classify, fullwidth de format, rutas a ignorar…).
- `--desde <rev>` procesa sólo lo cambiado desde una revisión git; hooks de [pre-commit](./.pre-commit-hooks.yaml) y una acción de GitHub (`uses: INGCOM-UNRN/moodle-toolbox@main`, ejemplo en [docs/ejemplos/salud-banco.yml](./docs/ejemplos/salud-banco.yml)) para revisar la salud de cada PR.

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

### Opciones de `moodle-toolbox`

| Opción | Descripción |
|:--|:--|
| `--llm` | Muestra instrucciones generales para un LLM. |

### Comandos de `moodle-toolbox`

| Comando | Descripción |
|:--|:--|
| `moodle-toolbox doctor` | Verifica el estado del entorno de MOODLE-TOOLBOX (Python, LanguageTool, gcc y el motor de síntesis). |
| `moodle-toolbox health` | Audita la salud, porcentajes de opciones, feedback y enlaces en el banco de preguntas. |
| `moodle-toolbox ai` | Procesamiento de preguntas usando IA (Gemini). |
| `moodle-toolbox validate` | Valida archivos o directorios de preguntas GIFT. |
| `moodle-toolbox format` | Formatea archivos GIFT y ajusta bloques de código. |
| `moodle-toolbox split` | Divide archivos GIFT con múltiples preguntas en archivos individuales. |
| `moodle-toolbox unify` | Unifica árboles o grupos de archivos de preguntas (GIFT o XML) en un único archivo. |
| `moodle-toolbox synth` | daedalus en belmont: sintetiza preguntas de C verificadas con GCC. |
| `moodle-toolbox ui` | Abre el editor web local (cerebro) sobre DIRECTORIO. |
| `moodle-toolbox spellcheck`, `moodle-toolbox languagetool`, `moodle-toolbox grammar` | Verifica y corrige ortografía y gramática en bancos GIFT y XML usando LanguageTool. |
| `moodle-toolbox config` | Configuración global de las herramientas. |
| `moodle-toolbox convert` | Comandos para convertir entre formatos. |
| `moodle-toolbox fix` | Comandos para corregir problemas comunes. |
| `moodle-toolbox analyze` | Análisis y estadísticas de preguntas. |
| `moodle-toolbox tree` | Organiza bancos en árboles de directorios por categoría. |
| `moodle-toolbox xml` | Herramientas para archivos XML de Moodle. |

Ayuda de cada comando: `moodle-toolbox <comando> -h`.

### Salida JSON de `moodle-toolbox`

Con `--json`, estos comandos emiten el resultado como JSON por la salida estándar, para usarlo desde scripts, ripley o dredd: `moodle-toolbox doctor`, `moodle-toolbox health`, `moodle-toolbox validate`, `moodle-toolbox synth`, `moodle-toolbox spellcheck`, `moodle-toolbox languagetool`, `moodle-toolbox grammar`. El de `doctor --json` lleva `schema_version` y `ok`.

### Códigos de salida

| Código | Significado |
|:--|:--|
| `0` | Terminó bien (en `doctor`: está todo lo requerido). |
| `1` | El comando encontró problemas (hallazgos, pruebas que fallan, un umbral que no se alcanza) o un dato no se pudo usar (un archivo ilegible, un formato inválido). |
| `2` | Error de uso: comando, opción o argumento inválido. |

<!-- p1:referencia:fin -->
