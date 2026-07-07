---
name: traveler-experience-lab
description: Use when a Product Engineer wants to run `/mrt scenario` or `/mrt diagnose`, ground a traveler-experience problem in MyRealTrip inventory, combine de-identified VoC with travel products, or generate a thin scenario/experiment/QA brief for MyRealTrip.
---

# Traveler Experience Lab

Use this skill to help a MyRealTrip Product Engineer turn traveler experience work into a grounded, thin brief. The plugin has two wedge workflows:

- `/mrt scenario`: build a traveler scenario from real MyRealTrip inventory.
- `/mrt diagnose`: structure de-identified VoC, then hand off to scenario work.

The canonical command instructions live in `commands/`. Read the relevant command file before acting:

- For scenario work, read `commands/scenario.md`.
- For VoC diagnosis, read `commands/diagnose.md`.
- If both apply, run diagnose first, then scenario.

## Grounding Rules

- Do not invent product candidates. All product data MUST come from the adapter CLI, which normalizes MCP responses into ProductCandidate rows.
- **Canonical data path (ADR 0001):** use the adapter CLI from the plugin root — this is the ONLY supported source of ScenarioFixture material:
  - `python3 -m core.cli fetch <tool> --args '{...}'`  → normalized candidates (use this to build scenarios)
  - `python3 -m core.cli list-tools-raw`  → inputSchema, when unsure of arguments (debugging)
- **Do NOT call the `myrealtrip` MCP server (`.mcp.json`) to build scenarios.** It is allowed for human native exploration/debugging only; its raw tool output must never be normalized by hand. Likewise `core.cli call` is a raw debugging surface — not a data source. (See [ADR 0001](../../docs/adr/0001-adapter-cli-canonical-data-path.md).)
- Argument reminders (see [docs/schema/field_notes.md](../../docs/schema/field_notes.md)):
  - `searchTnas` uses `query` (not `keyword`); `searchStays` uses `keyword` + `checkIn` + `checkOut`.
  - Use `searchInternationalFlights` or `searchDomesticFlights` per destination type.
  - Date-specific TNA availability: chain `searchTnas` → `getTnaOptions` (fetch both).
  - Stay detail: chain `searchStays` → `getStayDetail` (fetch both).

## Security Rules

- Do not accept or forward customer names, phone numbers, email addresses, reservation numbers, payment data, or other PII.
- VoC must be a de-identified summary only.
- Before any external MCP call, state the non-sensitive fields being sent, such as destination, date, party size, and product query.
- Never perform booking, payment, cancellation, or account-changing actions.

## Output Shape

For `/mrt scenario`, include:

1. Traveler scenario
2. Real product candidates with source/tool provenance
3. Domain edge cases
4. Experiment draft
5. QA draft

For `/mrt diagnose`, include:

1. VoC-to-journey mapping
2. Friction type and severity/frequency
3. Scenario handoff prompts

Keep the result focused on the two moats: real inventory and real de-identified VoC.
