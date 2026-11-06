const fs = require("node:fs");

try {
  const report = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  if (!report.total || Object.keys(report).length < 2) {
    throw new Error("Coverage report must contain totals and source files");
  }
  for (const [name, entry] of Object.entries(report)) {
    const minimum = name === "total" ? 75 : 50;
    const percent = entry?.lines?.pct;
    if (typeof percent !== "number" || !Number.isFinite(percent) || percent < minimum || percent > 100) {
      throw new Error(`${name}: invalid or insufficient line coverage (${percent}; minimum ${minimum}%)`);
    }
  }
} catch (error) {
  console.error(`Coverage check failed: ${error.message}`);
  process.exitCode = 1;
}
