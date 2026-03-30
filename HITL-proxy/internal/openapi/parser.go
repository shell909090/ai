package openapi

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"github.com/getkin/kin-openapi/openapi3"
)

var pathParamRe = regexp.MustCompile(`\{(\w+)\}`)

// ParseSpec parses an OpenAPI spec and returns operations, dependencies,
// the spec-level security schemes JSON (map[schemeName]SecurityScheme),
// and the spec-level global security requirements JSON.
func ParseSpec(ctx context.Context, specID int64, raw []byte) ([]Operation, []Dependency, string, string, error) {
	loader := openapi3.NewLoader()
	doc, err := loader.LoadFromData(raw)
	if err != nil {
		return nil, nil, "", "", fmt.Errorf("load spec: %w", err)
	}

	if err := doc.Validate(ctx, openapi3.DisableExamplesValidation(), openapi3.DisableSchemaDefaultsValidation()); err != nil {
		return nil, nil, "", "", fmt.Errorf("validate spec: %w", err)
	}

	// Extract security scheme definitions from components.
	schemes := make(map[string]SecurityScheme)
	if doc.Components != nil {
		for name, ref := range doc.Components.SecuritySchemes {
			if ref == nil || ref.Value == nil {
				continue
			}
			s := ref.Value
			schemes[name] = SecurityScheme{
				Type:   s.Type,
				Scheme: s.Scheme,
				In:     s.In,
				Name:   s.Name,
			}
		}
	}
	schemesJSON, _ := json.Marshal(schemes)

	// Extract global (spec-level) security requirements.
	globalSecJSON := []byte("null")
	if doc.Security != nil {
		globalSecJSON, _ = json.Marshal(doc.Security)
	}

	var ops []Operation
	for path, pathItem := range doc.Paths.Map() {
		for method, op := range pathItem.Operations() {
			if op.OperationID == "" {
				continue
			}

			paramsJSON, _ := json.Marshal(op.Parameters)
			bodyJSON := []byte("{}")
			if op.RequestBody != nil {
				bodyJSON, _ = json.Marshal(op.RequestBody)
			}

			// Serialize per-operation security requirements.
			// nil Security means "inherit global"; store as "null".
			secJSON := []byte("null")
			if op.Security != nil {
				secJSON, _ = json.Marshal(op.Security)
			}

			tags := strings.Join(op.Tags, ",")

			ops = append(ops, Operation{
				SpecID:          specID,
				OperationID:     op.OperationID,
				Method:          strings.ToUpper(method),
				Path:            path,
				Summary:         op.Summary,
				Description:     op.Description,
				ParametersJSON:  string(paramsJSON),
				RequestBodyJSON: string(bodyJSON),
				Tags:            tags,
				SecurityJSON:    string(secJSON),
			})
		}
	}

	deps := analyzeDependencies(ops)
	return ops, deps, string(schemesJSON), string(globalSecJSON), nil
}

// analyzeDependencies detects dependencies between operations.
// If an operation has path parameters like {id}, it likely depends on
// a list/GET operation on the parent path to obtain that parameter.
func analyzeDependencies(ops []Operation) []Dependency {
	// Build index: path → operations
	pathOps := make(map[string][]Operation)
	for _, op := range ops {
		pathOps[op.Path] = append(pathOps[op.Path], op)
	}

	var deps []Dependency
	for _, op := range ops {
		params := pathParamRe.FindAllStringSubmatch(op.Path, -1)
		if len(params) == 0 {
			continue
		}

		// Find parent path by removing the last segment
		lastSlash := strings.LastIndex(op.Path, "/")
		if lastSlash <= 0 {
			continue
		}
		parentPath := op.Path[:lastSlash]

		// Look for GET operations on the parent path
		for _, parentOp := range pathOps[parentPath] {
			if parentOp.Method == "GET" && parentOp.OperationID != op.OperationID {
				paramNames := make([]string, 0, len(params))
				for _, p := range params {
					paramNames = append(paramNames, p[1])
				}
				deps = append(deps, Dependency{
					OperationID: op.OperationID,
					DependsOnID: parentOp.OperationID,
					Reason:      fmt.Sprintf("needs %s from list endpoint", strings.Join(paramNames, ", ")),
				})
			}
		}
	}

	return deps
}
