"""
Escritura de planillas XLSX como texto plano.

Solo I/O: `write_rows()` arma el XLSX de resultado de la emisión masiva
(ver `services/bulk_biller.py`). La lectura de las planillas subidas la hace
la biblioteca, vía el SDK.
"""

from __future__ import annotations

import io

from openpyxl import Workbook


def write_rows(filas: list[list[str]]) -> bytes:
    """
    Un XLSX con `filas` en su primera hoja, tal cual, como texto.

    :param filas: Las filas a escribir, con cada celda como texto.
    :type filas: list[list[str]]
    :return: El XLSX.
    :rtype: bytes
    """
    libro = Workbook()
    hoja = libro.active
    # `Workbook()` siempre crea una hoja activa; el `None` de los stubs
    # es para libros cargados sin ninguna.
    assert hoja is not None
    for fila in filas:
        hoja.append(fila)

    archivo = io.BytesIO()
    libro.save(archivo)
    return archivo.getvalue()
