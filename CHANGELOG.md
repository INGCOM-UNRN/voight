# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/);
versiones según [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Cambiado

- **nombres anteriores retirados**: ya no se instalan los comandos `questions` ni `moodle-toolbox`, ni se leen `.questions.toml`, `~/.questions`, `QUESTIONS_DEBUG`, `QUESTIONS_PROVEEDOR`, `QUESTIONS_SIN_CACHE` ni `QUESTIONS_SIN_PROGRESO` (ahora `VOIGHT_*`); la caché pasa a `~/.cache/voight` y los hooks `questions-*` se quitaron. Se quitó `manual/plugins.md`, que describía un sistema de plugins que voight no tiene.
- **comandos**: sin duplicados. `health` absorbe `validate` y `analyze` (`health check`, predeterminado: `voight health RUTAS` funciona igual; `health validate`, `health stats`, `health similar`); `fix` absorbe `format`, `xml` y la revisión ortográfica (`fix format`, `fix xml cdata|clean-tags|rename`, `fix grammar`, antes `spellcheck`, `languagetool` y `grammar`). Los nombres anteriores quedan ocultos, avisan y se van a retirar. Los hooks de pre-commit usan los nombres nuevos.
- **format**: `--gaff` formatea el código C con gaff y lo vuelve a proteger; en los bloques ``` la última línea de código también lleva `↵`; en Moodle XML cada guarda ``` queda sola en su línea.
- **repositorio**: `INGCOM-UNRN/moodle-toolbox` pasa a `INGCOM-UNRN/voight` (GitHub redirige la URL vieja): instalación, hooks de pre-commit, acción de GitHub y documentación usan la URL nueva; el JSON de `--json` dice `"herramienta": "voight"`.
- **nombre**: la herramienta se llama **voight** (por el test Voight-Kampff): paquete `voight`, comando `voight`, configuración `.voight.toml` y `~/.voight/.env`, variables `VOIGHT_DEBUG` y `VOIGHT_PROVEEDOR`, hooks `voight-*`. Los nombres anteriores siguen funcionando: los comandos `questions` y `moodle-toolbox` avisan que se van a retirar; `.questions.toml`, `~/.questions`, `QUESTIONS_DEBUG`, `QUESTIONS_PROVEEDOR` y los hooks `questions-*` se siguen leyendo.

### Agregado

- **paridad GIFT/XML**: `validate`, `analyze stats` y `analyze similar` recorren repositorios con archivos `.gift` y `.xml` (y mezclados) sobre un parser de Moodle XML al modelo unificado; los duplicados se detectan también entre formatos.
- **health**: acepta archivos y directorios (`-r`) de ambos formatos con el mismo diagnóstico; agrega fracciones que Moodle rechaza al importar, respuesta única/múltiple, feedback por opción, cantidad de opciones y opciones repetidas, longitud relativa de las respuestas (correcta vs. distractores y sesgo a nivel banco), código sin proteger, backticks sin cerrar; `--clean-html` también en XML; `--min-opciones`, `--umbral-longitud`, `--max-items`.
- **format**: formatea Moodle XML (sangría, CDATA, comentarios) y `--correct-first` ordena por porcentaje en ambos formatos; `--fullwidth` agrega las marcas `·` (indentación) y `↵` (fin de línea), con `--sin-marcas` para omitirlas.
- **split**: divide archivos Moodle XML (un archivo por pregunta, con su categoría).
- **ai**: procesa GIFT y Moodle XML. El modelo recibe GIFT compacto (sin comentarios, categorías, estructura XML ni marcas `·`/`↵`, con el código en ASCII) y la respuesta se aplica sobre el original: en XML se conservan penalización, tags, `idnumber` y formatos. Valida cada respuesta (GIFT válido, mismo tipo y, en `improve`, misma cantidad de opciones) y si no, conserva el original. `--dry-run` muestra el prompt y el ahorro sin llamar a la API.
- **dedup**: elimina preguntas duplicadas (GIFT y XML) según un umbral configurable (`-s`, 0.95 por defecto). Sólo son duplicadas las del mismo tipo, con la misma respuesta correcta y con enunciados que también superan el umbral; conserva la más completa (o la primera) sin encadenar parecidos. Simula salvo `--aplicar`, que registra cada eliminación con las rutas completas en `--log` (TSV). `--tui` (extra `tui`, Textual) permite revisar los grupos lado a lado, con las diferencias resaltadas, y decidir cuáles eliminar.
- **ai --mode classify**: clasifica cada pregunta (GIFT o XML) con Jev de TypeSafe: nivel de Bloom (choice B1–B6) y dificultad del enunciado y de las respuestas (scores 1–5), en una solicitud por pregunta sin la retroalimentación. Escribe un comentario por pregunta (`// [bloom:B3-aplicar] [dificultad-enunciado:3.7/5] …` o `<!-- … -->`), saltea las ya clasificadas salvo `--reclasificar`, `--tags` agrega tags de Moodle y `config set-typesafe-key` guarda la clave.
- **health**: separa errores (lo que Moodle no importaría o importaría mal) de advertencias; sale con código 1 si hay errores y `--estricto` también falla con advertencias.
- **código**: un único módulo (`voight.core.codigo`) para fullwidth y marcas en GIFT y XML, con la forma normal de GIFT escapada y las variantes históricas (U+2007, U+037E) llevadas a `·` y `；`.
- **verify**: compila y ejecuta el código C y Java de las preguntas (gcc, javac) y compara la salida con la clave: avisa si la salida coincide con un distractor, si el código no compila, falla, no termina o tiene comportamiento indefinido (`--sanitizar`). `--estilo` revisa el código C con las reglas de la cátedra (ripley).
- **health**: distribución de Bloom y dificultad, blueprint categoría × Bloom y categorías sin niveles altos (de los comentarios de `classify`); señales de redacción (posición de la correcta, «todas/ninguna de las anteriores», negaciones sin resaltar, distractores débiles); campos de Moodle inconsistentes en una categoría (penalización, puntaje, numeración, mezcla); líneas `//` que GIFT descarta y bloques ``` sin lenguaje; `--csv` con una fila por pregunta y todas sus señales; `--json` y `--md` juntos escriben ambos.
- **health --tui**: interfaz de terminal para recorrer los hallazgos, ver cada pregunta en su archivo, abrirla en `$EDITOR` y aplicar los arreglos automáticos (proteger el código, etiquetar el lenguaje, limpiar HTML) a un archivo o a todos los del hallazgo.
- **ai**: modos `feedback` (completa sólo la retroalimentación que falta) y `distractors` (agrega distractores hasta `--opciones`, también cuando la correcta delata por su largo); proveedor configurable entre Gemini y Claude (`--proveedor`, `config set-provider`, `config set-anthropic-key`); estimación de tokens y costo (`--precio-entrada`, `--precio-salida`); caché de respuestas por contenido (`--sin-cache`).
- **ai --mode classify**: `--calibrar referencias.csv` mide la concordancia con una clasificación hecha por docentes (exacta, ±1 nivel, kappa, matriz, error de dificultad) sin escribir nada; `--revisar` abre una interfaz de terminal para corregir las clasificaciones con poca confianza (1–6 Bloom, +/- dificultad), que quedan como `manual` (reclasificar no las pisa) y se agregan a `--referencias`.
- **dedup**: `--confirmar-jev` confirma cada par con Jev y descarta los que no evalúan lo mismo; `--aplicar` guarda una copia completa de cada archivo modificado o borrado en `--respaldo` y `--restaurar ultimo` lo deshace sin pisar ediciones posteriores.
- **fix**: `code-lang` etiqueta el lenguaje de los bloques ``` (C o Java); `code-format` formatea el código C y Java con clang-format.
- **ui**: editor propio para cada tipo de pregunta de Moodle (numérica y calculadas con tolerancia, verdadero/falso, emparejamiento, ordenamiento, huecos por grupo; campos comunes y opciones en ensayo, cloze, arrastrar sobre imagen y emparejamiento aleatorio); al guardar se conserva lo que el editor no muestra.
- **ui**: filtro por cantidad de opciones (menos de / exactamente / más de N) en el árbol del visor web, con la cantidad de cada pregunta al lado de su nombre; la navegación recorre sólo las filtradas.
- **fix extension**: renombra `.xml` ↔ `.gift` según el contenido de cada archivo, sin pisar los existentes; `--json`.
- **format**: `--check` (sale con 1 si algo cambiaría) y `--diff`, para CI y pre-commit; `--json`.
- **moodle subir**: sube un banco a un curso de Moodle por servicio web (requiere el plugin `local_questions_importer_ws` en el sitio): convierte y unifica GIFT/XML, lo sube al área de borradores e importa con sus categorías.
- **configuración por banco**: `.questions.toml` en la raíz del repositorio con los valores por defecto de `health`, `format`, `dedup` y `ai`, y `[general] ignorar` para excluir rutas; las opciones de la línea de comandos tienen prioridad.
- **integración**: `.pre-commit-hooks.yaml` (format, health, validate) y una acción de GitHub (`uses: INGCOM-UNRN/moodle-toolbox@main`) que revisa la salud de lo que cambia en un PR, publica el informe en el resumen y en el PR, y falla ante errores.
- **cli**: `--desde <rev>` en `health`, `format`, `validate`, `verify` y `dedup` para procesar sólo lo cambiado desde una revisión git; `-n/--dry-run` en todos los comandos que escriben; alias en inglés de las opciones en castellano (`--apply`, `--keep`, `--strict`, `--since`…); barra de progreso en `health`, `classify` y `verify` cuando la salida es una terminal.

### Corregido

- **fix code-format**: `--estilo allman` (u otro estilo de llaves) no cambiaba nada: clang-format no lo acepta como estilo y cada bloque fallaba en silencio. Ahora se aplica como `BreakBeforeBraces` sobre el estilo por defecto, y un estilo inválido termina con error.
- **health / fix code-lang**: con varios bloques ``` seguidos, el cierre de uno se tomaba por la apertura de otro (y se etiquetaba con un lenguaje equivocado); «código sin cerrar» ya no marca los backticks que están dentro de un bloque.
- **parser**: el formato «palabra faltante» (`El {=gato ~perro} maúlla.`) se leía como descripción y el rango numérico `{#1..5}` perdía la respuesta; al pasar a XML el rango se escribe como valor ± tolerancia.
- **ui**: guardar un XML desde el visor rompía el emparejamiento, perdía la tolerancia de las numéricas y calculadas y convertía los `<` del código en `&lt;`.
- **formatter**: el formato GIFT ya no corta preguntas con líneas en blanco en el código, no mezcla el código del enunciado con el bloque de respuestas ni une las líneas del código de una opción; `--correct-first` mueve el feedback junto a su opción.
- **code-chars**: el mapa de caracteres había perdido el NBSP y el `;` griego (entradas `" " → " "`), cada pasada agregaba una línea en blanco antes del cierre del bloque y en XML sólo se procesaba el CDATA.
- **parser**: las opciones con `\=`, `\~` o `\#` escapados ya no se parten.
- **xml cdata**: un `<text/>` vacío hacía que el contenido se extendiera hasta el próximo `</text>` y el XML quedaba inválido.
- **tree/unify (XML)**: el código con `<` o `&` producía XML inválido al exportar.
- **validate --json**: el progreso del escaneo de directorios ya no ensucia la salida.
- **health**: salía siempre con código 0; un banco vacío mostraba 100 % de cobertura; un directorio sin `-r` fallaba sin sugerir la opción.
- **ai**: con `--output`, los archivos de carpetas distintas con el mismo nombre se pisaban; los separadores `---` cortaban preguntas que los contenían.
- **ai**: los comentarios del XML (`<!-- question: … -->`) se perdían al escribir.
- **parser**: los títulos GIFT se desescapan (`::C\\: punteros::`).
- **analyze similar**: filtrado por prefijos exacto; un repositorio de 10 mil preguntas pasa de más de una hora a segundos.
- **parser**: una pregunta sin su `}` (o con llaves sin proteger en el código) ya no se traga las preguntas siguientes: la línea en blanco corta igual si lo que sigue es otra pregunta o una `$CATEGORY`.
- **parser**: escapes en preguntas numéricas y de emparejamiento; la retroalimentación de verdadero/falso se lee en el orden de Moodle (`{T#si-responde-mal#si-responde-bien}`).
- **convert**: conserva el crédito parcial de las respuestas cortas; serializa el XML sin desescapar el documento ni borrar líneas en blanco; `xml-to-gift` pasa por el modelo unificado sin pérdidas y protege también el enunciado de los cloze (antes una línea en blanco de un `<pre>` partía la pregunta); `html-to-md` cambia el formato sólo de los campos que convierte.
- **tree export / unify**: separan las preguntas como el parser (antes partían las que tenían líneas en blanco en el código), export toma el título del parser (un comentario `// CAT: …::` lo confundía), conserva los comentarios y exporta las preguntas sin título; unify protege las barras del código respetando los escapes de GIFT (`\\0` quedaba como dos barras).
- **split**: cada archivo GIFT resultante lleva su `$CATEGORY`.
- **analyze similar / dedup**: IDF suavizado; dos preguntas idénticas en un conjunto chico ya no quedan con similitud 0.
- **validate / analyze**: salen con código 1 cuando hay hallazgos.

### Cambiado

- `GiftAnalyzer` pasa a llamarse `AnalizadorBanco` (queda el alias); el lector de unidades vive en `voight.core.lector` (reexportado desde `voight.core.ai`).
- El contrato del modelo de preguntas pasa a 1.1.0: claves `metadata` (clasificación, con su `confianza`) y `moodle` (penalización, puntaje, mezcla, numeración, respuesta única).
- `health` lee y resuelve cada archivo una sola vez (≈13 % más rápido en bancos de miles de archivos).
- Se quitan los `main()` con argparse de `parser.py` y `validator.py` y `estandarizar_nombre_pregunta`, que no usaba ningún comando.

### Mantenimiento

- **ci**: ruff exige también F401 y F841; mypy sobre `src/questions/core`.
- **tests**: corpus sintético (`tests/data/corpus`) con invariantes de formato, conversión, unificación/exportación y salud; las mismas verificaciones corren sobre bancos reales con `QUESTIONS_BANCOS=/banco1:/banco2` (sólo lectura).

## [0.2.0] - 2026-09-28

Primera versión con registro de cambios; lo anterior está en el historial de git.

### Agregado

- **cli**: cumplir el contrato de línea de comandos de LINEAMIENTOS §3.2 (N-ECO-04) (`af62923`)

### Documentación

- agregar el texto de la licencia GPL-3.0-or-later que declara pyproject (N-ECO-06) (`703388b`)
- **archivo**: quitar enlaces a scripts y documentos que ya no existen (N-ECO-17) (`ac4779e`)
- **instalacion**: instalar desde el repositorio y no con pip install questions (N-MOODLE-03) (`430349a`)
- incorporar manual de uso integral y referencia tecnica (moodle-toolbox) (`7c4a32f`)

### Mantenimiento

- **calidad**: verificar errores de Python y dependencias vulnerables (N-ECO-08, N-ECO-13) (`e2d396b`)
- **deps**: mover google-genai al extra opcional ai y actualizar dependencias vulnerables (N-MOODLE-02) (`9bb92c4`)
