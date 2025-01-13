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

Running your local version of Mutmut against a test codebase
------------------------------------------------------------

You can install your local version of Mutmut and run it, including any changes you have made, as normal.

.. code-block:: console

    python -m pip install --editable <path_to_mutmut_codebase>
