# TweetSumm local dataset

This directory contains the official TweetSumm train/validation/test JSONL files downloaded from:

https://github.com/guyfe/Tweetsumm

TweetSumm contains 1,100 dialogs derived from real Twitter customer-support conversations. The
repository provides human-written extractive and abstractive summaries. SupportOps imports only
the paired abstractive customer/agent summaries; it does not claim these records are raw enterprise
tickets. Imported rows are therefore labeled `source_type=real_derived`.

Dataset license: CDLA-Sharing-1.0. Keep the bundled `LICENSE` file with redistributed data.

Verified file counts in this checkout:

- train: 879 records
- validation: 110 records
- test: 110 records

Import without paid embeddings (Elasticsearch lexical fields are still indexed):

```bash
docker exec supportops_api python scripts/import_support_dataset.py \
  --dataset tweetsumm --file /datasets/external/tweetsumm/final_train_tweetsum.jsonl --user-id 3
```

Add `--with-embeddings` only when API cost has been explicitly approved.

