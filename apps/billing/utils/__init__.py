"""
Utilidades de `billing` sin DB ni SDK — separadas por concepto.

A diferencia de `services/*.py` (orquestan DB y/o el SDK de LibreDTE
Lib), estos módulos son funciones puras. `period.py` (aritmética de
`YYYYMM`) y `dte.py` (lectura del nodo `Totales` de un DTE crudo) no
tienen relación entre sí — viven en archivos separados, no uno
compartido, por el mismo criterio que separa `sales_reporter.py` de
`purchases_reporter.py`.
"""
