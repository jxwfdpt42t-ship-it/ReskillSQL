MemRL upstream code used by ReskillSQL

Repository: https://github.com/MemTensor/MemRL
Commit: c1b322ca43de36ddf64c6712f89d0095bfc35ce0
License: MIT, reproduced in LICENSE. Original copyright: (c) 2026 jiaqian.
UPSTREAM.json records SHA-256 checksums of the original source files.

Direct reuse:

- service/value_driven.py: RLConfig, ValueAwareSelector and QValueUpdater.
  Only the MemOS type import was moved behind TYPE_CHECKING. The selection
  and update algorithms are unchanged. The SQLite adapter supplies the small
  text_mem.get/update interface required by QValueUpdater.
- service/builders.py and strategies.py: upstream trajectory, script and
  proceduralization builders and strategy definitions, unchanged.
- providers/base.py and embedding.py: upstream provider interfaces, chunking,
  API/local embedding implementations and usage logging, unchanged.

The adapter is in text2sql_evolver/memory/, outside this vendor package. It adds
SQL attempt provenance, SQLite persistence, semantic candidate filtering, context
budgets, consumer/skill/model-specific utility and evaluation isolation. It uses
the upstream ValueAwareSelector policy (Q first, similarity tie-break) after cosine
recall, with epsilon=0. This differs from the normalized similarity/Q mixture in
the paper and upstream memory_service.retrieve_query; it is not claimed to be an
exact reproduction of that experiment. No random mock embeddings are used in
normal operation. Tests inject a deterministic fake embedder explicitly.

We do not copy MemOS, benchmark environments, their datasets or third-party
benchmark dependencies. Only the upstream core files above are vendored.
