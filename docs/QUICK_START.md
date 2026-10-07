# Guía Rápida - Questions CLI

Guía rápida de 5 minutos para empezar a usar la nueva interfaz unificada.

## 🎯 Casos de Uso Más Comunes

### 1️⃣ Validar y Analizar un Directorio
```bash
# Análisis completo con detección de duplicados
uv run voight health validate ./preguntas -o informe.txt

# Ver estadísticas rápidas
uv run voight health stats ./preguntas
```

### 2️⃣ Encontrar preguntas similares
```bash
# Buscar con threshold personalizado (0.0 - 1.0)
uv run voight health similar ./preguntas --similarity 0.8
```

### 3️⃣ Formatear y Preparar archivos GIFT
```bash
# Estandarizar formato visual
uv run voight fix format ./preguntas/archivo.gift

# Corregir indentación en bloques de código
uv run voight fix code-indent ./preguntas/archivo.gift
```

### 4️⃣ Mantenimiento de archivos XML
```bash
# Asegurar que usen CDATA
uv run voight fix xml cdata ./preguntas

# Renombrar archivos según el nombre de la pregunta
uv run voight fix xml rename ./preguntas/*.xml

# Eliminar tags innecesarios
uv run voight fix xml clean-tags ./preguntas
```

### 5️⃣ Procesamiento con IA (Gemini)
```bash
# Mejorar calidad pedagógica
uv run voight ai ./preguntas/pregunta.gift --mode improve

# Crear 3 variaciones de una pregunta
uv run voight ai ./preguntas/pregunta.gift --mode multiply
```

### 6️⃣ Conversión HTML a Markdown
```bash
# Convertir tags <code>, <p>, etc. a Markdown
uv run voight convert html-to-md ./preguntas
```

## 📚 Documentación de Referencia

| Para... | Consulta... |
|-----------|--------|
| Visión general | [README.md](../README.md) |
| Caracteres especiales | [caracteres_especiales.md](./caracteres_especiales.md) |
| Mantenimiento XML | [README_xml_maintenance.md](./README_xml_maintenance.md) |
| Validación GIFT | [README_validate_questions.md](./README_validate_questions.md) |

## 💡 Tips Rápidos

1. **Siempre usar `--dry-run` (-n)** en comandos de formateo para previsualizar cambios.
2. **Los backups `.bak`** se crean automáticamente en la mayoría de operaciones de corrección.
3. **Threshold 0.9** para duplicados exactos, **0.7** para encontrar preguntas similares pero no idénticas.
4. **Usa `uv run`** para asegurar que todas las dependencias estén correctamente instaladas.

---

**¿Listo?** Empieza con: `uv run voight --help`
