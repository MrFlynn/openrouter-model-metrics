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
uvx --with 'git-history>=0.8' git-history file \
  model-metrics.db model-metrics.json \
  --id model --id provider --ignore-duplicate-ids \
  --import re --convert "$(cat git-history-convert.py)"
```

Once that's done, you can query model-metrics.db any way you like. For example,
to see the history of the metrics for glm-4.7 on Chutes, use this query:

```sql
select i.model, i.provider, iv.tokens_per_second, iv.time_to_first_token, c.commit_at
  from item i
  join item_version iv on iv._item = i._id
  join commits c on c.id = iv._commit
  where i.model = 'z-ai/glm-4.7' and i.provider = 'Chutes'
  order by c.commit_at;
```
