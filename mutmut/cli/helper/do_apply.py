from typing import List

from mutmut.helpers.context import Context
from mutmut.mutator.mutator import Mutator
from mutmut.cache import filename_and_mutation_id_from_pk, update_line_numbers


def do_apply(mutation_pk: str, dict_synonyms: List[str], backup: bool):
    """Apply a specified mutant to the source code

    :param mutation_pk: mutmut cache primary key of the mutant to apply
    :param dict_synonyms: list of synonym keywords for a python dictionary
    :param backup: if :obj:`True` create a backup of the source file
        before applying the mutation
    """
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))

    update_line_numbers(filename)

    context = Context(
        mutation_id=mutation_id,
        filename=filename,
        dict_synonyms=dict_synonyms,
    )

    mutator = Mutator(context=context)
    mutator.mutate_file(backup=backup)
