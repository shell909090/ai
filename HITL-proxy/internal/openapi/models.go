package openapi

// Operation represents a parsed OpenAPI operation.
type Operation struct {
	SpecID          int64  `json:"spec_id"`
	OperationID     string `json:"operation_id"`
	Method          string `json:"method"`
	Path            string `json:"path"`
	Summary         string `json:"summary"`
	Description     string `json:"description"`
	ParametersJSON  string `json:"parameters_json"`
	RequestBodyJSON string `json:"request_body_json"`
	Tags            string `json:"tags"`
}

// Dependency represents a dependency between two operations.
type Dependency struct {
	OperationID string `json:"operation_id"`
	DependsOnID string `json:"depends_on_id"`
	Reason      string `json:"reason"`
}
