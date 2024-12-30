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

If you are using a virtual environment for your codebase, make sure the Mutmut dependencies are installed:

.. code-block:: console

    pip install -r <path_to_mutmut_codebase>/requirements.txt

Run Mutmut:

.. code-block:: console

    python <path_to_mutmut_codebase>/mutmut/__main__.py run
