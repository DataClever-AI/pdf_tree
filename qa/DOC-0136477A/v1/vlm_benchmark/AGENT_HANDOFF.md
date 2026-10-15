# Handoff: benchmark visual con Qwen3-VL

## Objetivo

Confirmar de forma independiente si un VLM puede validar visualmente la salida de
`pdf-tree` contra páginas renderizadas del PDF. La prueba no mide transcripción OCR:
mide detección de errores de jerarquía, límites de sección, omisiones y clasificación
de tablas.

Fuentes de verdad:

- PDF: `/Users/j/Documents/Dataclever/Manuales técnicos TEST/DOC-0136477A.pdf`
- árbol: `qa/DOC-0136477A/v1/exports/tree.json`
- revisión humana: `qa/DOC-0136477A/v1/findings/findings_log.csv`
- criterios: `qa/DOC-0136477A/v1/findings/checklist_reference.md`

No leas `reference_score_*.json` antes de la ejecución si quieres hacer una revisión
ciega. Ejecuta primero los modelos, examina sus evidencias y después calcula el score.

## Matriz de prueba

Hay seis secciones y tres criterios por sección, para un total de 18 decisiones:

| Sección | Tipo | Páginas renderizadas | Veredicto humano esperado |
|---|---|---|---|
| `sec_0004` | defecto conocido | 17 | `PASS`, `FAIL Critical`, `PASS` |
| `sec_0015` | defecto conocido | 26-27 | `PASS`, `FAIL Critical`, `PASS` |
| `sec_0279` | defecto conocido | 231-233, 236-238, 240 | `FAIL Critical`, `FAIL Medium`, `FAIL Medium` |
| `sec_0025` | control limpio | 41 | tres `PASS` |
| `sec_0066` | control limpio | 69 y 71 | tres `PASS` |
| `sec_0243` | control limpio | 200 y 205 | tres `PASS` |

Los controles limpios no tienen fallas estructurales o de contenido para los criterios
seleccionados. Hallazgos visuales Low ajenos a esos criterios no deben convertirse en
fallas.

## Reproducción exacta

Desde la raíz del repositorio y dentro del entorno `qwen3-vl-validator`:

```bash
cd /Users/j/Documents/Dataclever/pdf_tree
chmod +x qa/DOC-0136477A/v1/vlm_benchmark/render_pages.sh
qa/DOC-0136477A/v1/vlm_benchmark/render_pages.sh
```

Esto usa Poppler únicamente para renderizar a 160 DPI. No usa PyMuPDF ni vuelve a
extraer el contenido del documento.

Ejecuta cada modelo una sola vez por proceso, para que permanezca cargado durante sus
seis casos:

```bash
/usr/bin/time -l python qa/DOC-0136477A/v1/vlm_benchmark/benchmark_sections.py \
  --model mlx-community/Qwen3-VL-4B-Instruct-4bit \
  --output qa/DOC-0136477A/v1/vlm_benchmark/rerun_results_4b.json \
  2>qa/DOC-0136477A/v1/vlm_benchmark/rerun_time_4b.log \
  | tee qa/DOC-0136477A/v1/vlm_benchmark/rerun_run_4b.log

/usr/bin/time -l python qa/DOC-0136477A/v1/vlm_benchmark/benchmark_sections.py \
  --model mlx-community/Qwen3-VL-8B-Instruct-4bit \
  --output qa/DOC-0136477A/v1/vlm_benchmark/rerun_results_8b.json \
  2>qa/DOC-0136477A/v1/vlm_benchmark/rerun_time_8b.log \
  | tee qa/DOC-0136477A/v1/vlm_benchmark/rerun_run_8b.log
```

Calcula los resultados:

```bash
python qa/DOC-0136477A/v1/vlm_benchmark/score_results.py \
  --input qa/DOC-0136477A/v1/vlm_benchmark/rerun_results_4b.json \
  --output qa/DOC-0136477A/v1/vlm_benchmark/rerun_score_4b.json

python qa/DOC-0136477A/v1/vlm_benchmark/score_results.py \
  --input qa/DOC-0136477A/v1/vlm_benchmark/rerun_results_8b.json \
  --output qa/DOC-0136477A/v1/vlm_benchmark/rerun_score_8b.json
```

## Resultados de referencia obtenidos

| Métrica | Qwen3-VL-4B | Qwen3-VL-8B |
|---|---:|---:|
| Tiempo de generación total | 301.33 s | 509.46 s |
| Promedio por sección | 50.22 s | 84.91 s |
| Pico reportado por MLX | 7.05 GB | 10.02 GB |
| JSON válido | 6/6 | 6/6 |
| `section_id` exacto | 2/6 | 2/6 |
| Orden exacto de criterios | 6/6 | 6/6 |
| Exactitud por criterio | 13/18 (72.2%) | 14/18 (77.8%) |
| Secciones defectuosas detectadas | 0/3 | 2/3 |
| Falsos positivos en controles limpios | 0/3 | 0/3 |

El 4B aprobó las tres secciones defectuosas. En `sec_0279` su evidencia afirmó que
G.3.6 terminaba en la página 232 y que las páginas 233-240 no pertenecían a ella, pero
devolvió `PASS` para un rango declarado hasta 240.

El 8B detectó defectos en `sec_0004` y `sec_0279`, y omitió `sec_0015`. En `sec_0004`
produjo falsos fallos por criterio y evidencia contradictoria. En `sec_0279` acertó el
rango y la omisión del glosario/índice, pero dejó `table_content` en `REVIEW` y elevó
una severidad Medium a Critical.

Los dos modelos reemplazaron el `section_id` en cuatro de seis respuestas, pese a la
instrucción explícita de preservarlo.

## Evaluación adicional solicitada al agente

Además del score automático, revisa manualmente cada salida con estas preguntas:

1. ¿La evidencia implica lógicamente el `result` elegido?
2. ¿La evidencia describe algo visible o inventa contenido?
3. ¿Cada fallo corresponde al criterio correcto?
4. ¿La severidad coincide con `findings_log.csv`?
5. ¿Conserva exactamente `section_id`, número y orden de checks?
6. ¿Los tres controles limpios permanecen sin falsos positivos?

Después repite el 8B con `max_tokens=900`. En la ejecución de referencia generó como
máximo 721 tokens, por lo que 900 debería conservar las respuestas. El ahorro puede
ser pequeño porque las imágenes dominan el contexto. Prueba también dividir
`sec_0279` en ventanas de dos o tres imágenes y combinar los hallazgos: el caso de
siete imágenes tardó 228.20 s con 8B y 147.40 s con 4B.

## Hipótesis que debe intentar refutar

`Qwen3-VL-8B-Instruct-4bit` es el mejor de estos dos modelos para la validación visual
en este Mac, pero aún no es seguro para escribir hallazgos finales sin una capa de
consistencia. Esa capa debe preservar identificadores y rechazar contradicciones como
evidencia que dice “termina en 232” junto a un `PASS` para `page_end=240`.

La arquitectura sugerida para el sprint es:

1. Ejecutar primero reglas deterministas sobre `tree.json` para IDs, rangos, huecos y
   estructura básica.
2. Enviar al 8B únicamente páginas y criterios ambiguos que requieran inspección
   visual.
3. Validar el JSON y la coherencia entre evidencia, resultado y severidad.
4. Enviar a revisión humana los `REVIEW`, contradicciones y fallos Critical.

## Mensaje listo para pegar al agente de CLI

> Reproduce de forma independiente el benchmark descrito en
> `qa/DOC-0136477A/v1/vlm_benchmark/AGENT_HANDOFF.md`. Ejecuta primero sin mirar los
> scores de referencia. Compara Qwen3-VL-4B-Instruct-4bit y
> Qwen3-VL-8B-Instruct-4bit en las seis secciones, incluyendo los tres controles
> limpios. Evalúa exactitud, recall de defectos, falsos positivos, JSON, IDs,
> severidades, coherencia entre evidencia y veredicto, tiempo y memoria. Después
> contrasta tus resultados con `reference_score_4b.json` y
> `reference_score_8b.json`. Intenta refutar la conclusión de que el 8B es mejor para
> este caso, pero que requiere una capa determinista de consistencia. Prueba además el
> 8B con `max_tokens=900` y divide `sec_0279` en ventanas de 2-3 imágenes. Documenta
> dónde coincides, dónde difieres y qué configuración recomiendas para integrarlo al
> sprint. No uses PyMuPDF para extracción; Poppler se usa únicamente para renderizar.
