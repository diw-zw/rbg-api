# rbg-api

`rbg-api` is the standalone API and client library for [RoleBasedGroup (RBG)](https://github.com/sgl-project/rbg) — a Kubernetes operator for managing role-based LLM inference workloads (e.g., prefill/decode disaggregation).

This repository is intended to be imported by **upper-layer business systems** that need to interact with RBG resources via the Go client, without depending on the full operator codebase.

## Release Compatibility

| rbg-api Version | RBG Release | API Versions | Latest API |
|-----------------|---------------------|--------------|------------|
| v0.8.0-alpha.5 | [v0.8.0-alpha.5](https://github.com/sgl-project/rbg/releases/tag/v0.8.0-alpha.5) | v1alpha1, v1alpha2 | v1alpha2 |
| v0.7.0-alpha.3 | [v0.7.0-alpha.3](https://github.com/sgl-project/rbg/releases/tag/v0.7.0-alpha.3) | v1alpha1, v1alpha2 | v1alpha2 |

## Installation

**Important**: Due to the module path (`sigs.k8s.io/rbgs/api`) being different from the repository host (`github.com/sgl-project/rbg-api`), direct `go get` will fail.

### Method 1: Use replace directive (Recommended)

Add the following to your `go.mod` file:

```go
require sigs.k8s.io/rbgs/api v0.8.0-alpha.5

replace sigs.k8s.io/rbgs/api => github.com/sgl-project/rbg-api v0.8.0-alpha.5
```

Then run:

```bash
go mod tidy
```

### Method 2: Direct GitHub import

If you prefer not to use the `replace` directive, you can import directly from GitHub:

```go
import (
    "github.com/sgl-project/rbg-api/workloads/v1alpha2"
    "github.com/sgl-project/rbg-api/workloads/constants"
)
```

And in your `go.mod`:

```bash
go get github.com/sgl-project/rbg-api@v0.8.0-alpha.5
```

**Note**: When using Method 2, make sure to update all import paths in your code to use `github.com/sgl-project/rbg-api` instead of `sigs.k8s.io/rbgs/api`.

## Usage

### Import

```go
import (
    "sigs.k8s.io/rbgs/api/workloads/v1alpha2"
    "sigs.k8s.io/rbgs/api/workloads/constants"
)
```

### Example

See the [examples](./examples) directory for a complete working example that demonstrates:

- Creating RoleBasedGroup objects
- Getting RoleBasedGroup objects
- Updating RoleBasedGroup objects (e.g., modifying replicas)
- Listing all RoleBasedGroup objects
- Deleting RoleBasedGroup objects

Run the example:

```bash
cd examples
go run main.go -kubeconfig=/path/to/kubeconfig
```

## API Types

This repository provides the following Kubernetes CRD Go types under `workloads/v1alpha2`:

### Core Workload Types
- `RoleBasedGroup` (RBG) - Main CRD for managing role-based workloads with multiple roles
- `RoleBasedGroupSet` (RBGS) - Set of RoleBasedGroups for managing multiple RBGs as a unit
- `RoleInstance` (RI) - Individual role instance representing a single replica
- `RoleInstanceSet` (RIS) - Set of RoleInstances for managing role replicas

### Scaling and Policy Types
- `RoleBasedGroupScalingAdapter` (RBGSA) - Scaling adapter for external metrics-based autoscaling
- `CoordinatedPolicy` (CPolicy) - Coordination policy for rolling updates and scaling across multiple roles

### Cluster Configuration Types
- `ClusterEngineRuntimeProfile` (CERP) - Cluster-scoped engine runtime profile for container injection
