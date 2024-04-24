from typing import Optional

from mutmut.helpers.config import Config, should_exclude
from mutmut.helpers.relativemutationid import RelativeMutationID

ALL = RelativeMutationID(filename='%all%', line='%all%', index=-1, line_number=-1)


class Context:
    def __init__(
        self,
        source: Optional[str] = None,
        mutation_id=ALL,
        dict_synonyms=None,
        filename=None,
        config: Optional[Config] = None,
        index=0,
    ):
        self.index = index
        self.remove_newline_at_end = False
        self._source = None
        self._set_source(source)
        self.mutation_id = mutation_id
        self.performed_mutation_ids = []
        assert isinstance(mutation_id, RelativeMutationID)
        self.current_line_index = 0
        self.filename = filename
        self.stack = []
        self.dict_synonyms = (dict_synonyms or []) + ['dict']
        self._source_by_line_number = None
        self._pragma_no_mutate_lines = None
        self._path_by_line = None
        self.config = config
        self.skip = False

    def exclude_line(self):
        return self.current_line_index in self.pragma_no_mutate_lines or should_exclude(context=self, config=self.config)

    @property
    def source(self):
        if self._source is None:
            with open(self.filename) as f:
                self._set_source(f.read())
        return self._source

    def _set_source(self, source):
        if source and source[-1] != '\n':
            source += '\n'
            self.remove_newline_at_end = True
        self._source = source

    @property
    def source_by_line_number(self):
        if self._source_by_line_number is None:
            self._source_by_line_number = self.source.split('\n')
        return self._source_by_line_number

    @property
    def current_source_line(self):
        return self.source_by_line_number[self.current_line_index]

    @property
    def mutation_id_of_current_index(self):
        return RelativeMutationID(filename=self.filename, line=self.current_source_line, index=self.index, line_number=self.current_line_index)

    @property
    def pragma_no_mutate_lines(self):
        if self._pragma_no_mutate_lines is None:
            self._pragma_no_mutate_lines = {
                i
                for i, line in enumerate(self.source_by_line_number)
                if '# pragma:' in line and 'no mutate' in line.partition('# pragma:')[-1]
            }
        return self._pragma_no_mutate_lines

    def should_mutate(self, node):
        if self.config and node.type not in self.config.mutation_types_to_apply:
            return False
        if self.mutation_id == ALL:
            return True
        return self.mutation_id in (ALL, self.mutation_id_of_current_index)
