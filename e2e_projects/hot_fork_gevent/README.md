# Hot Fork Gevent E2E Test Project

This project tests that `process_isolation = "hot-fork"` works correctly
when conftest.py imports gevent and calls `monkey.patch_all()`.

## The Problem

When conftest.py contains:
```python
from gevent import monkey
monkey.patch_all()
```

Regular fork mode crashes because gevent creates internal state (hubs, greenlets)
that doesn't survive `os.fork()`.

## The Solution

Hot-fork mode keeps the parent process clean by:
1. Running stats collection in a forked child
2. Forking a orchestrator that imports pytest once
3. Orchestrator forks grandchildren for each mutant

The parent never imports pytest/conftest, so it stays fork-safe.

## Running

```bash
cd e2e_projects/hot_fork_gevent
python -m mutmut run
```
