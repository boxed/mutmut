# flat-src

E2E fixture project for mutmut: a **flat layout** where the import package is
literally `src` (with `src/__init__.py`), instead of the src-layout convention
where `src/` is only a container directory. Tests import `from src.calc ...`,
and `[tool.mutmut] strip_src_prefix = false` keeps that prefix in mutant names.
