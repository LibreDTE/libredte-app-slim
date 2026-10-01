## Paginación, filtros y orden

Los listados responden el formato que espera Tabulator, la grilla que
usa la propia aplicación web:

```json
{"last_page": 4, "data": [{"...": "..."}]}
```

Se controlan con estos parámetros de consulta:

| Parámetro | Ejemplo | Qué hace |
|---|---|---|
| `page` | `page=2` | Página pedida, empezando en 1. |
| `size` | `size=50` | Filas por página. |
| `filter[0][field]` + `filter[0][value]` | `filter[0][field]=receptor&filter[0][value]=sasco` | Filtra por un campo. El índice permite encadenar varios. |
| `sort[0][field]` + `sort[0][dir]` | `sort[0][field]=fecha&sort[0][dir]=desc` | Ordena por un campo (`asc`/`desc`). |

Los campos aceptados en `filter` y `sort` son los que documenta cada
endpoint, que no siempre coinciden con los del modelo: varios son
calculados (`receptor` busca a la vez en razón social y RUT, `tipo` en
glosa y código del DTE).
