# Inspección de cuestionarios y herramientas docentes

Estos comandos trabajan con archivos locales. Los bancos pueden mezclar GIFT y
Moodle XML: se usa el mismo lector, con categorías explícitas o deducidas de las
carpetas. Se recorren subdirectorios por defecto (`--no-recursive` lo limita),
se respetan las exclusiones del banco y una ruta repetida no duplica preguntas.
Un archivo ilegible o inválido detiene el comando con su ruta en el error.

## Revisar un MBZ antes de restaurarlo

```sh
voight moodle inspeccionar cuestionario.mbz
voight moodle inspeccionar cuestionario.mbz --json
```

Lee copias tar/tar.gz y ZIP sin extraer archivos, conectar con Moodle ni restaurar.
Muestra categorías y tipos del banco, preguntas lógicas y versiones, cuestionarios,
slots fijos y aleatorios, referencias de categorías de los cupos, tiempo límite,
intentos, nota máxima y barajado. Cuenta la última versión de cada entrada del
banco; las versiones anteriores se informan aparte. También reconoce la estructura
antigua con preguntas directamente dentro de las categorías.

Un dato ausente se muestra como «sin dato» (`null` en JSON). En intentos y tiempo,
cero significa «sin límite». Las categorías estructurales vacías también aparecen.
Los filtros que no se pueden interpretar y la ausencia de banco o de cuestionarios
se informan como avisos. Cuando un slot filtra varias categorías, se muestra el
conjunto: no se inventa una distribución entre ellas. Se conserva el filtro completo
en JSON; reglas con distinta inclusión de subcategorías o tags no se fusionan.

La lectura rechaza rutas ambiguas, entradas duplicadas y XML con DTD/entidades;
limita el XML a 64 MiB por miembro y 128 MiB totales, y el paquete a 100000 entradas.
Es un inventario para revisión, no una certificación de restauración. La estructura
se contrastó con la [API de backup de Moodle](https://moodledev.io/docs/5.1/apis/subsystems/backup)
y la [definición del backup de quiz](https://github.com/moodle/moodle/blob/MOODLE_405_STABLE/mod/quiz/backup/moodle2/backup_quiz_stepslib.php).

## Planificar cupos sin generar archivos

```sh
voight moodle backup-quiz banco/ --plan -k 2 --titulo "Parcial 1"
voight moodle backup-quiz banco/ --plan -k 2 --json
```

El plan muestra preguntas disponibles, cupo solicitado y faltantes por categoría,
slots totales y configuración del cuestionario. No requiere `-o` y no escribe
ningún MBZ, incluso si se pasa una salida ya existente. Si hay cupos imposibles,
el JSON lleva `ok: false` y el comando termina con código 1.

El escritor MBZ actual implementa selección múltiple y verdadero/falso. El plan
informa los otros tipos y la generación los rechaza antes de escribir; para esos
bancos, usá la exportación Moodle XML. Esto evita convertirlos silenciosamente en
preguntas incompletas. La planificación y la generación usan la misma validación.

Cuando el plan sea válido:

```sh
voight moodle backup-quiz banco/ -k 2 --titulo "Parcial 1" -o parcial.mbz
voight moodle inspeccionar parcial.mbz
```

El cupo debe ser positivo; tiempo e intentos admiten cero para «sin límite» y no
admiten negativos. La nota máxima debe ser positiva y finita. El plan verifica
cupos y tipos exportables: `voight health` y `verify` siguen siendo las revisiones
del contenido de las preguntas.

## Exportar un catálogo docente

```sh
voight catalogo banco/ -o catalogo.md
voight catalogo banco/ --titulo "Preguntas de programación" --json
```

El catálogo Markdown incluye enunciado, opciones y claves de corrección, además de
categoría, archivo y número de pregunta para volver a la fuente. V/F muestra las
dos opciones y su clave; emparejamiento incluye los pares. Es material de revisión
docente, con respuestas. No modifica los bancos.

Sin `-o`, el Markdown va a stdout; con `--json`, stdout contiene el modelo de
preguntas y sus referencias. Si se combinan `-o` y `--json`, el archivo sigue
siendo Markdown y stdout es JSON. Se rechaza usar una fuente como salida.

## Obtener una muestra reproducible

```sh
voight muestra banco/ -n 10 --semilla 42 -o muestra.md
voight muestra banco/ -n 10 --semilla 42 --json
```

Selecciona exactamente N preguntas evaluables sin reemplazo y sin cambiar el orden
del banco original ni el generador aleatorio global. Misma semilla, mismo conjunto
de archivos y misma versión del lector producen la misma selección y orden.
Se excluyen categorías y descripciones. Si faltan preguntas, informa el problema y
sale con 1; no entrega silenciosamente una muestra más chica.

Es muestreo uniforme para revisión docente, con claves. No pretende balancear Bloom
o dificultad ni producir un paquete de examen. El JSON incluye semilla, cantidad
disponible y origen de cada pregunta; el Markdown se puede leer como catálogo.

## Revisar texto alternativo de imágenes

```sh
voight health accesibilidad banco/
voight health accesibilidad banco/ --json
```

Revisa imágenes HTML y Markdown en enunciados, opciones, emparejamientos y
retroalimentación. Informa archivo, título, número de pregunta y campo de cada
hallazgo. En Markdown omite los bloques e inline de código; también reconoce
imágenes con referencias. En HTML acepta atributos con o sin comillas.

Las imágenes sin `alt` o con texto alternativo vacío requieren revisión. No se
completan descripciones automáticamente. Este chequeo no certifica accesibilidad
integral y los casos decorativos deben revisarse según su contexto.

## Salidas y automatización

Los cinco comandos tienen `--json`, con `schema_version: "1.0.0"`,
`herramienta: "voight"` y el nombre de comando. Un plan insuficiente o hallazgos de
accesibilidad también producen JSON y salen con 1. Los errores de lectura se
explican por stderr. Código 0: operación correcta; 1: hallazgos/datos inválidos;
2: argumentos incorrectos.
