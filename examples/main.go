/*
Copyright 2026 The RBG Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

// RBG (RoleBasedGroup) Client-Go Demo
// This demo shows how to use client-go with sigs.k8s.io/rbgs/api to operate RBG objects.
//
// Features:
// 1. Create RoleBasedGroup object
// 2. Get RoleBasedGroup object
// 3. Update RoleBasedGroup object (e.g., modify replicas)
// 4. Delete RoleBasedGroup object
//
// Usage:
//   go run main.go -kubeconfig=/path/to/kubeconfig
//   If kubeconfig is not specified, it defaults to ~/.kube/config or in-cluster config

package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"

	"sigs.k8s.io/rbgs/api/workloads/constants"
	"sigs.k8s.io/rbgs/api/workloads/v1alpha2"
)

const (
	namespace = "default"
	rbgName   = "example-rbg"
	roleName  = "web-server"
)

func main() {
	var kubeconfig *string
	if home := homedir.HomeDir(); home != "" {
		kubeconfig = flag.String("kubeconfig", filepath.Join(home, ".kube", "config"), "(optional) absolute path to the kubeconfig file")
	} else {
		kubeconfig = flag.String("kubeconfig", "", "absolute path to the kubeconfig file")
	}
	flag.Parse()

	// Build Kubernetes config
	config, err := clientcmd.BuildConfigFromFlags("", *kubeconfig)
	if err != nil {
		fmt.Printf("Failed to build Kubernetes config: %v\n", err)
		os.Exit(1)
	}

	// Create dynamic client for CRD operations
	dynamicClient, err := dynamic.NewForConfig(config)
	if err != nil {
		fmt.Printf("Failed to create dynamic client: %v\n", err)
		os.Exit(1)
	}

	// Create standard Kubernetes client
	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		fmt.Printf("Failed to create clientset: %v\n", err)
		os.Exit(1)
	}

	ctx := context.Background()

	// Ensure namespace exists
	if err := ensureNamespace(ctx, clientset, namespace); err != nil {
		fmt.Printf("Failed to ensure namespace exists: %v\n", err)
		os.Exit(1)
	}

	// Get RBG GVR (GroupVersionResource)
	rbgGVR := schema.GroupVersionResource{
		Group:    "workloads.x-k8s.io",
		Version:  "v1alpha2",
		Resource: "rolebasedgroups",
	}

	// Create RBG resource interface
	rbgClient := dynamicClient.Resource(rbgGVR).Namespace(namespace)

	fmt.Println("========================================")
	fmt.Println("RBG Client-Go Demo")
	fmt.Println("========================================")

	// ========== Step 1: Create RBG object ==========
	fmt.Println("\n[Step 1] Creating RoleBasedGroup object...")
	if err := createRBG(ctx, rbgClient); err != nil {
		fmt.Printf("Failed to create RBG: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("✓ RBG created successfully")

	// Wait a moment for resource creation
	time.Sleep(2 * time.Second)

	// ========== Step 2: Get RBG object ==========
	fmt.Println("\n[Step 2] Getting RoleBasedGroup object...")
	rbg, err := getRBG(ctx, rbgClient, rbgName)
	if err != nil {
		fmt.Printf("Failed to get RBG: %v\n", err)
		os.Exit(1)
	}
	printRBG(rbg)

	// ========== Step 3: Update RBG object ==========
	fmt.Println("\n[Step 3] Updating RoleBasedGroup object (modifying replicas)...")
	if err := updateRBG(ctx, rbgClient, rbg); err != nil {
		fmt.Printf("Failed to update RBG: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("✓ RBG updated successfully")

	// Re-fetch to see the update result
	fmt.Println("\n[Step 3.1] Re-fetching to verify update result...")
	updatedRBG, err := getRBG(ctx, rbgClient, rbgName)
	if err != nil {
		fmt.Printf("Failed to get updated RBG: %v\n", err)
		os.Exit(1)
	}
	printRBG(updatedRBG)

	// ========== Step 4: List all RBG objects ==========
	fmt.Println("\n[Step 4] Listing all RoleBasedGroup objects...")
	if err := listRBGs(ctx, rbgClient); err != nil {
		fmt.Printf("Failed to list RBGs: %v\n", err)
		os.Exit(1)
	}

	// ========== Step 5: Delete RBG object ==========
	fmt.Println("\n[Step 5] Deleting RoleBasedGroup object...")
	if err := deleteRBG(ctx, rbgClient, rbgName); err != nil {
		fmt.Printf("Failed to delete RBG: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("✓ RBG deleted successfully")

	fmt.Println("\n========================================")
	fmt.Println("Demo completed successfully!")
	fmt.Println("========================================")
}

// ensureNamespace ensures the specified namespace exists
func ensureNamespace(ctx context.Context, clientset *kubernetes.Clientset, ns string) error {
	_, err := clientset.CoreV1().Namespaces().Get(ctx, ns, metav1.GetOptions{})
	if err != nil {
		if errors.IsNotFound(err) {
			// Create namespace
			namespace := &corev1.Namespace{
				ObjectMeta: metav1.ObjectMeta{
					Name: ns,
				},
			}
			_, err = clientset.CoreV1().Namespaces().Create(ctx, namespace, metav1.CreateOptions{})
			if err != nil {
				return fmt.Errorf("failed to create namespace: %w", err)
			}
			fmt.Printf("Created namespace: %s\n", ns)
		} else {
			return fmt.Errorf("failed to get namespace: %w", err)
		}
	}
	return nil
}

// createRBG creates a new RoleBasedGroup object
func createRBG(ctx context.Context, rbgClient dynamic.ResourceInterface) error {
	replicas := int32(3)
	partition := intstr.FromInt32(0)
	maxUnavailable := intstr.FromInt32(1)

	// Construct RBG object
	rbg := &v1alpha2.RoleBasedGroup{
		TypeMeta: metav1.TypeMeta{
			APIVersion: "workloads.x-k8s.io/v1alpha2",
			Kind:       "RoleBasedGroup",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name:      rbgName,
			Namespace: namespace,
			Labels: map[string]string{
				"app":        "example",
				"managed-by": "rbg-client-demo",
			},
		},
		Spec: v1alpha2.RoleBasedGroupSpec{
			Roles: []v1alpha2.RoleSpec{
				{
					Name:     roleName,
					Replicas: &replicas,
					Labels: map[string]string{
						"role": "web",
					},
					RolloutStrategy: &v1alpha2.RolloutStrategy{
						Type: v1alpha2.RollingUpdateStrategyType,
						RollingUpdate: &v1alpha2.RollingUpdate{
							Type:           v1alpha2.InPlaceIfPossibleUpdateStrategyType,
							Partition:      &partition,
							MaxUnavailable: &maxUnavailable,
						},
					},
					PodManagementPolicy: constants.ParallelPodManagement,
					// The workload type defaults to RoleInstanceSet. To use another workload,
					// set the constants.RoleWorkloadTypeAnnotationKey annotation on the role,
					// e.g. "apps/v1/StatefulSet".
					Pattern: v1alpha2.Pattern{
						StandalonePattern: &v1alpha2.StandalonePattern{
							TemplateSource: v1alpha2.TemplateSource{
								Template: &corev1.PodTemplateSpec{
									ObjectMeta: metav1.ObjectMeta{
										Labels: map[string]string{
											"app": "web-server",
										},
									},
									Spec: corev1.PodSpec{
										Containers: []corev1.Container{
											{
												Name:  "nginx",
												Image: "nginx:latest",
												Ports: []corev1.ContainerPort{
													{
														ContainerPort: 80,
														Protocol:      corev1.ProtocolTCP,
													},
												},
												Resources: corev1.ResourceRequirements{
													Requests: corev1.ResourceList{
														corev1.ResourceCPU:    resourceQuantity("100m"),
														corev1.ResourceMemory: resourceQuantity("128Mi"),
													},
													Limits: corev1.ResourceList{
														corev1.ResourceCPU:    resourceQuantity("500m"),
														corev1.ResourceMemory: resourceQuantity("256Mi"),
													},
												},
											},
										},
									},
								},
							},
						},
					},
				},
			},
		},
	}

	// Convert to unstructured object
	unstructuredObj, err := toUnstructured(rbg)
	if err != nil {
		return fmt.Errorf("failed to convert RBG to unstructured: %w", err)
	}

	// Create object
	_, err = rbgClient.Create(ctx, unstructuredObj, metav1.CreateOptions{})
	if err != nil {
		if errors.IsAlreadyExists(err) {
			fmt.Printf("RBG %s already exists, skipping creation\n", rbgName)
			return nil
		}
		return fmt.Errorf("failed to create RBG: %w", err)
	}

	return nil
}

// getRBG gets the specified RoleBasedGroup object
func getRBG(ctx context.Context, rbgClient dynamic.ResourceInterface, name string) (*v1alpha2.RoleBasedGroup, error) {
	unstructuredObj, err := rbgClient.Get(ctx, name, metav1.GetOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to get RBG: %w", err)
	}

	// Convert back to typed object
	rbg := &v1alpha2.RoleBasedGroup{}
	if err := fromUnstructured(unstructuredObj, rbg); err != nil {
		return nil, fmt.Errorf("failed to convert unstructured to RBG: %w", err)
	}

	return rbg, nil
}

// updateRBG updates the RoleBasedGroup object (modifying replicas)
func updateRBG(ctx context.Context, rbgClient dynamic.ResourceInterface, rbg *v1alpha2.RoleBasedGroup) error {
	// Change replicas from 3 to 5
	newReplicas := int32(5)
	if len(rbg.Spec.Roles) > 0 {
		rbg.Spec.Roles[0].Replicas = &newReplicas
	}

	// Convert to unstructured object (keep resourceVersion for update)
	unstructuredObj, err := toUnstructuredForUpdate(rbg)
	if err != nil {
		return fmt.Errorf("failed to convert RBG to unstructured: %w", err)
	}

	// Update object
	_, err = rbgClient.Update(ctx, unstructuredObj, metav1.UpdateOptions{})
	if err != nil {
		return fmt.Errorf("failed to update RBG: %w", err)
	}

	return nil
}

// listRBGs lists all RoleBasedGroup objects
func listRBGs(ctx context.Context, rbgClient dynamic.ResourceInterface) error {
	list, err := rbgClient.List(ctx, metav1.ListOptions{})
	if err != nil {
		return fmt.Errorf("failed to list RBGs: %w", err)
	}

	fmt.Printf("Found %d RoleBasedGroup object(s):\n", len(list.Items))
	for _, item := range list.Items {
		name := item.GetName()
		creationTime := item.GetCreationTimestamp()
		fmt.Printf("  - Name: %s, Created: %s\n", name, creationTime.Format(time.RFC3339))
	}

	return nil
}

// deleteRBG deletes the specified RoleBasedGroup object
func deleteRBG(ctx context.Context, rbgClient dynamic.ResourceInterface, name string) error {
	err := rbgClient.Delete(ctx, name, metav1.DeleteOptions{})
	if err != nil {
		if errors.IsNotFound(err) {
			fmt.Printf("RBG %s does not exist, no need to delete\n", name)
			return nil
		}
		return fmt.Errorf("failed to delete RBG: %w", err)
	}
	return nil
}

// printRBG prints detailed information of the RBG object
func printRBG(rbg *v1alpha2.RoleBasedGroup) {
	fmt.Printf("RBG Details:\n")
	fmt.Printf("  Name:        %s\n", rbg.Name)
	fmt.Printf("  Namespace:   %s\n", rbg.Namespace)
	fmt.Printf("  UID:         %s\n", rbg.UID)
	fmt.Printf("  Created:     %s\n", rbg.CreationTimestamp.Format(time.RFC3339))
	fmt.Printf("  Generation:  %d\n", rbg.Generation)

	if len(rbg.Spec.Roles) > 0 {
		role := rbg.Spec.Roles[0]
		fmt.Printf("\n  Role Info:\n")
		fmt.Printf("    Name:     %s\n", role.Name)
		if role.Replicas != nil {
			fmt.Printf("    Replicas: %d\n", *role.Replicas)
		}
		fmt.Printf("    WorkloadType: %s\n", role.GetWorkloadType())
		if role.PodManagementPolicy != "" {
			fmt.Printf("    PodManagementPolicy: %s\n", role.PodManagementPolicy)
		}
	}

	if len(rbg.Status.Conditions) > 0 {
		fmt.Printf("\n  Conditions:\n")
		for _, cond := range rbg.Status.Conditions {
			fmt.Printf("    Type: %s, Status: %s\n", cond.Type, cond.Status)
		}
	}

	if len(rbg.Status.RoleStatuses) > 0 {
		fmt.Printf("\n  Role Statuses:\n")
		for _, rs := range rbg.Status.RoleStatuses {
			fmt.Printf("    Name: %s, Ready: %d/%d, Updated: %d\n",
				rs.Name, rs.ReadyReplicas, rs.Replicas, rs.UpdatedReplicas)
		}
	}
}

// toUnstructured converts a typed object to an unstructured object
func toUnstructured(obj runtime.Object) (*unstructured.Unstructured, error) {
	// First convert to JSON
	jsonBytes, err := json.Marshal(obj)
	if err != nil {
		return nil, fmt.Errorf("marshal failed: %w", err)
	}

	// Then convert to unstructured
	unstructuredObj := &unstructured.Unstructured{}
	if err := unstructuredObj.UnmarshalJSON(jsonBytes); err != nil {
		return nil, fmt.Errorf("unmarshal to unstructured failed: %w", err)
	}

	// Clean up read-only fields that should not be sent to the API server
	cleanUpReadOnlyFields(unstructuredObj)

	return unstructuredObj, nil
}

// cleanUpReadOnlyFields removes read-only fields from the unstructured object
func cleanUpReadOnlyFields(obj *unstructured.Unstructured) {
	// Remove metadata.read-only fields (for create operation)
	metadata, found, _ := unstructured.NestedMap(obj.Object, "metadata")
	if found {
		delete(metadata, "creationTimestamp")
		delete(metadata, "resourceVersion")
		delete(metadata, "uid")
		delete(metadata, "selfLink")
		delete(metadata, "generation")
		unstructured.SetNestedMap(obj.Object, metadata, "metadata")
	}

	// Clean up template metadata in spec.roles
	roles, found, _ := unstructured.NestedSlice(obj.Object, "spec", "roles")
	if found {
		for i, role := range roles {
			if roleMap, ok := role.(map[string]interface{}); ok {
				// Clean up standalonePattern.template.metadata
				if template, found, _ := unstructured.NestedMap(roleMap, "standalonePattern", "template"); found {
					if metadata, found, _ := unstructured.NestedMap(template, "metadata"); found {
						delete(metadata, "creationTimestamp")
						unstructured.SetNestedMap(template, metadata, "metadata")
						unstructured.SetNestedMap(roleMap, template, "standalonePattern", "template")
					}
				}
				roles[i] = roleMap
			}
		}
		unstructured.SetNestedSlice(obj.Object, roles, "spec", "roles")
	}
}

// toUnstructuredForUpdate converts a typed object to an unstructured object for update operations
// It preserves resourceVersion but cleans up other read-only fields
func toUnstructuredForUpdate(obj runtime.Object) (*unstructured.Unstructured, error) {
	// First convert to JSON
	jsonBytes, err := json.Marshal(obj)
	if err != nil {
		return nil, fmt.Errorf("marshal failed: %w", err)
	}

	// Then convert to unstructured
	unstructuredObj := &unstructured.Unstructured{}
	if err := unstructuredObj.UnmarshalJSON(jsonBytes); err != nil {
		return nil, fmt.Errorf("unmarshal to unstructured failed: %w", err)
	}

	// Clean up read-only fields but keep resourceVersion for update
	metadata, found, _ := unstructured.NestedMap(unstructuredObj.Object, "metadata")
	if found {
		delete(metadata, "creationTimestamp")
		delete(metadata, "uid")
		delete(metadata, "selfLink")
		delete(metadata, "generation")
		// Note: resourceVersion is kept for update operations
		unstructured.SetNestedMap(unstructuredObj.Object, metadata, "metadata")
	}

	// Clean up template metadata in spec.roles
	roles, found, _ := unstructured.NestedSlice(unstructuredObj.Object, "spec", "roles")
	if found {
		for i, role := range roles {
			if roleMap, ok := role.(map[string]interface{}); ok {
				// Clean up standalonePattern.template.metadata
				if template, found, _ := unstructured.NestedMap(roleMap, "standalonePattern", "template"); found {
					if metadata, found, _ := unstructured.NestedMap(template, "metadata"); found {
						delete(metadata, "creationTimestamp")
						unstructured.SetNestedMap(template, metadata, "metadata")
						unstructured.SetNestedMap(roleMap, template, "standalonePattern", "template")
					}
				}
				roles[i] = roleMap
			}
		}
		unstructured.SetNestedSlice(unstructuredObj.Object, roles, "spec", "roles")
	}

	return unstructuredObj, nil
}

// fromUnstructured converts an unstructured object to a typed object
func fromUnstructured(unstructuredObj *unstructured.Unstructured, obj runtime.Object) error {
	jsonBytes, err := unstructuredObj.MarshalJSON()
	if err != nil {
		return fmt.Errorf("marshal unstructured failed: %w", err)
	}

	if err := json.Unmarshal(jsonBytes, obj); err != nil {
		return fmt.Errorf("unmarshal failed: %w", err)
	}

	return nil
}

// resourceQuantity helper function to create resource.Quantity
func resourceQuantity(s string) resource.Quantity {
	return resource.MustParse(s)
}
