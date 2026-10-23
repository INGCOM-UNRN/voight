# Manual de Uso y Referencia Técnica: voight

> **VOIGHT** — Herramientas para gestionar preguntas de Moodle (GIFT, XML)
> **Versión:** `0.1.0` · **CLI principal:** `voight` · **Plugin Ripley:** `voight`

---

## 1. Arquitectura y Propósito Pedagógico

`voight` forma parte del ecosistema de herramientas de la cátedra de Programación 1 (UNRN). Su objetivo central es resolver de forma modular, determinista y automatizada las tareas asociadas a su dominio específico dentro del ciclo de desarrollo, evaluación y aprendizaje de software en C.

### Alcance Funcional (Qué cubre)
- Gestión integral, validación y mantenimiento de bancos de preguntas pedagógicas de Moodle.
- Conversión bidireccional fiel y sin pérdida entre formatos GIFT y Moodle XML.
- Normalización tipográfica de delimitadores de fórmulas matemáticas (LaTeX `\(...\)` y `\[...\]`) y bloques de código Markdown.
- Validación sintáctica y de completitud de metadatos de preguntas (retroalimentación, pesos porcentuales, categorías).
- Reorganización y sincronización de estructuras de directorios de categorías de preguntas.

### Límites de Responsabilidad y Delegación (Qué no cubre)
- Generación de preguntas de C con salida verificada por compilación: el comando `synth` **invoca** el motor de síntesis de `alucarD` (`generador_examenes.synthesizer`); la lógica de plantillas y su validación con GCC vive allí, no acá.
- Generación de exámenes en PDF con reconocimiento OMR (delegado a `alucard`).
- Creación de módulos de aprendizaje SCORM (delegado a `scorm-tools`).

### Principios de Diseño
- **Enfoque Pedagógico:** Diagnósticos y mensajes en español rioplatense orientados a facilitar la comprensión de errores conceptuales.
- **Salida Estructurada Dual:** Soporte nativo para visualización enriquecida en terminal (Rich) y salida parseable para orquestadores (`--json`).
- **Integración Contractual:** Capacidad de emitir secciones de reporte para `dredd` (`dredd-section`) y actuar como satélite orquestado por `ripley`.
- **Idempotencia y Robustez:** Validación de precondiciones y comandos de autodiagnóstico (`doctor`) para verificación del entorno.

---

## 2. Instalación y Requisitos

### Requisitos del Sistema
- **Python:** `>= 3.10` (recomendado Python 3.11 o 3.12).
- **Gestor de paquetes:** [`uv`](https://github.com/astral-sh/uv) (entorno estándar de cátedra).
- **Toolchain C (si aplica):** GCC / Clang, Make, GDB y bibliotecas estándar de desarrollo.

### Instalación en el Entorno de Usuario
Para instalar la herramienta de forma global y aislada en el sistema mediante `uv tool`:
```bash
uv tool install "voight[ai,ui,languagetool] @ git+https://github.com/INGCOM-UNRN/voight"
```

### Verificación de Instalación
Ejecutá el comando `doctor` para constatar que todas las dependencias y binarios requeridos estén presentes y operativos:
```bash
voight doctor
```

---

## 3. Guía Integral de Comandos (CLI)

| Comando | Descripción Breve |
| :--- | :--- |
| [`voight doctor`](#doctor) | Verifica el estado del entorno de VOIGHT (Python, LanguageTool, gcc y el motor de síntesis). |
| [`voight health`](#health) | Audita la salud del banco: claves de corrección, feedback, opciones, redacción, Bloom y dificultad, código y enlaces; con TUI para arreglar. |
| [`voight ai`](#ai) | Procesa preguntas GIFT y Moodle XML con IA (Gemini o Claude) y las clasifica por Bloom y dificultad con Jev. |
| [`voight verify`](#verify) | Compila y ejecuta el código C y Java de las preguntas y verifica que la clave coincida con la salida. |
| [`voight health validate`](#validate) | Valida archivos o directorios de preguntas GIFT y Moodle XML. |
| `voight health stats` · `voight health similar` | Estadísticas del repositorio y preguntas similares o duplicadas (GIFT y XML, también entre formatos). |
| [`voight dedup`](#dedup) | Elimina preguntas duplicadas según un umbral de similitud (GIFT y Moodle XML), con log y revisión en TUI. |
| [`voight fix format`](#format) | Formatea archivos GIFT y Moodle XML y transforma el código (fullwidth, · y ↵); `--check` para CI; `--gaff` da al código C el estilo de la cátedra. |
| [`voight fix format-init`](#format) | Crea la plantilla `[format]` del `.voight.toml` en la raíz del árbol de preguntas. |
| `voight fix xml cdata` · `clean-tags` · `rename` | Mantenimiento de archivos Moodle XML. |
| [`voight fix`](#fix) | Correcciones puntuales: lenguaje y formato del código, caracteres, nombres de archivo y títulos. |
| [`voight moodle subir`](#moodle-subir) | Sube un banco a un curso de Moodle por servicio web. |
| [`voight split`](#split) | Divide archivos GIFT o Moodle XML con múltiples preguntas en archivos individuales. |
| [`voight unify`](#unify) | Unifica árboles o grupos de archivos de preguntas (GIFT o XML) en un único archivo. |
| [`voight synth`](#synth) | daedalus en belmont: sintetiza preguntas de C verificadas con GCC. |
| [`voight ui`](#ui) | Abre el editor web local (cerebro) sobre DIRECTORIO. |
| [`voight fix grammar`](#grammar) | Verifica y corrige ortografía y gramática en bancos GIFT y XML usando LanguageTool. |

`voight health RUTAS` es lo mismo que `voight health check RUTAS`. Los nombres anteriores siguen funcionando, con un aviso, y se van a retirar: `validate` → `health validate`, `analyze stats|similar` → `health stats|similar`, `spellcheck`, `languagetool` y `grammar` → `fix grammar`, `format` → `fix format`, `xml …` → `fix xml …`.

Todas las opciones largas en castellano aceptan también su nombre en inglés (`--aplicar`/`--apply`, `--conservar`/`--keep`, `--estricto`/`--strict`, `--desde`/`--since`, `--contexto`/`--context`…). Los comandos que escriben aceptan `-n/--dry-run`, y `health`, `health validate`, `fix format`, `verify` y `dedup` aceptan `--desde <rev>` para procesar sólo los archivos cambiados desde una revisión git (más los nuevos sin seguimiento). Los valores por defecto de cada banco pueden fijarse en un [`.voight.toml`](#configuracion-por-banco).

### `voight doctor`

Verifica el estado del entorno de VOIGHT (Python, LanguageTool, gcc y el motor de síntesis).

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `<class 'bool'>` | `False` | Emitir diagnóstico en formato JSON estructurado. |

#### Ejemplo de Invocación
```bash
voight doctor
```

### `voight health`

Audita la salud del banco sobre el modelo unificado de preguntas: **da el mismo diagnóstico para GIFT y Moodle XML** y acepta archivos sueltos, directorios o una mezcla de ambos formatos.

- **Claves de corrección:** respuesta única con una opción de 100 % (las demás pueden dar crédito parcial), respuesta múltiple cuyos porcentajes positivos suman 100, respuesta corta y numérica con alguna opción de 100 %, y porcentajes que Moodle acepta al importar (`%33.33%` se rechaza: hace falta `%33.33333%`).
- **Retroalimentación:** cobertura del feedback general y por opción; preguntas sin ningún feedback y preguntas con feedback en sólo algunas opciones.
- **Cantidad de opciones:** distribución en opción múltiple, preguntas con menos de `--min-opciones` (emparejamiento: menos de 3 pares) y opciones repetidas.
- **Longitud relativa de las respuestas:** preguntas donde la correcta es `--umbral-longitud` veces más larga (o más corta) que los distractores, y cuántas veces la correcta es la opción más larga frente a lo esperable por azar.
- **Código:** secciones sin proteger para GIFT, marcas no canónicas (U+2007, NBSP, `;` griego) y líneas en blanco sin `↵`; backticks sin cerrar.
- **Enlaces y HTML:** URLs `http://` o locales y etiquetas obsoletas (`<font>`, `<center>`, `style=`).
- **Redacción (opción múltiple):** en qué posición queda la correcta (y cuántas veces es la primera frente a lo esperable), opciones como «todas/ninguna de las anteriores» (se rompen al mezclar), negaciones sin resaltar en el enunciado («excepto», «incorrecta», «no es»…) y distractores mucho más cortos que la correcta.
- **Bloom y dificultad:** con los comentarios que escribe `ai --mode classify`, la distribución de Bloom, las dificultades medias, el blueprint categoría × Bloom y las categorías sin preguntas de niveles altos (analizar, evaluar, crear).
- **Metadatos de Moodle (XML):** penalización, puntaje, numeración o mezcla de opciones distintos dentro de una misma categoría y tipo.
- **Código:** además, líneas `//` dentro del código (GIFT y Moodle las descartan como comentario) y bloques ``` sin etiqueta de lenguaje.

`--csv` exporta una fila por pregunta con todas sus señales (archivo, categoría, tipo, opciones y correctas, feedback, razón de longitud, fracciones inválidas, código sin cerrar, señales de redacción, Bloom y dificultades), para filtrar el banco en una planilla. Con `--json` y `--md` juntos se escriben ambos en una sola auditoría.

`--tui` abre una interfaz de terminal (extra `tui`) con tres paneles: los errores y advertencias (🔧 marca los que tienen arreglo automático), las preguntas o archivos afectados y el archivo con la pregunta resaltada. `f` aplica el arreglo al archivo seleccionado y `F` a todos los del hallazgo (con confirmación): proteger el código con fullwidth y marcas, etiquetar el lenguaje de los bloques ``` o limpiar el HTML obsoleto. `e` abre el archivo en `$EDITOR` en la línea de la pregunta, `r` vuelve a auditar y `q` sale informando qué se arregló.

El informe empieza con un **resultado** que separa errores de advertencias. Son errores lo que Moodle no importaría o importaría mal: archivos ilegibles, porcentajes rechazados o que no suman 100, preguntas sin respuesta correcta o sin enunciado y, en GIFT, código que el formato interpreta o con líneas en blanco. El resto (feedback, opciones, longitud, enlaces, HTML) son advertencias. **Sale con código 1 si hay errores** (con `--estricto`, también ante advertencias); el JSON lleva `ok` y `resumen`.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `rutas` | `List[pathlib.Path]` | Archivos `.gift`/`.xml` o directorios. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `-r`, `--recursive` | `<class 'bool'>` | `False` | Buscar recursivamente en los directorios. |
| `--md` | `Optional[pathlib.Path]` | `None` | Exportar reporte en Markdown. |
| `--clean-html` | `<class 'bool'>` | `False` | Limpiar etiquetas HTML obsoletas y estilos inline (GIFT y XML). |
| `--min-opciones` | `<class 'int'>` | `3` | Mínimo de opciones esperado en opción múltiple. |
| `--umbral-longitud` | `<class 'float'>` | `1.5` | Razón de largo correcta/distractores a partir de la cual se advierte. |
| `--max-items` | `<class 'int'>` | `50` | Máximo de preguntas listadas por sección (0: todas). |
| `--estricto` | `<class 'bool'>` | `False` | Salir con código 1 también ante advertencias. |
| `--csv` | `Optional[pathlib.Path]` | `None` | Exportar una fila por pregunta con todas sus señales. |
| `--tui` | `<class 'bool'>` | `False` | Recorrer los hallazgos y aplicar los arreglos en una interfaz de terminal. |
| `--desde` | `Optional[str]` | `None` | Sólo los archivos cambiados desde esta revisión git. |
| `-n`, `--dry-run` | `<class 'bool'>` | `False` | Con `--clean-html`: mostrar qué se limpiaría sin escribir. |
| `--json` | `<class 'bool'>` | `False` | Emite el diagnóstico como JSON versionado (con `--md`, escribe también el informe). |

#### Ejemplo de Invocación
```bash
voight health banco.xml
voight health preguntas/ -r --md salud.md
voight health preguntas/ -r --csv preguntas.csv
voight health preguntas/ -r --desde origin/main --estricto
voight health preguntas/ -r --tui
```

### `voight ai`

Procesa preguntas GIFT y Moodle XML con un LLM: Gemini (por defecto) o Claude (`--proveedor claude`, o `config set-provider`; la clave con `config set-anthropic-key` o `ANTHROPIC_API_KEY`). Modos:

- `improve`: mejora redacción y precisión sin cambiar el tipo ni la cantidad de opciones.
- `multiply`: crea variaciones que evalúan lo mismo.
- `transform`: aplica un `--prompt` propio.
- `feedback`: completa **sólo** la retroalimentación que falta (general y por opción); el resto de la pregunta no se toca.
- `distractors`: agrega distractores hasta `--opciones` (4 por defecto) en las preguntas que tienen menos o donde la correcta delata por su largo; no modifica los existentes.
- `classify`: Bloom y dificultad con Jev (ver más abajo).

Antes de llamar al modelo informa una estimación de tokens (y de costo, con `--precio-entrada` y `--precio-salida` en USD por millón de tokens); `--dry-run` sólo muestra eso y la primera solicitud. Las respuestas se guardan en una caché por contenido (`$XDG_CACHE_HOME/voight`): volver a correr sobre preguntas que no cambiaron no gasta tokens (`--sin-cache` la desactiva).

El modelo siempre recibe **GIFT compacto**, el formato más corto y el que los LLM conocen mejor:

- No se envían comentarios (`// [tag:…]`, `[id:…]`), `$CATEGORY` ni la estructura del XML; se conservan aparte.
- El código va en ASCII normal y sin las marcas `·`/`↵` (los símbolos fullwidth cuestan más tokens); la respuesta se vuelve a proteger y cada archivo recupera la convención de su original.
- En XML la respuesta se aplica sobre el `<question>` original: se conservan penalización, puntaje, numeración, tags, `idnumber` y formatos. Las variaciones de `multiply` no repiten el `idnumber`.
- Una respuesta que no es GIFT válido, que cambia el tipo o (en `improve`) la cantidad de opciones o de correctas deja la pregunta original.
- Con `--output`, la salida conserva la estructura de directorios.

En los bancos de la cátedra, lo enviado es un 47 % más corto que los archivos XML y un 7 % más corto que los GIFT.

#### Clasificación con Jev (`--mode classify`)

Usa **Jev** ([TypeSafe](https://docs.typesafe.ai), modelo *System One*) en lugar de Gemini: por pregunta, una sola solicitud con tres juicios tipados que corren en paralelo.

| Juicio | Tipo | Resultado |
| :-- | :-- | :-- |
| Nivel de Bloom | `choice` entre los 6 niveles de la taxonomía revisada | `B1-recordar` … `B6-crear` |
| Dificultad del enunciado | `score` de 5 niveles descritos como situaciones | 1–5 (con un decimal) |
| Dificultad de las respuestas (cuán difícil es distinguir la correcta de los distractores) | `score` de 5 niveles; sólo opción múltiple y emparejamiento | 1–5 |

Jev recibe la pregunta como JSON (contexto del curso, tipo, enunciado y opciones con la correcta marcada; el código en ASCII y **sin** la retroalimentación, que revelaría la respuesta). El resultado se agrega como comentario: en GIFT una línea antes del título y en XML un `<!-- … -->` antes del `<question>`:

```text
// [bloom:B3-aplicar] [dificultad-enunciado:3.7/5] [dificultad-respuestas:3.7/5] [clasificacion:jev-1.13.0 confianza=1,0.74,0.71]
```

Las preguntas ya clasificadas se saltean (`--reclasificar` las reemplaza, sin duplicar la línea); `--tags` agrega además los tags de Moodle `bloom:…`, `dificultad-enunciado:N` y `dificultad-respuestas:N`, que se conservan al importar y permiten filtrar el banco. Al terminar informa la distribución de Bloom, las dificultades medias, cuántas preguntas tuvieron baja confianza y los tokens usados (≈1300 de entrada por pregunta). La clave `TYPESAFE_API_KEY` se toma del entorno, de `.env.local`, de `~/.env` o de `voight config set-typesafe-key`.

**Calibración.** `--calibrar referencias.csv` (columnas `archivo,titulo,bloom[,dificultad_enunciado,dificultad_respuestas]`, hecho por docentes) clasifica esas preguntas con Jev sin escribir nada y mide la concordancia: acuerdo exacto y a ±1 nivel de Bloom, kappa de Cohen, matriz de confusión y error medio de las dificultades. Sirve para ajustar `--contexto` antes de clasificar todo el banco.

**Revisión.** `--revisar` abre una interfaz de terminal (extra `tui`) con las preguntas clasificadas con alguna confianza menor que `--umbral-revision` (0.6), de la menos a la más confiable, junto a la escala de Bloom. `1`–`6` elige el nivel, `+`/`-` ajusta la dificultad del enunciado, `a` acepta la del modelo, `u` deshace y `s` guarda: cada corrección reemplaza el comentario con clasificador `manual` (que `--reclasificar` no pisa) y, con `--referencias`, se agrega al CSV de calibración.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--inputs` | `Optional[List[pathlib.Path]]` | `None` | Archivos .gift/.xml o directorios. |
| `--llm` | `<class 'bool'>` | `False` | Muestra instrucciones para un LLM sobre este comando. |
| `--mode` | `<class 'str'>` | `improve` | Modo: improve (mejorar), multiply (variaciones), transform (usar prompt personalizado) o classify (Bloom y dificultad con Jev). |
| `--prompt` | `Optional[str]` | `None` | Prompt personalizado o ruta a un archivo .txt con el prompt. |
| `--output` | `Optional[pathlib.Path]` | `None` | Directorio de salida (por defecto: output_<mode>). |
| `--model` | `Optional[str]` | `None` | Modelo de Gemini (default: configurado o gemini-2.0-flash). |
| `-r`, `--recursive` | `<class 'bool'>` | `False` | Procesar subdirectorios recursivamente. |
| `--batch-size` | `<class 'int'>` | `5` | Número de preguntas por petición a la API (default: 5). |
| `-i`, `--in-place` | `<class 'bool'>` | `False` | Escribir en la misma carpeta que el original. |
| `--suffix` | `Optional[str]` | `None` | Sufijo para los nuevos archivos (usado con --in-place, ej: -ia). |
| `-n`, `--dry-run` | `<class 'bool'>` | `False` | Mostrar lo que se enviaría (y cuánto se ahorra) sin llamar al modelo ni escribir archivos. |
| `--contexto` | `Optional[str]` | `None` | classify: curso y nivel de los estudiantes (calibra Bloom y dificultad). |
| `--concurrencia` | `<class 'int'>` | `4` | classify: solicitudes simultáneas a Jev. |
| `--reclasificar` | `<class 'bool'>` | `False` | classify: volver a clasificar las ya clasificadas. |
| `--tags` | `<class 'bool'>` | `False` | classify: escribir también tags de Moodle (bloom:…, dificultad-…). |
| `--proveedor` | `Optional[str]` | configurado o `gemini` | `gemini` o `claude`. |
| `--opciones` | `<class 'int'>` | `4` | distractors: cantidad de opciones a alcanzar. |
| `--precio-entrada`, `--precio-salida` | `Optional[float]` | `None` | USD por millón de tokens, para estimar el costo. |
| `--sin-cache` | `<class 'bool'>` | `False` | No usar ni guardar respuestas en la caché. |
| `--calibrar` | `Optional[pathlib.Path]` | `None` | classify: comparar con una referencia CSV sin escribir nada. |
| `--revisar` | `<class 'bool'>` | `False` | classify: revisar en una TUI las clasificaciones con poca confianza. |
| `--umbral-revision` | `<class 'float'>` | `0.6` | classify --revisar: confianza por debajo de la cual se pide revisar. |
| `--referencias` | `Optional[pathlib.Path]` | `None` | classify --revisar: CSV al que se agregan las correcciones. |

#### Ejemplo de Invocación
```bash
voight ai banco.xml --dry-run
voight ai preguntas/ -r --mode multiply --output variaciones/
voight ai preguntas/ -r --mode classify -i --tags --contexto "Programación 1 (C), primer año"
voight ai preguntas/ -r --mode feedback -i --precio-entrada 3 --precio-salida 15 --dry-run
voight ai preguntas/ -r --mode distractors --proveedor claude -i
voight ai preguntas/ -r --mode classify --calibrar referencias.csv
voight ai preguntas/ -r --mode classify --revisar --referencias referencias.csv
```

### `voight health validate`

Valida archivos o directorios de preguntas GIFT y Moodle XML: errores de parseo, estadísticas por formato y tipo, preguntas sin respuesta correcta y duplicados (también entre un `.gift` y un `.xml`). `voight health stats` y `voight health similar` recorren los mismos repositorios mixtos; la búsqueda de duplicados filtra por prefijos y escala a miles de preguntas.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--paths` | `Optional[List[pathlib.Path]]` | `None` | - |
| `--llm` | `<class 'bool'>` | `False` | Muestra instrucciones para un LLM sobre este comando. |
| `-o`, `--output` | `Optional[str]` | `None` | Archivo de salida para el informe |
| `-r`, `--recursive` | `<class 'bool'>` | `False` | Buscar recursivamente |
| `-v`, `--verbose` | `<class 'bool'>` | `False` | Información detallada |
| `-s`, `--similarity` | `<class 'float'>` | `0.85` | Threshold para duplicados |
| `-j`, `--json` | `<class 'bool'>` | `False` | Salida en JSON |
| `--desde` | `Optional[str]` | `None` | Sólo los archivos cambiados desde esta revisión git. |

#### Ejemplo de Invocación
```bash
voight health validate preguntas/ -r
```

### `voight dedup`

Elimina preguntas duplicadas (GIFT y Moodle XML, también entre formatos) según un umbral de similitud configurable. La similitud es la de `analyze similar` (TF-IDF + Jaccard sobre título, enunciado y respuestas), pero como el comando elimina, el criterio es conservador: dos preguntas son duplicadas sólo si son **del mismo tipo**, tienen **la misma respuesta correcta** (los bancos tienen pares casi idénticos que sólo cambian cuál opción es la correcta, como recorrido inorden/posorden) y sus **enunciados por sí solos** también superan el umbral (así no se confunden "complejidad de la inserción" con "… de la extracción" cuando las opciones son iguales).

De cada grupo se conserva la más completa (feedback, título, opciones) o la primera (`--conservar primera`), y se eliminan sólo las directamente similares a ella (no se encadenan parecidos). En GIFT se quita el bloque de la pregunta con sus comentarios (las `$CATEGORY` se conservan); en XML, el `<question>` con los comentarios que lo preceden; un archivo que queda sin preguntas se borra.

**Por defecto sólo simula**; `--aplicar` elimina y agrega a `--log` (TSV, `dedup.log` por defecto) una línea por pregunta eliminada: fecha, acción (`archivo-borrado` o `pregunta-quitada`), ruta completa del archivo eliminado y del conservado (las categorías se infieren de ellas), similitud, umbral, tipo y título.

Antes de tocar nada, `--aplicar` guarda una copia completa de cada archivo que modifica o borra en `--respaldo/<fecha>/` (`dedup-respaldos/` por defecto, con un manifiesto). `--restaurar ultimo` (o el nombre de un respaldo) lo deshace: devuelve los archivos a su contenido original y recrea los borrados, pero no pisa uno editado después del dedup (lo informa y sale con 1; `--forzar` lo pisa igual).

`--confirmar-jev` consulta a Jev por cada par y descarta los que no evalúan exactamente lo mismo (útil con umbrales bajos); los pares casi idénticos no se consultan. Con `--desde <rev>` se compara contra todo el banco pero sólo se informan los grupos donde aparece una pregunta cambiada: «¿mi pregunta nueva duplica una existente?».

`--tui` abre una interfaz de terminal (extra `tui`): grupos a la izquierda y, a la derecha, la pregunta que se conserva y el duplicado en revisión lado a lado, con las palabras que difieren resaltadas. Teclas: `→`/`←` recorren los duplicados del grupo, `d` alterna eliminar/conservar, `p` conserva el duplicado en lugar de la principal, `c` conserva todo el grupo, `a` aplica (pide confirmación y escribe el log), `q` sale sin cambios.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--paths` | `Optional[List[pathlib.Path]]` | `None` | Archivos .gift/.xml o directorios. |
| `-r`, `--recursive` | `<class 'bool'>` | `False` | Buscar recursivamente. |
| `-s`, `--similarity` | `<class 'float'>` | `0.95` | Similitud mínima (0–1) para considerar dos preguntas duplicadas. |
| `--conservar` | `<class 'str'>` | `completa` | Cuál se conserva de cada grupo: la más completa o la primera. |
| `--aplicar` | `<class 'bool'>` | `False` | Eliminar de verdad (sin esta opción sólo se muestra lo que se eliminaría). |
| `--log` | `<class 'pathlib.Path'>` | `dedup.log` | Con --aplicar, log (TSV, se agrega al final) de cada pregunta eliminada con las rutas completas. |
| `--respaldo` | `<class 'pathlib.Path'>` | `dedup-respaldos` | Con --aplicar, directorio para la copia completa de cada archivo modificado o borrado. |
| `--restaurar` | `Optional[str]` | `None` | Deshacer un dedup: `ultimo` o el nombre de un respaldo. |
| `--forzar` | `<class 'bool'>` | `False` | Con --restaurar, pisar también los archivos editados después. |
| `--confirmar-jev` | `<class 'bool'>` | `False` | Confirmar cada par con Jev. |
| `--desde` | `Optional[str]` | `None` | Sólo los grupos con alguna pregunta cambiada desde esta revisión git. |
| `--tui` | `<class 'bool'>` | `False` | Revisar los grupos en una interfaz de terminal y decidir cuáles eliminar. |
| `--json` | `<class 'bool'>` | `False` | Emite los grupos de duplicados como JSON versionado. |

#### Ejemplo de Invocación
```bash
voight dedup preguntas/ -r -s 0.9
voight dedup preguntas/ -r -s 0.9 --aplicar
voight dedup preguntas/ -r -s 0.85 --tui
voight dedup preguntas/ -r -s 0.8 --confirmar-jev
voight dedup --restaurar ultimo
```

### `voight fix format`

Formatea archivos GIFT y Moodle XML y transforma el código. GIFT: `::Título::`, enunciado, `{` y `}` en líneas propias y una opción por línea con 4 espacios. XML: sangría de 2 espacios y cada `<text>` con contenido en CDATA (conserva los comentarios). El código de enunciados y opciones conserva sus saltos de línea y sangría.

Las transformaciones de código son las mismas en ambos formatos (ver [caracteres especiales](docs/caracteres_especiales.md)): `--fullwidth` reemplaza los símbolos que chocan con GIFT (`{ } = ~ # : \ //`, y además `; < > [ ] ( ) * " &`) por sus formas fullwidth, marca la indentación con `·` (un punto por espacio) y cada fin de línea con `↵`; `--normal` lo deshace (en GIFT, escapando con `\` lo que GIFT interpretaría).

Los valores por defecto de todas las opciones de formato salen de la sección `[format]` del [`.voight.toml`](#configuracion-por-banco) (o `.voight`) de la raíz del árbol, así todo el banco se formatea igual; `voight fix format-init [DIR]` la crea con cada clave explicada. Una opción en la línea de comandos gana (`--fullwidth` sobre `normal = true` y viceversa).

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--paths` | `Optional[List[pathlib.Path]]` | `None` | - |
| `--llm` | `<class 'bool'>` | `False` | Muestra instrucciones para un LLM sobre este comando. |
| `-r`, `--recursive` | `<class 'bool'>` | `False` | Procesar recursivamente |
| `-n`, `--dry-run` | `<class 'bool'>` | `False` | No aplicar cambios |
| `--code` | `<class 'bool'>` | `False` | Marcar la indentación del código con · (un punto por espacio) |
| `--fullwidth` | `<class 'bool'>` | `False` | Proteger el código: símbolos fullwidth y marcas · (indentación) y ↵ (fin de línea) |
| `--normal` | `<class 'bool'>` | `False` | Restaurar el código a caracteres normales (sin marcas) |
| `--marcas/--sin-marcas` | `<class 'bool'>` | `True` | Con --fullwidth, agregar las marcas · y ↵. |
| `--gaff` | `<class 'bool'>` | `False` | Formatear el código C con gaff (estilo de la cátedra). |
| `--correct-first` | `<class 'bool'>` | `False` | Ordena las opciones de opción múltiple por porcentaje (la correcta primero). |
| `--check` | `<class 'bool'>` | `False` | No escribir: salir con 1 si algún archivo cambiaría (CI y pre-commit). |
| `--diff` | `<class 'bool'>` | `False` | No escribir: mostrar los cambios como diff unificado. |
| `--desde` | `Optional[str]` | `None` | Sólo los archivos cambiados desde esta revisión git. |
| `--json` | `<class 'bool'>` | `False` | Emite los archivos que cambian y los errores como JSON versionado. |

#### Ejemplo de Invocación
```bash
voight fix format preguntas/ -r --fullwidth
voight fix format banco.xml --correct-first
voight fix format preguntas/ -r --check --desde origin/main
voight fix format-init preguntas/   # plantilla de [format] en preguntas/.voight.toml
```

### `voight verify`

Compila y ejecuta el código C (gcc, `-std=gnu11`) y Java (javac/java) de las preguntas que preguntan por la salida de un programa y compara lo que imprime con la respuesta correcta (exacta, ignorando espacios o por palabras). Informa:

- `coincide_distractor`: la salida coincide con un distractor y no con la correcta (la clave está mal);
- `no_compila`, `error_ejecucion`, `tiempo` (no termina) y `comportamiento_indefinido` (con `--sanitizar`, AddressSanitizer y UBSan);
- por defecto sólo verifica las preguntas que piden la salida del programa; `--todas` intenta con toda pregunta que tenga código. Las que usan archivos o la entrada estándar, los fragmentos que no compilan solos y las salidas que no aparecen literalmente en las opciones quedan como `revisar` (para una persona; no cuentan como problema).

`--estilo` revisa además el código C con las reglas de estilo de la cátedra (ripley, instalado aparte). Sale con código 1 si hay problemas.

#### Ejemplo de Invocación
```bash
voight verify preguntas/ -r --solo-problemas
voight verify preguntas/ -r --sanitizar --estilo --json
```

### `voight fix`

Correcciones puntuales, en GIFT, Moodle XML y Markdown; todas aceptan `-r` y `-n/--dry-run`:

- `fix code-lang`: agrega la etiqueta de lenguaje a los bloques ``` que no la tienen (detecta C o Java; `--lenguaje` fija uno).
- `fix code-format`: formatea el código C y Java con clang-format (el instalado o `uvx clang-format`), estilo LLVM con sangría de 4 (`--estilo` para otro; `--estilo allman` u otro estilo de llaves las aplica sobre ese estilo).
- `fix code-chars --to-fullwidth|--to-normal` y `fix code-indent`: caracteres fullwidth y marcas del código, combinables: `code-chars` cambia los símbolos y conserva la indentación `·` y los `↵` (con `--to-fullwidth` los agrega; `--sin-marcas` no los agrega y, con `--to-normal`, los quita), y `code-indent` marca la indentación.
- `fix slugify`, `fix name-from-title`, `fix title-from-name`: nombres de archivo y títulos.
- `fix extension`: corrige la extensión según el contenido: un `.xml` con preguntas GIFT pasa a `.gift` y un `.gift` con Moodle XML, a `.xml`. Si el destino ya existe no lo pisa (lo informa y sale con 1); los archivos que no parecen GIFT ni Moodle XML quedan como están. `--json` lista los renombrados, los conflictos y los no reconocidos.

### `voight moodle subir`

Sube un banco a un curso de Moodle por servicio web. Moodle estándar no tiene un servicio para importar preguntas: hace falta el plugin local **Question Web Service Import** (`local_questions_importer_ws`) en el sitio y un token de un usuario que pueda importar preguntas en el curso. El comando convierte y unifica los GIFT/XML indicados (las carpetas se vuelven categorías), sube el Moodle XML al área de borradores con `webservice/upload.php` y lo importa con `local_questions_importer_ws_import_xml`. Con un curso de prueba sirve para probar la importación contra el Moodle real.

`--url` (o `MOODLE_URL`), `--curso` (id) y el token por `--token`, `MOODLE_TOKEN` o `voight config set-moodle-token`. `--dry-run` prepara el XML sin contactar al sitio y `--guardar` conserva el XML que se sube.

```bash
voight moodle subir preguntas/ --url https://moodle.ejemplo.edu.ar --curso 1234 --dry-run
```

### `voight split`

Divide archivos GIFT o Moodle XML con múltiples preguntas en archivos individuales. En XML, cada archivo lleva la categoría vigente.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--paths` | `Optional[List[pathlib.Path]]` | `None` | - |
| `--llm` | `<class 'bool'>` | `False` | Muestra instrucciones para un LLM sobre este comando. |
| `-r`, `--recursive` | `<class 'bool'>` | `False` | Procesar recursivamente. |
| `--remove` | `<class 'bool'>` | `False` | Borrar el archivo original después de dividirlo. |

#### Ejemplo de Invocación
```bash
voight split banco.xml
```

### `voight convert`

Conversión entre formatos. Los tres subcomandos aceptan archivos y directorios, que recorren recursivamente (`--no-recursive` para un solo nivel; los directorios ocultos y lo que ignora el `.voight.toml` quedan afuera).

- `convert html-to-md RUTAS`: convierte las etiquetas HTML a Markdown (en XML, campo por campo: sólo los campos que cambian pasan a `format="markdown"`). `-n` simula.
- `convert xml-to-gift RUTAS` y `convert gift-to-xml RUTAS`: con un solo archivo (o stdin, `-`), la salida va a stdout o al archivo `-o`. Con un directorio o varias rutas, cada archivo se convierte al lado del original o, con `-o DIR`, replicando el árbol en `DIR`. No pisan archivos existentes (lo informan y salen con 1) salvo `--forzar`; `-n` muestra qué se convertiría.

#### Ejemplo de Invocación
```bash
voight convert gift-to-xml preguntas/ -o preguntas-xml/
voight convert xml-to-gift banco.xml > banco.gift
voight convert html-to-md preguntas/ -n
```

### `voight unify`

Unifica árboles o grupos de archivos de preguntas (GIFT o XML) en un único archivo.

    Es la operación inversa a 'split' y 'tree export': recopila preguntas
    recorriendo los directorios especificados, infiere y preserva las categorías,
    y genera un único banco monolítico (.gift o .xml).

    En Moodle XML, los bloques ```mermaid se renderizan con mermaid-cli (`mmdc`) y las
    imágenes con ruta relativa al archivo de la pregunta se incrustan en la salida.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `output_file` | `<class 'pathlib.Path'>` | Archivo de salida unificado (.gift o .xml). |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--paths` | `Optional[List[pathlib.Path]]` | `None` | - |
| `--llm` | `<class 'bool'>` | `False` | Muestra instrucciones para un LLM sobre este comando. |
| `-f`, `--format` | `Optional[str]` | `None` | Formato de salida (por defecto se deduce de la extensión del archivo de salida). |
| `-r`, `--recursive/--no-recursive` | `<class 'bool'>` | `True` | Procesar directorios recursivamente (por defecto True). |
| `--remove` | `<class 'bool'>` | `False` | Borrar los archivos fuente después de unificarlos. |
| `--incrustar/--no-incrustar` | `<class 'bool'>` | `True` | XML: renderiza los diagramas mermaid e incrusta las imágenes relativas en la salida. |
| `--diagramas` | `<class 'str'>` | `png` | Formato de imagen de los diagramas mermaid incrustados (`png` o `svg`). |

#### Ejemplo de Invocación
```bash
voight unify <output_file>
```

#### Diagramas mermaid e imágenes relativas

Las preguntas se escriben y versionan como texto; sólo el archivo fusionado
(`voight unify … -o banco.xml` y `voight tree collect … -o banco.xml`) lleva las
imágenes incrustadas. Los archivos fuente no se modifican.

- **Diagramas**: un bloque ```` ```mermaid ```` (en campos `markdown`) o un
  `<pre class="mermaid">` / `<div class="mermaid">` (en campos `html`) se renderiza
  con [mermaid-cli](https://github.com/mermaid-js/mermaid-cli) (`npm install -g
  @mermaid-js/mermaid-cli`; otra ruta con `VOIGHT_MMDC`). El código puede estar
  protegido con fullwidth y marcas `·`/`↵`: se restaura antes de renderizar. Los
  renders se guardan en la caché de voight.
- **Imágenes relativas**: `![alt](img/a.png)` y `<img src="img/a.png">` se resuelven
  contra el directorio del archivo de la pregunta. Las URL absolutas, `data:` y
  `@@PLUGINFILE@@` quedan como están.

Cada recurso se adjunta al campo que lo usa (enunciado, retroalimentación, opción…)
como `<file name="…" path="/" encoding="base64">` y la referencia pasa a
`@@PLUGINFILE@@/<nombre>`, que es como Moodle importa archivos en Moodle XML. Una
imagen que no existe o un diagrama que no compila detienen la fusión con el error.
`--no-incrustar` deja el texto como está. En GIFT no aplica: el formato no lleva
archivos.

````markdown
<!-- Tema/flujo.xml, campo questiontext format="markdown" -->
¿Qué imprime el programa?

```mermaid
graph TD
  A[inicio] --> B{x > 0}
```

![salida esperada](img/salida.png)
````

### `voight synth`

daedalus en belmont: sintetiza preguntas de C verificadas con GCC.

    PLANTILLA es una de las generadoras incorporadas (ver --listar). Cada
    pregunta se crea con parámetros aleatorios, se compila y ejecuta de verdad
    para fijar la salida correcta, y se acompaña de distractores verosímiles.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--plantilla` | `<class 'str'>` | `` | - |
| `--llm` | `<class 'bool'>` | `False` | Muestra instrucciones para un LLM sobre este comando. |
| `-n`, `--cantidad` | `<class 'int'>` | `5` | Cantidad de preguntas a sintetizar. |
| `-s`, `--semilla` | `<class 'int'>` | `42` | Semilla pseudo-aleatoria (salida reproducible). |
| `-o`, `--output` | `Optional[pathlib.Path]` | `None` | Archivo destino: .gift o .xml según la extensión. |
| `--listar` | `<class 'bool'>` | `False` | Lista las plantillas disponibles y sale. |
| `--json` | `<class 'bool'>` | `False` | Emite el resultado como JSON versionado. |

#### Ejemplo de Invocación
```bash
voight synth
```

### `voight ui`

Abre el editor web local (cerebro) sobre DIRECTORIO.

    Permite navegar y editar preguntas en Moodle XML y GIFT desde el navegador.
    Requiere el extra 'ui': uv tool install "voight[ui] @ git+https://github.com/INGCOM-UNRN/voight"

Edita todos los tipos de pregunta de Moodle, cada uno con su editor: respuestas con porcentaje (opción múltiple, respuesta corta), valor y tolerancia (numérica), fórmula y tolerancia (calculadas), verdadero/falso con la retroalimentación de cada opción, pares (emparejamiento), elementos en orden (ordenamiento) y opciones por grupo para los huecos `[[n]]` (seleccionar palabras faltantes, arrastrar sobre texto). Ensayo, descripción, cloze, emparejamiento aleatorio y arrastrar sobre imagen editan los campos comunes y sus opciones. Al guardar sólo cambia lo que el editor muestra: en XML se conservan unidades, variables, imágenes y zonas, y en GIFT la categoría, los comentarios y las demás preguntas del archivo.

Cada pregunta del árbol muestra su cantidad de opciones (respuestas en opción múltiple y respuesta corta, pares en emparejamiento). El filtro **Opciones: menos de / exactamente / más de N** de la barra lateral deja sólo las preguntas que cumplen la condición, para encontrar las que tienen pocas opciones; la navegación anterior/siguiente recorre sólo las filtradas. Las preguntas sin opciones (verdadero/falso, ensayo, descripción) quedan afuera mientras el filtro está activo.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--directorio` | `<class 'str'>` | `.` | - |
| `--llm` | `<class 'bool'>` | `False` | Muestra instrucciones para un LLM sobre este comando. |
| `--host` | `<class 'str'>` | `127.0.0.1` | Host del servidor web. |
| `--port` | `<class 'int'>` | `5000` | Puerto del servidor web. |
| `--debug/--no-debug` | `<class 'bool'>` | `False` | Modo debug de Flask. |

#### Ejemplo de Invocación
```bash
voight ui
```

### `voight fix grammar`

Verifica y corrige ortografía y gramática en bancos GIFT y XML usando LanguageTool.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--paths` | `Optional[List[pathlib.Path]]` | `None` | - |
| `--llm` | `<class 'bool'>` | `False` | Muestra instrucciones para un LLM sobre este comando. |
| `-s`, `--server` | `Optional[str]` | `None` | URL del servidor LanguageTool (por defecto http://localhost:8081 y API pública) |
| `-u`, `--username` | `Optional[str]` | `None` | Usuario / email de LanguageTool Premium |
| `-k`, `--api-key` | `Optional[str]` | `None` | API Key / Token de LanguageTool Premium |
| `--premium` | `<class 'bool'>` | `False` | Forzar uso de la API LanguageTool Premium |
| `-l`, `--lang` | `<class 'str'>` | `es-AR` | Código de idioma (default: es-AR) |
| `--ignore-rules` | `Optional[str]` | `None` | Reglas a ignorar separadas por comas |
| `--ignore-words` | `Optional[str]` | `None` | Palabras a ignorar separadas por comas |
| `-f`, `--fix` | `<class 'bool'>` | `False` | Aplica correcciones ortográficas automáticas |
| `--md`, `--output-md` | `Optional[pathlib.Path]` | `None` | Genera reporte Markdown |
| `--json` | `<class 'bool'>` | `False` | Emite salida estructurada en formato JSON |

#### Ejemplo de Invocación
```bash
voight fix grammar
```


---

## 4. Formatos de Salida e Integración con el Ecosistema

### Modo Interactivo / Terminal (Rich)
Por defecto, la herramienta renderiza paneles, árboles y tablas estilizadas para facilitar la lectura del estudiante y docente en terminales modernas con soporte ANSI.

### Modo Estructurado JSON (`--json`)
Para integración con pipelines de CI/CD, scripts de automatización u orquestadores externos, la opción `--json` emite un documento JSON estricto por la salida estándar (`stdout`), dirigiendo cualquier mensaje de logging a `stderr`:
```bash
voight doctor --json
```

<a id="configuracion-por-banco"></a>
### Configuración por banco (`.voight.toml`)

En la raíz del repositorio de preguntas, un `.voight.toml` (o `.voight`, con el mismo contenido TOML) fija los valores por defecto de cada comando (una opción en la línea de comandos siempre gana). Se busca subiendo desde la ruta indicada hasta la raíz del repositorio git. `voight fix format-init` agrega la sección `[format]` completa, con un comentario por clave.

```toml
[general]
ignorar = ["borradores/**", "*.bak.xml"]   # rutas que ningún comando procesa

[ai]
contexto = "Programación 1 (C), primer año"
proveedor = "claude"
opciones = 4

[dedup]
umbral = 0.9
conservar = "completa"

[health]
min_opciones = 4
umbral_longitud = 1.5

[format]              # todas las opciones de `fix format`
fullwidth = true      # o normal = true (excluyentes)
normal = false
marcas = true
indentacion = false   # --code
gaff = false
correct_first = false
```

### pre-commit y acción de GitHub

El repositorio publica hooks de [pre-commit](https://pre-commit.com) (`voight-format`, `voight-health`, `voight-health-estricto`, `voight-validate`), que reciben sólo los `.gift`/`.xml` del commit:

```yaml
repos:
  - repo: https://github.com/INGCOM-UNRN/voight
    rev: <etiqueta o commit>
    hooks:
      - id: voight-format
      - id: voight-health
```

Y una acción de GitHub que corre `health` sobre lo que cambia en un pull request (respecto de su base, con `fetch-depth: 0`), publica el informe en el resumen del job y como comentario del PR, expone `ok`, `errores` y `advertencias`, y falla ante errores (o advertencias, con `estricto: true`). Ejemplo completo en `docs/ejemplos/salud-banco.yml`:

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: 0
- uses: INGCOM-UNRN/voight@main
  with:
    rutas: preguntas
```

### Pruebas sobre bancos reales

`tests/test_corpus.py` verifica invariantes (format no cambia las preguntas y es idempotente, la conversión GIFT ↔ XML no las parte ni las pierde, unify y tree export tampoco, health es consistente) sobre un corpus sintético en cada corrida. Las mismas verificaciones corren sobre bancos reales, que sólo se leen, sin copiarlos al repositorio:

```bash
VOIGHT_BANCOS=/ruta/banco1:/ruta/banco2 uv run pytest tests/test_corpus.py
```

### Integración con Dredd (`dredd-section`)
Cuando la herramienta genera reportes de evaluación para entregas de alumnos, produce una sección Markdown estandarizada conforme al contrato de integración de Dredd (v1.0.0):
```markdown
<!-- dredd-section: voight, tool=voight, version=0.1.0, status=ok -->
```
Este encabezado garantiza la agregación determinista de los hallazgos en la rúbrica docente.

### Integración con Ripley
`voight` está registrada en el catálogo de plugins satélites de Ripley (`SATELLITE_CATALOG`). Puede invocarse directamente a través del motor de evaluación de Ripley configurando el análisis en `ripley.toml`.

---

## 5. Diagnóstico y Códigos de Salida

### Códigos de Retorno (`exit code`)
| Código | Significado |
| :---: | :--- |
| `0` | Ejecución exitosa sin hallazgos críticos ni errores de sintaxis. |
| `1` | Hallazgos pedagógicos detectados, infracción de reglas o advertencias activas. |
| `2` | Error de sintaxis en argumentos CLI o archivo fuente no encontrado. |
| `>2` | Error no recuperable del sistema, fallo de memoria o excepción interna. |

### Diagnóstico del Entorno (`doctor`)
Ante comportamientos inesperados, verificá el estado operativo con:
```bash
voight doctor
```
Comprueba la presencia de las dependencias requeridas y la integridad de los componentes del paquete.