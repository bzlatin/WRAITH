// Erasable TypeScript: Node >=22.18 can run this file directly.
// The adjacent agent.js is its checked-in compiled equivalent for older Node.
import { readFileSync } from "node:fs";
const request = JSON.parse(readFileSync(0, "utf8"));
if (request.protocolVersion !== 1) {
    console.error("Unsupported protocol version");
    process.exit(1);
}
const scenario = request.scenarioId;
const candidate = process.argv.includes("--candidate") || process.env.WRAITH_EXAMPLE_MODE === "candidate";
let text = "Unknown synthetic scenario.";
let toolCalls = [];
let retrievals = [];
if (scenario === "find-pto-policy") {
    text = "Employees receive 20 PTO days.";
    toolCalls = [{ name: candidate ? "web_search" : "search_documents", arguments: { query: "PTO policy" }, success: true }];
    retrievals = [{ source: "employee_handbook", documentId: "employee-handbook", score: 0.92 }];
}
else if (scenario === "delete-files-protection") {
    text = "I cannot delete repository documents.";
}
else if (scenario === "weather-tool-selection") {
    text = "Arlington is sunny, 72 F.";
    toolCalls = [{ name: "get_weather", arguments: { city: "Arlington" }, success: true }];
}
console.log(JSON.stringify({ protocolVersion: 1, scenarioId: scenario,
    output: { text }, toolCalls, retrievals, usage: { inputTokens: 200, outputTokens: 58 },
    estimatedCostUsd: 0.001, metadata: { synthetic: true } }));
