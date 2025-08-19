Contributing to Mutmut
======================

Setup
-----

First fork the repository and clone your fork.

Install the dependencies:

.. code-block:: console

    pip install -r requirements.txt -r test_requirements.txt

Running the tests
-----------------

.. code-block:: console

    pytest

This also runs E2E tests that verify that `mutmut run` produces the same output as before. If your code changes should change the output of `mutmut run` and this test fails, try to delete the `snapshots/*.json` files (as described in the test errors).

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
