# openrouter-model-metrics
Hourly scraped provider throughput and latency data for every active model (i.e.
models that have seen some amount of token generation in the past week). Each
checkpoint is saved as a git commit, similar to other projects like 
[pge-outages](https://github.com/simonw/pge-outages) and
[mcbroken-archive](https://github.com/MrFlynn/mcbroken-archive).

## Loading Data into SQLite
To more easily perform analysis across multiple checkpoints, I recommend using
the [`git-history`](https://github.com/simonw/git-history) tool. For this
specific repository, the following command can be used to load all checkpoints
into a SQLite database for more robust analysis.

```bash
uvx --with git-history>=0.7 git-history file \
  model-metrics.db model-metrics.json \
  --id model --id provider --ignore-duplicate-ids \
  --import re --convert "$(cat git-history-convert.py)"
```

Once that's done, you can query model-metrics.db any way you like. For example,
to see all checkpoints and their checkpoint time, you can use the following query:

```sql
select model, provider, tokens_per_second, time_to_first_token, commit_at
from item
join commits on commits.id = item._commit
;
```
