from copy import copy as copy_obj
from typing import Dict, List
from mutmut.helpers.config import Config
from mutmut.helpers.context import Context
from mutmut.helpers.progress import *
from mutmut.helpers.relativemutationid import RelativeMutationID


class QueueManager:
    def __init__(self):
        # List of active multiprocessing queues
        self._active_queues = []

    def add_to_active_queues(self, queue):
        self._active_queues.append(queue)

    def close_active_queues(self):
        for queue in self._active_queues:
            queue.close()

    def queue_mutants(self,
            *,
            progress: Progress,
            config: Config,
            mutants_queue,
            mutations_by_file: Dict[str, List[RelativeMutationID]],
    ):
        from mutmut.cache import get_cached_mutation_statuses

        try:
            index = 0
            for filename, mutations in mutations_by_file.items():
                cached_mutation_statuses = get_cached_mutation_statuses(filename, mutations, config.hash_of_tests)
                with open(filename) as f:
                    source = f.read()
                for mutation_id in mutations:
                    cached_status = cached_mutation_statuses.get(mutation_id)
                    if cached_status != UNTESTED:
                        progress.register(cached_status)
                        continue
                    context = Context(
                        mutation_id=mutation_id,
                        filename=filename,
                        dict_synonyms=config.dict_synonyms,
                        config=copy_obj(config),
                        source=source,
                        index=index,
                    )
                    mutants_queue.put(('mutant', context))
                    index += 1
        finally:
            mutants_queue.put(('end', None))
