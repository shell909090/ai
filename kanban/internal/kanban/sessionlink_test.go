package kanban

import (
	"strings"
	"testing"
)

func TestFormatSessionRef(t *testing.T) {
	cases := []struct {
		name      string
		baseURL   string
		workdir   string
		sessionID string
		want      string
	}{
		{
			name:      "empty session id",
			baseURL:   "http://x:4096",
			workdir:   "/home/shell/tmp/kanban",
			sessionID: "",
			want:      "",
		},
		{
			name:      "kanban workdir",
			baseURL:   "http://x:4096",
			workdir:   "/home/shell/tmp/kanban",
			sessionID: "ses_1",
			want:      "[ses_1](http://x:4096/L2hvbWUvc2hlbGwvdG1wL2thbmJhbg/session/ses_1)",
		},
		{
			name:      "trailing slash on base url",
			baseURL:   "http://x:4096/",
			workdir:   "/home/shell/tmp/kanban",
			sessionID: "ses_1",
			want:      "[ses_1](http://x:4096/L2hvbWUvc2hlbGwvdG1wL2thbmJhbg/session/ses_1)",
		},
		{
			name:      "https base",
			baseURL:   "https://opencode.example.com",
			workdir:   "/home/shell/tmp/kanban",
			sessionID: "ses_abc",
			want:      "[ses_abc](https://opencode.example.com/L2hvbWUvc2hlbGwvdG1wL2thbmJhbg/session/ses_abc)",
		},
		{
			name:      "root workdir",
			baseURL:   "http://x:4096",
			workdir:   "/",
			sessionID: "ses_root",
			want:      "[ses_root](http://x:4096/Lw/session/ses_root)",
		},
		{
			name:      "utf-8 workdir",
			baseURL:   "http://x:4096",
			workdir:   "/home/用户/项目",
			sessionID: "ses_中文",
			want:      "[ses_中文](http://x:4096/L2hvbWUv55So5oi3L-mhueebrg/session/ses_中文)",
		},
		{
			name:      "real session id from opencode",
			baseURL:   "http://opencode.home:1234",
			workdir:   "/home/shell/tmp/kanban",
			sessionID: "ses_116a4e22dffe6j32Y01bVDbJup",
			want:      "[ses_116a4e22dffe6j32Y01bVDbJup](http://opencode.home:1234/L2hvbWUvc2hlbGwvdG1wL2thbmJhbg/session/ses_116a4e22dffe6j32Y01bVDbJup)",
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := formatSessionRef(c.baseURL, c.workdir, c.sessionID); got != c.want {
				t.Errorf("formatSessionRef(%q, %q, %q) = %q, want %q",
					c.baseURL, c.workdir, c.sessionID, got, c.want)
			}
		})
	}
}

// TestFormatSessionRefMatchesOpencodeWeb locks the encoding against
// the canonical example URL the user provided. If the encoding ever
// drifts, this test fails before any user-visible breakage.
func TestFormatSessionRefMatchesOpencodeWeb(t *testing.T) {
	got := formatSessionRef("http://opencode.home:1234", "/home/shell/tmp/kanban", "ses_116a4e22dffe6j32Y01bVDbJup")
	want := "http://opencode.home:1234/L2hvbWUvc2hlbGwvdG1wL2thbmJhbg/session/ses_116a4e22dffe6j32Y01bVDbJup"
	if !strings.Contains(got, want) {
		t.Errorf("formatSessionRef output %q does not contain the opencode web URL %q", got, want)
	}
}
