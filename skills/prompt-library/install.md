# Prompt Library installed

The `prompt-library` skill is now available. Your agent can pull, list, push, and update prompts from [broomva.tech/prompts](https://broomva.tech/prompts) or any compatible endpoint.

## Try it

Ask your agent:

- "Pull the code-review-agent prompt"
- "List available prompts"
- "Save this as a prompt for later"
- "Push this prompt to the library" (requires auth token)

## Remote access

To push prompts over the air:

1. Log in at [broomva.tech](https://broomva.tech) via OAuth
2. Get your token: `curl https://broomva.tech/api/auth/api-token`
3. Set it: `export BROOMVA_API_TOKEN="your-token"`
4. Push: `prompt-sync.py remote-push --title "..." --category system-prompts --body "..."`

## API endpoint

Default: `https://broomva.tech/api/prompts`

Override with `--endpoint` in the sync script, or point to your own prompt repository.
