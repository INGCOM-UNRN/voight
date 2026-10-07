# Caracteres especiales en el código de las preguntas

Los bancos tienen código C y Java, cuya sintaxis se superpone con la de GIFT: `{ }`
abren y cierran las respuestas, `=` y `~` marcan opciones, `#` el feedback, `:` el
título, `\` escapa, una línea que empieza con `//` es un comentario y **una línea en
blanco termina la pregunta**. Además, Moodle descarta la indentación al importar.

Por eso, dentro de las secciones de código, los caracteres que chocan se reemplazan
por sus formas *fullwidth* (se ven casi iguales) y los espacios y saltos se marcan.
La transformación es **la misma para GIFT y Moodle XML**: un banco puede pasar de un
formato al otro sin romperse. La implementa `voight.core.codigo` y la usan
`voight format --fullwidth/--normal`, `voight fix code-chars` y
`voight fix code-indent`; `voight health` informa el código que falta proteger.

## Secciones de código

- Bloques ```` ```lenguaje ... ``` ````.
- Código en línea `` `...` `` (puede ocupar varias líneas, pero no cruzar un párrafo
  ni, en GIFT, el comienzo de otra opción).
- `<pre>...</pre>` y `<code>...</code>` en texto HTML (las entidades `&lt;` `&gt;`
  `&amp;`… se interpretan al proteger y se vuelven a escapar al restaurar).

En GIFT se procesa el texto del archivo; en XML, el contenido de cada `<text>` (en
CDATA o escapado; si cambia, se escribe en CDATA).

## Símbolos

| Normal | Fullwidth | Por qué |
| :-: | :-: | :-- |
| `==` | `⩵` (U+2A75) | operador de igualdad |
| `=` | `＝` | opción correcta en GIFT |
| `~` | `～` | opción incorrecta en GIFT |
| `#` | `＃` | feedback en GIFT (`#include`, `#define`) |
| `{` `}` | `｛` `｝` | bloque de respuestas en GIFT |
| `:` | `：` | título en GIFT |
| `\` | `＼` | escape de GIFT (`\n` se importaría como salto de línea) |
| `//` | `／／` | comentario de GIFT al comienzo de una línea |
| `;` | `；` | convención de los bancos |
| `<` `>` `&` | `＜` `＞` `＆` | HTML |
| `[` `]` `(` `)` `*` `"` | `［` `］` `（` `）` `＊` `＂` | markdown y convención de los bancos |

Al restaurar, **toda** la tabla fullwidth (U+FF01–U+FF5E) vuelve a ASCII, incluidos
`＋ － ． ／ ， ％ ！ ？` que aparecen en los bancos.

## Marcas de espacio y de salto de línea

| Marca | Significado |
| :-: | :-- |
| `·` (U+00B7) | un espacio de indentación (un tabulador son cuatro `·`) |
| `↵` (U+21B5) | fin de línea: va al final de cada línea del código; en un bloque ``` también en la última (la que precede al cierre), en `<pre>` y en el código en línea no |

```c
#include <stdio.h>↵
↵
int main（） ｛↵
····printf（＂%d＼n＂, 42）；↵
｝↵
```

- Una línea en blanco dentro del código queda como `↵`: en GIFT es obligatorio (sin la
  marca, la línea en blanco cortaría la pregunta) y por eso se conserva incluso al
  restaurar a caracteres normales en GIFT.
- Al restaurar sólo se quita el `↵` que precede a un salto real. Uno a mitad de línea
  (por ejemplo la salida `hola↵mundo` en una opción) es contenido del autor.
- `voight format --fullwidth --sin-marcas` aplica sólo los símbolos;
  `voight fix code-indent` sólo la indentación con `·` (con `--saltos`, también `↵`).

## Variantes históricas

Los bancos XML usaban otras marcas; al proteger se llevan a la forma canónica y al
restaurar todas vuelven a ASCII.

| Variante | Forma canónica |
| :-- | :-: |
| U+2007 (figure space), U+2000, U+00A0 (NBSP), U+3000 | `·` |
| U+037E (punto y coma griego, idéntico a `;`) | `；` |

El punto y coma griego tiene descomposición canónica a `;`: cualquier normalización
Unicode NFC lo convierte silenciosamente en un `;` común. `；` no tiene ese problema.

## Forma normal en GIFT

`voight format --normal` (o `fix code-chars --to-normal`) restaura el código a
ASCII y, en GIFT, escapa con `\` lo que GIFT interpretaría (`\{`, `\=`, `\#`, `\~`,
`\:`, `\\`): el resultado sigue siendo GIFT válido y Moodle muestra el código original.
