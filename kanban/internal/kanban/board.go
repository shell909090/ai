package kanban

import "context"

// CardID is an opaque, board-scoped card identifier. The underlying
// representation is string, but callers must not parse or construct
// raw ID values — treat it as a map key and pass it back to the same
// BoardGateway that returned it.
type CardID string

// CardSnapshot is a point-in-time view of a board card.
type CardSnapshot struct {
	ID          CardID
	Title       string
	Description string
	URL         string
	List        string   // logical list name (todo/doing/done)
	Labels      []string // label names
}

// BoardGateway abstracts the underlying kanban board backend.
// All list names are logical ("todo", "doing", "done"); backend-specific
// identifiers are an implementation detail of the concrete type.
// Label operations use label names; ID resolution is internal to the implementation.
type BoardGateway interface {
	ListCards(ctx context.Context, listName string) ([]CardSnapshot, error)
	GetCard(ctx context.Context, id CardID) (CardSnapshot, error)
	MoveCard(ctx context.Context, id CardID, listName string) error
	AddComment(ctx context.Context, id CardID, text string) error
	AddLabel(ctx context.Context, id CardID, labelName string) error
	RemoveLabel(ctx context.Context, id CardID, labelName string) error
	CreateCard(ctx context.Context, listName, title, description string, labels []string) (CardSnapshot, error)
}
