// Session link rendering: builds the markdown link that appears in
// every Trello comment that mentions an opencode session id (▶️
// Started / ✅ Completed / ❌ Error). The link points at the
// opencode web session URL, which is constructed as
//
//	<baseURL>/<base64url(workdir)>/session/<sessionID>
//
// The base64url encoding matches opencode's own implementation in
// packages/core/src/util/encode.ts:base64Encode. See design.md §6.4.1
// for the full rationale and the source of the encoding rule.
package kanban

import (
	"encoding/base64"
	"strings"
)

// formatSessionRef renders sessionID as a markdown link to the
// corresponding opencode web session URL. An empty sessionID returns
// the empty string. A trailing slash on baseURL is tolerated.
//
// The link is the canonical place for humans to click through to
// opencode web from Trello; all session-id mentions in comments must
// go through this function so the encoding stays consistent.
func formatSessionRef(baseURL, workdir, sessionID string) string {
	if sessionID == "" {
		return ""
	}
	base := strings.TrimRight(baseURL, "/")
	encoded := base64.RawURLEncoding.EncodeToString([]byte(workdir))
	return "[" + sessionID + "](" + base + "/" + encoded + "/session/" + sessionID + ")"
}
