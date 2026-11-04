# rbg-api sync scripts

`sync_from_rbg.py` extracts API types and generated client-go code from an rbg
repository revision.

```bash
python3 script/sync_from_rbg.py \
  --source ../rbg \
  --ref v0.8.0 \
  --version v0.8.0
```

The script:

1. copies `api/workloads` type, constants, scheme, and generated DeepCopy files;
2. copies the complete generated `client-go` tree;
3. rewrites client-go imports to `sigs.k8s.io/rbgs/api/client-go`;
4. formats the copied Go files;
5. updates the root Go module dependencies and runs `go mod tidy`.
6. updates version references in the README, root go.mod comments, and examples module.
