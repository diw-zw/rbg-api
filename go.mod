// Module: sigs.k8s.io/rbgs/api
//
// This is the API module for RoleBasedGroup (RBG), a Kubernetes operator for managing
// role-based LLM inference workloads.
//
// Repository: https://github.com/sgl-project/rbg-api
//
// WARNING: The module path uses the sigs.k8s.io domain (sigs.k8s.io/rbgs/api), but the
// actual source code is hosted on GitHub at github.com/sgl-project/rbg-api. These two
// do not match, so direct `go get sigs.k8s.io/rbgs/api` will FAIL.
//
// To use this module, you MUST add a replace directive in your go.mod:
//
//   require sigs.k8s.io/rbgs/api v0.8.0
//   replace sigs.k8s.io/rbgs/api => github.com/sgl-project/rbg-api v0.8.0
//
// Alternatively, you can import directly from GitHub:
//   import "github.com/sgl-project/rbg-api/workloads/v1alpha2"
//   go get github.com/sgl-project/rbg-api@v0.8.0
module sigs.k8s.io/rbgs/api

go 1.25.0

require (
	k8s.io/api v0.34.2
	k8s.io/apimachinery v0.34.2
)

require (
	github.com/fxamacker/cbor/v2 v2.9.0 // indirect
	github.com/kr/text v0.2.0 // indirect
	github.com/x448/float16 v0.8.4 // indirect
	go.yaml.in/yaml/v2 v2.4.2 // indirect
	sigs.k8s.io/randfill v1.0.0 // indirect
	sigs.k8s.io/structured-merge-diff/v6 v6.3.0 // indirect
)

require (
	github.com/davecgh/go-spew v1.1.2-0.20180830191138-d8f796af33cc // indirect
	github.com/go-logr/logr v1.4.3 // indirect
	github.com/gogo/protobuf v1.3.2 // indirect
	github.com/json-iterator/go v1.1.12 // indirect
	github.com/modern-go/concurrent v0.0.0-20180306012644-bacd9c7ef1dd // indirect
	github.com/modern-go/reflect2 v1.0.3-0.20250322232337-35a7c28c31ee // indirect
	github.com/spf13/pflag v1.0.10 // indirect
	golang.org/x/net v0.43.0 // indirect
	golang.org/x/text v0.28.0 // indirect
	gopkg.in/inf.v0 v0.9.1 // indirect
	k8s.io/klog/v2 v2.130.1 // indirect
	k8s.io/utils v0.0.0-20250604170112-4c0f3b243397 // indirect
	sigs.k8s.io/json v0.0.0-20241014173422-cfa47c3a1cc8 // indirect
)
