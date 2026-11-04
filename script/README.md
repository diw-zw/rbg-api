# rbg-api sync scripts

`sync_from_rbg.py` extracts API types from an rbg repository revision.

The script:

1. copies `api/workloads` type, constants, scheme, and generated DeepCopy files;
2. does not copy the generated `client-go` tree;
3. formats the copied Go files;
4. updates the root Go module dependencies and runs `go mod tidy`;
5. updates version references in the README, root go.mod comments, and examples module.

## Complete sync workflow

Run the commands below from the root of the `rbg-api` repository.

### 1. Set the version and source repository

Use the same tag or branch name for both the rbg source revision and the
`rbg-api` release version.

```bash
export VERSION=v0.8.0
export RBG_SOURCE=../rbg
```

Ensure the local rbg repository has the target tag. If necessary, fetch tags
first:

```bash
git -C "$RBG_SOURCE" fetch --tags
git -C "$RBG_SOURCE" tag --list "$VERSION"
```

### 2. Create or switch to the release branch

Create the matching `rbg-api` release branch:

```bash
git switch -c "release/$VERSION"
```

If the branch already exists, switch to it instead:

```bash
git switch "release/$VERSION"
```

### 3. Run the sync script

```bash
python3 script/sync_from_rbg.py \
  --source "$RBG_SOURCE" \
  --ref "$VERSION" \
  --version "$VERSION"
```

The script replaces the existing `workloads/` tree with the selected files,
removes any stale `client-go/` tree, formats the copied Go code, and updates
`go.mod`, `go.sum`, `README.md`, and `examples/go.mod`.

### 4. Verify the result

```bash
go test ./...
git diff --check
git status --short
```

Inspect the diff before committing. In particular, confirm that validation,
conversion, webhook, admission, defaulting, helper, and test files were not
copied into `workloads/`.

### 5. Commit the sync result

```bash
git add README.md go.mod go.sum examples/go.mod workloads script
git commit -m "feat(api): sync public API from rbg $VERSION"
```

### 6. Push the release branch

```bash
git push -u origin "release/$VERSION"
```

After the branch is reviewed and merged, create and publish the matching
`v$VERSION` Git tag from the `rbg-api` repository if that is the intended
release process.
