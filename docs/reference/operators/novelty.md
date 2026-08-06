# Novelty

`novelty` checks whether a proposed edit is sufficiently different from prior
accepted candidate diffs. It is optional and runs before spending a canonical
evaluation on a near-duplicate.

## Contract

```python
class NoveltyOperator:
    def assess(self, checkout, ctx) -> NoveltyResult: ...
```

The result contains a novelty score, where `1.0` is wholly novel and `0.0` is an
exact duplicate, plus an acceptance boolean.

## Variants

| Variant | Rule |
| --- | --- |
| `accept_all` | accept every candidate edit and disable deduplication |
| `diff_similarity` | compare the candidate diff with recent accepted diffs and reject excessive similarity |

## Configuration

```yaml
operators:
  novelty:
    variant: diff_similarity
    threshold: 0.98
    history_k: 8
    timeout_s: 600
```

- `threshold` is the similarity level at which an edit is considered too close
  to prior work.
- `history_k` bounds the accepted history examined.

Use `accept_all` when novelty is not part of the method contract. Adding or
changing novelty filtering changes which candidates receive evaluator budget
and therefore changes the experiment policy.

