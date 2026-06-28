# Content Brief Intake

## Purpose

The content brief is the single source of truth for the entire publishing package. A well-structured brief eliminates ambiguity downstream — every adaptation, media asset, and CTA traces back to decisions made here.

## Gathering the Brief

### When the user provides a full brief
Accept it as-is. Validate completeness against required fields. Fill obvious gaps with sensible defaults and confirm.

### When the user provides only a topic
Use this questioning sequence (ask all at once, not one-by-one):

1. **Who is this for?** (developers, founders, general audience, specific community)
2. **What should they do after reading?** (try something, follow, subscribe, share, change their thinking)
3. **What's the core insight?** (the one thing that makes this worth reading)
4. **Any references or prior work to build on?** (URLs, posts, papers, experiences)
5. **Which platforms matter most?** (all, or prioritize specific ones)

If the user says "just write it," infer from context:
- Topic complexity → audience level
- User's own expertise → tone
- Topic novelty → intent (educate if new, persuade if contrarian, announce if launch)

### When the user provides a reference URL
Extract the reference content first (using `/agent-browser` or FxTwitter API for X posts), then ask: "Do you want to respond to this, build on it, or create something inspired by it?"

## Brief Validation

A brief is **complete** when you can answer:
- What is the **one sentence** this post exists to communicate?
- Who **specifically** will find this valuable?
- What **action** should they take?
- What **evidence** supports the core claim?

A brief is **too vague** when:
- The topic is a single word without context ("AI", "Rust", "design")
- No clear audience or intent
- No unique angle distinguishing it from every other post on the topic

## Inferring Defaults

| Field | Default Logic |
|-------|--------------|
| `audience` | Match to user's domain (if developer → developers) |
| `intent` | educate (most common; switch to announce for launches, persuade for opinions) |
| `tone` | confident-technical (adjust to conversational for personal stories) |
| `platforms` | all (broomva-tech + x-post + x-thread + linkedin + instagram-post + instagram-reel) |
| `media` | png + mp3 (add mp4/gif if topic is visual or demo-oriented) |
| `cta` | read the full post (adjust to try/subscribe/follow based on intent) |
| `destination` | broomva-tech (switch to substack if user specifies or doesn't use broomva.tech) |
| `slug` | kebab-case from first 5-6 words of topic |
