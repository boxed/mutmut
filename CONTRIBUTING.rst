Contributing to Mutmut
======================

Setup
-----

First fork the repository and clone your fork.

We use [uv](https://docs.astral.sh/uv/) to manage dependencies.
All `uv` commands will implicitly install the required dependencies,
however you can also explicitly install them with `uv sync`:

.. code-block:: console

    uv sync

Running the tests
-----------------

.. code-block:: console

    uv run pytest

We use `inline-snapshot` for E2E and integration tests, to prevent unexpected changes in the output. If the output _should_ change, you can use `uv run pytest --inline-snapshot=fix` to update the snapshots.

If pytest terminates before reporting the test failures, it likely hit a case where mutmut calls `os._exit(...)`. Try looking at these calls first for troubleshooting.

Running your local version of Mutmut against a test codebase
------------------------------------------------------------

You can install your local version of Mutmut and run it, including any changes you have made, as normal.

Codebases using pip
^^^^^^^^^^^^^^^^^^^

.. code-block:: console

    python -m pip install --editable <path_to_mutmut_codebase>

Codebases using Poetry
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: console

    poetry add --group dev --editable <path_to_mutmut_codebase>
    # Install dependencies in your Poetry environment
    pip install -r <path_to_mutmut_codebase>/requirements.txt

Documentation about mutmut's architecture
-----------------------------------------

Please see ARCHITECTURE.rst for more details on how mutmut works.
