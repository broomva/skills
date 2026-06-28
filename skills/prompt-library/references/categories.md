# Prompt Categories

## Taxonomy

| Category | Description | Examples |
|----------|-------------|----------|
| `system-prompts` | Persona and behavior-defining prompts that set the agent's role, constraints, and output format | Code Review Agent, Brutally Honest Advisor, Deep Thinking Directive |
| `agent-instructions` | Step-by-step workflow instructions for multi-phase tasks | Content Creation Pipeline, Codebase Deep Analysis, Agentic Development Loop |
| `templates` | Structural templates with high variable density, designed to be filled in per use case | Ontology & State Design, UX Interaction Design, Prompt Engineering Guide |
| `chains` | Multi-prompt sequences where the output of one feeds the input of the next | (future: research-then-write, analyze-then-fix) |
| `evaluators` | Prompts that judge or score the output of other prompts or agent actions | (future: output-quality-scorer, safety-checker) |

## Adding a New Category

1. Add the category to this file with description and examples
2. Use it in prompt frontmatter: `category: your-new-category`
3. The API and UI filter automatically pick it up
