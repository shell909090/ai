package openapi

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
)

// minimalSpec is a valid OpenAPI 3.0 document with:
//   - 2 operations (listPets GET /pets, getPet GET /pets/{petId})
//   - 1 securityScheme (ApiKeyAuth)
//   - no global security field
const minimalSpec = `{
  "openapi": "3.0.0",
  "info": {"title": "Test", "version": "1.0.0"},
  "paths": {
    "/pets": {
      "get": {
        "operationId": "listPets",
        "summary": "List all pets",
        "tags": ["pets"],
        "parameters": [
          {
            "name": "limit",
            "in": "query",
            "schema": {"type": "integer"}
          }
        ],
        "responses": {"200": {"description": "ok"}}
      }
    },
    "/pets/{petId}": {
      "get": {
        "operationId": "getPet",
        "summary": "Get a pet",
        "parameters": [
          {
            "name": "petId",
            "in": "path",
            "required": true,
            "schema": {"type": "integer"}
          }
        ],
        "responses": {"200": {"description": "ok"}}
      }
    }
  },
  "components": {
    "securitySchemes": {
      "ApiKeyAuth": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key"
      }
    }
  }
}`

// specWithGlobalSecurity adds a global security requirement.
const specWithGlobalSecurity = `{
  "openapi": "3.0.0",
  "info": {"title": "Test", "version": "1.0.0"},
  "security": [{"ApiKeyAuth": []}],
  "paths": {
    "/items": {
      "get": {
        "operationId": "listItems",
        "responses": {"200": {"description": "ok"}}
      }
    }
  },
  "components": {
    "securitySchemes": {
      "ApiKeyAuth": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key"
      }
    }
  }
}`

func TestParseSpec_Operations(t *testing.T) {
	ctx := context.Background()
	ops, _, _, _, err := ParseSpec(ctx, 42, []byte(minimalSpec))
	if err != nil {
		t.Fatalf("ParseSpec: %v", err)
	}

	if len(ops) != 2 {
		t.Fatalf("expected 2 operations, got %d", len(ops))
	}

	// Build a lookup by operationId for order-independent checks.
	byID := make(map[string]Operation, len(ops))
	for _, op := range ops {
		byID[op.OperationID] = op
	}

	listPets, ok := byID["listPets"]
	if !ok {
		t.Fatal("operation listPets not found")
	}
	if listPets.SpecID != 42 {
		t.Errorf("listPets.SpecID: want 42, got %d", listPets.SpecID)
	}
	if listPets.Method != "GET" {
		t.Errorf("listPets.Method: want GET, got %q", listPets.Method)
	}
	if listPets.Path != "/pets" {
		t.Errorf("listPets.Path: want /pets, got %q", listPets.Path)
	}
	if listPets.Summary != "List all pets" {
		t.Errorf("listPets.Summary: want %q, got %q", "List all pets", listPets.Summary)
	}
	if !strings.Contains(listPets.Tags, "pets") {
		t.Errorf("listPets.Tags: expected to contain 'pets', got %q", listPets.Tags)
	}

	getPet, ok := byID["getPet"]
	if !ok {
		t.Fatal("operation getPet not found")
	}
	if getPet.Path != "/pets/{petId}" {
		t.Errorf("getPet.Path: want /pets/{petId}, got %q", getPet.Path)
	}
}

func TestParseSpec_SecuritySchemes(t *testing.T) {
	ctx := context.Background()
	_, _, schemesJSON, _, err := ParseSpec(ctx, 1, []byte(minimalSpec))
	if err != nil {
		t.Fatalf("ParseSpec: %v", err)
	}

	var schemes map[string]SecurityScheme
	if err := json.Unmarshal([]byte(schemesJSON), &schemes); err != nil {
		t.Fatalf("unmarshal schemesJSON: %v", err)
	}

	apiKey, ok := schemes["ApiKeyAuth"]
	if !ok {
		t.Fatal("expected ApiKeyAuth in security schemes")
	}
	if apiKey.Type != "apiKey" {
		t.Errorf("ApiKeyAuth.Type: want apiKey, got %q", apiKey.Type)
	}
	if apiKey.In != "header" {
		t.Errorf("ApiKeyAuth.In: want header, got %q", apiKey.In)
	}
	if apiKey.Name != "X-API-Key" {
		t.Errorf("ApiKeyAuth.Name: want X-API-Key, got %q", apiKey.Name)
	}
}

func TestParseSpec_NoGlobalSecurity_IsNull(t *testing.T) {
	ctx := context.Background()
	_, _, _, globalSecJSON, err := ParseSpec(ctx, 1, []byte(minimalSpec))
	if err != nil {
		t.Fatalf("ParseSpec: %v", err)
	}
	if globalSecJSON != "null" {
		t.Errorf("globalSecJSON: want %q, got %q", "null", globalSecJSON)
	}
}

func TestParseSpec_WithGlobalSecurity(t *testing.T) {
	ctx := context.Background()
	_, _, _, globalSecJSON, err := ParseSpec(ctx, 1, []byte(specWithGlobalSecurity))
	if err != nil {
		t.Fatalf("ParseSpec: %v", err)
	}
	if globalSecJSON == "null" {
		t.Error("expected non-null globalSecJSON when spec has security field")
	}
	// Should be parseable as a JSON array.
	var sec []map[string][]string
	if err := json.Unmarshal([]byte(globalSecJSON), &sec); err != nil {
		t.Errorf("unmarshal globalSecJSON: %v", err)
	}
	if len(sec) == 0 {
		t.Error("expected at least one security requirement")
	}
}

func TestParseSpec_InvalidJSON(t *testing.T) {
	ctx := context.Background()
	_, _, _, _, err := ParseSpec(ctx, 1, []byte(`{not valid json`))
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

func TestParseSpec_AnalyzeDependencies(t *testing.T) {
	ctx := context.Background()
	_, deps, _, _, err := ParseSpec(ctx, 1, []byte(minimalSpec))
	if err != nil {
		t.Fatalf("ParseSpec: %v", err)
	}

	// getPet /pets/{petId} should depend on listPets /pets.
	found := false
	for _, d := range deps {
		if d.OperationID == "getPet" && d.DependsOnID == "listPets" {
			found = true
			if !strings.Contains(d.Reason, "petId") {
				t.Errorf("dependency reason should mention petId, got %q", d.Reason)
			}
		}
	}
	if !found {
		t.Errorf("expected dependency getPet -> listPets, got deps: %+v", deps)
	}
}

func TestParseSpec_SpecID_PropagatedToAllOps(t *testing.T) {
	ctx := context.Background()
	const specID int64 = 99
	ops, _, _, _, err := ParseSpec(ctx, specID, []byte(minimalSpec))
	if err != nil {
		t.Fatalf("ParseSpec: %v", err)
	}
	for _, op := range ops {
		if op.SpecID != specID {
			t.Errorf("op %q: SpecID want %d, got %d", op.OperationID, specID, op.SpecID)
		}
	}
}
